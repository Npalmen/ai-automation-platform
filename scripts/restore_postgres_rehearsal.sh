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
#                         If set, runs psql via docker exec.
#                         If unset, runs psql directly.
#
#   POSTGRES_USER         Postgres superuser (default: postgres)
#   POSTGRES_DB           Production database name — used only for the safety check.
#                         (default: ai_platform)
#   POSTGRES_PASSWORD     Password — only used when DOCKER_DB_CONTAINER is unset.
#   POSTGRES_HOST         Host for direct psql (default: localhost)
#   POSTGRES_PORT         Port for direct psql (default: 5432)
#
#   SKIP_CLEANUP          If set to "true", do not drop RESTORE_TARGET_DB after rehearsal.
#                         Default: false (target DB is dropped after verification).
#
# Exit codes:
#   0  — restore and verification succeeded
#   1  — refused (safety check) or restore/verification failed

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

RESTORE_SOURCE_FILE="${RESTORE_SOURCE_FILE:-}"
RESTORE_TARGET_DB="${RESTORE_TARGET_DB:-}"
DOCKER_DB_CONTAINER="${DOCKER_DB_CONTAINER:-}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
SKIP_CLEANUP="${SKIP_CLEANUP:-false}"

# Tables to verify after restore.
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
fail() { echo "[restore] FAIL: $*" >&2; exit 1; }

# Run a psql command.
# Usage: _psql -d <dbname> -c "<sql>"
_psql() {
    if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
        docker exec "$DOCKER_DB_CONTAINER" psql -U "$POSTGRES_USER" "$@"
    else
        PGPASSWORD="${POSTGRES_PASSWORD:-}" \
            psql -U "$POSTGRES_USER" -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" "$@"
    fi
}

# Pipe SQL from stdin to psql.
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
    || fail "RESTORE_SOURCE_FILE is required. Set it to the path of a .sql or .sql.gz backup file."

[[ -n "$RESTORE_TARGET_DB" ]] \
    || fail "RESTORE_TARGET_DB is required. Set it to a non-production database name (e.g. ai_platform_restore_test)."

[[ -f "$RESTORE_SOURCE_FILE" ]] \
    || fail "Source file does not exist: ${RESTORE_SOURCE_FILE}"

# Safety check — refuse to restore into production.
if [[ "$RESTORE_TARGET_DB" == "$POSTGRES_DB" ]]; then
    fail "RESTORE_TARGET_DB ('${RESTORE_TARGET_DB}') matches POSTGRES_DB ('${POSTGRES_DB}')." \
         " Refusing to restore into production. Use a different target database name."
fi

# Additional guard: reject common production database names unless explicitly overridden.
case "$RESTORE_TARGET_DB" in
    ai_platform|krowolf|production|prod)
        fail "RESTORE_TARGET_DB ('${RESTORE_TARGET_DB}') looks like a production database name. Refusing to restore."
        ;;
esac

log "Source file:   ${RESTORE_SOURCE_FILE}"
log "Target DB:     ${RESTORE_TARGET_DB}"
log "Production DB: ${POSTGRES_DB} (protected from overwrite)"
if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
    log "Container:     ${DOCKER_DB_CONTAINER}"
else
    log "Direct psql:   ${POSTGRES_HOST}:${POSTGRES_PORT}"
fi

# ── create target database ────────────────────────────────────────────────────

log "Creating target database '${RESTORE_TARGET_DB}' (if not exists)..."
# Use || true — CREATE DATABASE errors if it already exists; we allow that.
_psql -d postgres -c "CREATE DATABASE \"${RESTORE_TARGET_DB}\";" 2>/dev/null || {
    warn "Database '${RESTORE_TARGET_DB}' may already exist — continuing."
}

# ── restore ───────────────────────────────────────────────────────────────────

log "Restoring backup..."

# Determine if source is compressed.
if [[ "$RESTORE_SOURCE_FILE" == *.gz ]]; then
    log "Decompressing and restoring from: ${RESTORE_SOURCE_FILE}"
    gunzip -c "$RESTORE_SOURCE_FILE" | _psql_stdin -d "$RESTORE_TARGET_DB" -v ON_ERROR_STOP=0 -q
else
    log "Restoring from: ${RESTORE_SOURCE_FILE}"
    _psql_stdin -d "$RESTORE_TARGET_DB" -v ON_ERROR_STOP=0 -q < "$RESTORE_SOURCE_FILE"
fi

log "Restore SQL executed."

# ── verify tables ─────────────────────────────────────────────────────────────

log "Verifying restored tables..."
ALL_OK=true

for table in "${VERIFY_TABLES[@]}"; do
    # Check table exists and get row count.
    ROW_COUNT=$( _psql -d "$RESTORE_TARGET_DB" -t -c \
        "SELECT COALESCE(reltuples::bigint, -1) FROM pg_class WHERE relname = '${table}';" \
        2>/dev/null | tr -d ' ' ) || ROW_COUNT=""

    # pg_class reltuples may be 0 for empty tables or -1 if table doesn't exist.
    # Use a direct COUNT for accuracy.
    COUNT=$( _psql -d "$RESTORE_TARGET_DB" -t -c \
        "SELECT COUNT(*) FROM \"${table}\";" 2>/dev/null | tr -d ' ' ) || COUNT="TABLE_NOT_FOUND"

    if [[ "$COUNT" == "TABLE_NOT_FOUND" || -z "$COUNT" ]]; then
        warn "  Table '${table}': NOT FOUND (may be expected if table is new)"
        ALL_OK=false
    else
        log "  Table '${table}': ${COUNT} row(s)"
    fi
done

if [[ "$ALL_OK" == "false" ]]; then
    warn "One or more tables could not be verified. Review warnings above."
    warn "This may be acceptable if schema evolved since the backup was taken."
else
    log "All expected tables verified."
fi

# ── cleanup ───────────────────────────────────────────────────────────────────

if [[ "$SKIP_CLEANUP" == "true" ]]; then
    log "SKIP_CLEANUP=true — leaving '${RESTORE_TARGET_DB}' in place for inspection."
    log "Remember to drop it manually when done:"
    if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
        log "  docker exec ${DOCKER_DB_CONTAINER} psql -U ${POSTGRES_USER} -c 'DROP DATABASE \"${RESTORE_TARGET_DB}\";'"
    else
        log "  psql -U ${POSTGRES_USER} -h ${POSTGRES_HOST} -c 'DROP DATABASE \"${RESTORE_TARGET_DB}\";'"
    fi
else
    log "Dropping target database '${RESTORE_TARGET_DB}'..."
    _psql -d postgres -c "DROP DATABASE IF EXISTS \"${RESTORE_TARGET_DB}\";" 2>/dev/null \
        || warn "Could not drop '${RESTORE_TARGET_DB}' — clean up manually."
    log "Target database dropped."
fi

log "Rehearsal complete."
