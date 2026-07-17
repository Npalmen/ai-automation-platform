#!/usr/bin/env bash
# restore_postgres_rehearsal.sh — Restore a backup to a SEPARATE target database.
#
# Safety guarantee: This script refuses to restore into the production database
# by default. It requires an explicit RESTORE_TARGET_DB that differs from
# POSTGRES_DB (the production database name).
#
# Usage:
#   RESTORE_SOURCE_FILE=/opt/krowolf/backups/ai_platform_2026-07-08-020000.sql.gz \
#   RESTORE_TARGET_DB=ai_platform_restore_test \
#   bash scripts/restore_postgres_rehearsal.sh
#
# Required env vars:
#
#   RESTORE_SOURCE_FILE   Full path to the .sql or .sql.gz backup file to restore.
#   RESTORE_TARGET_DB     Name of the database to restore INTO.
#                         MUST differ from POSTGRES_DB — production restore is refused.
#
# Optional env vars:
#
#   DOCKER_DB_CONTAINER   Docker container running Postgres.
#   POSTGRES_USER         Postgres superuser (default: postgres)
#   POSTGRES_DB           Production database name — used only for the safety check.
#   STORAGE_DIR           Shared storage root for status metadata (default: /opt/krowolf/storage)
#   RESTORE_STATUS_FILE   Machine-readable restore status JSON (default: ${STORAGE_DIR}/status/restore_status.json)
#   SKIP_CLEANUP          If set to "true", do not drop RESTORE_TARGET_DB after rehearsal.
#
# Exit codes:
#   0  — restore and verification succeeded (metadata write failure does not change exit code)
#   1  — refused (safety check) or restore/verification failed

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESTORE_SOURCE_FILE="${RESTORE_SOURCE_FILE:-}"
RESTORE_TARGET_DB="${RESTORE_TARGET_DB:-}"
DOCKER_DB_CONTAINER="${DOCKER_DB_CONTAINER:-}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
SKIP_CLEANUP="${SKIP_CLEANUP:-false}"
STORAGE_DIR="${STORAGE_DIR:-/opt/krowolf/storage}"
RESTORE_STATUS_FILE="${RESTORE_STATUS_FILE:-${STORAGE_DIR}/status/restore_status.json}"
TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TEST_ID="restore_${TIMESTAMP}"
BACKUP_ID="$(basename "$RESTORE_SOURCE_FILE" .sql.gz)"
BACKUP_ID="${BACKUP_ID%.sql}"
SCHEMA_VERIFICATION="not_performed"
RESTORE_OPERATION_STATUS="success"
RESTORE_ERROR_CODE=""
ALL_OK=true

VERIFY_TABLES=(
    "tenants"
    "jobs"
    "approvals"
    "oauth_credentials"
    "audit_events"
    "integration_events"
)

# ── helpers ───────────────────────────────────────────────────────────────────

log()  { echo "[restore] $*"; }
warn() { echo "[restore] WARN: $*" >&2; }
fail() {
    echo "[restore] FAIL: $*" >&2
    RESTORE_OPERATION_STATUS="failed"
    RESTORE_ERROR_CODE="${RESTORE_ERROR_CODE:-restore_failed}"
    _write_restore_metadata || warn "metadata write failed"
    exit 1
}

_write_restore_metadata() {
    local completed_at
    completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local -a cmd=(
        python3 "${SCRIPT_DIR}/write_operation_status.py" restore
        --output "$RESTORE_STATUS_FILE"
        --test-id "$TEST_ID"
        --backup-id "$BACKUP_ID"
        --started-at "$STARTED_AT"
        --completed-at "$completed_at"
        --status "$RESTORE_OPERATION_STATUS"
        --schema-verification "$SCHEMA_VERIFICATION"
        --application-smoke-verification "not_performed"
    )
    if [[ -n "$RESTORE_ERROR_CODE" ]]; then
        cmd+=(--error-code "$RESTORE_ERROR_CODE")
    fi
    "${cmd[@]}"
}

_psql() {
    if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
        docker exec "$DOCKER_DB_CONTAINER" psql -U "$POSTGRES_USER" "$@"
    else
        PGPASSWORD="${POSTGRES_PASSWORD:-}" \
            psql -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" "$@"
    fi
}

_psql_stdin() {
    if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
        docker exec -i "$DOCKER_DB_CONTAINER" psql -U "$POSTGRES_USER" "$@"
    else
        PGPASSWORD="${POSTGRES_PASSWORD:-}" \
            psql -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" "$@"
    fi
}

# ── pre-flight checks ─────────────────────────────────────────────────────────

[[ -n "$RESTORE_SOURCE_FILE" ]] \
    || fail "RESTORE_SOURCE_FILE is required."

[[ -n "$RESTORE_TARGET_DB" ]] \
    || fail "RESTORE_TARGET_DB is required."

[[ -f "$RESTORE_SOURCE_FILE" ]] \
    || fail "Source file does not exist"

if [[ "$RESTORE_TARGET_DB" == "$POSTGRES_DB" ]]; then
    RESTORE_ERROR_CODE="safety_refused"
    fail "RESTORE_TARGET_DB matches POSTGRES_DB — refusing production restore"
fi

case "$RESTORE_TARGET_DB" in
    ai_platform|krowolf|production|prod)
        RESTORE_ERROR_CODE="safety_refused"
        fail "RESTORE_TARGET_DB looks like a production database name"
        ;;
esac

log "Source file:   ${RESTORE_SOURCE_FILE}"
log "Target DB:     ${RESTORE_TARGET_DB}"
log "Production DB: ${POSTGRES_DB} (protected from overwrite)"

# ── create target database ────────────────────────────────────────────────────

log "Creating target database '${RESTORE_TARGET_DB}' (if not exists)..."
_psql -d postgres -c "CREATE DATABASE \"${RESTORE_TARGET_DB}\";" 2>/dev/null || {
    warn "Database '${RESTORE_TARGET_DB}' may already exist — continuing."
}

# ── restore ───────────────────────────────────────────────────────────────────

log "Restoring backup..."

if [[ "$RESTORE_SOURCE_FILE" == *.gz ]]; then
    gunzip -c "$RESTORE_SOURCE_FILE" | _psql_stdin -d "$RESTORE_TARGET_DB" -v ON_ERROR_STOP=0 -q \
        || {
            RESTORE_ERROR_CODE="restore_failed"
            fail "Restore SQL failed"
        }
else
    _psql_stdin -d "$RESTORE_TARGET_DB" -v ON_ERROR_STOP=0 -q < "$RESTORE_SOURCE_FILE" \
        || {
            RESTORE_ERROR_CODE="restore_failed"
            fail "Restore SQL failed"
        }
fi

log "Restore SQL executed."

# ── verify tables ─────────────────────────────────────────────────────────────

log "Verifying restored tables..."

for table in "${VERIFY_TABLES[@]}"; do
    COUNT=$( _psql -d "$RESTORE_TARGET_DB" -t -c \
        "SELECT COUNT(*) FROM \"${table}\";" 2>/dev/null | tr -d ' ' ) || COUNT="TABLE_NOT_FOUND"

    if [[ "$COUNT" == "TABLE_NOT_FOUND" || -z "$COUNT" ]]; then
        warn "  Table '${table}': NOT FOUND (may be expected if table is new)"
        ALL_OK=false
    else
        log "  Table '${table}': ${COUNT} row(s)"
    fi
done

if [[ "$ALL_OK" == "true" ]]; then
    SCHEMA_VERIFICATION="success"
    log "All expected tables verified."
else
    SCHEMA_VERIFICATION="failed"
    RESTORE_OPERATION_STATUS="failed"
    RESTORE_ERROR_CODE="verify_failed"
    warn "One or more tables could not be verified."
    _write_restore_metadata || warn "metadata write failed"
    exit 1
fi

# ── cleanup ───────────────────────────────────────────────────────────────────

if [[ "$SKIP_CLEANUP" == "true" ]]; then
    log "SKIP_CLEANUP=true — leaving '${RESTORE_TARGET_DB}' in place for inspection."
else
    log "Dropping target database '${RESTORE_TARGET_DB}'..."
    _psql -d postgres -c "DROP DATABASE IF EXISTS \"${RESTORE_TARGET_DB}\";" 2>/dev/null \
        || warn "Could not drop '${RESTORE_TARGET_DB}' — clean up manually."
    log "Target database dropped."
fi

if ! _write_restore_metadata; then
    warn "metadata write failed after successful restore rehearsal"
fi

log "Rehearsal complete."
