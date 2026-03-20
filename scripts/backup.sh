#!/data/data/com.termux/files/usr/bin/bash
# =============================================================================
# backup.sh — Backup do banco de dados para o SD card
# =============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$APP_DIR/logs"
DB_FILE="$APP_DIR/data/enem.db"
BACKUP_LOG="$LOG_DIR/backup.log"
KEEP_DAYS=7

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*" >&2; }

mkdir -p "$LOG_DIR"

log() {
    local ts; ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" | tee -a "$BACKUP_LOG"
}

# -----------------------------------------------------------------------------
# Valida banco de dados
# -----------------------------------------------------------------------------
if [ ! -f "$DB_FILE" ]; then
    error "Banco não encontrado: $DB_FILE"
    log "ERRO: banco não encontrado"
    exit 1
fi

# -----------------------------------------------------------------------------
# Detecta SD card
# -----------------------------------------------------------------------------
SD_BACKUP_DIR=""
for sd in /storage/*/; do
    [[ "$sd" == *emulated* ]] && continue
    if [ -d "$sd" ]; then
        SD_BACKUP_DIR="${sd%/}/enem-backups"
        break
    fi
done

if [ -z "$SD_BACKUP_DIR" ]; then
    warn "SD card não detectado — usando backup local em $APP_DIR/data/backups"
    SD_BACKUP_DIR="$APP_DIR/data/backups"
fi

mkdir -p "$SD_BACKUP_DIR"

# -----------------------------------------------------------------------------
# Cria backup com timestamp
# -----------------------------------------------------------------------------
TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
BACKUP_FILE="$SD_BACKUP_DIR/enem_${TIMESTAMP}.db"

log "Iniciando backup: $DB_FILE → $BACKUP_FILE"

# Usa sqlite3 .backup para backup quente (seguro com WAL mode)
if command -v sqlite3 &>/dev/null; then
    sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"
else
    # Fallback: cópia direta (segura se app estiver parado)
    cp "$DB_FILE" "$BACKUP_FILE"
fi

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
log "Backup criado: $BACKUP_FILE ($BACKUP_SIZE)"
info "Backup criado: $BACKUP_FILE ($BACKUP_SIZE)"

# -----------------------------------------------------------------------------
# Remove backups com mais de KEEP_DAYS dias
# -----------------------------------------------------------------------------
log "Removendo backups com mais de $KEEP_DAYS dias..."
REMOVED=0
while IFS= read -r old_file; do
    rm -f "$old_file"
    log "Removido: $old_file"
    REMOVED=$((REMOVED + 1))
done < <(find "$SD_BACKUP_DIR" -name "enem_*.db" -mtime "+$KEEP_DAYS" 2>/dev/null || true)

if [ "$REMOVED" -gt 0 ]; then
    info "$REMOVED backup(s) antigo(s) removido(s)"
else
    info "Nenhum backup antigo para remover"
fi

# -----------------------------------------------------------------------------
# Lista backups existentes
# -----------------------------------------------------------------------------
TOTAL=$(find "$SD_BACKUP_DIR" -name "enem_*.db" 2>/dev/null | wc -l)
log "Backups armazenados: $TOTAL"
info "Backups armazenados em $SD_BACKUP_DIR: $TOTAL"
