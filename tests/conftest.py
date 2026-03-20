import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import RequiresLoginException, create_access_token, get_current_user, hash_password
from app.database import get_db
from app.models import Base, User
from app.routers import auth_routes


def _make_test_engine():
    # StaticPool: todas as conexões compartilham o mesmo banco in-memory
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def _make_app() -> FastAPI:
    """App mínima de teste: rotas de auth + rota protegida para testar get_current_user."""
    app = FastAPI()

    @app.exception_handler(RequiresLoginException)
    async def _requires_login(_request, _exc):
        return RedirectResponse(url="/login", status_code=302)

    app.include_router(auth_routes.router)

    @app.get("/")
    async def _dashboard(user: User = Depends(get_current_user)):
        return {"email": user.email}

    return app


@pytest.fixture()
def db_session():
    """Sessão SQLite em memória isolada por teste."""
    engine = _make_test_engine()
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestSession()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db_session: Session):
    """TestClient com banco em memória; não segue redirects."""
    app = _make_app()

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture()
def authenticated_client(client: TestClient, db_session: Session):
    """TestClient com cookie JWT válido de um usuário pré-criado."""
    user = User(
        name="Test User",
        email="testuser@enem.test",
        hashed_password=hash_password("senha_teste"),
    )
    db_session.add(user)
    db_session.commit()

    token = create_access_token({"sub": user.email})
    # "testserver" é o domínio padrão do TestClient (starlette/httpx)
    client.cookies.set("access_token", token, domain="testserver")
    return client
