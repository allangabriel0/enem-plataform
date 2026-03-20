"""
routers/sync.py — Sincronização da biblioteca com o Telegram.

Endpoints:
  POST /api/sync-videos — varre os grupos configurados, faz upsert de vídeos
                          e materiais no banco, retorna estatísticas.

Upsert de vídeos: delegado a fetch_library_from_groups() do telegram_client.
Upsert de materiais: implementado aqui, seguindo o mesmo padrão.

Materiais são mensagens com documentos não-vídeo (PDF, ZIP, RAR, etc.).
A extensão é extraída do mime_type ou do nome do arquivo.
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Material, User
from app.utils.text import clean_title

logger = logging.getLogger("enem")

router = APIRouter()

# MIME types que identificam materiais (não-vídeo)
_MATERIAL_MIMES = {
    "application/pdf",
    "application/zip",
    "application/x-zip-compressed",
    "application/x-rar-compressed",
    "application/vnd.rar",
    "application/octet-stream",   # RAR/ZIP genérico
    "application/x-7z-compressed",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

_MATERIAL_EXTS = {".pdf", ".zip", ".rar", ".7z", ".doc", ".docx", ".ppt", ".pptx"}


# ---------------------------------------------------------------------------
# Helpers internos — detecção e extração de materiais
# ---------------------------------------------------------------------------

def _is_material_message(message) -> bool:
    """True se a mensagem contém um documento que é material (não-vídeo)."""
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
    # Fallback: verifica a extensão do nome do arquivo
    fname = _extract_filename(doc)
    if fname:
        ext = os.path.splitext(fname)[1].lower()
        return ext in _MATERIAL_EXTS
    return False


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
    """Extrai extensão a partir do filename ou mime_type."""
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


# ---------------------------------------------------------------------------
# Upsert de material
# ---------------------------------------------------------------------------

def _upsert_material(db: Session, message, group_id: int, group_name: str) -> bool:
    """
    Cria ou atualiza um registro Material.
    Retorna True se inserção, False se atualização.

    Padrão idêntico ao _upsert_video do telegram_client:
      - identifica pelo par (telegram_group_id, telegram_message_id)
      - atualiza todos os campos extraíveis em caso de colisão
    """
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
        logger.debug(
            "Material adicionado: msg=%d grupo=%s tag=%s", message.id, group_name, tag
        )
        return True
    else:
        existing.title = title
        existing.description = msg_text or None
        existing.menu_tag = tag
        existing.file_name = fname
        existing.file_ext = _extract_ext(doc)
        existing.file_size = doc.size
        db.commit()
        logger.debug("Material atualizado: msg=%d grupo=%s", message.id, group_name)
        return False


# ---------------------------------------------------------------------------
# Sync de materiais (paralelo ao fetch_library_from_groups do telegram_client)
# ---------------------------------------------------------------------------

async def _sync_materials(db: Session) -> dict:
    """
    Varre os grupos configurados buscando documentos não-vídeo (materiais).
    Retorna {"added": int, "updated": int, "errors": int}.
    """
    from app.telegram_client import get_telegram_client

    client = await get_telegram_client()
    stats = {"added": 0, "updated": 0, "errors": 0}

    for group_id in settings.TELEGRAM_GROUP_IDS:
        try:
            entity = await client.get_entity(group_id)
            group_name: str = getattr(entity, "title", str(group_id))
        except Exception:
            logger.error(
                "sync_materials: não foi possível obter grupo %s", group_id, exc_info=True
            )
            stats["errors"] += 1
            continue

        mat_count = 0
        async for message in client.iter_messages(entity, limit=settings.TELEGRAM_FETCH_LIMIT):
            if not _is_material_message(message):
                continue
            try:
                added = _upsert_material(db, message, group_id, group_name)
                if added:
                    stats["added"] += 1
                else:
                    stats["updated"] += 1
                mat_count += 1
            except Exception:
                logger.error(
                    "sync_materials: erro na mensagem %d grupo %s",
                    message.id, group_id, exc_info=True,
                )
                stats["errors"] += 1

        logger.info(
            "sync_materials: grupo %s — %d materiais processados.", group_name, mat_count
        )

    return stats


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/api/sync-videos")
async def sync_videos(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sincroniza vídeos e materiais de todos os grupos Telegram configurados.

    Fluxo:
      1. Itera grupos em settings.TELEGRAM_GROUP_IDS
      2. Para cada grupo: vídeos via fetch_library_from_groups(),
         materiais via _sync_materials()
      3. Registra "Sincronizando X vídeos e Y materiais do grupo Z"
      4. Retorna {synced, updated, total, materials}
    """
    from app.telegram_client import fetch_library_from_groups

    if not settings.TELEGRAM_GROUP_IDS:
        raise HTTPException(
            status_code=503,
            detail="Nenhum grupo Telegram configurado. Verifique TELEGRAM_GROUP_IDS no .env.",
        )

    logger.info(
        "Iniciando sync: %d grupo(s) configurado(s).", len(settings.TELEGRAM_GROUP_IDS)
    )

    video_stats = await fetch_library_from_groups(db)
    mat_stats = await _sync_materials(db)

    synced = video_stats["added"]
    updated = video_stats["updated"]
    total = synced + updated
    materials = mat_stats["added"] + mat_stats["updated"]

    logger.info(
        "Sync concluído: %d vídeos novos, %d atualizados, %d materiais novos/atualizados. "
        "Erros: vídeos=%d materiais=%d",
        synced, updated, materials,
        video_stats.get("errors", 0), mat_stats.get("errors", 0),
    )

    return {
        "synced": synced,
        "updated": updated,
        "total": total,
        "materials": materials,
    }
