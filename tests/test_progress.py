"""
Testes para app/routers/progress.py.

Testam as funções de serviço diretamente (sem HTTP) para focar na lógica
de negócio: não-regressão, auto-complete e persistência do flag completed.
"""
from sqlalchemy.orm import Session

from app.models import User, Video, WatchProgress
from app.routers.progress import AUTO_COMPLETE_THRESHOLD, get_progress, save_progress


# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

def _make_user(db: Session, email: str = "u@test.com") -> User:
    user = User(name="Teste", email=email, hashed_password="hashed")
    db.add(user)
    db.commit()
    return user


def _make_video(db: Session, msg_id: int = 1, group_id: int = 1) -> Video:
    video = Video(
        telegram_message_id=msg_id,
        telegram_group_id=group_id,
        telegram_group_name="Canal Teste",
        title="Aula de Teste",
    )
    db.add(video)
    db.commit()
    return video


# ---------------------------------------------------------------------------
# test_save_progress_new_video
# ---------------------------------------------------------------------------

def test_save_progress_new_video(db_session: Session):
    """Primeira chamada cria o registro com os valores fornecidos."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    record = save_progress(db_session, user.id, video.id, current_time=120.0, duration=3600.0)

    assert record.user_id == user.id
    assert record.video_id == video.id
    assert record.current_time == 120.0
    assert record.duration == 3600.0
    assert record.completed is False


# ---------------------------------------------------------------------------
# test_save_progress_existing_video_updates
# ---------------------------------------------------------------------------

def test_save_progress_existing_video_updates(db_session: Session):
    """Segunda chamada com valor maior atualiza o registro existente."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    save_progress(db_session, user.id, video.id, current_time=500.0, duration=3600.0)
    record = save_progress(db_session, user.id, video.id, current_time=1000.0, duration=3600.0)

    # Deve haver apenas um registro (UniqueConstraint)
    count = db_session.query(WatchProgress).filter_by(user_id=user.id, video_id=video.id).count()
    assert count == 1
    assert record.current_time == 1000.0


# ---------------------------------------------------------------------------
# test_auto_complete_at_90_percent
# ---------------------------------------------------------------------------

def test_auto_complete_at_90_percent(db_session: Session):
    """Ao atingir 90% da duração, completed deve ser marcado automaticamente."""
    user = _make_user(db_session)
    video = _make_video(db_session)
    duration = 3600.0
    threshold_time = duration * AUTO_COMPLETE_THRESHOLD  # 3240s

    # Exatamente no limiar
    record = save_progress(db_session, user.id, video.id, current_time=threshold_time, duration=duration)
    assert record.completed is True


def test_auto_complete_below_threshold_not_triggered(db_session: Session):
    """Abaixo de 90% não marca completed."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    record = save_progress(db_session, user.id, video.id, current_time=3000.0, duration=3600.0)
    assert record.completed is False


def test_auto_complete_above_threshold(db_session: Session):
    """Acima de 90% (ex: 95%) também marca completed."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    record = save_progress(db_session, user.id, video.id, current_time=3500.0, duration=3600.0)
    assert record.completed is True


# ---------------------------------------------------------------------------
# test_progress_never_regresses
# ---------------------------------------------------------------------------

def test_progress_never_regresses(db_session: Session):
    """current_time não deve ser sobrescrito por um valor menor."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    save_progress(db_session, user.id, video.id, current_time=1000.0, duration=3600.0)
    record = save_progress(db_session, user.id, video.id, current_time=500.0, duration=3600.0)

    assert record.current_time == 1000.0


def test_progress_same_time_accepted(db_session: Session):
    """current_time igual ao atual não causa regressão nem erro."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    save_progress(db_session, user.id, video.id, current_time=600.0, duration=3600.0)
    record = save_progress(db_session, user.id, video.id, current_time=600.0, duration=3600.0)

    assert record.current_time == 600.0


# ---------------------------------------------------------------------------
# test_get_progress_for_unwatched_video_returns_zeros
# ---------------------------------------------------------------------------

def test_get_progress_for_unwatched_video_returns_zeros(db_session: Session):
    """Para vídeo nunca assistido, get_progress retorna None."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    result = get_progress(db_session, user.id, video.id)
    assert result is None


def test_get_progress_returns_saved_record(db_session: Session):
    """get_progress retorna o registro salvo quando existe."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    save_progress(db_session, user.id, video.id, current_time=300.0, duration=1800.0)
    record = get_progress(db_session, user.id, video.id)

    assert record is not None
    assert record.current_time == 300.0
    assert record.duration == 1800.0


# ---------------------------------------------------------------------------
# test_completed_flag_persists
# ---------------------------------------------------------------------------

def test_completed_flag_persists(db_session: Session):
    """
    Uma vez marcado completed=True, chamadas subsequentes nunca o resetam,
    mesmo que a nova current_time não atinja o limiar de 90%.
    """
    user = _make_user(db_session)
    video = _make_video(db_session)

    # Insere diretamente com completed=True e current_time abaixo do limiar
    # (simula marcação manual ou migração de dados)
    record = WatchProgress(
        user_id=user.id,
        video_id=video.id,
        current_time=500.0,
        duration=3600.0,
        completed=True,
    )
    db_session.add(record)
    db_session.commit()

    # Atualiza com current_time maior mas ainda abaixo de 90%
    updated = save_progress(db_session, user.id, video.id, current_time=1000.0, duration=3600.0)

    assert updated.completed is True


def test_completed_flag_not_reset_on_regression_attempt(db_session: Session):
    """completed=True mantido mesmo quando current_time tentaria regredir."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    # Primeiro: auto-complete por atingir 91%
    save_progress(db_session, user.id, video.id, current_time=3276.0, duration=3600.0)

    # Segundo: tenta regredir (ignorado pela regra de não-regressão)
    record = save_progress(db_session, user.id, video.id, current_time=100.0, duration=3600.0)

    assert record.completed is True
    assert record.current_time == 3276.0  # não regrediu
