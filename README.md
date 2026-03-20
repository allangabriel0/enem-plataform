# ENEM Study Platform v2

Plataforma web de estudos para o ENEM que organiza vídeos e materiais de canais do Telegram. Roda localmente em um Galaxy S8 (ARM64, Termux) e é acessível de qualquer lugar via Tailscale — sem mensalidade de nuvem, sem latência de proxy.

O sistema faz streaming direto do Telegram com cache agressivo no SD card: o primeiro acesso baixa o vídeo em background; a partir do segundo, reprodução instantânea. Suporta tracking de progresso por vídeo, anotações com timestamp clicável, download de materiais (PDF/ZIP) e cronograma de estudos com calendário mensal.

---

## Features

- **Player com progresso** — retoma de onde parou, barra de progresso por seção e curso
- **Cache LRU em dois níveis** — SD card (primário) + armazenamento interno (fallback), evicção automática
- **Streaming do Telegram** — suporte a Range headers, compatível com seek no player
- **Anotações com timestamp** — clique no timestamp para pular para aquele momento
- **Hierarquia Canal → Curso → Seção** — parseada das tags `#F001` dos canais do Telegram
- **Materiais de estudo** — download de PDF, ZIP, RAR diretamente do Telegram
- **Cronograma** — calendário mensal com criação/edição de itens por AJAX, status pendente/concluído
- **Sincronização** — botão "Sincronizar Telegram" no dashboard faz upsert de todos os canais
- **Busca e filtros** — por matéria, grupo e título
- **Acesso remoto** — via Tailscale (WireGuard mesh, sem relay quando na mesma rede)
- **Watchdog automático** — crontab reinicia o app se o health check falhar
- **CLI de manutenção** — `status`, `precache`, `cleanup` via `python -m app.cli`

---

## Quick Start (desenvolvimento no PC)

**Requisitos:** Python 3.11+, Git

```bash
git clone <repo> enem-v2
cd enem-v2

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt

cp .env.example .env              # edite com suas credenciais do Telegram

python -c "from app.database import init_db; init_db()"
python scripts/create_users.py

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse: [http://localhost:8000](http://localhost:8000)

> **Nota:** o streaming de vídeo requer autenticação real no Telegram. Para desenvolvimento, o resto da interface (dashboard, player, schedule, notas) funciona sem conexão com o Telegram.

### Testes

```bash
pytest tests/ -v                  # todos os testes
pytest tests/test_menu_parser.py  # teste específico
ruff check app/ tests/            # lint
```

---

## Deploy no Galaxy S8 (Termux)

### Pré-requisitos

- Termux instalado via **F-Droid** (não pela Play Store — versão desatualizada)
- Termux:Boot e Termux:API instalados via F-Droid
- Root com Magisk (necessário para Tailscale)

### Setup inicial

```bash
# No Termux do S8 — tudo em 3 comandos:
pkg install git -y
git clone https://github.com/allangabriel0/enem-plataform.git ~/enem-platform
bash ~/enem-platform/scripts/setup_termux.sh
```

O `setup_termux.sh` faz automaticamente:
- `pkg install` de todas as dependências (python, openssh, rust, cronie, etc.)
- Cria o venv e instala os pacotes Python
- Detecta o SD card e configura o caminho no `.env`
- Cria os diretórios `logs/`, `data/menus/`, `data/cache/`, `data/materials/`
- Inicializa o banco SQLite
- Registra o watchdog no crontab (`*/5 * * * *`)

### Configuração pós-setup

```bash
cd ~/enem-platform

# 1. Edite o .env com suas credenciais
cp .env.example .env
nano .env

# 2. Crie os usuários (lê USER1_* e USER2_* do .env)
source venv/bin/activate
python scripts/create_users.py

# 3. Autentique no Telegram (só uma vez — salva sessão em data/telegram.session)
#    Lista os grupos disponíveis e atualiza TELEGRAM_GROUP_IDS no .env
python scripts/setup_telegram.py

# 4. Inicie o app
bash scripts/start.sh

# 5. Sincronize os vídeos
curl -X POST http://localhost:8000/api/sync-videos
```

> **Atualizar o app no futuro:**
> ```bash
> cd ~/enem-platform
> git pull
> source venv/bin/activate && pip install -r requirements.txt
> bash scripts/stop.sh && bash scripts/start.sh
> ```

### Boot automático

O arquivo `.termux/boot/start-enem` é executado automaticamente pelo **Termux:Boot** ao ligar o S8. Ele:
1. Ativa o wake lock (impede suspensão pelo Android)
2. Aguarda 10s para o sistema carregar
3. Inicia `sshd`, `crond` e o app

Não requer nenhuma configuração adicional — o Termux:Boot executa tudo no diretório `~/.termux/boot/` automaticamente.

---

## Configuração do Tailscale

O Tailscale cria uma rede mesh WireGuard entre seus dispositivos. Na mesma rede Wi-Fi, o tráfego vai direto S8 → dispositivo sem sair para a internet.

### No S8 (servidor)

Requer o módulo **[Magisk-Tailscaled](https://github.com/popsteve/magisk-tailscaled)** instalado via Magisk Manager. Ele roda o `tailscaled` com userspace-networking, coexistindo com o Cloudflare WARP.

```bash
# Após instalar o módulo Magisk, no Termux:
tailscale up --authkey=<sua-authkey>   # authkey gerada em tailscale.com/settings/keys

# Verifica IP atribuído
tailscale ip -4
# Exemplo: 100.90.x.x
```

O WARP fica sempre ligado no S8 para garantir acesso rápido aos servidores do Telegram (ISPs brasileiros fazem traffic shaping nos IPs do Telegram).

### Nos outros dispositivos (clientes)

Instale o app Tailscale e faça login na mesma conta:

| Plataforma | Download |
|---|---|
| Android | Play Store / F-Droid |
| iOS | App Store |
| Windows | [tailscale.com/download](https://tailscale.com/download) |
| macOS | App Store / Homebrew |
| Linux | `curl -fsSL https://tailscale.com/install.sh | sh` |

### Endereços de acesso

| Rede | Endereço |
|---|---|
| Wi-Fi local | `http://192.168.100.127:8000` |
| Tailscale (remoto) | `http://<IP-tailscale>:8000` |

```bash
# Descobrir o IP Tailscale do S8 (rode no Termux):
tailscale ip -4
```

---

## Comandos úteis

### App

```bash
bash scripts/start.sh             # inicia o app (com health check)
bash scripts/stop.sh              # para o app
bash scripts/status.sh            # painel: app, Tailscale, disco, cache, erros
```

### Sincronização e cache

```bash
# Sincroniza vídeos e materiais do Telegram
curl -X POST http://localhost:8000/api/sync-videos

# Status do banco e cache
python -m app.cli status

# Pré-cacheia um curso inteiro
python -m app.cli precache --course "Filosofia"
python -m app.cli precache --all --yes     # toda a biblioteca (lento)

# Remove vídeos antigos do cache (LRU)
python -m app.cli cleanup
python -m app.cli cleanup --max-gb 30     # com limite customizado
```

### Manutenção

```bash
bash scripts/backup.sh            # backup do banco para o SD card
bash scripts/watchdog.sh          # health check manual (normalmente via crontab)

# Ver logs
tail -f logs/app.log              # log principal do app
tail -f logs/watchdog.log         # restarts automáticos
tail -f logs/backup.log           # histórico de backups
```

### SSH no S8

```bash
# Do PC ou celular (na mesma rede ou via Tailscale):
ssh -p 8022 <usuario>@192.168.100.127       # rede local
ssh -p 8022 <usuario>@<ip-tailscale>        # remoto
```

---

## Estrutura do projeto

```
enem-v2/
├── app/
│   ├── main.py              # FastAPI app, lifespan, exception handlers
│   ├── config.py            # Pydantic BaseSettings (.env)
│   ├── database.py          # SQLite WAL + pragmas
│   ├── models.py            # User, Video, Material, WatchProgress, Note, ScheduleItem
│   ├── auth.py              # JWT (cookie httponly) + bcrypt
│   ├── cache_manager.py     # Cache LRU dois níveis (SD + interno)
│   ├── telegram_client.py   # Telethon: fetch, stream, download
│   ├── menu_parser.py       # Tags #F001 → Canal → Curso → Seção
│   ├── cli.py               # CLI: status, precache, cleanup
│   ├── routers/
│   │   ├── auth_routes.py   # GET/POST /login, /logout
│   │   ├── dashboard.py     # GET / (dashboard)
│   │   ├── player.py        # GET /watch/{id}
│   │   ├── streaming.py     # GET /stream/{id} (Range headers)
│   │   ├── sync.py          # POST /api/sync-videos
│   │   ├── progress.py      # POST/GET /api/progress
│   │   ├── notes.py         # CRUD /api/notes
│   │   ├── schedule.py      # CRUD /api/schedule + GET /schedule
│   │   └── materials.py     # GET /download/material/{id}
│   ├── templates/           # Jinja2 (base, login, dashboard, player, schedule)
│   ├── static/
│   │   ├── css/style.css    # Dark theme completo
│   │   └── js/app.js        # Sidebar, toasts, collapsible sections
│   └── utils/
│       ├── text.py          # Normalização de títulos
│       └── logging.py       # RotatingFileHandler (5MB × 3)
├── tests/                   # pytest, SQLite em memória
├── scripts/
│   ├── setup_termux.sh      # Setup completo no S8
│   ├── start.sh             # Inicia com health check
│   ├── stop.sh              # Para com SIGTERM/SIGKILL
│   ├── status.sh            # Painel de status
│   ├── backup.sh            # Backup do banco para SD
│   ├── watchdog.sh          # Health check para crontab
│   ├── create_users.py      # Cria usuários a partir do .env
│   └── setup_telegram.py    # Autenticação Telethon (salva sessão)
├── .termux/boot/
│   └── start-enem           # Boot automático via Termux:Boot
├── data/
│   ├── menus/raw_menus.txt  # Hierarquia de cursos (tags → Canal/Curso/Seção)
│   ├── cache/               # Cache interno (fallback)
│   └── materials/           # Materiais baixados do Telegram
├── logs/                    # app.log, boot.log, watchdog.log, backup.log
├── .env.example             # Template de configuração
├── requirements.txt         # Dependências de produção
├── requirements-dev.txt     # pytest, httpx, ruff
├── CLAUDE.md                # Instruções para Claude Code
└── SPEC.md                  # Especificação técnica completa
```

---

## Troubleshooting

### Termux fecha os processos em background

O Android mata processos em background agressivamente. Soluções:

1. **Desative a otimização de bateria para o Termux** — Configurações → Apps → Termux → Bateria → "Sem restrições"
2. **Instale o Termux:Boot** e use o `.termux/boot/start-enem` para `termux-wake-lock`
3. **Modo de alta performance** no gerenciador de bateria do S8

### SSH não conecta

```bash
# Verifica se sshd está rodando
pgrep sshd && echo "ok" || sshd

# Porta padrão do Termux é 8022, não 22
ssh -p 8022 usuario@192.168.100.127

# Se estiver fora da rede local, use o IP Tailscale
ssh -p 8022 usuario@$(tailscale ip -4)
```

### Vídeo trava / lento

O gargalo principal é o streaming em tempo real do Telegram. Soluções em ordem:

1. **Pré-cacheia o vídeo** — `python -m app.cli precache --course "Nome"` — depois da segunda visualização é instantâneo
2. **Verifica o WARP** — garante que o WARP está ativo no S8 para o acesso ao Telegram não ser throttled
3. **Verifica a rede** — na mesma rede Wi-Fi o tráfego não passa pelo Tailscale relay; fora da rede passa pela nuvem da Tailscale
4. **Verifica o cache disponível** — `python -m app.cli status` mostra se há espaço no SD

### Cache cheio

```bash
# Ver uso atual
python -m app.cli status

# Evicção LRU (remove os menos assistidos)
python -m app.cli cleanup

# Com limite menor que o .env
python -m app.cli cleanup --max-gb 30
```

### App não inicia após atualização

```bash
cd ~/enem-platform
git pull
bash scripts/stop.sh
source venv/bin/activate
pip install -r requirements.txt
python -c "from app.database import init_db; init_db()"
bash scripts/start.sh
```

### Telegram: FloodWait / sessão expirada

```bash
# Reautentica (gera nova sessão)
source venv/bin/activate
python scripts/setup_telegram.py

# Se der FloodWait, aguarde o tempo indicado e tente novamente
# A sessão fica salva em data/telegram.session — não delete sem necessidade
```

### Tailscale não conecta após reboot do S8

O módulo Magisk-Tailscaled inicia automaticamente com o boot. Se não estiver funcionando:

```bash
# Verifica status
tailscale status

# Reconecta
tailscale up

# Se o módulo Magisk não estiver ativo, reative pelo Magisk Manager e reinicie
```

### Espaço insuficiente no interno

Mova o cache para o SD card editando o `.env`:

```bash
# Descobre o UUID do SD
ls /storage/

# Edita o .env
nano ~/enem-platform/.env
# SD_CARD_PATH=/storage/<UUID>

# Reinicia o app
bash scripts/stop.sh && bash scripts/start.sh
```

---

## Variáveis de ambiente (.env)

Copie `.env.example` para `.env` e preencha:

```env
# Segurança
SECRET_KEY=troque-por-string-aleatoria-longa

# Banco
DATABASE_URL=sqlite:///./data/enem.db

# Cache
CACHE_DIR=data/cache
CACHE_MAX_GB=50
SD_CARD_PATH=/storage/xxxx-xxxx      # UUID do SD card (deixe vazio se não tiver)

# Telegram (obtenha em my.telegram.org)
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
TELEGRAM_PHONE=+5511999999999
TELEGRAM_GROUP_IDS=-1001234567890,-1009876543210   # IDs dos canais (CSV)
TELEGRAM_FETCH_LIMIT=3000

# Arquivo de hierarquia de cursos
MENU_FILE=data/menus/raw_menus.txt

# Usuários
USER1_NAME=Maria
USER1_EMAIL=maria@email.com
USER1_PASSWORD=senha-segura-aqui
USER2_NAME=João
USER2_EMAIL=joao@email.com
USER2_PASSWORD=outra-senha-segura
```

---

## Stack

| Componente | Tecnologia | Versão |
|---|---|---|
| Framework | FastAPI | 0.115.6 |
| Server | Uvicorn (sem uvloop) | 0.30.6 |
| ORM | SQLAlchemy | 2.0.35 |
| Database | SQLite (WAL mode) | — |
| Telegram | Telethon + cryptg | 1.37.0 |
| Auth | python-jose + passlib/bcrypt | — |
| Config | pydantic-settings | 2.7.1 |
| Templates | Jinja2 | 3.1.4 |
| Testes | pytest + httpx | — |
| Rede | Tailscale (WireGuard mesh) | — |
