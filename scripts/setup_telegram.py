"""
scripts/setup_telegram.py — Autenticação no Telegram e listagem de grupos.

Uso:
  python scripts/setup_telegram.py

O que faz:
  1. Autentica via Telethon (salva sessão em data/telegram.session)
  2. Lista todos os grupos/canais acessíveis com seus IDs
  3. Resolve ID a partir de link público (t.me/... ou @username)
  4. Sugere o valor correto para TELEGRAM_GROUP_IDS no .env
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings


SESSION_FILE = "data/telegram.session"


async def _run() -> None:
    # Import tardio — Telethon pode não estar instalado em dev sem credenciais
    try:
        from telethon import TelegramClient
        from telethon.tl.types import Channel, Chat
    except ImportError:
        print("Erro: telethon não instalado. Execute: pip install telethon")
        sys.exit(1)

    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
        print("Erro: TELEGRAM_API_ID e TELEGRAM_API_HASH não configurados no .env")
        print("  Obtenha em: https://my.telegram.org → API Development Tools")
        sys.exit(1)

    Path("data").mkdir(exist_ok=True)

    client = TelegramClient(
        SESSION_FILE,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )

    print()
    print("=== Autenticação no Telegram ===")
    print()

    await client.start(phone=settings.TELEGRAM_PHONE or None)

    me = await client.get_me()
    print(f"  Autenticado como: {me.first_name} {me.last_name or ''} (@{me.username or 'sem username'})")
    print(f"  Sessão salva em:  {SESSION_FILE}")
    print()

    # -------------------------------------------------------------------------
    # Lista grupos e canais
    # -------------------------------------------------------------------------
    print("=== Grupos e Canais acessíveis ===")
    print()

    dialogs = await client.get_dialogs()
    groups = []
    for d in dialogs:
        entity = d.entity
        if isinstance(entity, (Channel, Chat)):
            gid = entity.id
            # IDs de canais/grupos no Telegram são negativos na API
            if isinstance(entity, Channel):
                full_id = -(1000000000000 + gid)  # formato -100XXXXX
            else:
                full_id = -gid
            groups.append({
                "id": full_id,
                "name": entity.title,
                "type": "Canal" if isinstance(entity, Channel) else "Grupo",
                "username": getattr(entity, "username", None) or "",
            })

    if groups:
        print(f"  {'ID':<20} {'Tipo':<8} {'Nome'}")
        print(f"  {'─'*20} {'─'*8} {'─'*40}")
        for g in sorted(groups, key=lambda x: x["name"]):
            username = f"  (@{g['username']})" if g["username"] else ""
            print(f"  {g['id']:<20} {g['type']:<8} {g['name']}{username}")
    else:
        print("  Nenhum grupo/canal encontrado.")

    print()

    # -------------------------------------------------------------------------
    # Resolver ID a partir de link
    # -------------------------------------------------------------------------
    print("=== Resolver ID por link ou @username ===")
    print("  (Enter para pular)")
    print()

    resolved_ids = []
    while True:
        link = input("  Link ou @username (ou Enter para sair): ").strip()
        if not link:
            break

        try:
            entity = await client.get_entity(link)
            gid = entity.id
            if hasattr(entity, "megagroup") or hasattr(entity, "broadcast"):
                full_id = -(1000000000000 + gid)
            else:
                full_id = -gid
            name = getattr(entity, "title", str(gid))
            print(f"  → ID: {full_id}  Nome: {name}")
            resolved_ids.append(full_id)
        except Exception as exc:
            print(f"  Erro ao resolver '{link}': {exc}")

    # -------------------------------------------------------------------------
    # Sugestão para o .env
    # -------------------------------------------------------------------------
    print()

    all_ids = resolved_ids or [g["id"] for g in groups]
    if all_ids:
        csv = ",".join(str(i) for i in all_ids)
        print("=== Sugestão para o .env ===")
        print()
        print(f"  TELEGRAM_GROUP_IDS={csv}")
        print()

        env_file = Path(".env")
        if env_file.exists():
            update = input("  Atualizar TELEGRAM_GROUP_IDS no .env agora? [s/N] ").strip().lower()
            if update in ("s", "sim", "y", "yes"):
                text = env_file.read_text(encoding="utf-8")
                if "TELEGRAM_GROUP_IDS=" in text:
                    lines = []
                    for line in text.splitlines():
                        if line.startswith("TELEGRAM_GROUP_IDS="):
                            lines.append(f"TELEGRAM_GROUP_IDS={csv}")
                        else:
                            lines.append(line)
                    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                else:
                    with env_file.open("a", encoding="utf-8") as f:
                        f.write(f"\nTELEGRAM_GROUP_IDS={csv}\n")
                print("  .env atualizado.")

    await client.disconnect()
    print()
    print("Pronto. Próximos passos:")
    print("  bash scripts/start.sh")
    print("  curl -X POST http://localhost:8000/api/sync-videos")
    print()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
