"""
Testes para app/routers/schedule.py — testam as funções de serviço diretamente.
"""
import pytest
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import RequiresLoginException, get_current_user
from app.database import get_db
from app.models import ScheduleItem, User
from app.routers.schedule import (
    ScheduleIn,
    ScheduleUpdate,
    create_item,
    delete_item,
    list_items,
    update_item,
)
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(db: Session, email: str = "u@test.com") -> User:
    user = User(name="Teste", email=email, hashed_password="hashed")
    db.add(user)
    db.commit()
    return user


# ---------------------------------------------------------------------------
# test_create_schedule_item
# ---------------------------------------------------------------------------

def test_create_schedule_item(db_session: Session):
    user = _make_user(db_session)

    data = ScheduleIn(
        subject="Matemática",
        topic="Progressões",
        scheduled_date="2026-04-10",
        scheduled_time="09:00",
    )
    item = create_item(db_session, user.id, data)

    assert item.id is not None
    assert item.subject == "Matemática"
    assert item.topic == "Progressões"
    assert item.scheduled_date == "2026-04-10"
    assert item.scheduled_time == "09:00"
    assert item.status == "pending"
    assert item.user_id == user.id


# ---------------------------------------------------------------------------
# test_auto_color_by_subject
# ---------------------------------------------------------------------------

def test_auto_color_by_subject(db_session: Session):
    """Cor deve ser inferida pela matéria quando não fornecida."""
    user = _make_user(db_session)

    data = ScheduleIn(subject="Matemática", topic="Funções", scheduled_date="2026-04-11")
    item = create_item(db_session, user.id, data)

    assert item.color == "#ef4444"


def test_explicit_color_overrides_inference(db_session: Session):
    """Cor fornecida explicitamente deve ser usada."""
    user = _make_user(db_session)

    data = ScheduleIn(
        subject="Física",
        topic="Cinemática",
        scheduled_date="2026-04-12",
        color="#aabbcc",
    )
    item = create_item(db_session, user.id, data)

    assert item.color == "#aabbcc"


# ---------------------------------------------------------------------------
# test_update_schedule_item
# ---------------------------------------------------------------------------

def test_update_schedule_item(db_session: Session):
    user = _make_user(db_session)

    data = ScheduleIn(subject="Física", topic="Dinâmica", scheduled_date="2026-04-13")
    item = create_item(db_session, user.id, data)

    update = ScheduleUpdate(status="done", topic="Cinemática")
    updated = update_item(db_session, item.id, user.id, update)

    assert updated.status == "done"
    assert updated.topic == "Cinemática"
    assert updated.subject == "Física"  # inalterado


def test_update_item_of_another_user_returns_404(db_session: Session):
    owner = _make_user(db_session, "owner@test.com")
    other = _make_user(db_session, "other@test.com")

    data = ScheduleIn(subject="Química", topic="Estequiometria", scheduled_date="2026-04-14")
    item = create_item(db_session, owner.id, data)

    with pytest.raises(HTTPException) as exc_info:
        update_item(db_session, item.id, other.id, ScheduleUpdate(status="done"))

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# test_delete_schedule_item
# ---------------------------------------------------------------------------

def test_delete_schedule_item(db_session: Session):
    user = _make_user(db_session)

    data = ScheduleIn(subject="Biologia", topic="Genética", scheduled_date="2026-04-15")
    item = create_item(db_session, user.id, data)
    item_id = item.id

    delete_item(db_session, item_id, user.id)

    assert db_session.get(ScheduleItem, item_id) is None


def test_delete_item_of_another_user_returns_404(db_session: Session):
    owner = _make_user(db_session, "owner2@test.com")
    other = _make_user(db_session, "other2@test.com")

    data = ScheduleIn(subject="História", topic="Brasil Colônia", scheduled_date="2026-04-16")
    item = create_item(db_session, owner.id, data)

    with pytest.raises(HTTPException) as exc_info:
        delete_item(db_session, item.id, other.id)

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# test_filter_by_month
# ---------------------------------------------------------------------------

def test_filter_by_month(db_session: Session):
    user = _make_user(db_session)

    for subject, date in [
        ("Matemática", "2026-04-01"),
        ("Física", "2026-04-15"),
        ("Química", "2026-05-01"),
    ]:
        create_item(db_session, user.id, ScheduleIn(subject=subject, topic="T", scheduled_date=date))

    abril = list_items(db_session, user.id, month="2026-04")
    assert len(abril) == 2
    assert all(i.scheduled_date.startswith("2026-04") for i in abril)

    maio = list_items(db_session, user.id, month="2026-05")
    assert len(maio) == 1

    todos = list_items(db_session, user.id)
    assert len(todos) == 3


# ---------------------------------------------------------------------------
# test_schedule_page_returns_200
# ---------------------------------------------------------------------------

@pytest.fixture()
def schedule_client(db_session: Session):
    """TestClient com schedule router, banco in-memory e auth mockada."""
    from app.routers import schedule as schedule_router

    app = FastAPI()

    @app.exception_handler(RequiresLoginException)
    async def _requires_login(_request, _exc):
        return RedirectResponse(url="/login", status_code=302)

    app.include_router(schedule_router.router)

    user = User(name="Test", email="sched@test.com", hashed_password="hashed")
    db_session.add(user)
    db_session.commit()

    def _override_get_db():
        yield db_session

    def _override_get_current_user():
        return user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user

    with TestClient(app, follow_redirects=False) as c:
        yield c


def test_schedule_page_returns_200(schedule_client: TestClient):
    response = schedule_client.get("/schedule")
    assert response.status_code == 200
    assert "Cronograma" in response.text
