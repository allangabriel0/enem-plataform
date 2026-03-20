"""
routers/materials.py — Download de materiais (PDF, ZIP, RAR, etc.).

Endpoints:
  GET /download/material/{material_id} — verifica cache (campo cached_path no banco),
      se ausente baixa via Telegram, salva path, retorna FileResponse.

Estratégia de cache:
  - cached_path no banco aponta para o arquivo local.
  - Se o arquivo existir em disco: serve direto (FileResponse).
  - Se não existir: download atômico do Telegram (.tmp → arquivo final),
    atualiza cached_path no banco, serve o arquivo.

Download atômico: salva em <dest>.tmp, renomeia para <dest> ao concluir.
Em caso de falha a .tmp é apagada e o erro é propagado (404/502).
"""
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Material, User

logger = logging.getLogger("enem")

router = APIRouter()

# Diretório base para materiais cacheados
_MATERIALS_DIR = Path("data/materials")


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _safe_filename(material: Material) -> str:
    """
    Retorna um nome de arquivo seguro para o material.
    Usa file_name se disponível; caso contrário deriva do id e extensão.
    """
    if material.file_name:
        # Sanitiza: mantém apenas o basename, sem barras/nulos
        return Path(material.file_name).name
    ext = material.file_ext or ""
    return f"material_{material.id}{ext}"


def _dest_path(material: Material) -> Path:
    """Caminho canônico do arquivo no cache local."""
    return _MATERIALS_DIR / str(material.telegram_group_id) / _safe_filename(material)


async def _download_from_telegram(material: Material, dest: Path) -> None:
    """
    Baixa o arquivo do Telegram de forma atômica:
      1. Escreve em dest.with_suffix('.tmp')
      2. Renomeia para dest ao concluir
      3. Apaga .tmp se falhar

    Levanta RuntimeError se a mensagem não existir ou não tiver documento.
    """
    from app.telegram_client import get_telegram_client

    client = await get_telegram_client()
    entity = await client.get_entity(material.telegram_group_id)
    message = await client.get_messages(entity, ids=material.telegram_message_id)

    if message is None or not getattr(message, "media", None):
        raise RuntimeError(
            f"Mensagem {material.telegram_message_id} no grupo "
            f"{material.telegram_group_id} não encontrada ou sem documento."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")

    try:
        logger.info(
            "Baixando material id=%d '%s' (%s bytes) → %s",
            material.id,
            material.title,
            material.file_size or "?",
            dest.name,
        )
        await client.download_media(message, file=str(tmp))
        os.replace(tmp, dest)
        logger.info(
            "Material id=%d salvo: %s (%d bytes)",
            material.id,
            dest.name,
            dest.stat().st_size,
        )
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        logger.error(
            "Falha ao baixar material id=%d", material.id, exc_info=True
        )
        raise


# ---------------------------------------------------------------------------
# GET /download/material/{material_id}
# ---------------------------------------------------------------------------

@router.get("/download/material/{material_id}")
async def download_material(
    material_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Serve o arquivo de material para download.

    Fluxo:
      1. Busca Material no banco (404 se não existir)
      2. Se cached_path preenchido e arquivo existe em disco → FileResponse
      3. Senão → download do Telegram, atualiza cached_path, FileResponse
    """
    material = db.query(Material).filter_by(id=material_id).first()
    if material is None:
        raise HTTPException(status_code=404, detail="Material não encontrado.")

    # ------------------------------------------------------------------
    # 1. Verifica cache pelo campo cached_path (pode estar populado de
    #    download anterior ou de sincronização)
    # ------------------------------------------------------------------
    if material.cached_path:
        cached = Path(material.cached_path)
        if cached.exists():
            logger.info(
                "Material id=%d servido do cache: %s (user=%s)",
                material_id, cached.name, user.email,
            )
            return FileResponse(
                path=str(cached),
                filename=_safe_filename(material),
                media_type=_guess_media_type(material.file_ext),
            )
        else:
            # Registro desatualizado: arquivo foi apagado do disco
            logger.warning(
                "Material id=%d: cached_path '%s' não existe, rebaixando.",
                material_id, material.cached_path,
            )

    # ------------------------------------------------------------------
    # 2. Download do Telegram
    # ------------------------------------------------------------------
    dest = _dest_path(material)

    # Arquivo pode já estar em disco mesmo sem cached_path no banco
    if not dest.exists():
        try:
            await _download_from_telegram(material, dest)
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Falha ao baixar material do Telegram. Tente novamente.",
            ) from exc

    # Atualiza cached_path no banco
    material.cached_path = str(dest)
    db.commit()
    logger.info(
        "Material id=%d entregue: %s (user=%s)",
        material_id, dest.name, user.email,
    )

    return FileResponse(
        path=str(dest),
        filename=_safe_filename(material),
        media_type=_guess_media_type(material.file_ext),
    )


# ---------------------------------------------------------------------------
# Helpers de MIME
# ---------------------------------------------------------------------------

def _guess_media_type(file_ext: Optional[str]) -> str:
    """Retorna o Content-Type adequado pela extensão."""
    _EXT_MIME = {
        ".pdf":  "application/pdf",
        ".zip":  "application/zip",
        ".rar":  "application/vnd.rar",
        ".7z":   "application/x-7z-compressed",
        ".doc":  "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".ppt":  "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    if file_ext:
        return _EXT_MIME.get(file_ext.lower(), "application/octet-stream")
    return "application/octet-stream"
