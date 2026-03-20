"""
routers/progress.py — Tracking de progresso de vídeos.

Regras de negócio:
  - current_time nunca regride (novo valor só é salvo se for maior que o atual)
  - completed=True é acionado automaticamente ao atingir 90% do vídeo
  - completed nunca volta para False depois de marcado
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, WatchProgress

logger = logging.getLogger("enem")

router = APIRouter()

AUTO_COMPLETE_THRESHOLD = 0.90  # 90% assistido → marca como concluído


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProgressIn(BaseModel):
    video_id: int
    current_time: float  # segundos
    duration: float      # segundos totais do vídeo


class ProgressOut(BaseModel):
    video_id: int
    current_time: float
    duration: float
    completed: bool


# ---------------------------------------------------------------------------
# Funções de serviço
# ---------------------------------------------------------------------------

def get_progress(db: Session, user_id: int, video_id: int) -> WatchProgress | None:
    """Busca o registro de progresso para um par (user, video)."""
    return (
        db.query(WatchProgress)
        .filter_by(user_id=user_id, video_id=video_id)
        .first()
    )


def save_progress(
    db: Session,
    user_id: int,
    video_id: int,
    current_time: float,
    duration: float,
) -> WatchProgress:
    """
    Cria ou atualiza o progresso de um vídeo para um usuário.

    Invariantes mantidos:
      - current_time nunca regride
      - completed=True nunca volta a False
      - auto-complete disparado ao atingir AUTO_COMPLETE_THRESHOLD
    """
    record = get_progress(db, user_id, video_id)

    if record is None:
        record = WatchProgress(
            user_id=user_id,
            video_id=video_id,
            current_time=current_time,
            duration=duration,
        )
        db.add(record)
        logger.debug("Novo progresso: user=%d video=%d t=%.1fs", user_id, video_id, current_time)
    else:
        # current_time nunca regride
        if current_time > record.current_time:
            record.current_time = current_time

        # Atualiza duração se fornecida
        if duration > 0:
            record.duration = duration

        record.last_watched = datetime.utcnow()
        logger.debug("Progresso atualizado: user=%d video=%d t=%.1fs", user_id, video_id, record.current_time)

    # Auto-complete a 90% — completed nunca volta a False
    if (
        not record.completed
        and record.duration > 0
        and record.current_time >= record.duration * AUTO_COMPLETE_THRESHOLD
    ):
        record.completed = True
        logger.info("Video %d marcado como concluido para user %d", video_id, user_id)

    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@router.post("/api/progress", response_model=ProgressOut)
async def post_progress(
    data: ProgressIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = save_progress(db, user.id, data.video_id, data.current_time, data.duration)
    return ProgressOut(
        video_id=record.video_id,
        current_time=record.current_time,
        duration=record.duration,
        completed=record.completed,
    )


@router.get("/api/progress/{video_id}", response_model=ProgressOut)
async def get_progress_route(
    video_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_progress(db, user.id, video_id)
    if record is None:
        return ProgressOut(video_id=video_id, current_time=0.0, duration=0.0, completed=False)
    return ProgressOut(
        video_id=record.video_id,
        current_time=record.current_time,
        duration=record.duration,
        completed=record.completed,
    )
