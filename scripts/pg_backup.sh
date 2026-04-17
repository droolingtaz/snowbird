#!/usr/bin/env bash
# scripts/pg_backup.sh — nightly local Postgres backup for Snowbird
# Intended to be run via the snowbird-backup.service systemd unit.
set -euo pipefail

# ── configuration ────────────────────────────────────────────────────────────
COMPOSE_FILE="/opt/snowbird/docker-compose.prod.yml"
BACKUP_DIR="/var/backups/snowbird"
LOG_FILE="/var/log/snowbird-backup.log"
RETENTION_DAYS=14
DB_USER="snowbird"
DB_NAME="snowbird"
BACKUP_OWNER="bparker"
# ─────────────────────────────────────────────────────────────────────────────

TIMESTAMP=$(date +"%Y-%m-%d-%H%M")
BACKUP_FILE="${BACKUP_DIR}/snowbird-${TIMESTAMP}.sql.gz"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Snowbird backup started ==="

# Ensure backup directory exists with tight permissions
if [[ ! -d "$BACKUP_DIR" ]]; then
    log "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR"
    chmod 700 "$BACKUP_DIR"
    chown "${BACKUP_OWNER}:" "$BACKUP_DIR"
fi

# Run pg_dump and pipe through gzip
log "Dumping database '${DB_NAME}' to ${BACKUP_FILE} ..."
set +e
docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$BACKUP_FILE"
PG_EXIT=${PIPESTATUS[0]}
GZIP_EXIT=${PIPESTATUS[1]}
set -e

if [[ $PG_EXIT -ne 0 ]]; then
    log "ERROR: pg_dump exited with code ${PG_EXIT}. Removing incomplete file."
    rm -f "$BACKUP_FILE"
    log "=== Backup FAILED (exit ${PG_EXIT}) ==="
    exit "$PG_EXIT"
fi

if [[ $GZIP_EXIT -ne 0 ]]; then
    log "ERROR: gzip exited with code ${GZIP_EXIT}. Removing incomplete file."
    rm -f "$BACKUP_FILE"
    log "=== Backup FAILED (gzip exit ${GZIP_EXIT}) ==="
    exit "$GZIP_EXIT"
fi

# Verify the file is non-empty
if [[ ! -s "$BACKUP_FILE" ]]; then
    log "ERROR: Backup file is empty: ${BACKUP_FILE}"
    rm -f "$BACKUP_FILE"
    log "=== Backup FAILED (empty file) ==="
    exit 1
fi

# Verify gzip integrity
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
    log "ERROR: gzip integrity check failed for ${BACKUP_FILE}"
    rm -f "$BACKUP_FILE"
    log "=== Backup FAILED (corrupt gzip) ==="
    exit 1
fi

BACKUP_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
log "Backup verified OK — size: ${BACKUP_SIZE}"

# Prune backups older than RETENTION_DAYS
log "Pruning .sql.gz files older than ${RETENTION_DAYS} days in ${BACKUP_DIR} ..."
DELETED=0
while IFS= read -r -d '' old_file; do
    log "  Deleting old backup: ${old_file}"
    rm -f "$old_file"
    ((DELETED++)) || true
done < <(find "$BACKUP_DIR" -maxdepth 1 -name "*.sql.gz" \
             -mtime +"$RETENTION_DAYS" -print0)

RETAINED=$(find "$BACKUP_DIR" -maxdepth 1 -name "*.sql.gz" | wc -l)

log "Pruned ${DELETED} file(s). Retained backups: ${RETAINED}"
log "Backup file: ${BACKUP_FILE} (${BACKUP_SIZE})"
log "=== Backup completed successfully (exit 0) ==="
