#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# stop.sh — Para a plataforma ENEM
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$APP_DIR/enem.pid"
LOG_DIR="$APP_DIR/logs"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }

log() {
    local ts; ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" >> "$LOG_DIR/boot.log" 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# Verifica se está rodando
# -----------------------------------------------------------------------------
if ! pkill -0 -f "uvicorn app.main:app" 2>/dev/null; then
    warn "App não está rodando"
    rm -f "$PID_FILE"
    exit 0
fi

# -----------------------------------------------------------------------------
# SIGTERM — permite finalizar conexões em andamento
# -----------------------------------------------------------------------------
info "Enviando SIGTERM..."
pkill -TERM -f "uvicorn app.main:app" 2>/dev/null || true
log "SIGTERM enviado"

# Aguarda até 8s para encerramento limpo
for i in $(seq 1 8); do
    sleep 1
    if ! pkill -0 -f "uvicorn app.main:app" 2>/dev/null; then
        info "App encerrado (${i}s)"
        log "App encerrado"
        rm -f "$PID_FILE"
        exit 0
    fi
done

# -----------------------------------------------------------------------------
# SIGKILL — força se não encerrou
# -----------------------------------------------------------------------------
warn "App não encerrou após 8s — forçando SIGKILL..."
pkill -KILL -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

if pkill -0 -f "uvicorn app.main:app" 2>/dev/null; then
    error "Não foi possível encerrar o processo"
    log "ERRO: SIGKILL falhou"
    exit 1
fi

rm -f "$PID_FILE"
info "App encerrado forçadamente"
log "App encerrado via SIGKILL"
