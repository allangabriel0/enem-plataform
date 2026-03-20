"""
routers/streaming.py — Streaming e cache de vídeos.

Endpoints:
  GET  /stream/{video_id}            — retorna vídeo cacheado (FileResponse) ou faz
                                       streaming do Telegram com Range headers; cacheia
                                       em background após o primeiro acesso.
  POST /api/videos/{video_id}/cache  — trigger manual de cache (202 Accepted)
  PUT  /api/videos/{video_id}        — atualiza metadados do vídeo (subject, title…)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.cache_manager import CacheManager, get_cache_manager
from app.database import get_db
from app.models import User, Video

logger = logging.getLogger("enem")

router = APIRouter()

# ---------------------------------------------------------------------------
# Dependência — CacheManager
# ---------------------------------------------------------------------------

def _get_cache() -> CacheManager:
    """Dependência FastAPI que retorna o singleton de CacheManager."""
    return get_cache_manager()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class VideoUpdate(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    course_name: Optional[str] = None
    lesson_name: Optional[str] = None
    menu_tag: Optional[str] = None


class VideoOut(BaseModel):
    id: int
    telegram_group_id: int
    telegram_message_id: int
    title: str
    subject: Optional[str]
    course_name: Optional[str]
    lesson_name: Optional[str]
    menu_tag: Optional[str]
    duration: Optional[int]
    file_size: Optional[int]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _parse_range(range_header: str) -> tuple[int, Optional[int]]:
    """
    Faz parse do header 'Range: bytes=start-end'.
    Retorna (start, end) onde end pode ser None (até EOF).
    Retorna (0, None) se o header estiver ausente ou malformado.
    """
    if not range_header or not range_header.startswith("bytes="):
        return 0, None
    spec = range_header[len("bytes="):]
    parts = spec.split("-", 1)
    try:
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else None
    except ValueError:
        return 0, None
    return start, end


async def _stream_from_telegram(
    group_id: int,
    msg_id: int,
    offset: int,
) -> AsyncIterator[bytes]:
    """Wrapper que importa stream_video com import tardio para facilitar mock."""
    from app.telegram_client import stream_video

    async for chunk in stream_video(group_id, msg_id, offset=offset):
        yield chunk


async def _run_cache_background(
    group_id: int,
    msg_id: int,
    cache: CacheManager,
) -> None:
    """
    Tarefa de background: baixa o vídeo e salva no cache.
    Ignora silenciosamente se já estiver cacheado ou se falhar.
    """
    if cache.get_cached_path(str(group_id), msg_id):
        return  # já está cacheado, nada a fazer

    from app.telegram_client import download_video

    async def _dl(dest: Path) -> None:
        await download_video(group_id, msg_id, dest)

    await cache.cache_in_background(str(group_id), msg_id, _dl)


def _video_or_404(db: Session, video_id: int) -> Video:
    video = db.query(Video).filter_by(id=video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")
    return video


# ---------------------------------------------------------------------------
# GET /stream/{video_id}
# ---------------------------------------------------------------------------

@router.get("/stream/{video_id}")
async def stream_video_endpoint(
    video_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: CacheManager = Depends(_get_cache),
):
    """
    Retorna o vídeo para o player.

    Fluxo:
      1. Verifica cache (SD card ou interno)  →  FileResponse (Range nativo)
      2. Se não cacheado: streaming do Telegram com Range headers
         + agenda download completo em background para cachear
    """
    video = _video_or_404(db, video_id)
    group_id: int = video.telegram_group_id
    msg_id: int = video.telegram_message_id

    # ------------------------------------------------------------------
    # 1. Cache hit → FileResponse (Starlette suporta Range nativamente)
    # ------------------------------------------------------------------
    cached_path = cache.get_cached_path(str(group_id), msg_id)
    if cached_path:
        logger.debug("stream: cache hit video_id=%d → %s", video_id, cached_path.name)
        return FileResponse(
            path=str(cached_path),
            media_type="video/mp4",
            filename=video.filename or cached_path.name,
        )

    # ------------------------------------------------------------------
    # 2. Cache miss → streaming do Telegram + cacheia em background
    # ------------------------------------------------------------------
    range_header = request.headers.get("range", "")
    start, end = _parse_range(range_header)

    # Tamanho do arquivo para o header Content-Range
    file_size: Optional[int] = video.file_size

    # Agenda download completo em background (primeira vez apenas)
    background_tasks.add_task(_run_cache_background, group_id, msg_id, cache)

    headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
    }

    if start > 0 or end is not None:
        # Resposta parcial (206)
        end_byte = end if end is not None else (
            (file_size - 1) if file_size else None
        )
        range_end_str = str(end_byte) if end_byte is not None else ""
        size_str = str(file_size) if file_size else "*"
        headers["Content-Range"] = f"bytes {start}-{range_end_str}/{size_str}"

        if end_byte is not None:
            headers["Content-Length"] = str(end_byte - start + 1)
        elif file_size:
            headers["Content-Length"] = str(file_size - start)

        logger.debug(
            "stream: parcial video_id=%d range=%s-%s/%s",
            video_id, start, range_end_str, size_str,
        )
        return StreamingResponse(
            _stream_from_telegram(group_id, msg_id, offset=start),
            status_code=206,
            headers=headers,
        )

    # Resposta completa (200)
    if file_size:
        headers["Content-Length"] = str(file_size)

    logger.debug("stream: completo video_id=%d", video_id)
    return StreamingResponse(
        _stream_from_telegram(group_id, msg_id, offset=0),
        status_code=200,
        headers=headers,
    )


# ---------------------------------------------------------------------------
# POST /api/videos/{video_id}/cache
# ---------------------------------------------------------------------------

@router.post("/api/videos/{video_id}/cache", status_code=202)
async def trigger_cache(
    video_id: int,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: CacheManager = Depends(_get_cache),
):
    """
    Dispara o download do vídeo para cache manualmente.
    Retorna 202 Accepted imediatamente; o download ocorre em background.
    Se o vídeo já estiver cacheado, retorna status 'already_cached'.
    """
    video = _video_or_404(db, video_id)
    group_id: int = video.telegram_group_id
    msg_id: int = video.telegram_message_id

    if cache.get_cached_path(str(group_id), msg_id):
        logger.debug("trigger_cache: já cacheado video_id=%d", video_id)
        return {"status": "already_cached", "video_id": video_id}

    background_tasks.add_task(_run_cache_background, group_id, msg_id, cache)
    logger.info("trigger_cache: agendado video_id=%d", video_id)
    return {"status": "caching", "video_id": video_id}


# ---------------------------------------------------------------------------
# PUT /api/videos/{video_id}
# ---------------------------------------------------------------------------

@router.put("/api/videos/{video_id}", response_model=VideoOut)
async def update_video(
    video_id: int,
    data: VideoUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Atualiza metadados editáveis do vídeo: title, subject, course_name,
    lesson_name, menu_tag.  Campos ausentes no body não são alterados.
    """
    video = _video_or_404(db, video_id)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(video, field, value)

    db.commit()
    db.refresh(video)
    logger.info("Video atualizado: id=%d", video_id)
    return video
