"""
app/cli.py — CLI de operações de manutenção.

Uso:
  python -m app.cli status
  python -m app.cli precache --course "Filosofia"
  python -m app.cli precache --all
  python -m app.cli cleanup
  python -m app.cli cleanup --max-gb 30
"""
import argparse
import asyncio
import logging
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.utils.logging import setup_logging

logger = logging.getLogger("enem")

# ---------------------------------------------------------------------------
# Helpers de formatação (print é OK no CLI interativo)
# ---------------------------------------------------------------------------

def _fmt_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024**3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def _fmt_seconds(s: float) -> str:
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}min"
    if m:
        return f"{m}min {sec}s"
    return f"{sec}s"


def _progress_bar(done: int, total: int, width: int = 30) -> str:
    if total == 0:
        return f"[{'─' * width}]"
    filled = int(width * done / total)
    bar = "█" * filled + "─" * (width - filled)
    pct = done / total * 100
    return f"[{bar}] {done}/{total} ({pct:.0f}%)"


# ---------------------------------------------------------------------------
# Comando: status
# ---------------------------------------------------------------------------

def cmd_status(_args) -> None:
    from app.cache_manager import get_cache_manager
    from app.config import settings
    from app.database import SessionLocal
    from app.models import Material, Video

    db = SessionLocal()
    try:
        total_videos    = db.query(Video).count()
        cached_videos   = db.query(Video).filter(Video.cached_at.isnot(None)).count()
        total_materials = db.query(Material).count()
    finally:
        db.close()

    cache = get_cache_manager()
    stats = cache.get_stats()

    # Espaço em disco real do sistema de arquivos
    cache_dir = Path(settings.CACHE_DIR)
    try:
        disk = shutil.disk_usage(cache_dir)
        disk_total = disk.total
        disk_free  = disk.free
    except FileNotFoundError:
        disk_total = disk_free = 0

    oldest_str = newest_str = "—"
    if stats["oldest_access"]:
        oldest_str = datetime.fromtimestamp(stats["oldest_access"]).strftime("%d/%m/%Y %H:%M")
    if stats["newest_access"]:
        newest_str = datetime.fromtimestamp(stats["newest_access"]).strftime("%d/%m/%Y %H:%M")

    print()
    print("═" * 50)
    print("  ENEM Study Platform — Status")
    print("═" * 50)

    print("\n📚  Banco de dados")
    print(f"    Vídeos no banco:    {total_videos}")
    print(f"    Vídeos cacheados:   {cached_videos}  ({cached_videos/total_videos*100:.0f}%)" if total_videos else "    Vídeos cacheados:   0")
    print(f"    Materiais:          {total_materials}")

    print("\n💾  Cache de vídeos")
    print(f"    Arquivos em cache:  {stats['count']}")
    print(f"    Espaço usado:       {stats['used_gb']:.2f} GB / {stats['total_gb']:.1f} GB")
    bar_filled = int(30 * stats["used_gb"] / stats["total_gb"]) if stats["total_gb"] else 0
    print(f"    [{('█' * bar_filled).ljust(30, '─')}] {stats['used_gb']/stats['total_gb']*100:.0f}%" if stats["total_gb"] else "")
    print(f"    Espaço livre:       {stats['free_gb']:.2f} GB")
    print(f"    Acesso mais antigo: {oldest_str}")
    print(f"    Acesso mais recente:{newest_str}")

    if disk_total:
        print("\n🖥️   Disco (partição do cache)")
        print(f"    Total:  {_fmt_bytes(disk_total)}")
        print(f"    Livre:  {_fmt_bytes(disk_free)}")
        print(f"    Usado:  {_fmt_bytes(disk_total - disk_free)}")

    print()


# ---------------------------------------------------------------------------
# Comando: precache
# ---------------------------------------------------------------------------

async def _precache_videos(videos, db, cache) -> None:
    """Loop principal de download para precache."""
    from app.telegram_client import download_video

    total     = len(videos)
    skipped   = 0
    downloaded = 0
    failed    = 0

    for idx, video in enumerate(videos, 1):
        group_id = str(video.telegram_group_id)
        msg_id   = video.telegram_message_id

        # Já está em cache?
        if cache.get_cached_path(group_id, msg_id):
            skipped += 1
            print(f"  [{idx:>4}/{total}] ✓ (já cacheado) {video.title[:60]}")
            continue

        size_str = f"  {_fmt_bytes(video.file_size)}" if video.file_size else ""
        print(f"  [{idx:>4}/{total}] ↓ {video.title[:60]}{size_str}", end="", flush=True)

        dest = cache._cache_path(group_id, msg_id)
        tmp  = dest.with_suffix(".tmp")
        t0   = time.monotonic()
        try:
            await download_video(group_id, msg_id, tmp)
            import os
            os.replace(tmp, dest)
            video.cached_at = datetime.now(tz=timezone.utc)
            db.add(video)
            db.commit()
            elapsed = time.monotonic() - t0
            downloaded += 1
            print(f"  ✓ ({elapsed:.0f}s)")
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            failed += 1
            print(f"  ✗ ERRO: {exc}")
            logger.error("precache: falha no vídeo %d — %s", video.id, exc, exc_info=True)

        # Evicção após cada download
        cache.evict_lru()

    print()
    print(f"  Resultado: {downloaded} baixados · {skipped} já cacheados · {failed} erros")


def cmd_precache(args) -> None:
    from app.cache_manager import get_cache_manager
    from app.database import SessionLocal
    from app.models import Video

    if not args.course and not args.all:
        print("Erro: informe --course NOME ou --all", file=sys.stderr)
        sys.exit(1)

    db    = SessionLocal()
    cache = get_cache_manager()

    try:
        query = db.query(Video)
        if args.course:
            pattern = f"%{args.course}%"
            query = query.filter(Video.course_name.ilike(pattern))
            videos = query.order_by(Video.course_name, Video.id).all()
            if not videos:
                print(f"Nenhum vídeo encontrado para o curso '{args.course}'.")
                return
            label = f"curso '{args.course}'"
        else:
            videos = query.order_by(Video.course_name, Video.id).all()
            label  = "toda a biblioteca"

        # Filtra os que ainda não estão em cache
        uncached = [
            v for v in videos
            if not cache.get_cached_path(str(v.telegram_group_id), v.telegram_message_id)
        ]

        total_size   = sum(v.file_size or 0 for v in uncached)
        # Estimativa baseada em 5 Mbps (conservador para streaming do Telegram)
        _SPEED_BPS   = 5 * 1024 * 1024
        est_secs     = total_size / _SPEED_BPS if total_size else 0

        print()
        print(f"Precache: {label}")
        print(f"  Vídeos encontrados: {len(videos)}")
        print(f"  Já cacheados:       {len(videos) - len(uncached)}")
        print(f"  A baixar:           {len(uncached)}")
        if total_size:
            print(f"  Tamanho estimado:   {_fmt_bytes(total_size)}")
            print(f"  Tempo estimado:     {_fmt_seconds(est_secs)} (a ~5 Mbps)")
        print()

        if not uncached:
            print("Nada a baixar. Cache já está atualizado.")
            return

        if args.all and not args.yes:
            resp = input("Confirmar download de todos os vídeos? [s/N] ").strip().lower()
            if resp not in ("s", "sim", "y", "yes"):
                print("Operação cancelada.")
                return

        asyncio.run(_precache_videos(uncached, db, cache))

    finally:
        db.close()


# ---------------------------------------------------------------------------
# Comando: cleanup
# ---------------------------------------------------------------------------

def cmd_cleanup(args) -> None:
    from app.cache_manager import get_cache_manager

    cache = get_cache_manager()

    # Sobrescreve limite se --max-gb foi passado
    if args.max_gb is not None:
        if args.max_gb <= 0:
            print("Erro: --max-gb deve ser maior que zero.", file=sys.stderr)
            sys.exit(1)
        cache._max_bytes = int(args.max_gb * 1024 ** 3)
        print(f"Limite temporário de cache: {args.max_gb} GB")

    stats_before = cache.get_stats()
    print(f"\nCache antes: {stats_before['used_gb']:.2f} GB usados, {stats_before['count']} arquivo(s)")

    freed = cache.evict_lru()

    stats_after = cache.get_stats()
    if freed:
        print(f"Cache após:  {stats_after['used_gb']:.2f} GB usados, {stats_after['count']} arquivo(s)")
        print(f"Liberado:    {_fmt_bytes(freed)}")
    else:
        print("Sem evicção necessária — cache dentro do limite.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Garante UTF-8 no stdout (necessário no Windows; no-op no Termux)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    setup_logging()

    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="ENEM Study Platform — ferramentas de manutenção",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMANDO")
    sub.required = True

    # status
    sub.add_parser("status", help="Mostra estatísticas do banco e do cache")

    # precache
    p_pre = sub.add_parser("precache", help="Baixa vídeos para o cache local")
    grp = p_pre.add_mutually_exclusive_group(required=True)
    grp.add_argument("--course", metavar="NOME", help="Nome (parcial) do curso a cachear")
    grp.add_argument("--all", action="store_true", help="Baixar todos os vídeos da biblioteca")
    p_pre.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Confirmar --all sem prompt interativo",
    )

    # cleanup
    p_clean = sub.add_parser("cleanup", help="Remove vídeos antigos do cache (evicção LRU)")
    p_clean.add_argument(
        "--max-gb",
        type=float,
        metavar="GB",
        help="Limite de cache em GB para esta execução (sobrescreve .env)",
    )

    args = parser.parse_args()

    # Garante que as tabelas existem (no-op se já criadas)
    from app.database import init_db
    init_db()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "precache":
        cmd_precache(args)
    elif args.command == "cleanup":
        cmd_cleanup(args)


if __name__ == "__main__":
    main()
