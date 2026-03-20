"""
routers/sync.py — Sincronização da biblioteca com o Telegram.

Endpoints:
  POST /api/sync-videos         — sync incremental (só mensagens novas)
  POST /api/sync-videos?force=1 — sync completo (re-varre tudo)

Upsert de vídeos e materiais: identificados por (group_id, message_id).
Sync incremental: guarda o maior message_id visto em SyncState e na próxima
execução usa min_id para pular mensagens já processadas.
"""
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Material, SyncState, User
from app.utils.text import clean_title

logger = logging.getLogger("enem")

router = APIRouter()

_MATERIAL_MIMES = {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/vnd.rar",
    "application/octet-stream",
    "application/x-7z-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_MATERIAL_EXTS = {".pdf", ".zip", ".rar", ".7z", ".doc", ".docx", ".ppt", ".pptx"}


def _is_material_message(message) -> bool:
    if not message.media:
        return False
    doc = getattr(message.media, "document", None)
    if doc is None:
        return False
    mime: str = getattr(doc, "mime_type", "") or ""
    if mime.startswith("video/"):
        return False
    if mime in _MATERIAL_MIMES:
        return True
    fname = _extract_filename(doc)
    if fname:
        ext = os.path.splitext(fname)[1].lower()
        return ext in _MATERIAL_EXTS
    return False


def _is_video_message(message) -> bool:
    if not message.media:
        return False
    doc = getattr(message.media, "document", None)
    if doc is None:
        return False
    mime = getattr(doc, "mime_type", "") or ""
    return mime.startswith("video/")


def _extract_filename(document) -> Optional[str]:
    try:
        from telethon.tl.types import DocumentAttributeFilename
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name
    except Exception:
        pass
    return None


def _extract_ext(document) -> Optional[str]:
    fname = _extract_filename(document)
    if fname:
        ext = os.path.splitext(fname)[1].lower()
        return ext if ext else None
    mime: str = getattr(document, "mime_type", "") or ""
    _MIME_TO_EXT = {
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
        "application/x-rar-compressed": ".rar",
        "application/vnd.rar": ".rar",
        "application/x-7z-compressed": ".7z",
    }
    return _MIME_TO_EXT.get(mime)


def _extract_duration(document) -> Optional[int]:
    try:
        from telethon.tl.types import DocumentAttributeVideo
        for attr in document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                return attr.duration
    except Exception:
        pass
    return None


def _upsert_video(db: Session, message, group_id: int, group_name: str) -> bool:
    from app.models import Video
    from app.telegram_client import extract_tag

    doc = message.media.document
    msg_text = message.text or ""
    tag = extract_tag(msg_text)
    title = clean_title(msg_text.split("\n")[0]) or f"Vídeo {message.id}"

    existing = (
        db.query(Video)
        .filter_by(telegram_group_id=group_id, telegram_message_id=message.id)
        .first()
    )

    if existing is None:
        from app.models import Video as V
        video = V(
            telegram_message_id=message.id,
            telegram_group_id=group_id,
            telegram_group_name=group_name,
            title=title,
            description=msg_text or None,
            duration=_extract_duration(doc),
            file_size=doc.size,
            menu_tag=tag,
            filename=_extract_filename(doc),
        )
        db.add(video)
        db.commit()
        return True
    else:
        existing.title = title
        existing.description = msg_text or None
        existing.duration = _extract_duration(doc)
        existing.file_size = doc.size
        existing.menu_tag = tag
        existing.filename = _extract_filename(doc)
        db.commit()
        return False


def _upsert_material(db: Session, message, group_id: int, group_name: str) -> bool:
    from app.telegram_client import extract_tag

    doc = message.media.document
    msg_text: str = message.text or ""
    tag = extract_tag(msg_text)
    fname = _extract_filename(doc)
    title = (
        clean_title(msg_text.split("\n")[0])
        or (fname or f"Material {message.id}")
    )

    existing = (
        db.query(Material)
        .filter_by(
            telegram_group_id=group_id,
            telegram_message_id=message.id,
        )
        .first()
    )

    if existing is None:
        material = Material(
            telegram_message_id=message.id,
            telegram_group_id=group_id,
            telegram_group_name=group_name,
            title=title,
            description=msg_text or None,
            menu_tag=tag,
            file_name=fname,
            file_ext=_extract_ext(doc),
            file_size=doc.size,
        )
        db.add(material)
        db.commit()
        return True
    else:
        existing.title = title
        existing.description = msg_text or None
        existing.menu_tag = tag
        existing.file_name = fname
        existing.file_ext = _extract_ext(doc)
        existing.file_size = doc.size
        db.commit()
        return False


def _get_sync_state(db: Session, group_id: int) -> SyncState:
    state = db.query(SyncState).filter_by(group_id=group_id).first()
    if state is None:
        state = SyncState(group_id=group_id, last_message_id=0, videos_total=0)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


@router.post("/api/sync-videos")
async def sync_videos(
    force: bool = Query(default=False, description="Reprocessa todas as mensagens, ignorando o último ID salvo"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sincroniza vídeos e materiais de todos os grupos Telegram configurados.

    Modo incremental (padrão): usa min_id para buscar só mensagens novas.
    Modo forçado (?force=1): reprocessa tudo a partir do zero.
    """
    from app.telegram_client import get_telegram_client

    if not settings.TELEGRAM_GROUP_IDS:
        raise HTTPException(
            status_code=503,
            detail="Nenhum grupo Telegram configurado. Verifique TELEGRAM_GROUP_IDS no .env.",
        )

    client = await get_telegram_client()
    total_stats = {"added": 0, "updated": 0, "materials": 0, "errors": 0}

    for group_id in settings.TELEGRAM_GROUP_IDS:
        state = _get_sync_state(db, group_id)
        min_id = 0 if force else state.last_message_id

        try:
            entity = await client.get_entity(group_id)
            group_name: str = getattr(entity, "title", str(group_id))
        except Exception:
            logger.error("sync: não foi possível obter grupo %s", group_id, exc_info=True)
            total_stats["errors"] += 1
            continue

        mode = "completo" if force else f"incremental (min_id={min_id})"
        logger.info("Sincronizando grupo %s — modo %s", group_name, mode)

        max_seen_id = min_id
        v_added = v_updated = m_count = 0

        async for message in client.iter_messages(
            entity,
            limit=settings.TELEGRAM_FETCH_LIMIT,
            min_id=min_id,
        ):
            if message.id > max_seen_id:
                max_seen_id = message.id

            if _is_video_message(message):
                try:
                    added = _upsert_video(db, message, group_id, group_name)
                    if added:
                        v_added += 1
                    else:
                        v_updated += 1
                except Exception:
                    logger.error("sync: erro vídeo msg=%d grupo=%s", message.id, group_id, exc_info=True)
                    total_stats["errors"] += 1

            elif _is_material_message(message):
                try:
                    _upsert_material(db, message, group_id, group_name)
                    m_count += 1
                except Exception:
                    logger.error("sync: erro material msg=%d grupo=%s", message.id, group_id, exc_info=True)
                    total_stats["errors"] += 1

        # Atualiza SyncState
        if max_seen_id > state.last_message_id:
            state.last_message_id = max_seen_id
        state.last_sync_at = datetime.utcnow()
        state.videos_total += v_added
        db.commit()

        total_stats["added"] += v_added
        total_stats["updated"] += v_updated
        total_stats["materials"] += m_count

        logger.info(
            "Grupo %s: +%d vídeos, ~%d atualizados, %d materiais. max_id=%d",
            group_name, v_added, v_updated, m_count, max_seen_id,
        )

    logger.info(
        "Sync concluído: %d novos, %d atualizados, %d materiais, %d erros",
        total_stats["added"], total_stats["updated"],
        total_stats["materials"], total_stats["errors"],
    )

    return {
        "synced": total_stats["added"],
        "updated": total_stats["updated"],
        "total": total_stats["added"] + total_stats["updated"],
        "materials": total_stats["materials"],
        "errors": total_stats["errors"],
        "mode": "force" if force else "incremental",
    }
