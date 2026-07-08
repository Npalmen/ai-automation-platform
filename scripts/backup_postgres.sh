#!/usr/bin/env bash
# backup_postgres.sh — Create a timestamped, compressed PostgreSQL backup.
#
# Usage:
#   bash scripts/backup_postgres.sh
#
# Required env vars (none are hard-required by default; all have safe defaults
# except POSTGRES_PASSWORD which is warned about if missing):
#
#   DOCKER_DB_CONTAINER   Name of the running Postgres Docker container.
#                         If set, uses "docker exec <container> pg_dump".
#                         If unset, calls pg_dump directly (requires pg_dump in PATH).
#                         Production default: krowolf-db-1
#
#   POSTGRES_USER         Postgres superuser name (default: postgres)
#   POSTGRES_DB           Database to back up (default: ai_platform)
#   POSTGRES_PASSWORD     Password — not logged. Set in env or .env.production.
#                         Only used when DOCKER_DB_CONTAINER is unset (direct pg_dump).
#
#   BACKUP_DIR            Directory to store backups (default: /opt/krowolf/backups)
#   BACKUP_RETENTION_DAYS Number of days to keep local backups (default: 30)
#                         Set to 0 to disable local retention pruning.
#
#   OFFSITE_BACKUP_COMMAND  Optional shell command run after a successful local backup.
#                           Receives the backup filename as the first argument ($1).
#                           Example: "rclone copy $1 remote:krowolf-backups/"
#                           If unset or empty, offsite step is skipped with a warning.
#
# Exit codes:
#   0  — backup created, verified, and (if configured) uploaded
#   1  — backup failed or verification failed

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

DOCKER_DB_CONTAINER="${DOCKER_DB_CONTAINER:-}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
BACKUP_DIR="${BACKUP_DIR:-/opt/krowolf/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
OFFSITE_BACKUP_COMMAND="${OFFSITE_BACKUP_COMMAND:-}"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

# ── helpers ───────────────────────────────────────────────────────────────────

log()  { echo "[backup] $*"; }
warn() { echo "[backup] WARN: $*" >&2; }
fail() { echo "[backup] FAIL: $*" >&2; exit 1; }

# ── pre-flight checks ─────────────────────────────────────────────────────────

if [[ -z "${POSTGRES_PASSWORD:-}" && -z "$DOCKER_DB_CONTAINER" ]]; then
    warn "POSTGRES_PASSWORD is not set. Direct pg_dump may fail if the server requires a password."
fi

# Create backup directory if it doesn't exist.
if [[ ! -d "$BACKUP_DIR" ]]; then
    log "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR" || fail "Cannot create backup directory: $BACKUP_DIR"
fi

log "Starting backup of database '${POSTGRES_DB}' → ${BACKUP_FILE}"

# ── create backup ─────────────────────────────────────────────────────────────

if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
    log "Using docker exec on container: ${DOCKER_DB_CONTAINER}"
    docker exec "$DOCKER_DB_CONTAINER" \
        pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
        | gzip > "$BACKUP_FILE"
else
    log "Using pg_dump directly (no DOCKER_DB_CONTAINER set)"
    # Password handled via PGPASSWORD env var — not echoed.
    PGPASSWORD="${POSTGRES_PASSWORD:-}" \
        pg_dump \
        -U "$POSTGRES_USER" \
        -h "${POSTGRES_HOST:-localhost}" \
        -p "${POSTGRES_PORT:-5432}" \
        "$POSTGRES_DB" \
        | gzip > "$BACKUP_FILE"
fi

# ── verify backup ─────────────────────────────────────────────────────────────

if [[ ! -f "$BACKUP_FILE" ]]; then
    fail "Backup file was not created: ${BACKUP_FILE}"
fi

BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo 0)
if [[ "$BACKUP_SIZE" -lt 100 ]]; then
    fail "Backup file is suspiciously small (${BACKUP_SIZE} bytes): ${BACKUP_FILE}"
fi

log "Verifying gzip integrity..."
gunzip -t "$BACKUP_FILE" || fail "Backup file failed gzip integrity check: ${BACKUP_FILE}"

log "Backup created successfully: ${BACKUP_FILE} ($(du -h "$BACKUP_FILE" | cut -f1))"

# ── offsite upload ────────────────────────────────────────────────────────────

if [[ -n "$OFFSITE_BACKUP_COMMAND" ]]; then
    log "Running offsite backup command..."
    eval "$OFFSITE_BACKUP_COMMAND" "$BACKUP_FILE" \
        || fail "Offsite backup command failed for: ${BACKUP_FILE}"
    log "Offsite upload completed."
else
    warn "OFFSITE_BACKUP_COMMAND is not set. Backup is local only."
    warn "Configure OFFSITE_BACKUP_COMMAND to upload to remote storage (e.g. rclone, aws s3 cp)."
fi

# ── local retention ───────────────────────────────────────────────────────────

if [[ "$BACKUP_RETENTION_DAYS" -gt 0 ]]; then
    log "Pruning local backups older than ${BACKUP_RETENTION_DAYS} days from ${BACKUP_DIR}..."
    PRUNED=0
    while IFS= read -r -d '' old_file; do
        log "  Removing old backup: ${old_file}"
        rm -f "$old_file"
        PRUNED=$((PRUNED + 1))
    done < <(find "$BACKUP_DIR" -maxdepth 1 -name "${POSTGRES_DB}_*.sql.gz" \
               -mtime "+${BACKUP_RETENTION_DAYS}" -print0 2>/dev/null)
    log "Pruned ${PRUNED} old backup(s)."
else
    log "BACKUP_RETENTION_DAYS=0 — local retention pruning is disabled."
fi

log "Backup complete. File: ${BACKUP_FILE}"
