from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import User


def _create_user(db: Session, email: str = "user@enem.test", password: str = "senha123") -> User:
    user = User(name="Teste", email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    return user


def test_login_page_returns_200(client: TestClient):
    response = client.get("/login")
    assert response.status_code == 200
    assert "Entrar" in response.text


def test_login_with_valid_credentials_redirects(client: TestClient, db_session: Session):
    _create_user(db_session, email="valid@enem.test", password="senha123")

    response = client.post("/login", data={"email": "valid@enem.test", "password": "senha123"})

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert "access_token" in response.cookies


def test_login_with_invalid_credentials_returns_401(client: TestClient):
    response = client.post("/login", data={"email": "ghost@enem.test", "password": "errada"})

    assert response.status_code == 401
    assert "inválidos" in response.text


def test_logout_clears_cookie(authenticated_client: TestClient):
    response = authenticated_client.get("/logout")

    assert response.status_code == 302
    assert response.headers["location"] == "/login"
    # Set-Cookie deve conter access_token com Max-Age=0 (deleção)
    set_cookie = response.headers.get("set-cookie", "")
    assert "access_token" in set_cookie


def test_protected_route_without_token_redirects_to_login(client: TestClient):
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["location"] == "/login"
