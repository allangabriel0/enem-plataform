#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# watchdog.sh — Health check para crontab (*/5 * * * *)
# Reinicia o app automaticamente se não responder
# =============================================================================
# Adicionar ao crontab:
#   */5 * * * * bash ~/enem-platform/scripts/watchdog.sh >> ~/enem-platform/logs/watchdog.log 2>&1

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$APP_DIR/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
PORT="${PORT:-8000}"
HEALTH_URL="http://127.0.0.1:$PORT/health"
MAX_RESTARTS=3
RESTART_TRACKER="$APP_DIR/.watchdog_restarts"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(ts)] $*"; }

# Controle de restart em loop (evita reinicialização infinita)
# Reseta o contador a cada hora
CURRENT_HOUR=$(date '+%Y%m%d%H')
if [ -f "$RESTART_TRACKER" ]; then
    read -r saved_hour saved_count < "$RESTART_TRACKER" 2>/dev/null || { saved_hour=""; saved_count=0; }
    if [ "$saved_hour" != "$CURRENT_HOUR" ]; then
        saved_count=0
    fi
else
    saved_hour=""
    saved_count=0
fi

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------
if curl -sf --max-time 5 "$HEALTH_URL" -o /dev/null 2>/dev/null; then
    # App OK — sem log para não poluir (só loga se houve restart anterior)
    if [ "$saved_count" -gt 0 ]; then
        log "OK — app respondeu (após $saved_count restart(s) nesta hora)"
    fi
    exit 0
fi

# -----------------------------------------------------------------------------
# App não respondeu
# -----------------------------------------------------------------------------
log "AVISO: health check falhou em $HEALTH_URL"

if [ "$saved_count" -ge "$MAX_RESTARTS" ]; then
    log "ERRO: limite de $MAX_RESTARTS restarts/hora atingido — não reiniciando"
    log "       Verifique manualmente: tail -50 $LOG_DIR/app.log"
    exit 1
fi

# -----------------------------------------------------------------------------
# Reinicia
# -----------------------------------------------------------------------------
new_count=$((saved_count + 1))
echo "$CURRENT_HOUR $new_count" > "$RESTART_TRACKER"

log "Reiniciando app (tentativa $new_count/$MAX_RESTARTS nesta hora)..."

bash "$APP_DIR/scripts/start.sh" >> "$LOG_DIR/app.log" 2>&1

# Aguarda e verifica
sleep 5
if curl -sf --max-time 5 "$HEALTH_URL" -o /dev/null 2>/dev/null; then
    log "OK — app reiniciado com sucesso"
else
    log "ERRO — app não respondeu após reinicialização"
fi
