# SPEC.md — Especificação Técnica ENEM Study Platform v2.0

## 1. Visão geral

Plataforma web de estudos para o ENEM que organiza vídeos e materiais de canais do Telegram. Funcionalidades: player com tracking de progresso, anotações com timestamp, download de materiais (PDF/ZIP/RAR), cronograma de estudos, busca por título/tag/seção.

## 2. Ambiente de produção

| Item | Valor |
|------|-------|
| Hardware | Galaxy S8 — Exynos 8895, 4GB RAM, ARM64 |
| OS | LineageOS Android 12 + root Magisk |
| Runtime | Termux (F-Droid) |
| Armazenamento | ~40GB interno + SD card 64GB |
| Rede servidor | Wi-Fi fixo, IP local 192.168.100.127 |
| Acesso remoto | Tailscale (IP 100.x.x.x atribuído no setup) |
| VPN saída | Cloudflare WARP (1.1.1.1) para acesso ao Telegram |
| Usuários | 2 pessoas, acessam de qualquer lugar (5G, Wi-Fi, etc.) |
| Conteúdo | ~2.500 vídeos em canais Telegram (~208GB total) |

## 3. Stack

| Componente | Tecnologia | Versão |
|------------|-----------|--------|
| Framework | FastAPI | 0.115+ |
| Server | Uvicorn (sem uvloop) | 0.30+ |
| Database | SQLAlchemy + SQLite WAL | 2.0+ |
| Telegram | Telethon + cryptg | 1.37+ |
| Auth | python-jose + passlib/bcrypt | — |
| Config | pydantic-settings | 2.0+ |
| Templates | Jinja2 | 3.1+ |
| Testes | pytest + httpx | — |
| Rede | Tailscale (Magisk-Tailscaled) | — |

## 4. Decisões de arquitetura

### 4.1 Tailscale no lugar de Cloudflare Tunnel

Cloudflare Tunnel proxeia todo o tráfego por CDN intermediária, adicionando latência no streaming de vídeo. Tailscale cria rede mesh WireGuard ponto-a-ponto: tráfego vai direto do dispositivo do usuário para o S8. Na mesma rede Wi-Fi, tráfego nem sai para a internet.

No S8 com root, o módulo Magisk-Tailscaled roda `tailscaled` com userspace-networking (sem usar o slot VPN do Android), permitindo coexistência com WARP.

### 4.2 WARP como VPN de saída

Provedores brasileiros podem fazer traffic shaping nos IPs do Telegram. O WARP muda a rota de saída, garantindo acesso rápido aos servidores do Telegram. Fica sempre ligado no S8.

### 4.3 Cache em dois níveis com LRU

Streaming em tempo real do Telegram é o principal gargalo de performance. Solução: cache agressivo no SD card.

**Fluxo:**
1. Usuário acessa vídeo → verifica cache no SD
2. Se existe → `FileResponse` direto (< 500ms)
3. Se não → streaming do Telegram + salva no SD em background
4. Segundo acesso em diante → sempre do cache
5. Quando cache atinge limite → LRU remove os mais antigos

**Limites configuráveis:** `CACHE_MAX_GB` no .env (padrão 50GB).

### 4.4 Pydantic BaseSettings

Substitui a classe simples de config. Validação automática de tipos no startup. Se `TELEGRAM_API_ID` não for número, erro claro em vez de crash críptico em runtime.

### 4.5 Logging com rotação

`logging.RotatingFileHandler` com 5MB x 3 backups (máximo 20MB de logs). Todo `print()` da v1 substituído por `logger.info/error/warning`. Essencial para debug remoto via SSH.

### 4.6 Quebra do videos.py

O `videos.py` da v1 tinha 366 linhas com 5 responsabilidades diferentes. Na v2, separado em: `dashboard.py`, `player.py`, `streaming.py`, `sync.py`, `materials.py`.

## 5. Models (banco de dados)

Mantidos da v1 com ajustes mínimos:

- **User** — id, name, email, hashed_password, created_at
- **Video** — id, telegram_message_id, telegram_group_id, telegram_group_name, title, description, duration, file_size, subject, course_name, lesson_name, menu_tag, filename, thumbnail_path, cached_at
- **Material** — id, telegram_message_id, telegram_group_id, telegram_group_name, title, description, subject, course_name, lesson_name, menu_tag, file_name, file_ext, file_size, cached_path, created_at
- **WatchProgress** — id, user_id, video_id, current_time, duration, completed, last_watched (UniqueConstraint user_id+video_id)
- **Note** — id, user_id, video_id, content, video_timestamp, created_at, updated_at
- **ScheduleItem** — id, user_id, subject, topic, description, scheduled_date, scheduled_time, status, color, created_at

**SQLite otimizações (pragmas):**
- `journal_mode=WAL` — leitura sem bloquear escrita
- `synchronous=NORMAL` — mais rápido, seguro com WAL
- `busy_timeout=5000` — espera 5s se banco ocupado
- `cache_size=-64000` — 64MB de cache em memória
- `foreign_keys=ON` — integridade referencial

## 6. Endpoints

### Páginas (HTML)
| Método | Path | Router | Descrição |
|--------|------|--------|-----------|
| GET | /login | auth_routes | Tela de login |
| POST | /login | auth_routes | Processa login |
| GET | /logout | auth_routes | Logout (limpa cookie) |
| GET | / | dashboard | Dashboard com vídeos agrupados |
| GET | /watch/{id} | player | Player de vídeo com notas |
| GET | /schedule | schedule | Cronograma de estudos |

### API (JSON)
| Método | Path | Router | Descrição |
|--------|------|--------|-----------|
| GET | /health | main | Health check |
| GET | /stream/{id} | streaming | Stream de vídeo (Range headers) |
| POST | /api/videos/{id}/cache | streaming | Trigger cache manual |
| PUT | /api/videos/{id} | streaming | Atualizar metadados do vídeo |
| POST | /api/sync-videos | sync | Sincronizar com Telegram |
| GET | /download/material/{id} | materials | Download de material |
| POST | /api/progress | progress | Salvar progresso |
| GET | /api/progress/{id} | progress | Ler progresso |
| GET | /api/notes/{video_id} | notes | Listar notas |
| POST | /api/notes | notes | Criar nota |
| PUT | /api/notes/{id} | notes | Editar nota |
| DELETE | /api/notes/{id} | notes | Deletar nota |
| GET | /api/schedule | schedule | Listar itens do cronograma |
| POST | /api/schedule | schedule | Criar item |
| PUT | /api/schedule/{id} | schedule | Editar item |
| DELETE | /api/schedule/{id} | schedule | Deletar item |

## 7. Sistema de tags e menu

O arquivo `data/menus/raw_menus.txt` (1048 linhas) mapeia tags para a hierarquia Canal → Curso → Seção.

**Formato:**
```
CANAL: Filosofia

= Nome_do_Curso
== Nome_da_Seção
#F001 #F002 #F003
```

**Parsing:** `=` define curso, `==` define seção, `#F001` e `#Doc01` são tags de vídeos e materiais respectivamente. O `menu_parser.py` faz match por tag com fallback em cascata: canal exato → canal parcial → matéria → primeiro candidato.

## 8. Autenticação

JWT em cookie httponly (não header Authorization). Token expira em 72 horas. Bcrypt para hash de senhas. Apenas 2 usuários, criados via script `create_users.py` a partir do .env.

Se token inválido/expirado → redirect para /login.

## 9. Cache manager

```
CacheManager
├── get_cached_path(group_id, msg_id) → Path | None
├── get_or_stream(group_id, msg_id, stream_func) → path ou stream
├── cache_in_background(group_id, msg_id, download_func)
├── evict_lru() → remove vídeos antigos quando acima do limite
├── get_stats() → {total_gb, used_gb, count, oldest, newest}
└── precache_course(course_name) → baixa todos os vídeos de um curso
```

**Storage layout:**
- Primário: SD card (`/storage/xxxx-xxxx/enem-cache/videos/`)
- Fallback: interno (`data/cache/`)
- Nomes: hash MD5 de `{group_id}_{message_id}` + `.mp4`
- Download atômico: salva em `.tmp`, renomeia para `.mp4` ao completar

## 10. Estrutura de diretórios

```
enem-platform/
├── CLAUDE.md
├── SPEC.md
├── README.md
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── auth.py
│   ├── cache_manager.py
│   ├── telegram_client.py
│   ├── menu_parser.py
│   ├── cli.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── text.py
│   │   └── logging.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth_routes.py
│   │   ├── dashboard.py
│   │   ├── player.py
│   │   ├── streaming.py
│   │   ├── sync.py
│   │   ├── progress.py
│   │   ├── notes.py
│   │   ├── schedule.py
│   │   └── materials.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── dashboard.html
│   │   ├── player.html
│   │   └── schedule.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_menu_parser.py
│   ├── test_progress.py
│   ├── test_notes.py
│   ├── test_schedule.py
│   ├── test_cache_manager.py
│   └── test_text_utils.py
├── scripts/
│   ├── create_users.py
│   ├── setup_telegram.py
│   ├── setup_termux.sh
│   ├── start.sh
│   ├── stop.sh
│   ├── status.sh
│   └── backup.sh
├── data/
│   ├── menus/raw_menus.txt
│   ├── cache/    (symlink para SD se disponível)
│   └── materials/
└── logs/
```
