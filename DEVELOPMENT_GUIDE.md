# DEVELOPMENT_GUIDE.md — Guia de Desenvolvimento com Claude Code

## Como usar este guia

Cada prompt abaixo é uma sessão do Claude Code. Cole o prompt no terminal do Claude Code, ele vai implementar, e você verifica o resultado antes de seguir para o próximo.

**Regra de ouro:** Rode `pytest tests/ -v` após cada prompt que cria testes. Se algo falhar, peça ao Claude Code para corrigir antes de avançar.

**Ambiente:** Tudo roda no seu PC. O S8 só entra na Fase 5.

---

## Fase 1 — Fundação (prompts 1-10)

Tudo aqui é testável no PC sem Telegram.

---

### Prompt 1 — Estrutura base do projeto

```
Leia CLAUDE.md e SPEC.md.

Crie a estrutura base do projeto:
- requirements.txt com: fastapi==0.115.6, uvicorn==0.30.6, sqlalchemy==2.0.35, python-jose[cryptography]==3.3.0, passlib[bcrypt]==1.7.4, python-dotenv==1.0.1, python-multipart==0.0.12, jinja2==3.1.4, aiofiles==24.1.0, telethon==1.37.0, cryptg==0.4.0, pydantic-settings==2.7.1
- requirements-dev.txt com: pytest==8.3.4, httpx==0.28.1, ruff==0.8.6, pytest-asyncio==0.24.0
- .env.example com todas as variáveis documentadas com comentários
- .gitignore completo
- app/__init__.py vazio
- app/routers/__init__.py vazio
- app/utils/__init__.py vazio
- tests/__init__.py vazio

Não crie nenhum outro arquivo ainda.
```

---

### Prompt 2 — Config com Pydantic

```
Leia CLAUDE.md e SPEC.md.

Implemente app/config.py usando Pydantic BaseSettings:
- Todas as variáveis do .env.example
- field_validator para TELEGRAM_GROUP_IDS (parse "id1,id2" em lista)
- model_config com env_file=".env"
- Valores padrão sensatos para desenvolvimento local
- SD_CARD_PATH: str = "" (auto-detectado depois)

Crie tests/test_config.py:
- Teste que Settings carrega com valores padrão sem .env
- Teste que TELEGRAM_GROUP_IDS parseia "123,456" para [123, 456]
- Teste que TELEGRAM_GROUP_IDS vazio retorna []

Rode pytest tests/test_config.py -v e corrija se falhar.
```

---

### Prompt 3 — Database e Models

```
Leia CLAUDE.md e SPEC.md.

Implemente:
1. app/database.py — engine SQLite com WAL mode, pragmas otimizados (synchronous=NORMAL, busy_timeout=5000, cache_size=-64000, foreign_keys=ON), SessionLocal, get_db generator, init_db
2. app/models.py — User, Video, Material, WatchProgress, Note, ScheduleItem com todos os campos da SPEC.md, UniqueConstraints e Indexes

Use o código da v1 como referência (está no repositório original) mas com imports atualizados.

Não crie testes ainda para isso — os testes vão usar esses models via conftest.py.
```

---

### Prompt 4 — Auth

```
Leia CLAUDE.md e SPEC.md.

Implemente:
1. app/auth.py — hash_password, verify_password, create_access_token, get_current_user (lê JWT do cookie), authenticate_user
2. app/routers/auth_routes.py — GET /login (renderiza template), POST /login (autentica, seta cookie, redirect), GET /logout (limpa cookie, redirect)

Use logging em vez de print. Se token inválido, redirect para /login via RedirectResponse (não HTTPException com 307).

Crie tests/conftest.py com:
- fixture db_session (SQLite em memória)
- fixture client (TestClient com db override)
- fixture authenticated_client (com cookie JWT válido)

Crie tests/test_auth.py:
- test_login_page_returns_200
- test_login_with_valid_credentials_redirects
- test_login_with_invalid_credentials_returns_401
- test_logout_clears_cookie
- test_protected_route_without_token_redirects_to_login

Para os templates que ainda não existem, crie templates mínimos (login.html com form básico).

Rode pytest tests/test_auth.py -v e corrija se falhar.
```

---

### Prompt 5 — Menu Parser

```
Leia CLAUDE.md e SPEC.md.

Copie app/menu_parser.py da v1 e ajuste:
- Imports para a nova estrutura
- Logging em vez de print
- Type hints completos

Crie tests/test_menu_parser.py com:
- test_parse_menu_text_basic (canal + curso + seção + tags)
- test_parse_menu_text_multiple_courses
- test_infer_subject_portugues (com acento)
- test_infer_subject_unknown_returns_name
- test_match_menu_entry_exact_channel
- test_match_menu_entry_fallback_subject
- test_match_menu_entry_no_tag_returns_none
- test_extract_tag_from_text
- test_group_videos_for_dashboard (precisa de mock de Video objects)

Use um trecho real do raw_menus.txt como fixture de teste:
```
CANAL: Filosofia

= CORUJAFLIX_-_Filosofia
== 1-Introdução_à_Filosofia
#F001 #F002 #F003

== 2-Conhecimento_A_Filosofia_Grega
#F009 #F010 #F011
```

Rode pytest tests/test_menu_parser.py -v e corrija se falhar.
```

---

### Prompt 6 — Text Utils

```
Leia CLAUDE.md e SPEC.md.

Copie app/utils/text.py da v1 sem alterações (está bom).

Crie tests/test_text_utils.py com:
- test_clean_title_removes_underscores ("Aula_01_-_Introdução" → "Aula 01 - Introdução")
- test_clean_title_smart_capitalize ("ENEM" fica "ENEM", "de" fica minúsculo)
- test_clean_title_empty_string
- test_short_video_title_removes_course_prefix
- test_short_video_title_removes_tag_prefix ("#F001 Aula" → "Aula")
- test_short_video_title_fallback_to_original

Rode pytest tests/test_text_utils.py -v e corrija se falhar.
```

---

### Prompt 7 — Logging

```
Leia CLAUDE.md e SPEC.md.

Implemente app/utils/logging.py:
- setup_logging() que configura logger "enem"
- RotatingFileHandler em logs/app.log (5MB, 3 backups)
- StreamHandler para console
- Formato: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
- Cria diretório logs/ se não existir
- Retorna o logger configurado

Atualize app/main.py para:
- Chamar setup_logging() no lifespan
- Usar logger no exception handler global (logar traceback antes de retornar 500)
- Incluir health check em GET /health
- Incluir favicon handler em GET /favicon.ico

Não precisa de testes para logging (difícil de testar, baixo valor).
```

---

### Prompt 8 — Progress Router

```
Leia CLAUDE.md e SPEC.md.

Copie app/routers/progress.py da v1 e ajuste:
- Logging em vez de print
- Imports para nova estrutura

Crie tests/test_progress.py com:
- test_save_progress_new_video
- test_save_progress_existing_video_updates
- test_auto_complete_at_90_percent
- test_progress_never_regresses (current_time só aumenta)
- test_get_progress_for_unwatched_video_returns_zeros
- test_completed_flag_persists (se marcou completed, nunca desmarca)

Rode pytest tests/test_progress.py -v e corrija se falhar.
```

---

### Prompt 9 — Notes Router

```
Leia CLAUDE.md e SPEC.md.

Copie app/routers/notes.py da v1 e ajuste imports e logging.

Crie tests/test_notes.py com:
- test_create_note_with_timestamp
- test_create_note_without_timestamp
- test_get_notes_ordered_by_timestamp
- test_update_note
- test_delete_note
- test_delete_note_of_another_user_returns_404

Rode pytest tests/test_notes.py -v e corrija se falhar.
```

---

### Prompt 10 — Schedule Router

```
Leia CLAUDE.md e SPEC.md.

Copie app/routers/schedule.py da v1 e ajuste:
- Imports e logging
- Template schedule.html mínimo para testes

Crie tests/test_schedule.py com:
- test_create_schedule_item
- test_auto_color_by_subject (Matemática = #ef4444)
- test_update_schedule_item
- test_delete_schedule_item
- test_filter_by_month
- test_schedule_page_returns_200

Rode pytest tests/test_schedule.py -v e corrija se falhar.
```

---

## Fase 2 — Core de vídeo (prompts 11-17)

Precisa de mocks para o Telegram nos testes.

---

### Prompt 11 — Cache Manager

```
Leia CLAUDE.md e SPEC.md.

Implemente app/cache_manager.py:

class CacheManager:
    def __init__(self, primary_dir: Path, fallback_dir: Path, max_gb: float):
        """primary_dir = SD card, fallback_dir = interno"""
    
    def get_cached_path(self, group_id: str, message_id: int) -> Path | None:
        """Busca em primary, depois em fallback. Atualiza atime para LRU."""
    
    async def cache_in_background(self, group_id: str, message_id: int, download_func):
        """Baixa via download_func, salva atômicamente (.tmp → .mp4). Chama evict se necessário."""
    
    def evict_lru(self):
        """Se total > max_gb, remove arquivos com atime mais antigo até ficar abaixo de 90% do limite."""
    
    def get_stats(self) -> dict:
        """Retorna {total_gb, used_gb, free_gb, count, oldest_access, newest_access}"""
    
    def _cache_path(self, group_id: str, message_id: int) -> Path:
        """Hash MD5 de '{group_id}_{message_id}' + '.mp4'"""

Crie tests/test_cache_manager.py com:
- test_cache_path_is_deterministic
- test_get_cached_path_returns_none_when_empty
- test_get_cached_path_finds_file_in_primary
- test_get_cached_path_finds_file_in_fallback
- test_cache_in_background_saves_file (use async mock)
- test_cache_atomic_no_partial_files (simular falha no download)
- test_evict_lru_removes_oldest
- test_evict_respects_limit
- test_get_stats

Use tmp_path do pytest para diretórios temporários.

Rode pytest tests/test_cache_manager.py -v e corrija se falhar.
```

---

### Prompt 12 — Telegram Client

```
Leia CLAUDE.md e SPEC.md.

Refatore app/telegram_client.py da v1:
- Substituir print() por logger
- Remover funções de cache (agora no cache_manager)
- Manter: get_telegram_client, disconnect_client, extract_tag, fetch_library_from_groups, stream_video, get_video_file_size
- Adicionar: download_video(group_id, msg_id, dest_path) que baixa o vídeo completo para um path
- Manter o lock asyncio para singleton do client
- Manter o download atômico (.tmp → rename)

Não crie testes para o Telegram client (depende de conexão real). Os testes de integração vão mockar isso.
```

---

### Prompt 13 — Streaming Router

```
Leia CLAUDE.md e SPEC.md.

Implemente app/routers/streaming.py extraindo de videos.py da v1:

- GET /stream/{video_id} — verifica cache (via cache_manager), se existe retorna FileResponse. Se não, faz streaming do Telegram com Range headers. Em background, cacheia o vídeo.
- POST /api/videos/{video_id}/cache — trigger manual de cache
- PUT /api/videos/{video_id} — atualizar subject/title

Injete cache_manager como dependência do FastAPI (via Depends).

Não crie testes unitários (depende de streaming real). Verificar manualmente na Fase 5.
```

---

### Prompt 14 — Sync Router

```
Leia CLAUDE.md e SPEC.md.

Implemente app/routers/sync.py extraindo de videos.py da v1:

- POST /api/sync-videos — chama fetch_library_from_groups(), faz upsert de vídeos e materiais no banco
- Adicionar logging: "Sincronizando X vídeos e Y materiais do grupo Z"
- Retornar {synced: N, updated: N, total: N, materials: N}

Copiar a lógica exata da v1 para o upsert, apenas reorganizar.
```

---

### Prompt 15 — Materials Router

```
Leia CLAUDE.md e SPEC.md.

Implemente app/routers/materials.py extraindo de videos.py da v1:

- GET /download/material/{material_id} — verifica cache, se não existe baixa via telegram_client.cache_material, salva path no banco, retorna FileResponse
- Logging de downloads

Copiar a lógica exata da v1, apenas isolar.
```

---

### Prompt 16 — Dashboard Router

```
Leia CLAUDE.md e SPEC.md.

Implemente app/routers/dashboard.py extraindo de videos.py da v1:

- GET / — renderiza dashboard.html com:
  - grouped_videos (via group_videos_for_dashboard)
  - progress_map, lesson_progress
  - subjects e groups para filtros
  - stats (total, completed, in_progress, materials)
  - continue_videos (últimos 6 vídeos pausados)
  - materials_by_group
  - Parâmetros de query: group, subject, search

Extrair as funções auxiliares build_progress_map, build_lesson_progress, build_course_progress para o topo do arquivo como funções de serviço.

Template dashboard.html por enquanto pode ser um placeholder com {{ stats }}.
```

---

### Prompt 17 — Player Router

```
Leia CLAUDE.md e SPEC.md.

Implemente app/routers/player.py extraindo de videos.py da v1:

- GET /watch/{video_id} — renderiza player.html com:
  - video, progress, notes
  - prev_video, next_video (navegação na seção)
  - section_videos, course_sections
  - lesson_materials
  - lesson_progress, course_progress
  - is_cached (verifica via cache_manager)
  - Inicia cache em background se não cacheado

Template player.html por enquanto pode ser um placeholder.
```

---

## Fase 3 — Interface (prompts 18-22)

Templates e CSS. Copiar da v1 e ajustar.

---

### Prompt 18 — Templates base e login

```
Leia CLAUDE.md e SPEC.md.

Copie da v1 e ajuste:
1. app/templates/base.html — sidebar com links para Dashboard e Cronograma, user info, logout
2. app/templates/login.html — form de login com email e password

Ajustar todos os paths de static files para /static/css/style.css e /static/js/app.js.
Manter o design dark theme da v1.
```

---

### Prompt 19 — Dashboard template

```
Leia CLAUDE.md e SPEC.md.

Copie app/templates/dashboard.html da v1 e ajuste:
- Todas as variáveis do template devem bater com o que dashboard.py passa no context
- Botão "Sincronizar Telegram" chama POST /api/sync-videos
- Cards de "Continue Assistindo"
- Navegação por Canal → Curso → Seção com TOC lateral
- Barras de progresso por seção e curso
- Filtros por matéria e grupo
- Busca
```

---

### Prompt 20 — Player template

```
Leia CLAUDE.md e SPEC.md.

Copie app/templates/player.html da v1 e ajuste:
- Video player usando video.js, source em /stream/{video_id}
- Auto-save progresso a cada 5s via fetch POST /api/progress
- Anotações com timestamp clicável
- Lista de vídeos da seção na lateral
- Navegação prev/next
- Download de materiais da seção
- Indicador se vídeo está cacheado ou streaming
- Progress bar da seção e do curso
```

---

### Prompt 21 — Schedule template

```
Leia CLAUDE.md e SPEC.md.

Copie app/templates/schedule.html da v1 e ajuste:
- Calendário mensal com itens por dia
- Modal para criar/editar item
- Status: pendente/concluído
- Cores por matéria
- Filtro por mês
```

---

### Prompt 22 — CSS e JS

```
Leia CLAUDE.md e SPEC.md.

Copie da v1:
1. app/static/css/style.css — dark theme completo
2. app/static/js/app.js — mobile menu toggle + formatTime

Ajustar se necessário para os novos endpoints (ex: /api/sync-videos em vez do endpoint antigo).
```

---

## Fase 4 — CLI e Scripts (prompts 23-25)

---

### Prompt 23 — CLI

```
Leia CLAUDE.md e SPEC.md.

Implemente app/cli.py usando argparse:

Comandos:
- python -m app.cli status — mostra: vídeos no banco, cache stats, espaço em disco
- python -m app.cli precache --course "Filosofia" — baixa todos os vídeos de um curso para o cache
- python -m app.cli precache --all — baixa tudo (com estimativa de tempo e espaço)
- python -m app.cli cleanup — roda evict_lru do cache_manager
- python -m app.cli cleanup --max-gb 30 — evict com limite customizado

Usar logging e progress indicators (print é OK aqui pois é CLI interativo).
```

---

### Prompt 24 — Scripts de operação

```
Leia CLAUDE.md e SPEC.md.

Crie os seguintes scripts shell. TODOS com shebang #!/data/data/com.termux/files/usr/bin/bash:

1. scripts/setup_termux.sh — Setup completo:
   - pkg update && upgrade
   - Instala python, git, openssh, build-essential, libffi, openssl, rust, cronie, termux-api
   - Clone ou pull do repo
   - python -m venv venv + pip install
   - Verifica cryptg
   - Detecta SD card, cria symlinks para cache
   - Cria diretórios (logs, data/menus, data/cache, data/materials)
   - Mostra próximos passos

2. scripts/start.sh — Inicia o app:
   - Valida config (python -c "from app.config import settings")
   - Mata instância anterior (pkill)
   - Inicia uvicorn com nohup
   - Espera 3s e verifica /health
   - Loga em logs/boot.log

3. scripts/stop.sh — Para o app:
   - pkill -f "uvicorn app.main:app"
   - Confirma que parou

4. scripts/status.sh — Painel de status:
   - App rodando? (curl /health)
   - Tailscale conectado? (tailscale ip)
   - Espaço em disco (interno + SD)
   - Cache stats (contagem + tamanho)
   - Banco tamanho
   - Últimos 3 erros do log

5. scripts/backup.sh — Backup do banco:
   - Copia data/enem.db para SD card com data no nome
   - Remove backups com mais de 7 dias
   - Loga

6. scripts/watchdog.sh — Health check para crontab:
   - curl /health, se falhar reinicia com start.sh
   - Loga

Também crie o script de boot do Termux:
7. .termux/boot/start-enem — Executado no boot:
   - termux-wake-lock
   - sleep 10
   - sshd
   - bash ~/enem-platform/scripts/start.sh
```

---

### Prompt 25 — Documentação final

```
Leia CLAUDE.md e SPEC.md.

Atualize o README.md com:
1. Descrição do projeto (2 parágrafos)
2. Features (lista)
3. Quick start no PC (para desenvolvimento)
4. Deploy no S8 (referencia setup_termux.sh)
5. Configuração do Tailscale:
   - No S8: Magisk-Tailscaled, tailscale login
   - Nos dispositivos: app Tailscale (Android/iOS/Windows/Mac)
   - IP local do S8: 192.168.100.127
   - IP Tailscale: ver com "tailscale ip -4"
   - Acesso: http://[IP]:8000
6. Comandos úteis (start, stop, status, sync, precache, backup)
7. Estrutura do projeto
8. Troubleshooting (Termux fecha, SSH não conecta, vídeo lento, etc.)
```

---

## Fase 5 — Deploy e teste real (prompts 26-27)

Agora no S8 de verdade.

---

### Prompt 26 — Deploy no S8

```
NÃO é para Claude Code — este é um checklist manual para você executar no S8 via Termux:

1. No S8, abrir Termux
2. bash scripts/setup_termux.sh
3. cp .env.example .env && nano .env (preencher tudo)
4. python scripts/setup_telegram.py (autenticar)
5. python scripts/create_users.py
6. bash scripts/start.sh
7. No navegador do S8: http://localhost:8000
8. Login e clicar "Sincronizar Telegram"
9. bash scripts/status.sh (verificar tudo)

Se algo der errado, verificar logs/app.log e logs/uvicorn.log.
```

---

### Prompt 27 — Configurar Tailscale + teste remoto

```
NÃO é para Claude Code — checklist manual:

1. No S8 via Termux:
   su
   tailscale login
   (abrir link no navegador para autorizar)
   tailscale ip -4 (anotar o IP 100.x.x.x)

2. No seu celular pessoal:
   - Instalar Tailscale da Play Store / App Store
   - Login com mesma conta
   - Acessar http://[IP_TAILSCALE]:8000

3. No celular do outro usuário:
   - Instalar Tailscale
   - Compartilhar acesso via Tailscale Admin (https://login.tailscale.com/admin)
   - Ou usar mesma conta

4. Testar:
   - Desligar Wi-Fi do celular, usar 5G
   - Acessar a plataforma
   - Assistir um vídeo
   - Verificar que o segundo acesso ao mesmo vídeo é mais rápido (cache)

5. Configurar auto-start:
   - Copiar .termux/boot/start-enem para ~/.termux/boot/
   - chmod +x ~/.termux/boot/start-enem
   - Reiniciar S8 e verificar que tudo volta sozinho

6. Configurar watchdog:
   - crontab -e
   - */3 * * * * bash ~/enem-platform/scripts/watchdog.sh
   - 0 4 * * * bash ~/enem-platform/scripts/backup.sh

7. Verificar coexistência Tailscale + WARP:
   - WARP ligado no app 1.1.1.1
   - tailscale status (deve mostrar conectado)
   - Sincronizar vídeos (deve funcionar = Telegram acessível via WARP)
   - Acessar de fora (deve funcionar = Tailscale funcional)
```
