"""
routers/stats.py — Página de estatísticas por matéria.

Endpoints:
  GET /stats — página HTML com progresso por matéria, tempo total assistido,
               cursos concluídos e distribuição de vídeos.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, Video, WatchProgress

logger = logging.getLogger("enem")

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def build_subject_stats(db: Session, user_id: int) -> list[dict]:
    """
    Calcula estatísticas por matéria para o usuário.

    Retorna lista de dicts ordenada por total de vídeos desc:
      subject, total, completed, in_progress, watch_seconds, pct
    """
    videos = db.query(Video).all()
    progresses = (
        db.query(WatchProgress)
        .filter_by(user_id=user_id)
        .all()
    )
    prog_map = {p.video_id: p for p in progresses}

    # Agrupa por matéria
    subjects: dict[str, dict] = {}
    for v in videos:
        subj = v.subject or v.telegram_group_name or "Outros"
        if subj not in subjects:
            subjects[subj] = {
                "subject": subj,
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "watch_seconds": 0,
            }
        s = subjects[subj]
        s["total"] += 1
        p = prog_map.get(v.id)
        if p:
            if p.completed:
                s["completed"] += 1
            elif p.current_time > 0:
                s["in_progress"] += 1
            s["watch_seconds"] += int(p.current_time or 0)

    result = []
    for s in subjects.values():
        s["pct"] = round(s["completed"] / s["total"] * 100) if s["total"] > 0 else 0
        s["watch_h"] = round(s["watch_seconds"] / 3600, 1)
        result.append(s)

    return sorted(result, key=lambda x: x["total"], reverse=True)


def build_overall_stats(db: Session, user_id: int) -> dict:
    """Totais globais: vídeos, concluídos, tempo total, cursos."""
    total = db.query(Video).count()
    completed = db.query(WatchProgress).filter_by(user_id=user_id, completed=True).count()
    in_prog = (
        db.query(WatchProgress)
        .filter(
            WatchProgress.user_id == user_id,
            WatchProgress.completed.is_(False),
            WatchProgress.current_time > 0,
        )
        .count()
    )
    watch_seconds = (
        db.query(WatchProgress)
        .filter_by(user_id=user_id)
        .all()
    )
    total_sec = sum(int(p.current_time or 0) for p in watch_seconds)
    total_h = round(total_sec / 3600, 1)

    pct = round(completed / total * 100) if total > 0 else 0

    return {
        "total": total,
        "completed": completed,
        "in_progress": in_prog,
        "total_h": total_h,
        "pct": pct,
    }


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    subject_stats = build_subject_stats(db, user.id)
    overall = build_overall_stats(db, user.id)

    logger.debug("Stats: user=%s subjects=%d", user.email, len(subject_stats))

    return templates.TemplateResponse(
        request,
        "stats.html",
        {
            "user": user,
            "subject_stats": subject_stats,
            "overall": overall,
        },
    )
