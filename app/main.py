import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.auth import RequiresLoginException
from app.database import init_db
from app.routers import (
    auth_routes,
    dashboard,
    materials,
    notes,
    player,
    progress,
    schedule,
    stats,
    streaming,
    sync,
)
from app.utils.logging import setup_logging

logger = logging.getLogger("enem")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Iniciando ENEM Study Platform.")
    init_db()
    yield
    # Shutdown
    logger.info("Encerrando ENEM Study Platform.")


app = FastAPI(
    title="ENEM Study Platform",
    lifespan=lifespan,
    docs_url=None,   # desativa Swagger UI em produção
    redoc_url=None,
)

# Arquivos estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RequiresLoginException)
async def requires_login_handler(request: Request, exc: RequiresLoginException):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login", status_code=302)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Erro não tratado em %s %s\n%s",
        request.method,
        request.url.path,
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor."},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    # Apenas para rotas HTML (não API)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Não encontrado."})
    return templates.TemplateResponse(request, "404.html", {}, status_code=404)


# ---------------------------------------------------------------------------
# Rotas base
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/favicon.svg")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_routes.router)
app.include_router(dashboard.router)
app.include_router(player.router)
app.include_router(streaming.router)
app.include_router(sync.router)
app.include_router(materials.router)
app.include_router(notes.router)
app.include_router(progress.router)
app.include_router(schedule.router)
app.include_router(stats.router)
