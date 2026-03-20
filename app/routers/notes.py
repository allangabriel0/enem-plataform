"""
routers/notes.py — CRUD de anotações com timestamp de vídeo.

Endpoints:
  GET    /api/notes/{video_id}  — lista notas do usuário para o vídeo
  POST   /api/notes             — cria nota
  PUT    /api/notes/{id}        — edita nota
  DELETE /api/notes/{id}        — remove nota
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Note, User

logger = logging.getLogger("enem")

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NoteIn(BaseModel):
    video_id: int
    content: str
    video_timestamp: float = 0.0


class NoteUpdate(BaseModel):
    content: str
    video_timestamp: Optional[float] = None


class NoteOut(BaseModel):
    id: int
    video_id: int
    content: str
    video_timestamp: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Funções de serviço
# ---------------------------------------------------------------------------

def list_notes(db: Session, user_id: int, video_id: int) -> list[Note]:
    """Retorna as notas do usuário para um vídeo, ordenadas por timestamp."""
    return (
        db.query(Note)
        .filter_by(user_id=user_id, video_id=video_id)
        .order_by(Note.video_timestamp)
        .all()
    )


def create_note(
    db: Session,
    user_id: int,
    video_id: int,
    content: str,
    video_timestamp: float = 0.0,
) -> Note:
    """Cria uma nova nota."""
    note = Note(
        user_id=user_id,
        video_id=video_id,
        content=content,
        video_timestamp=video_timestamp,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    logger.info("Nota criada: id=%d user=%d video=%d ts=%.1fs", note.id, user_id, video_id, video_timestamp)
    return note


def update_note(
    db: Session,
    note_id: int,
    user_id: int,
    content: str,
    video_timestamp: Optional[float],
) -> Note:
    """Atualiza conteúdo e/ou timestamp de uma nota. Retorna 404 se não pertencer ao usuário."""
    note = db.query(Note).filter_by(id=note_id, user_id=user_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    note.content = content
    if video_timestamp is not None:
        note.video_timestamp = video_timestamp
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    logger.info("Nota atualizada: id=%d user=%d", note_id, user_id)
    return note


def delete_note(db: Session, note_id: int, user_id: int) -> None:
    """Remove uma nota. Retorna 404 se não pertencer ao usuário."""
    note = db.query(Note).filter_by(id=note_id, user_id=user_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    db.delete(note)
    db.commit()
    logger.info("Nota removida: id=%d user=%d", note_id, user_id)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@router.get("/api/notes/{video_id}", response_model=list[NoteOut])
async def get_notes(
    video_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_notes(db, user.id, video_id)


@router.post("/api/notes", response_model=NoteOut, status_code=201)
async def post_note(
    data: NoteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_note(db, user.id, data.video_id, data.content, data.video_timestamp)


@router.put("/api/notes/{note_id}", response_model=NoteOut)
async def put_note(
    note_id: int,
    data: NoteUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_note(db, note_id, user.id, data.content, data.video_timestamp)


@router.delete("/api/notes/{note_id}", status_code=204)
async def delete_note_route(
    note_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_note(db, note_id, user.id)
