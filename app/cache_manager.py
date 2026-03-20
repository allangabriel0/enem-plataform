"""
cache_manager.py — Cache LRU de dois níveis para arquivos de vídeo.

Storage layout:
  - Primário: SD card (primary_dir)
  - Fallback: armazenamento interno (fallback_dir)
  - Nomes: MD5 de '{group_id}_{message_id}' + '.mp4'
  - Download atômico: escreve em .tmp, renomeia para .mp4 ao concluir

Regras de evicção:
  - Aciona quando total > max_gb
  - Remove LRU (menor atime) até ficar abaixo de 90% do limite
"""
import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("enem")

_EVICT_TARGET_RATIO = 0.90  # Após evicção, manter abaixo de 90% do limite


class CacheManager:
    """Gerencia cache de vídeos em dois diretórios com evicção LRU."""

    def __init__(self, primary_dir: Path, fallback_dir: Path, max_gb: float) -> None:
        self._fallback = fallback_dir
        self._max_bytes = int(max_gb * 1024 ** 3)
        self._fallback.mkdir(parents=True, exist_ok=True)
        try:
            primary_dir.mkdir(parents=True, exist_ok=True)
            self._primary = primary_dir
        except (PermissionError, OSError) as e:
            logger.warning(
                "Cache primário inacessível (%s: %s), usando fallback: %s",
                primary_dir, e, fallback_dir,
            )
            self._primary = fallback_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _cache_path(self, group_id: str, message_id: int, directory: Optional[Path] = None) -> Path:
        """Retorna o caminho canônico. Nome = MD5('{group_id}_{message_id}') + '.mp4'."""
        key = f"{group_id}_{message_id}"
        name = hashlib.md5(key.encode()).hexdigest() + ".mp4"
        base = directory if directory is not None else self._primary
        return base / name

    def get_cached_path(self, group_id: str, message_id: int) -> Optional[Path]:
        """
        Busca o arquivo em primário, depois em fallback.
        Atualiza atime para LRU. Retorna None se não encontrado.
        """
        for directory in (self._primary, self._fallback):
            path = self._cache_path(group_id, message_id, directory)
            if path.exists():
                path.touch()  # atualiza atime para LRU
                return path
        return None

    async def cache_in_background(
        self,
        group_id: str,
        message_id: int,
        download_func,
    ) -> Optional[Path]:
        """
        Baixa o vídeo via download_func(dest: Path) → corrotina.
        Salva atomicamente (.tmp → .mp4). Chama evict_lru ao concluir.
        Retorna o caminho do arquivo ou None em caso de erro.
        """
        dest = self._cache_path(group_id, message_id, self._primary)
        tmp = dest.with_suffix(".tmp")
        try:
            await download_func(tmp)
            os.replace(tmp, dest)
            logger.info("Cache: salvo %s_%s → %s", group_id, message_id, dest.name)
            self.evict_lru()
            return dest
        except Exception:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            logger.error(
                "Cache: falha ao baixar %s_%s", group_id, message_id, exc_info=True
            )
            return None

    def evict_lru(self) -> int:
        """
        Se total > max_gb, remove arquivos com atime mais antigo até ficar
        abaixo de 90% do limite. Retorna bytes liberados.
        """
        total = self._total_bytes()
        if total <= self._max_bytes:
            return 0

        target = int(self._max_bytes * _EVICT_TARGET_RATIO)
        freed = 0

        files = sorted(
            (
                f
                for directory in (self._primary, self._fallback)
                for f in directory.glob("*.mp4")
                if f.exists()
            ),
            key=lambda f: f.stat().st_atime,
        )

        for f in files:
            if total - freed <= target:
                break
            size = f.stat().st_size
            f.unlink(missing_ok=True)
            freed += size
            logger.info("Cache evict: %s (%d bytes)", f.name, size)

        return freed

    def get_stats(self) -> dict:
        """
        Retorna estatísticas de uso:
          total_gb, used_gb, free_gb, count, oldest_access, newest_access
        """
        files = [
            f
            for directory in (self._primary, self._fallback)
            for f in directory.glob("*.mp4")
            if f.exists()
        ]

        used_bytes = sum(f.stat().st_size for f in files)
        atimes = [f.stat().st_atime for f in files] if files else []

        return {
            "total_gb": self._max_bytes / 1024 ** 3,
            "used_gb": used_bytes / 1024 ** 3,
            "free_gb": max(0.0, (self._max_bytes - used_bytes) / 1024 ** 3),
            "count": len(files),
            "oldest_access": min(atimes) if atimes else None,
            "newest_access": max(atimes) if atimes else None,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _total_bytes(self) -> int:
        return sum(
            f.stat().st_size
            for directory in (self._primary, self._fallback)
            for f in directory.glob("*.mp4")
            if f.exists()
        )


# ---------------------------------------------------------------------------
# Singleton de conveniência (instanciado na startup do app)
# ---------------------------------------------------------------------------

_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    global _manager
    if _manager is None:
        from app.config import settings

        internal = Path(settings.CACHE_DIR)
        sd = (
            Path(settings.SD_CARD_PATH) / "enem-cache" / "videos"
            if settings.SD_CARD_PATH
            else internal / "sd"
        )
        _manager = CacheManager(
            primary_dir=sd,
            fallback_dir=internal,
            max_gb=float(settings.CACHE_MAX_GB),
        )
    return _manager
