"""
routers/player.py — Player de vídeo com navegação e anotações.

Endpoints:
  GET /watch/{video_id} — renderiza player.html com todos os dados
                          necessários para o player, sidebar de seção,
                          notas e progresso.

Contexto do template:
  video             — Video atual
  progress          — WatchProgress do usuário (ou None)
  notes             — [Note] do usuário para este vídeo
  prev_video        — Video anterior na seção (ou None)
  next_video        — Próximo Video na seção (ou None)
  section_videos    — [Video] de toda a seção atual
  course_sections   — {seção: [Video]} de todo o curso atual
  lesson_materials  — [Material] com mesmo menu_tag do vídeo
  lesson_progress   — {seção: (done, total)} dentro do curso atual
  course_progress   — (done, total) do curso inteiro
  is_cached         — bool: vídeo disponível no cache local

Funções de serviço (topo do arquivo, testáveis isoladamente):
  find_section_position(section_videos, video_id) → (prev, current, next)
  collect_lesson_materials(db, video)             → [Material]
  build_section_lesson_progress(section_dict, pm) → {seção: (done, total)}
  build_single_course_progress(section_dict, pm)  → (done, total)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.cache_manager import CacheManager, get_cache_manager
from app.database import get_db
from app.menu_parser import group_videos_for_dashboard, parse_menu_file
from app.models import Material, Note, User, Video, WatchProgress

logger = logging.getLogger("enem")

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


# ---------------------------------------------------------------------------
# Dependência — CacheManager
# ---------------------------------------------------------------------------

def _get_cache() -> CacheManager:
    return get_cache_manager()


# ---------------------------------------------------------------------------
# Funções de serviço
# ---------------------------------------------------------------------------

def find_section_position(
    section_videos: list[Any],
    video_id: int,
) -> tuple[Optional[Any], Optional[Any], Optional[Any]]:
    """
    Localiza o vídeo na lista da seção e retorna (prev, current, next).
    Qualquer valor pode ser None (vídeo não encontrado, primeiro ou último).
    """
    for i, v in enumerate(section_videos):
        if v.id == video_id:
            prev_v = section_videos[i - 1] if i > 0 else None
            next_v = section_videos[i + 1] if i < len(section_videos) - 1 else None
            return prev_v, v, next_v
    return None, None, None


def collect_lesson_materials(db: Session, video: Video) -> list[Material]:
    """
    Retorna os materiais que compartilham o mesmo menu_tag do vídeo.
    Se o vídeo não tiver tag, tenta pelo course_name no mesmo grupo.
    """
    if video.menu_tag:
        mats = (
            db.query(Material)
            .filter_by(
                telegram_group_id=video.telegram_group_id,
                menu_tag=video.menu_tag,
            )
            .all()
        )
        if mats:
            return mats

    # Fallback: mesmo grupo + mesmo course_name
    if video.course_name:
        return (
            db.query(Material)
            .filter_by(
                telegram_group_id=video.telegram_group_id,
                course_name=video.course_name,
            )
            .all()
        )

    return []


def build_section_lesson_progress(
    course_sections: dict[str, list[Any]],
    progress_map: dict[int, WatchProgress],
) -> dict[str, tuple[int, int]]:
    """
    Para cada seção do curso retorna (concluídos, total).

    Args:
        course_sections — {seção: [Video]}
        progress_map    — {video_id: WatchProgress}

    Retorna:
        {seção: (concluídos, total)}
    """
    result: dict[str, tuple[int, int]] = {}
    for section, videos in course_sections.items():
        done = sum(
            1 for v in videos
            if progress_map.get(v.id) and progress_map[v.id].completed
        )
        result[section] = (done, len(videos))
    return result


def build_single_course_progress(
    course_sections: dict[str, list[Any]],
    progress_map: dict[int, WatchProgress],
) -> tuple[int, int]:
    """
    Agrega (concluídos, total) para o curso inteiro (todas as seções).
    """
    done = 0
    total = 0
    for videos in course_sections.values():
        total += len(videos)
        done += sum(
            1 for v in videos
            if progress_map.get(v.id) and progress_map[v.id].completed
        )
    return done, total


# ---------------------------------------------------------------------------
# Background cache
# ---------------------------------------------------------------------------

async def _cache_if_needed(
    group_id: int,
    msg_id: int,
    cache: CacheManager,
) -> None:
    """Baixa o vídeo em background se ainda não estiver cacheado."""
    if cache.get_cached_path(str(group_id), msg_id):
        return

    from app.telegram_client import download_video

    async def _dl(dest: Path) -> None:
        await download_video(group_id, msg_id, dest)

    await cache.cache_in_background(str(group_id), msg_id, _dl)


# ---------------------------------------------------------------------------
# Helpers de banco
# ---------------------------------------------------------------------------

def _get_progress_map_for_course(
    db: Session,
    user_id: int,
    video_ids: list[int],
) -> dict[int, WatchProgress]:
    """Busca progresso apenas dos vídeos do curso atual."""
    if not video_ids:
        return {}
    rows = (
        db.query(WatchProgress)
        .filter(
            WatchProgress.user_id == user_id,
            WatchProgress.video_id.in_(video_ids),
        )
        .all()
    )
    return {p.video_id: p for p in rows}


def _resolve_course_sections(
    video: Video,
) -> dict[str, list[Any]]:
    """
    Retorna {seção: [Video]} para o curso ao qual o vídeo pertence,
    usando o menu_parser para agrupamento hierárquico.

    Resolve: canal → curso correto → todas as seções daquele curso.
    Fallback: retorna apenas {lesson_name: [video]} se não houver menu_tag.
    """
    return {}   # preenchido dentro do handler onde db está disponível


# ---------------------------------------------------------------------------
# Rota principal
# ---------------------------------------------------------------------------

@router.get("/watch/{video_id}", response_class=HTMLResponse)
async def player(
    video_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    cache: CacheManager = Depends(_get_cache),
):
    """
    Renderiza o player com todos os dados necessários para:
      - Reproduzir o vídeo (stream ou cache)
      - Navegar entre vídeos da seção (prev/next)
      - Ver o índice do curso na sidebar
      - Ler e criar anotações com timestamp
    """
    # ------------------------------------------------------------------
    # 1. Vídeo
    # ------------------------------------------------------------------
    video = db.query(Video).filter_by(id=video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado.")

    # ------------------------------------------------------------------
    # 2. Cache — verifica e agenda download em background
    # ------------------------------------------------------------------
    is_cached = bool(
        cache.get_cached_path(str(video.telegram_group_id), video.telegram_message_id)
    )
    if not is_cached:
        background_tasks.add_task(
            _cache_if_needed,
            video.telegram_group_id,
            video.telegram_message_id,
            cache,
        )

    # ------------------------------------------------------------------
    # 3. Progresso e notas do usuário
    # ------------------------------------------------------------------
    progress = (
        db.query(WatchProgress)
        .filter_by(user_id=user.id, video_id=video_id)
        .first()
    )
    notes = (
        db.query(Note)
        .filter_by(user_id=user.id, video_id=video_id)
        .order_by(Note.video_timestamp)
        .all()
    )

    # ------------------------------------------------------------------
    # 4. Agrupamento hierárquico para navegação e sidebar
    # ------------------------------------------------------------------
    # Todos os vídeos do mesmo grupo para montar o índice do curso
    group_videos = (
        db.query(Video)
        .filter_by(telegram_group_id=video.telegram_group_id)
        .order_by(Video.title)
        .all()
    )
    menu_entries = parse_menu_file()
    grouped = group_videos_for_dashboard(group_videos, menu_entries)

    # Localiza o vídeo atual dentro da hierarquia canal → curso → seção
    current_canal: str = ""
    current_curso: str = ""
    current_secao: str = ""
    course_sections: dict[str, list[Any]] = {}
    section_videos: list[Any] = []

    for canal, cursos in grouped.items():
        for curso, secoes in cursos.items():
            for secao, videos_in_section in secoes.items():
                if any(v.id == video_id for v in videos_in_section):
                    current_canal = canal
                    current_curso = curso
                    current_secao = secao
                    section_videos = videos_in_section
                    course_sections = secoes   # {seção: [Video]} do curso inteiro
                    break
            if current_secao:
                break
        if current_secao:
            break

    # Fallback se o vídeo não aparecer no menu (sem tag)
    if not section_videos:
        section_videos = [video]
        course_sections = {video.lesson_name or "Sem Seção": [video]}

    # ------------------------------------------------------------------
    # 5. Navegação prev/next dentro da seção
    # ------------------------------------------------------------------
    prev_video, _, next_video = find_section_position(section_videos, video_id)

    # ------------------------------------------------------------------
    # 6. Progresso do curso
    # ------------------------------------------------------------------
    all_course_video_ids = [
        v.id for videos in course_sections.values() for v in videos
    ]
    progress_map = _get_progress_map_for_course(db, user.id, all_course_video_ids)

    lesson_progress = build_section_lesson_progress(course_sections, progress_map)
    course_progress = build_single_course_progress(course_sections, progress_map)

    # ------------------------------------------------------------------
    # 7. Materiais da aula
    # ------------------------------------------------------------------
    lesson_materials = collect_lesson_materials(db, video)

    logger.debug(
        "Player: user=%s video_id=%d cached=%s canal=%r curso=%r secao=%r",
        user.email, video_id, is_cached, current_canal, current_curso, current_secao,
    )

    return templates.TemplateResponse(
        request,
        "player.html",
        {
            "user": user,
            "video": video,
            "progress": progress,
            "notes": notes,
            "prev_video": prev_video,
            "next_video": next_video,
            "section_videos": section_videos,
            "course_sections": course_sections,
            "lesson_materials": lesson_materials,
            "lesson_progress": lesson_progress,
            "course_progress": course_progress,
            "is_cached": is_cached,
            "current_canal": current_canal,
            "current_curso": current_curso,
            "current_secao": current_secao,
        },
    )
