#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# setup_termux.sh — Setup completo da plataforma ENEM no Termux/S8
# =============================================================================
set -euo pipefail

REPO_URL="https://github.com/allangabriel0/enem-plataform.git"
APP_DIR="$HOME/enem-platform"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="$APP_DIR/logs"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*" >&2; }
section() { echo; echo -e "${GREEN}═══${NC} $* ${GREEN}═══${NC}"; }

# -----------------------------------------------------------------------------
# 1. Pacotes do sistema
# -----------------------------------------------------------------------------
section "Atualizando pacotes"
pkg update -y
pkg upgrade -y

section "Instalando dependências"
pkg install -y \
    python \
    git \
    openssh \
    build-essential \
    libffi \
    openssl \
    rust \
    cronie \
    termux-api \
    proot

# Garante pip atualizado
pip install --upgrade pip setuptools wheel

# -----------------------------------------------------------------------------
# 2. Clone ou pull do repositório
# -----------------------------------------------------------------------------
section "Repositório"
if [ -d "$APP_DIR/.git" ]; then
    info "Repositório já existe — fazendo git pull"
    git -C "$APP_DIR" pull --ff-only
else
    info "Clonando repositório em $APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"

# -----------------------------------------------------------------------------
# 3. Ambiente virtual Python
# -----------------------------------------------------------------------------
section "Ambiente virtual"
if [ ! -d "$VENV_DIR" ]; then
    info "Criando venv em $VENV_DIR"
    python -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

# Necessário para compilar pacotes Rust (pydantic-core, cryptg) no Termux ARM64
export ANDROID_API_LEVEL=24
export MATHLIB="m"

info "Instalando dependências Python"
pip install --upgrade pip

# pydantic-core não tem wheel oficial para Android ARM64 no PyPI.
# Usa índice alternativo com wheels pré-compilados para android_24_arm64_v8a.
# Fonte: https://github.com/Eutalix/android-pydantic-core
pip install pydantic-core \
    --extra-index-url https://eutalix.github.io/android-pydantic-core/

pip install -r requirements.txt \
    --extra-index-url https://eutalix.github.io/android-pydantic-core/

# Verifica cryptg (aceleração C para Telethon)
if python -c "import cryptg" 2>/dev/null; then
    info "cryptg: OK (aceleração nativa ativa)"
else
    warn "cryptg não disponível — tentando compilar..."
    pip install cryptg || warn "cryptg falhou — Telethon funciona sem ele, mas mais lento"
fi

deactivate

# -----------------------------------------------------------------------------
# 4. Diretórios da aplicação
# -----------------------------------------------------------------------------
section "Diretórios"
mkdir -p "$LOG_DIR"
mkdir -p "$APP_DIR/data/menus"
mkdir -p "$APP_DIR/data/materials"
mkdir -p "$APP_DIR/data/cache"
info "Diretórios criados"

# -----------------------------------------------------------------------------
# 5. SD card — detectar e criar symlink de cache
# -----------------------------------------------------------------------------
section "SD card"
SD_MOUNT=""
# Termux expõe o SD em /storage/<UUID-do-cartao>
for candidate in /storage/*/; do
    # Ignora emulated (armazenamento interno)
    if [[ "$candidate" != *emulated* ]] && [ -d "$candidate" ]; then
        SD_MOUNT="${candidate%/}"
        break
    fi
done

if [ -n "$SD_MOUNT" ]; then
    info "SD card detectado em: $SD_MOUNT"
    SD_CACHE="$SD_MOUNT/enem-cache/videos"
    mkdir -p "$SD_CACHE"
    info "Cache no SD: $SD_CACHE"

    # Grava o caminho no .env se ainda não estiver lá
    ENV_FILE="$APP_DIR/.env"
    if [ -f "$ENV_FILE" ]; then
        if grep -q "^SD_CARD_PATH=" "$ENV_FILE"; then
            sed -i "s|^SD_CARD_PATH=.*|SD_CARD_PATH=$SD_MOUNT|" "$ENV_FILE"
            info ".env: SD_CARD_PATH atualizado"
        else
            echo "SD_CARD_PATH=$SD_MOUNT" >> "$ENV_FILE"
            info ".env: SD_CARD_PATH adicionado"
        fi
    else
        warn ".env não encontrado — SD_CARD_PATH não configurado automaticamente"
        warn "Adicione manualmente: SD_CARD_PATH=$SD_MOUNT"
    fi
else
    warn "SD card não detectado — cache usará armazenamento interno ($APP_DIR/data/cache)"
    warn "Se inserir o SD depois, rode: bash scripts/setup_termux.sh novamente"
fi

# -----------------------------------------------------------------------------
# 6. Permissão de armazenamento (Termux:API)
# -----------------------------------------------------------------------------
section "Permissões"
if command -v termux-setup-storage &>/dev/null; then
    info "Solicitando acesso ao armazenamento externo..."
    termux-setup-storage || warn "termux-setup-storage falhou — faça manualmente nas configurações"
else
    warn "termux-setup-storage não encontrado — instale o app Termux:API da F-Droid"
fi

# -----------------------------------------------------------------------------
# 7. .env de exemplo
# -----------------------------------------------------------------------------
section "Configuração"
ENV_FILE="$APP_DIR/.env"
EXAMPLE_FILE="$APP_DIR/.env.example"

if [ ! -f "$ENV_FILE" ] && [ -f "$EXAMPLE_FILE" ]; then
    cp "$EXAMPLE_FILE" "$ENV_FILE"
    warn ".env criado a partir do .env.example — edite com suas credenciais do Telegram"
elif [ ! -f "$ENV_FILE" ]; then
    warn ".env não encontrado e .env.example ausente — crie manualmente"
fi

# -----------------------------------------------------------------------------
# 8. Banco de dados
# -----------------------------------------------------------------------------
section "Banco de dados"
source "$VENV_DIR/bin/activate"
python -c "from app.database import init_db; init_db()" && info "Banco inicializado"
deactivate

# -----------------------------------------------------------------------------
# 9. Crontab para watchdog
# -----------------------------------------------------------------------------
section "Crontab (watchdog)"
CRON_JOB="*/5 * * * * bash $APP_DIR/scripts/watchdog.sh >> $LOG_DIR/watchdog.log 2>&1"
CURRENT_CRON=$(crontab -l 2>/dev/null || true)
if echo "$CURRENT_CRON" | grep -qF "watchdog.sh"; then
    info "Crontab: watchdog já registrado"
else
    (echo "$CURRENT_CRON"; echo "$CRON_JOB") | crontab -
    info "Crontab: watchdog adicionado (a cada 5 minutos)"
fi

# Ativa crond se não estiver rodando
if ! pgrep -x crond &>/dev/null; then
    crond || warn "crond não pôde ser iniciado — inicie manualmente com: crond"
fi

# Permissões de execução
chmod +x "$APP_DIR"/scripts/*.sh 2>/dev/null || true
chmod +x "$APP_DIR/.termux/boot/"* 2>/dev/null || true

# -----------------------------------------------------------------------------
# 10. Próximos passos
# -----------------------------------------------------------------------------
section "Setup concluído"
echo
echo "  Próximos passos:"
echo
echo "  1. Edite o arquivo .env com suas credenciais:"
echo "       nano $APP_DIR/.env"
echo
echo "  2. Crie os usuários da plataforma:"
echo "       cd $APP_DIR && source venv/bin/activate"
echo "       python scripts/create_users.py"
echo
echo "  3. Autentique o Telegram (só precisa fazer uma vez, no S8):"
echo "       python scripts/setup_telegram.py"
echo
echo "  4. Inicie a plataforma:"
echo "       bash scripts/start.sh"
echo
echo "  5. Sincronize os vídeos:"
echo "       curl -X POST http://localhost:8000/api/sync-videos"
echo
echo "  Tailscale (acesso remoto):"
echo "    - Instale o módulo Magisk-Tailscaled"
echo "    - Execute: tailscale up --authkey=<sua-chave>"
echo
