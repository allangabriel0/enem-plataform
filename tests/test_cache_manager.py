"""
Testes para app/cache_manager.py — usam tmp_path para diretórios temporários.
"""
import asyncio
import hashlib
import os
from pathlib import Path

import pytest

from app.cache_manager import CacheManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(tmp_path: Path, max_gb: float = 1.0) -> CacheManager:
    return CacheManager(
        primary_dir=tmp_path / "primary",
        fallback_dir=tmp_path / "fallback",
        max_gb=max_gb,
    )


def _expected_name(group_id: str, message_id: int) -> str:
    key = f"{group_id}_{message_id}"
    return hashlib.md5(key.encode()).hexdigest() + ".mp4"


# ---------------------------------------------------------------------------
# test_cache_path_is_deterministic
# ---------------------------------------------------------------------------

def test_cache_path_is_deterministic(tmp_path: Path):
    """_cache_path retorna o mesmo caminho para os mesmos argumentos."""
    mgr = _make_manager(tmp_path)
    p1 = mgr._cache_path("canal1", 42)
    p2 = mgr._cache_path("canal1", 42)
    assert p1 == p2
    assert p1.name == _expected_name("canal1", 42)


def test_cache_path_different_for_different_inputs(tmp_path: Path):
    """IDs distintos geram caminhos distintos."""
    mgr = _make_manager(tmp_path)
    assert mgr._cache_path("canal1", 1) != mgr._cache_path("canal1", 2)
    assert mgr._cache_path("canal1", 1) != mgr._cache_path("canal2", 1)


# ---------------------------------------------------------------------------
# test_get_cached_path_returns_none_when_empty
# ---------------------------------------------------------------------------

def test_get_cached_path_returns_none_when_empty(tmp_path: Path):
    """Cache vazio retorna None."""
    mgr = _make_manager(tmp_path)
    assert mgr.get_cached_path("canal1", 99) is None


# ---------------------------------------------------------------------------
# test_get_cached_path_finds_file_in_primary
# ---------------------------------------------------------------------------

def test_get_cached_path_finds_file_in_primary(tmp_path: Path):
    """Arquivo no diretório primário é encontrado."""
    mgr = _make_manager(tmp_path)
    dest = mgr._cache_path("canal1", 1, mgr._primary)
    dest.write_bytes(b"video data")

    result = mgr.get_cached_path("canal1", 1)

    assert result is not None
    assert result == dest
    assert result.exists()


# ---------------------------------------------------------------------------
# test_get_cached_path_finds_file_in_fallback
# ---------------------------------------------------------------------------

def test_get_cached_path_finds_file_in_fallback(tmp_path: Path):
    """Arquivo no diretório de fallback é encontrado quando não está no primário."""
    mgr = _make_manager(tmp_path)
    dest = mgr._cache_path("canal2", 5, mgr._fallback)
    dest.write_bytes(b"fallback video")

    result = mgr.get_cached_path("canal2", 5)

    assert result is not None
    assert result == dest


# ---------------------------------------------------------------------------
# test_cache_in_background_saves_file
# ---------------------------------------------------------------------------

def test_cache_in_background_saves_file(tmp_path: Path):
    """cache_in_background baixa e salva o arquivo corretamente."""
    mgr = _make_manager(tmp_path)
    video_data = b"fake video content 1234"

    async def mock_download(dest: Path):
        dest.write_bytes(video_data)

    async def run():
        result = await mgr.cache_in_background("canal1", 10, mock_download)
        return result

    path = asyncio.run(run())

    assert path is not None
    assert path.exists()
    assert path.read_bytes() == video_data
    assert mgr.get_cached_path("canal1", 10) == path


# ---------------------------------------------------------------------------
# test_cache_atomic_no_partial_files
# ---------------------------------------------------------------------------

def test_cache_atomic_no_partial_files(tmp_path: Path):
    """Falha no download não deixa arquivo .tmp residual."""
    mgr = _make_manager(tmp_path)

    async def failing_download(dest: Path):
        dest.write_bytes(b"partial")
        raise RuntimeError("Simulando falha de rede")

    async def run():
        return await mgr.cache_in_background("canal1", 20, failing_download)

    result = asyncio.run(run())

    assert result is None
    # Nenhum .tmp deve sobrar
    tmp_files = list(mgr._primary.glob("*.tmp"))
    assert tmp_files == []
    # Nenhum .mp4 parcial
    assert mgr.get_cached_path("canal1", 20) is None


# ---------------------------------------------------------------------------
# test_evict_lru_removes_oldest
# ---------------------------------------------------------------------------

def test_evict_lru_removes_oldest(tmp_path: Path):
    """evict_lru remove os arquivos com atime mais antigo primeiro."""
    # max_gb pequeno: 200 bytes → em bytes direto
    bytes_limit = 200
    mgr = CacheManager(
        primary_dir=tmp_path / "primary",
        fallback_dir=tmp_path / "fallback",
        max_gb=bytes_limit / 1024 ** 3,
    )

    # Cria 3 arquivos de 100 bytes com atimes distintos
    paths = {}
    for i, msg_id in enumerate([1, 2, 3]):
        path = mgr._cache_path("canal1", msg_id, mgr._primary)
        path.write_bytes(b"x" * 100)
        atime = 1_000_000 + i * 1_000  # 1, 2, 3 em ordem crescente
        os.utime(path, (atime, atime))
        paths[msg_id] = path

    # 300 bytes > 200 bytes limite → evict deve agir
    freed = mgr.evict_lru()

    assert freed > 0
    # O mais velho (msg_id=1, atime menor) deve ter sido removido
    assert not paths[1].exists()


# ---------------------------------------------------------------------------
# test_evict_respects_limit
# ---------------------------------------------------------------------------

def test_evict_respects_limit(tmp_path: Path):
    """Após evicção, uso deve ficar abaixo de 90% do limite."""
    bytes_limit = 300
    mgr = CacheManager(
        primary_dir=tmp_path / "primary",
        fallback_dir=tmp_path / "fallback",
        max_gb=bytes_limit / 1024 ** 3,
    )

    # 5 arquivos de 100 bytes = 500 bytes, bem acima do limite de 300
    for i, msg_id in enumerate(range(1, 6)):
        path = mgr._cache_path("canal1", msg_id, mgr._primary)
        path.write_bytes(b"y" * 100)
        atime = 1_000_000 + i * 1_000
        os.utime(path, (atime, atime))

    mgr.evict_lru()

    # Após evicção, total deve ser ≤ 90% de 300 = 270 bytes
    remaining = sum(
        f.stat().st_size
        for f in mgr._primary.glob("*.mp4")
        if f.exists()
    )
    assert remaining <= int(bytes_limit * 0.90)


# ---------------------------------------------------------------------------
# test_get_stats
# ---------------------------------------------------------------------------

def test_get_stats_empty(tmp_path: Path):
    """get_stats com cache vazio retorna zeros e None para acessos."""
    mgr = _make_manager(tmp_path, max_gb=10.0)
    stats = mgr.get_stats()

    assert stats["count"] == 0
    assert stats["used_gb"] == 0.0
    assert stats["total_gb"] == pytest.approx(10.0)
    assert stats["free_gb"] == pytest.approx(10.0)
    assert stats["oldest_access"] is None
    assert stats["newest_access"] is None


def test_get_stats(tmp_path: Path):
    """get_stats reflete corretamente os arquivos em cache."""
    mgr = _make_manager(tmp_path, max_gb=1.0)

    # 2 arquivos no primário, 1 no fallback
    for msg_id in [1, 2]:
        mgr._cache_path("canal1", msg_id, mgr._primary).write_bytes(b"a" * 512)
    mgr._cache_path("canal1", 3, mgr._fallback).write_bytes(b"b" * 256)

    stats = mgr.get_stats()

    assert stats["count"] == 3
    assert stats["used_gb"] == pytest.approx((512 * 2 + 256) / 1024 ** 3, rel=1e-5)
    assert stats["free_gb"] == pytest.approx(1.0 - stats["used_gb"], rel=1e-5)
    assert stats["oldest_access"] is not None
    assert stats["newest_access"] is not None
    assert stats["newest_access"] >= stats["oldest_access"]
