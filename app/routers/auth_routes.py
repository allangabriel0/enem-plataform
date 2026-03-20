import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import authenticate_user, create_access_token
from app.database import get_db

logger = logging.getLogger("enem")

router = APIRouter()

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

ACCESS_TOKEN_COOKIE = "access_token"
ACCESS_TOKEN_MAX_AGE = 72 * 3600  # 72 horas em segundos


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, email, password)
    if not user:
        logger.info("Tentativa de login falhou para: %s", email)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Email ou senha inválidos"},
            status_code=401,
        )

    token = create_access_token({"sub": user.email})
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_MAX_AGE,
        samesite="lax",
    )
    logger.info("Login bem-sucedido: %s", user.email)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    return response
