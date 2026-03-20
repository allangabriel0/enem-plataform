"""
Testes para app/routers/notes.py — testam as funções de serviço diretamente.
"""
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Note, User, Video
from app.routers.notes import create_note, delete_note, list_notes, update_note


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db: Session, email: str = "u@test.com") -> User:
    user = User(name="Teste", email=email, hashed_password="hashed")
    db.add(user)
    db.commit()
    return user


def _make_video(db: Session, msg_id: int = 1) -> Video:
    video = Video(
        telegram_message_id=msg_id,
        telegram_group_id=1,
        telegram_group_name="Canal",
        title="Aula de Teste",
    )
    db.add(video)
    db.commit()
    return video


# ---------------------------------------------------------------------------
# test_create_note_with_timestamp
# ---------------------------------------------------------------------------

def test_create_note_with_timestamp(db_session: Session):
    user = _make_user(db_session)
    video = _make_video(db_session)

    note = create_note(db_session, user.id, video.id, content="Ponto importante", video_timestamp=142.5)

    assert note.id is not None
    assert note.content == "Ponto importante"
    assert note.video_timestamp == 142.5
    assert note.user_id == user.id
    assert note.video_id == video.id


# ---------------------------------------------------------------------------
# test_create_note_without_timestamp
# ---------------------------------------------------------------------------

def test_create_note_without_timestamp(db_session: Session):
    """Sem timestamp explícito, deve default para 0.0."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    note = create_note(db_session, user.id, video.id, content="Anotação geral")

    assert note.video_timestamp == 0.0


# ---------------------------------------------------------------------------
# test_get_notes_ordered_by_timestamp
# ---------------------------------------------------------------------------

def test_get_notes_ordered_by_timestamp(db_session: Session):
    """list_notes retorna notas ordenadas por video_timestamp crescente."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    create_note(db_session, user.id, video.id, "Última", video_timestamp=900.0)
    create_note(db_session, user.id, video.id, "Primeira", video_timestamp=10.0)
    create_note(db_session, user.id, video.id, "Meio", video_timestamp=450.0)

    notes = list_notes(db_session, user.id, video.id)

    assert len(notes) == 3
    assert notes[0].video_timestamp == 10.0
    assert notes[1].video_timestamp == 450.0
    assert notes[2].video_timestamp == 900.0


def test_get_notes_only_for_owner(db_session: Session):
    """list_notes não retorna notas de outros usuários."""
    user_a = _make_user(db_session, "a@test.com")
    user_b = _make_user(db_session, "b@test.com")
    video = _make_video(db_session)

    create_note(db_session, user_a.id, video.id, "Nota de A", video_timestamp=0.0)
    create_note(db_session, user_b.id, video.id, "Nota de B", video_timestamp=0.0)

    notes_a = list_notes(db_session, user_a.id, video.id)
    assert len(notes_a) == 1
    assert notes_a[0].content == "Nota de A"


# ---------------------------------------------------------------------------
# test_update_note
# ---------------------------------------------------------------------------

def test_update_note(db_session: Session):
    user = _make_user(db_session)
    video = _make_video(db_session)

    note = create_note(db_session, user.id, video.id, "Conteúdo original", video_timestamp=60.0)
    updated = update_note(db_session, note.id, user.id, "Conteúdo editado", video_timestamp=90.0)

    assert updated.content == "Conteúdo editado"
    assert updated.video_timestamp == 90.0


def test_update_note_keeps_timestamp_if_none(db_session: Session):
    """Timestamp None em update_note não altera o valor existente."""
    user = _make_user(db_session)
    video = _make_video(db_session)

    note = create_note(db_session, user.id, video.id, "Texto", video_timestamp=300.0)
    updated = update_note(db_session, note.id, user.id, "Novo texto", video_timestamp=None)

    assert updated.content == "Novo texto"
    assert updated.video_timestamp == 300.0


# ---------------------------------------------------------------------------
# test_delete_note
# ---------------------------------------------------------------------------

def test_delete_note(db_session: Session):
    user = _make_user(db_session)
    video = _make_video(db_session)

    note = create_note(db_session, user.id, video.id, "Para deletar")
    note_id = note.id

    delete_note(db_session, note_id, user.id)

    assert db_session.get(Note, note_id) is None


# ---------------------------------------------------------------------------
# test_delete_note_of_another_user_returns_404
# ---------------------------------------------------------------------------

def test_delete_note_of_another_user_returns_404(db_session: Session):
    """Tentar deletar nota de outro usuário deve levantar HTTPException 404."""
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")
    video = _make_video(db_session)

    note = create_note(db_session, owner.id, video.id, "Nota do owner")

    with pytest.raises(HTTPException) as exc_info:
        delete_note(db_session, note.id, other.id)

    assert exc_info.value.status_code == 404


def test_update_note_of_another_user_returns_404(db_session: Session):
    """update_note com user_id errado também levanta 404."""
    owner = _make_user(db_session, "owner2@test.com")
    other = _make_user(db_session, "other2@test.com")
    video = _make_video(db_session)

    note = create_note(db_session, owner.id, video.id, "Nota")

    with pytest.raises(HTTPException) as exc_info:
        update_note(db_session, note.id, other.id, "Tentativa", video_timestamp=None)

    assert exc_info.value.status_code == 404
