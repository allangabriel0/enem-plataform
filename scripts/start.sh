#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# start.sh — Inicia a plataforma ENEM
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="$APP_DIR/logs"
BOOT_LOG="$LOG_DIR/boot.log"
PID_FILE="$APP_DIR/enem.pid"
HOST="0.0.0.0"
PORT="8000"
HEALTH_URL="http://127.0.0.1:$PORT/health"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }

mkdir -p "$LOG_DIR"

log() {
    local ts; ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" | tee -a "$BOOT_LOG"
}

cd "$APP_DIR"

# -----------------------------------------------------------------------------
# 1. Valida configuração
# -----------------------------------------------------------------------------
info "Validando configuração..."
if ! "$VENV_DIR/bin/python" -c "from app.config import settings" 2>>"$BOOT_LOG"; then
    error "Configuração inválida — verifique o .env"
    log "ERRO: configuração inválida"
    exit 1
fi
info "Configuração OK"

# -----------------------------------------------------------------------------
# 2. Mata instância anterior
# -----------------------------------------------------------------------------
if pkill -0 -f "uvicorn app.main:app" 2>/dev/null; then
    warn "Instância anterior encontrada — encerrando..."
    pkill -TERM -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 2
    # Força kill se ainda estiver rodando
    pkill -KILL -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 1
    info "Instância anterior encerrada"
fi

# -----------------------------------------------------------------------------
# 3. Inicia uvicorn
# -----------------------------------------------------------------------------
info "Iniciando uvicorn em $HOST:$PORT..."
log "Iniciando uvicorn em $HOST:$PORT"

nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers 1 \
    --loop asyncio \
    >> "$LOG_DIR/app.log" 2>&1 &

APP_PID=$!
echo "$APP_PID" > "$PID_FILE"
log "PID: $APP_PID"

# -----------------------------------------------------------------------------
# 4. Aguarda e verifica /health
# -----------------------------------------------------------------------------
info "Aguardando inicialização (3s)..."
sleep 3

MAX_TRIES=5
for i in $(seq 1 $MAX_TRIES); do
    if curl -sf "$HEALTH_URL" -o /dev/null 2>/dev/null; then
        info "Health check OK — app rodando (PID $APP_PID)"
        log "OK — PID $APP_PID — http://$HOST:$PORT"
        echo
        echo "  Dashboard: http://192.168.100.127:$PORT"
        echo "  Tailscale: http://\$(tailscale ip -4 2>/dev/null || echo '<ip-tailscale>'):$PORT"
        echo "  PID:       $APP_PID"
        echo "  Logs:      $LOG_DIR/app.log"
        echo
        exit 0
    fi
    warn "Tentativa $i/$MAX_TRIES — aguardando..."
    sleep 2
done

error "App não respondeu ao health check após ${MAX_TRIES} tentativas"
log "ERRO: health check falhou após ${MAX_TRIES} tentativas"
error "Veja os logs: $LOG_DIR/app.log"
tail -20 "$LOG_DIR/app.log" >&2
exit 1
