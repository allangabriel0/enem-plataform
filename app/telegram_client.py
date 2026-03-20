"""
telegram_client.py — Conexão com Telegram via Telethon.

Funções públicas:
  get_telegram_client()                  → TelegramClient conectado (singleton)
  disconnect_client()                    → desconecta e limpa singleton
  extract_tag(text)                      → str | None  (primeira tag #XXX999)
  fetch_library_from_groups(db)          → dict com stats do sync
  stream_video(group_id, msg_id)         → async generator de bytes (chunks)
  get_video_file_size(group_id, msg_id)  → int | None
  download_video(group_id, msg_id, dest) → Path (download atômico .tmp → .mp4)

O client Telethon é um singleton protegido por asyncio.Lock para evitar
inicializações concorrentes.  A sessão é salva em data/telegram_session.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import AsyncIterator, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Video
from app.utils.text import clean_title

logger = logging.getLogger("enem")

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"#[A-Za-z]+\d+")
_VIDEO_MIME_PREFIX = "video/"
_CHUNK_SIZE = 512 * 1024          # 512 KB por chunk no streaming
_SESSION_PATH = "data/telegram.session"

# ---------------------------------------------------------------------------
# Singleton com lock
# ---------------------------------------------------------------------------

_client = None
_client_lock = asyncio.Lock()


async def get_telegram_client():
    """
    Retorna o TelegramClient conectado (singleton).
    Cria e conecta na primeira chamada; reutiliza nas seguintes.
    """
    global _client

    async with _client_lock:
        if _client is not None and _client.is_connected():
            return _client

        from telethon import TelegramClient as _TC  # import tardio: sem Telethon em testes

        Path(_SESSION_PATH).parent.mkdir(parents=True, exist_ok=True)

        _client = _TC(
            _SESSION_PATH,
            api_id=settings.TELEGRAM_API_ID,
            api_hash=settings.TELEGRAM_API_HASH,
        )
        await _client.connect()

        if not await _client.is_user_authorized():
            logger.warning(
                "Telegram não autorizado. Execute scripts/setup_telegram.py no S8."
            )

        logger.info("TelegramClient conectado (session=%s)", _SESSION_PATH)
        return _client


async def disconnect_client() -> None:
    """Desconecta o client e limpa o singleton."""
    global _client
    async with _client_lock:
        if _client is not None:
            await _client.disconnect()
            _client = None
            logger.info("TelegramClient desconectado.")


# ---------------------------------------------------------------------------
# Helpers de mensagem
# ---------------------------------------------------------------------------

def extract_tag(text: str) -> Optional[str]:
    """Retorna a primeira tag #XXX999 encontrada no texto, ou None."""
    if not text:
        return None
    m = _TAG_RE.search(text)
    return m.group(0) if m else None


def _is_video_message(message) -> bool:
    """True se a mensagem contém um documento de vídeo."""
    if not message.media:
        return False
    doc = getattr(message.media, "document", None)
    if doc is None:
        return False
    mime = getattr(doc, "mime_type", "") or ""
    return mime.startswith(_VIDEO_MIME_PREFIX)


def _extract_filename(document) -> Optional[str]:
    """Extrai o nome original do arquivo dos atributos do documento."""
    from telethon.tl.types import DocumentAttributeFilename

    for attr in document.attributes:
        if isinstance(attr, DocumentAttributeFilename):
            return attr.file_name
    return None


def _extract_duration(document) -> Optional[int]:
    """Extrai a duração em segundos dos atributos do documento."""
    from telethon.tl.types import DocumentAttributeVideo

    for attr in document.attributes:
        if isinstance(attr, DocumentAttributeVideo):
            return attr.duration
    return None


# ---------------------------------------------------------------------------
# Sync de biblioteca
# ---------------------------------------------------------------------------

async def fetch_library_from_groups(db: Session) -> dict:
    """
    Busca mensagens de vídeo em todos os grupos configurados e salva/atualiza
    no banco de dados.

    Retorna:
        {
            "added": int,      # novos registros criados
            "updated": int,    # registros atualizados
            "skipped": int,    # mensagens sem vídeo ou com erro
            "errors": int,
        }
    """
    client = await get_telegram_client()
    stats = {"added": 0, "updated": 0, "skipped": 0, "errors": 0}

    for group_id in settings.TELEGRAM_GROUP_IDS:
        logger.info("Sincronizando grupo %s (limit=%d)...", group_id, settings.TELEGRAM_FETCH_LIMIT)
        try:
            entity = await client.get_entity(group_id)
            group_name: str = getattr(entity, "title", str(group_id))
        except Exception:
            logger.error("Não foi possível obter entidade do grupo %s", group_id, exc_info=True)
            stats["errors"] += 1
            continue

        fetched = 0
        async for message in client.iter_messages(entity, limit=settings.TELEGRAM_FETCH_LIMIT):
            if not _is_video_message(message):
                stats["skipped"] += 1
                continue

            try:
                added = _upsert_video(db, message, group_id, group_name)
                if added:
                    stats["added"] += 1
                else:
                    stats["updated"] += 1
                fetched += 1
            except Exception:
                logger.error(
                    "Erro ao salvar mensagem %d do grupo %s",
                    message.id, group_id, exc_info=True,
                )
                stats["errors"] += 1

        logger.info(
            "Grupo %s: %d vídeos processados.", group_name, fetched
        )

    return stats


def _upsert_video(db: Session, message, group_id: int, group_name: str) -> bool:
    """
    Cria ou atualiza um registro Video.
    Retorna True se foi inserção, False se atualização.
    """
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
        video = Video(
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
        logger.debug("Video adicionado: msg=%d grupo=%s tag=%s", message.id, group_name, tag)
        return True
    else:
        existing.title = title
        existing.description = msg_text or None
        existing.duration = _extract_duration(doc)
        existing.file_size = doc.size
        existing.menu_tag = tag
        existing.filename = _extract_filename(doc)
        db.commit()
        logger.debug("Video atualizado: msg=%d grupo=%s", message.id, group_name)
        return False


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

async def stream_video(
    group_id: int,
    msg_id: int,
    offset: int = 0,
    chunk_size: int = _CHUNK_SIZE,
) -> AsyncIterator[bytes]:
    """
    Async generator que produz chunks do vídeo diretamente do Telegram.
    Suporta offset para Range headers (streaming parcial).

    Uso no router de streaming:
        async for chunk in stream_video(group_id, msg_id, offset=range_start):
            yield chunk
    """
    client = await get_telegram_client()
    entity = await client.get_entity(group_id)
    message = await client.get_messages(entity, ids=msg_id)

    if message is None or not _is_video_message(message):
        logger.warning("stream_video: mensagem %d não encontrada ou não é vídeo.", msg_id)
        return

    async for chunk in client.iter_download(
        message.media,
        request_size=chunk_size,
        offset=offset,
    ):
        yield chunk


# ---------------------------------------------------------------------------
# Utilitários de arquivo
# ---------------------------------------------------------------------------

async def get_video_file_size(group_id: int, msg_id: int) -> Optional[int]:
    """
    Retorna o tamanho em bytes do arquivo de vídeo sem baixá-lo.
    Retorna None se a mensagem não existir ou não for vídeo.
    """
    client = await get_telegram_client()
    entity = await client.get_entity(group_id)
    message = await client.get_messages(entity, ids=msg_id)

    if message is None or not _is_video_message(message):
        return None

    return message.media.document.size


async def download_video(
    group_id: int,
    msg_id: int,
    dest_path: Path,
) -> Path:
    """
    Baixa o vídeo completo para dest_path de forma atômica:
      1. Escreve em dest_path.with_suffix('.tmp')
      2. Renomeia para dest_path ao concluir

    Levanta RuntimeError se a mensagem não existir ou não for vídeo.
    Levanta qualquer exceção do Telethon em caso de falha de rede.
    """
    client = await get_telegram_client()
    entity = await client.get_entity(group_id)
    message = await client.get_messages(entity, ids=msg_id)

    if message is None or not _is_video_message(message):
        raise RuntimeError(
            f"Mensagem {msg_id} no grupo {group_id} não encontrada ou não é vídeo."
        )

    tmp_path = dest_path.with_suffix(".tmp")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Iniciando download: grupo=%d msg=%d → %s", group_id, msg_id, dest_path.name
    )

    try:
        await client.download_media(message, file=str(tmp_path))
        os.replace(tmp_path, dest_path)
        logger.info(
            "Download concluído: %s (%d bytes)",
            dest_path.name,
            dest_path.stat().st_size,
        )
        return dest_path
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        logger.error(
            "Falha no download: grupo=%d msg=%d", group_id, msg_id, exc_info=True
        )
        raise
