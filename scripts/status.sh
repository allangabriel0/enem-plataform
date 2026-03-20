#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# status.sh — Painel de status da plataforma ENEM
# =============================================================================
set -uo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="$APP_DIR/logs"
PORT="${PORT:-8000}"
HEALTH_URL="http://127.0.0.1:$PORT/health"
DB_FILE="$APP_DIR/data/enem.db"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
warn() { echo -e "  ${YELLOW}●${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; }
sep()  { echo -e "${CYAN}─────────────────────────────────────────${NC}"; }

echo
echo -e "${BOLD}  ENEM Study Platform — Status  $(date '+%d/%m/%Y %H:%M:%S')${NC}"
sep

# -----------------------------------------------------------------------------
# 1. App
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}  App${NC}"
if curl -sf "$HEALTH_URL" -o /dev/null 2>/dev/null; then
    PID=$(pgrep -f "uvicorn app.main:app" | head -1 || echo "?")
    ok "Rodando   PID $PID   http://127.0.0.1:$PORT"
else
    fail "Não está rodando"
fi

# -----------------------------------------------------------------------------
# 2. Tailscale
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}  Tailscale${NC}"
if command -v tailscale &>/dev/null; then
    TS_IP=$(tailscale ip -4 2>/dev/null || true)
    if [ -n "$TS_IP" ]; then
        ok "Conectado   $TS_IP"
        ok "URL remota  http://$TS_IP:$PORT"
    else
        fail "Não conectado (tailscale up?)"
    fi
else
    warn "tailscale não encontrado"
fi

# -----------------------------------------------------------------------------
# 3. Espaço em disco
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}  Disco${NC}"

# Interno (Termux home)
if df "$APP_DIR" &>/dev/null; then
    read -r _ total_kb used_kb free_kb _ <<< "$(df -k "$APP_DIR" | tail -1)"
    total_gb=$(awk "BEGIN{printf \"%.1f\", $total_kb/1048576}")
    free_gb=$(awk "BEGIN{printf \"%.1f\", $free_kb/1048576}")
    used_pct=$(awk "BEGIN{printf \"%.0f\", $used_kb/$total_kb*100}")
    ok "Interno   ${used_pct}% usado   ${free_gb} GB livre de ${total_gb} GB"
fi

# SD card
for sd in /storage/*/; do
    [[ "$sd" == *emulated* ]] && continue
    [ -d "$sd" ] || continue
    if df "$sd" &>/dev/null; then
        read -r _ sd_total sd_used sd_free _ <<< "$(df -k "$sd" | tail -1)"
        sd_total_gb=$(awk "BEGIN{printf \"%.1f\", $sd_total/1048576}")
        sd_free_gb=$(awk "BEGIN{printf \"%.1f\", $sd_free/1048576}")
        sd_pct=$(awk "BEGIN{printf \"%.0f\", $sd_used/$sd_total*100}")
        ok "SD card   ${sd_pct}% usado   ${sd_free_gb} GB livre de ${sd_total_gb} GB   (${sd%/})"
    fi
done

# -----------------------------------------------------------------------------
# 4. Cache de vídeos
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}  Cache${NC}"

CACHE_DIRS=()
# Tenta SD primeiro
for sd in /storage/*/enem-cache/videos; do
    [[ "$sd" == *emulated* ]] && continue
    [ -d "$sd" ] && CACHE_DIRS+=("$sd (SD)")
done
[ -d "$APP_DIR/data/cache" ] && CACHE_DIRS+=("$APP_DIR/data/cache (interno)")

if [ ${#CACHE_DIRS[@]} -eq 0 ]; then
    warn "Nenhum diretório de cache encontrado"
else
    for entry in "${CACHE_DIRS[@]}"; do
        dir="${entry% (*}"
        label="${entry##* (}"; label="${label%)}"
        if [ -d "$dir" ]; then
            count=$(find "$dir" -name "*.mp4" 2>/dev/null | wc -l)
            if [ "$count" -gt 0 ]; then
                size_kb=$(du -sk "$dir" 2>/dev/null | cut -f1)
                size_gb=$(awk "BEGIN{printf \"%.2f\", $size_kb/1048576}")
                ok "$label   $count arquivo(s)   ${size_gb} GB"
            else
                warn "$label   vazio"
            fi
        fi
    done
fi

# -----------------------------------------------------------------------------
# 5. Banco de dados
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}  Banco de dados${NC}"
if [ -f "$DB_FILE" ]; then
    db_size=$(du -sh "$DB_FILE" 2>/dev/null | cut -f1)
    if command -v sqlite3 &>/dev/null; then
        videos=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM videos;" 2>/dev/null || echo "?")
        cached=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM videos WHERE cached_at IS NOT NULL;" 2>/dev/null || echo "?")
        materials=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM materials;" 2>/dev/null || echo "?")
        ok "Tamanho    $db_size"
        ok "Vídeos     $videos total, $cached cacheados"
        ok "Materiais  $materials"
    else
        ok "Tamanho $db_size (instale sqlite3 para detalhes)"
    fi
else
    fail "Banco não encontrado: $DB_FILE"
fi

# -----------------------------------------------------------------------------
# 6. Últimos 3 erros do log
# -----------------------------------------------------------------------------
echo -e "\n${BOLD}  Últimos erros (app.log)${NC}"
APP_LOG="$LOG_DIR/app.log"
if [ -f "$APP_LOG" ]; then
    ERRORS=$(grep -i "error\|exception\|traceback" "$APP_LOG" 2>/dev/null | tail -3 || true)
    if [ -n "$ERRORS" ]; then
        while IFS= read -r line; do
            fail "$line"
        done <<< "$ERRORS"
    else
        ok "Nenhum erro recente"
    fi
else
    warn "app.log não encontrado"
fi

sep
echo
