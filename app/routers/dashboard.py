"""
routers/dashboard.py — Página principal da plataforma.

Endpoints:
  GET / — renderiza dashboard.html com vídeos agrupados, progresso,
           filtros de matéria/grupo, estatísticas e vídeos em andamento.

Parâmetros de query:
  group   — filtra por telegram_group_name
  subject — filtra por subject
  search  — filtra por título (case-insensitive, parcial)

Funções de serviço (topo do arquivo, testáveis isoladamente):
  build_progress_map(progresses)     → {video_id: WatchProgress}
  build_lesson_progress(grouped, pm) → {canal: {curso: {seção: (done, total)}}}
  build_course_progress(grouped, pm) → {canal: {curso: (done, total)}}
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.menu_parser import group_videos_for_dashboard, parse_menu_file
from app.models import Material, SyncState, User, Video, WatchProgress

logger = logging.getLogger("enem")

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)

_CONTINUE_LIMIT = 6   # máximo de vídeos "continuar assistindo"


# ---------------------------------------------------------------------------
# Funções de serviço
# ---------------------------------------------------------------------------

def build_progress_map(progresses: list[WatchProgress]) -> dict[int, WatchProgress]:
    """
    Converte lista de WatchProgress em {video_id: WatchProgress}.
    Permite lookup O(1) por video_id no template e nas funções de progresso.
    """
    return {p.video_id: p for p in progresses}


def build_lesson_progress(
    grouped: dict[str, dict[str, dict[str, list[Any]]]],
    progress_map: dict[int, WatchProgress],
) -> dict[str, dict[str, dict[str, tuple[int, int]]]]:
    """
    Para cada (canal, curso, seção) calcula (concluídos, total).

    Retorna:
        {canal: {curso: {seção: (concluídos, total)}}}
    """
    result: dict[str, dict[str, dict[str, tuple[int, int]]]] = {}
    for canal, cursos in grouped.items():
        result[canal] = {}
        for curso, secoes in cursos.items():
            result[canal][curso] = {}
            for secao, videos in secoes.items():
                done = sum(
                    1 for v in videos
                    if progress_map.get(v.id) and progress_map[v.id].completed
                )
                result[canal][curso][secao] = (done, len(videos))
    return result


def build_course_progress(
    grouped: dict[str, dict[str, dict[str, list[Any]]]],
    progress_map: dict[int, WatchProgress],
) -> dict[str, dict[str, tuple[int, int]]]:
    """
    Para cada (canal, curso) agrega (concluídos, total) somando todas as seções.

    Retorna:
        {canal: {curso: (concluídos, total)}}
    """
    result: dict[str, dict[str, tuple[int, int]]] = {}
    for canal, cursos in grouped.items():
        result[canal] = {}
        for curso, secoes in cursos.items():
            done = 0
            total = 0
            for videos in secoes.values():
                for v in videos:
                    total += 1
                    if progress_map.get(v.id) and progress_map[v.id].completed:
                        done += 1
            result[canal][curso] = (done, total)
    return result


# ---------------------------------------------------------------------------
# Queries de banco
# ---------------------------------------------------------------------------

def _get_videos(
    db: Session,
    group: str = "",
    subject: str = "",
    search: str = "",
) -> list[Video]:
    """Retorna vídeos com filtros opcionais de grupo, matéria e busca por título."""
    q = db.query(Video)
    if group:
        q = q.filter(Video.telegram_group_name == group)
    if subject:
        q = q.filter(Video.subject == subject)
    if search:
        q = q.filter(Video.title.ilike(f"%{search}%"))
    return q.order_by(Video.telegram_group_name, Video.title).all()


def _get_continue_videos(
    db: Session,
    user_id: int,
    limit: int = _CONTINUE_LIMIT,
) -> list[Video]:
    """
    Retorna até `limit` vídeos que o usuário pausou (não concluídos, current_time > 0),
    ordenados pelo acesso mais recente.
    """
    rows = (
        db.query(Video, WatchProgress)
        .join(WatchProgress, WatchProgress.video_id == Video.id)
        .filter(
            WatchProgress.user_id == user_id,
            WatchProgress.completed.is_(False),
            WatchProgress.current_time > 0,
        )
        .order_by(WatchProgress.last_watched.desc())
        .limit(limit)
        .all()
    )
    return [video for video, _ in rows]


def _get_stats(
    db: Session,
    user_id: int,
    total_videos: int,
) -> dict:
    """
    Agrega estatísticas globais do usuário.

    Retorna:
        total       — total de vídeos no banco (já filtrados se necessário)
        completed   — vídeos marcados como concluídos
        in_progress — vídeos iniciados mas não concluídos
        materials   — total de materiais
    """
    completed = (
        db.query(WatchProgress)
        .filter_by(user_id=user_id, completed=True)
        .count()
    )
    in_progress = (
        db.query(WatchProgress)
        .filter(
            WatchProgress.user_id == user_id,
            WatchProgress.completed.is_(False),
            WatchProgress.current_time > 0,
        )
        .count()
    )
    total_materials = db.query(Material).count()

    return {
        "total": total_videos,
        "completed": completed,
        "in_progress": in_progress,
        "materials": total_materials,
    }


def _get_materials_by_group(db: Session) -> dict[str, list[Material]]:
    """Agrupa materiais por telegram_group_name."""
    materials = db.query(Material).order_by(
        Material.telegram_group_name, Material.title
    ).all()
    result: dict[str, list[Material]] = {}
    for m in materials:
        result.setdefault(m.telegram_group_name, []).append(m)
    return result


def _get_last_sync_at(db: Session) -> Optional[datetime]:
    """Retorna o datetime da sincronização mais recente entre todos os grupos."""
    state = db.query(SyncState).order_by(SyncState.last_sync_at.desc()).first()
    return state.last_sync_at if state else None


# ---------------------------------------------------------------------------
# Rota
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    group: Optional[str] = Query(default=None),
    subject: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    only_unwatched: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dashboard principal.

    Contexto enviado ao template:
      user              — usuário autenticado
      grouped_videos    — canal → curso → seção → [Video]
      progress_map      — {video_id: WatchProgress}
      lesson_progress   — {canal: {curso: {seção: (done, total)}}}
      course_progress   — {canal: {curso: (done, total)}}
      stats             — {total, completed, in_progress, materials}
      continue_videos   — últimos 6 vídeos pausados
      materials_by_group — {grupo: [Material]}
      subjects          — lista de matérias distintas (para filtro)
      groups            — lista de grupos distintos (para filtro)
      filters           — {group, subject, search} aplicados
    """
    # Filtros normalizados (None → "")
    f_group = group or ""
    f_subject = subject or ""
    f_search = search or ""

    # Vídeos com filtros aplicados
    videos = _get_videos(db, group=f_group, subject=f_subject, search=f_search)

    # Progresso do usuário (sem filtro — tudo o que ele assistiu)
    progresses = (
        db.query(WatchProgress)
        .filter_by(user_id=user.id)
        .all()
    )

    # Filtro "não assistidos"
    if only_unwatched:
        watched_ids = {p.video_id for p in progresses if p.completed}
        videos = [v for v in videos if v.id not in watched_ids]

    # Agrupamento hierárquico via menu_parser
    menu_entries = parse_menu_file()
    grouped_videos = group_videos_for_dashboard(videos, menu_entries)

    progress_map = build_progress_map(progresses)

    # Progresso por seção e curso
    lesson_progress = build_lesson_progress(grouped_videos, progress_map)
    course_progress = build_course_progress(grouped_videos, progress_map)

    # Stats globais
    stats = _get_stats(db, user.id, len(videos))

    # Vídeos em andamento ("Continuar assistindo")
    continue_videos = _get_continue_videos(db, user.id)

    # Materiais por grupo
    materials_by_group = _get_materials_by_group(db)

    # Última sincronização
    last_sync_at = _get_last_sync_at(db)

    # Opções para filtros (distintos, ordenados)
    subjects: list[str] = sorted(
        {v.subject for v in db.query(Video).all() if v.subject}
    )
    groups: list[str] = sorted(
        {v.telegram_group_name for v in db.query(Video).all() if v.telegram_group_name}
    )

    logger.debug(
        "Dashboard: user=%s videos=%d grouped_canais=%d",
        user.email, len(videos), len(grouped_videos),
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "grouped_videos": grouped_videos,
            "progress_map": progress_map,
            "lesson_progress": lesson_progress,
            "course_progress": course_progress,
            "stats": stats,
            "continue_videos": continue_videos,
            "materials_by_group": materials_by_group,
            "subjects": subjects,
            "groups": groups,
            "last_sync_at": last_sync_at,
            "filters": {
                "group": f_group,
                "subject": f_subject,
                "search": f_search,
                "only_unwatched": only_unwatched,
            },
        },
    )
