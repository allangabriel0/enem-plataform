"""
routers/schedule.py — Cronograma de estudos.

Endpoints:
  GET  /schedule              — página HTML do cronograma
  GET  /api/schedule          — lista itens (JSON), aceita ?month=YYYY-MM
  POST /api/schedule          — cria item
  PUT  /api/schedule/{id}     — edita item
  DELETE /api/schedule/{id}   — deleta item
"""
import logging
import unicodedata
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ScheduleItem, User

logger = logging.getLogger("enem")

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

# Paleta de cores por matéria (normalizado → hex)
_SUBJECT_COLORS: dict[str, str] = {
    "matematica": "#ef4444",
    "mat": "#ef4444",
    "fisica": "#f97316",
    "fis": "#f97316",
    "quimica": "#eab308",
    "qui": "#eab308",
    "biologia": "#22c55e",
    "bio": "#22c55e",
    "historia": "#3b82f6",
    "hist": "#3b82f6",
    "geografia": "#8b5cf6",
    "geo": "#8b5cf6",
    "portugues": "#ec4899",
    "port": "#ec4899",
    "redacao": "#f43f5e",
    "red": "#f43f5e",
    "literatura": "#a855f7",
    "lit": "#a855f7",
    "filosofia": "#6366f1",
    "fil": "#6366f1",
    "sociologia": "#14b8a6",
    "soc": "#14b8a6",
    "ingles": "#0ea5e9",
    "ing": "#0ea5e9",
    "espanhol": "#06b6d4",
    "esp": "#06b6d4",
    "artes": "#f59e0b",
    "enem": "#64748b",
    "atualidades": "#0f172a",
}

DEFAULT_COLOR = "#6b7280"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Minúsculas, sem acentos, sem separadores."""
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace(" ", "").replace("_", "").replace("-", "")


def infer_color(subject: str) -> str:
    """Infere a cor hex para a matéria. Fallback: DEFAULT_COLOR."""
    key = _normalize(subject)
    if key in _SUBJECT_COLORS:
        return _SUBJECT_COLORS[key]
    for k, v in _SUBJECT_COLORS.items():
        if key.startswith(k):
            return v
    return DEFAULT_COLOR


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ScheduleIn(BaseModel):
    subject: str
    topic: str
    description: Optional[str] = None
    scheduled_date: str          # YYYY-MM-DD
    scheduled_time: Optional[str] = None   # HH:MM
    status: str = "pending"
    color: Optional[str] = None  # se None, inferida pela matéria


class ScheduleUpdate(BaseModel):
    subject: Optional[str] = None
    topic: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    scheduled_time: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None


class ScheduleOut(BaseModel):
    id: int
    subject: str
    topic: str
    description: Optional[str]
    scheduled_date: str
    scheduled_time: Optional[str]
    status: str
    color: Optional[str]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Funções de serviço
# ---------------------------------------------------------------------------

def list_items(
    db: Session,
    user_id: int,
    month: Optional[str] = None,   # "YYYY-MM"
) -> list[ScheduleItem]:
    """Lista os itens do cronograma, opcionalmente filtrado por mês (YYYY-MM)."""
    q = db.query(ScheduleItem).filter_by(user_id=user_id)
    if month:
        q = q.filter(ScheduleItem.scheduled_date.startswith(month))
    return q.order_by(ScheduleItem.scheduled_date, ScheduleItem.scheduled_time).all()


def create_item(db: Session, user_id: int, data: ScheduleIn) -> ScheduleItem:
    """Cria um item no cronograma. Cor é inferida pela matéria se não fornecida."""
    color = data.color or infer_color(data.subject)
    item = ScheduleItem(
        user_id=user_id,
        subject=data.subject,
        topic=data.topic,
        description=data.description,
        scheduled_date=data.scheduled_date,
        scheduled_time=data.scheduled_time,
        status=data.status,
        color=color,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    logger.info("ScheduleItem criado: id=%d user=%d date=%s", item.id, user_id, data.scheduled_date)
    return item


def update_item(
    db: Session,
    item_id: int,
    user_id: int,
    data: ScheduleUpdate,
) -> ScheduleItem:
    """Atualiza campos fornecidos. 404 se não pertencer ao usuário."""
    item = db.query(ScheduleItem).filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)

    # Re-infere cor se matéria mudou e cor não foi fornecida explicitamente
    if data.subject and data.color is None:
        item.color = infer_color(data.subject)

    db.commit()
    db.refresh(item)
    logger.info("ScheduleItem atualizado: id=%d user=%d", item_id, user_id)
    return item


def delete_item(db: Session, item_id: int, user_id: int) -> None:
    """Remove o item. 404 se não pertencer ao usuário."""
    item = db.query(ScheduleItem).filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    db.delete(item)
    db.commit()
    logger.info("ScheduleItem removido: id=%d user=%d", item_id, user_id)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

@router.get("/schedule", response_class=HTMLResponse)
async def schedule_page(
    request: Request,
    month: Optional[str] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = list_items(db, user.id, month=month)
    return templates.TemplateResponse(
        request,
        "schedule.html",
        {"items": items, "user": user, "month": month},
    )


@router.get("/api/schedule", response_model=list[ScheduleOut])
async def get_schedule(
    month: Optional[str] = Query(default=None, description="Filtrar por mês: YYYY-MM"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_items(db, user.id, month=month)


@router.post("/api/schedule", response_model=ScheduleOut, status_code=201)
async def post_schedule(
    data: ScheduleIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_item(db, user.id, data)


@router.put("/api/schedule/{item_id}", response_model=ScheduleOut)
async def put_schedule(
    item_id: int,
    data: ScheduleUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_item(db, item_id, user.id, data)


@router.delete("/api/schedule/{item_id}", status_code=204)
async def delete_schedule(
    item_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_item(db, item_id, user.id)
