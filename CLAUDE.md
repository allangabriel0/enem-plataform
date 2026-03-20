# CLAUDE.md — Instruções para Claude Code

## Sobre o projeto

Plataforma de estudos para o ENEM. Organiza vídeos e materiais de canais do Telegram com tracking de progresso, anotações com timestamp, download de materiais e cronograma de estudos.

**Stack:** FastAPI + Jinja2 + SQLite (WAL) + Telethon + Tailscale
**Target:** Galaxy S8 (ARM64) com LineageOS 12, root Magisk, Termux
**Usuários:** 2 pessoas, acesso remoto via Tailscale
**IP fixo local do S8:** 192.168.100.127

## Comandos essenciais

```bash
# Rodar app (dev no PC)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Rodar testes
pytest tests/ -v

# Rodar um teste específico
pytest tests/test_menu_parser.py -v

# Lint
ruff check app/ tests/

# Criar banco
python -c "from app.database import init_db; init_db()"

# Criar usuários
python scripts/create_users.py

# Autenticar no Telegram (só no S8)
python scripts/setup_telegram.py
```

## Arquitetura

```
app/
├── main.py              → FastAPI app, lifespan, exception handler
├── config.py            → Pydantic BaseSettings (validação automática do .env)
├── database.py          → SQLite + WAL mode + pragmas otimizados
├── models.py            → User, Video, Material, WatchProgress, Note, ScheduleItem
├── auth.py              → JWT (cookie httponly) + bcrypt
├── cache_manager.py     → Cache LRU em dois níveis (interno + SD card)
├── telegram_client.py   → Conexão Telegram, fetch, streaming via Telethon
├── menu_parser.py       → Parser de tags (#F001, #Doc01) → Canal → Curso → Seção
├── cli.py               → Comandos CLI (precache, status, cleanup)
├── utils/
│   ├── text.py          → Limpeza/normalização de títulos
│   └── logging.py       → RotatingFileHandler (5MB x 3 backups)
├── routers/
│   ├── auth_routes.py   → GET/POST /login, GET /logout
│   ├── dashboard.py     → GET / (dashboard com filtros, stats, TOC)
│   ├── player.py        → GET /watch/{id} (player + navegação + notas)
│   ├── streaming.py     → GET /stream/{id} (Range headers + cache)
│   ├── sync.py          → POST /api/sync-videos
│   ├── progress.py      → POST/GET /api/progress
│   ├── notes.py         → CRUD /api/notes
│   ├── schedule.py      → CRUD /api/schedule + GET /schedule
│   └── materials.py     → GET /download/material/{id}
├── templates/           → Jinja2 (base, login, dashboard, player, schedule)
└── static/              → CSS + JS
```

## Regras obrigatórias

1. **NUNCA usar print() para logging.** Usar:
   ```python
   import logging
   logger = logging.getLogger("enem")
   logger.info("mensagem")
   logger.error("erro", exc_info=True)
   ```

2. **Todo router novo precisa de testes** em `tests/test_<nome>.py`

3. **Queries ao banco em funções de serviço**, não inline nos handlers:
   ```python
   # ❌ Errado
   @router.get("/")
   async def dashboard(db: Session = Depends(get_db)):
       videos = db.query(Video).filter(...).all()  # query inline
   
   # ✅ Certo
   def get_filtered_videos(db: Session, group: str = "", subject: str = "") -> list[Video]:
       query = db.query(Video)
       if group:
           query = query.filter(Video.telegram_group_name == group)
       return query.all()
   ```

4. **Imports absolutos:** `from app.config import settings` (nunca relativos)

5. **Config via settings:** `from app.config import settings` (nunca `os.getenv` direto)

6. **Testes usam SQLite em memória**, nunca o banco real

7. **Templates são Jinja2** — sem React/Vue/frameworks JS

8. **Sem uvloop** — pode falhar no ARM do Termux, usar asyncio loop padrão

9. **Scripts shell com shebang do Termux:**
   ```bash
   #!/data/data/com.termux/files/usr/bin/bash
   ```

10. **Caminhos relativos ao projeto** — nunca hardcoded tipo `/home/ubuntu/...`

## Compatibilidade Termux (ARM64)

Pacotes que precisam de cuidado:
- `cryptg` → precisa de `pkg install build-essential` antes
- `bcrypt` → precisa de `pkg install rust` antes
- `cryptography` → precisa de `pkg install openssl` antes
- `uvicorn` → instalar SEM extras `[standard]` (uvloop pode falhar)

## Estrutura de testes

```python
# tests/conftest.py fornece:
# - db_session: SQLite em memória com todas as tabelas
# - client: TestClient do FastAPI com DB override
# - authenticated_client: TestClient com cookie JWT válido
# - sample_videos: lista de vídeos de teste no banco
```

## Ordem de desenvolvimento (fases)

1. **Fundação:** config, database, models, auth, menu_parser, utils, logging
2. **Core vídeo:** cache_manager, telegram_client, streaming, sync, materials
3. **Interface:** dashboard, player, templates, CSS/JS
4. **CLI e scripts:** cli.py, scripts de operação shell
5. **Deploy:** setup no S8, Tailscale, testes reais
