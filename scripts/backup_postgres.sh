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
#   STORAGE_DIR           Shared storage root for status metadata (default: /opt/krowolf/storage)
#   BACKUP_STATUS_FILE    Machine-readable backup status JSON (default: ${STORAGE_DIR}/status/backup_status.json)
#
#   OFFSITE_BACKUP_COMMAND  Optional shell command run after a successful local backup.
#                           Receives the backup filename as the first argument ($1).
#                           Example: "rclone copy $1 remote:krowolf-backups/"
#                           If unset or empty, offsite step is skipped with a warning.
#
# Exit codes:
#   0  — backup created, verified, and (if configured) uploaded (metadata write failure does not change exit code)
#   1  — backup failed or verification failed

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DB_CONTAINER="${DOCKER_DB_CONTAINER:-}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
BACKUP_DIR="${BACKUP_DIR:-/opt/krowolf/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
OFFSITE_BACKUP_COMMAND="${OFFSITE_BACKUP_COMMAND:-}"
STORAGE_DIR="${STORAGE_DIR:-/opt/krowolf/storage}"
BACKUP_STATUS_FILE="${BACKUP_STATUS_FILE:-${STORAGE_DIR}/status/backup_status.json}"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BACKUP_FILE="${BACKUP_DIR}/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
BACKUP_ID="${POSTGRES_DB}_${TIMESTAMP}"
BACKUP_SIZE=0
OPERATION_FAILED=false
OPERATION_ERROR_CODE=""

# ── helpers ───────────────────────────────────────────────────────────────────

log()  { echo "[backup] $*"; }
warn() { echo "[backup] WARN: $*" >&2; }
fail() {
    echo "[backup] FAIL: $*" >&2
    OPERATION_FAILED=true
    OPERATION_ERROR_CODE="${OPERATION_ERROR_CODE:-pg_dump_failed}"
    _write_backup_metadata "failed" "$OPERATION_ERROR_CODE" "false" || warn "metadata write failed"
    exit 1
}

_write_backup_metadata() {
    local status="$1"
    local error_code="${2:-}"
    local integrity="${3:-false}"
    local completed_at
    completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local -a cmd=(
        python3 "${SCRIPT_DIR}/write_operation_status.py" backup
        --output "$BACKUP_STATUS_FILE"
        --backup-id "$BACKUP_ID"
        --started-at "$STARTED_AT"
        --completed-at "$completed_at"
        --status "$status"
        --size-bytes "$BACKUP_SIZE"
        --retention-days "$BACKUP_RETENTION_DAYS"
        --archive-integrity-verified "$integrity"
    )
    if [[ -n "$error_code" ]]; then
        cmd+=(--error-code "$error_code")
    fi
    "${cmd[@]}"
}

# ── pre-flight checks ─────────────────────────────────────────────────────────

if [[ -z "${POSTGRES_PASSWORD:-}" && -z "$DOCKER_DB_CONTAINER" ]]; then
    warn "POSTGRES_PASSWORD is not set. Direct pg_dump may fail if the server requires a password."
fi

# Create backup directory if it doesn't exist.
if [[ ! -d "$BACKUP_DIR" ]]; then
    log "Creating backup directory: $BACKUP_DIR"
    mkdir -p "$BACKUP_DIR" || fail "Cannot create backup directory"
fi

log "Starting backup of database '${POSTGRES_DB}' → ${BACKUP_FILE}"

# ── create backup ─────────────────────────────────────────────────────────────

if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
    log "Using docker exec on container: ${DOCKER_DB_CONTAINER}"
    docker exec "$DOCKER_DB_CONTAINER" \
        pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
        | gzip > "$BACKUP_FILE" || fail "pg_dump failed"
else
    log "Using pg_dump directly (no DOCKER_DB_CONTAINER set)"
    PGPASSWORD="${POSTGRES_PASSWORD:-}" \
        pg_dump \
        -U "$POSTGRES_USER" \
        -h "${POSTGRES_HOST:-localhost}" \
        -p "${POSTGRES_PORT:-5432}" \
        "$POSTGRES_DB" \
        | gzip > "$BACKUP_FILE" || fail "pg_dump failed"
fi

# ── verify backup ─────────────────────────────────────────────────────────────

if [[ ! -f "$BACKUP_FILE" ]]; then
    OPERATION_ERROR_CODE="pg_dump_failed"
    fail "Backup file was not created"
fi

BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE" 2>/dev/null || echo 0)
if [[ "$BACKUP_SIZE" -lt 100 ]]; then
    OPERATION_ERROR_CODE="backup_too_small"
    fail "Backup file is suspiciously small (${BACKUP_SIZE} bytes)"
fi

log "Verifying gzip integrity..."
gunzip -t "$BACKUP_FILE" || {
    OPERATION_ERROR_CODE="gzip_invalid"
    fail "Backup file failed gzip integrity check"
}

log "Backup created successfully: ${BACKUP_FILE} ($(du -h "$BACKUP_FILE" | cut -f1))"

# ── offsite upload ────────────────────────────────────────────────────────────

if [[ -n "$OFFSITE_BACKUP_COMMAND" ]]; then
    log "Running offsite backup command..."
    eval "$OFFSITE_BACKUP_COMMAND" "$BACKUP_FILE" || {
        OPERATION_ERROR_CODE="offsite_failed"
        fail "Offsite backup command failed"
    }
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

# ── status metadata (operation success — metadata failure must not fail backup) ─

if ! _write_backup_metadata "success" "" "true"; then
    warn "metadata write failed after successful backup"
fi

log "Backup complete. File: ${BACKUP_FILE}"
