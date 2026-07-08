#!/usr/bin/env bash
# check_backup_freshness.sh — Verify that a recent, valid backup exists.
#
# Checks:
#   1. At least one backup file exists in BACKUP_DIR.
#   2. The most recent backup is not older than BACKUP_MAX_AGE_HOURS.
#   3. The most recent backup is larger than BACKUP_MIN_SIZE_BYTES.
#   4. If the backup is gzip-compressed, verify the archive integrity.
#
# Usage:
#   bash scripts/check_backup_freshness.sh
#
# Optional env vars:
#
#   BACKUP_DIR            Directory to search for backups (default: /opt/krowolf/backups)
#   POSTGRES_DB           Database name — used to filter backup filenames (default: ai_platform)
#   BACKUP_MAX_AGE_HOURS  Maximum acceptable age in hours (default: 25)
#                         25h gives a 1-hour grace window for a daily at 02:00 backup.
#   BACKUP_MIN_SIZE_BYTES Minimum acceptable backup size in bytes (default: 1024)
#
# Exit codes:
#   0  — backup is fresh, non-empty, and (if .gz) passes integrity check
#   1  — any check fails; details printed to stderr

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

BACKUP_DIR="${BACKUP_DIR:-/opt/krowolf/backups}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-25}"
BACKUP_MIN_SIZE_BYTES="${BACKUP_MIN_SIZE_BYTES:-1024}"

# ── helpers ───────────────────────────────────────────────────────────────────

log()  { echo "[freshness] $*"; }
warn() { echo "[freshness] WARN: $*" >&2; }
fail() { echo "[freshness] FAIL: $*" >&2; exit 1; }
pass() { echo "[freshness] OK: $*"; }

# ── check: backup directory exists ────────────────────────────────────────────

[[ -d "$BACKUP_DIR" ]] \
    || fail "Backup directory does not exist: ${BACKUP_DIR}"

log "Scanning ${BACKUP_DIR} for ${POSTGRES_DB}_*.sql.gz backups..."

# ── check: at least one backup exists ────────────────────────────────────────

# Find all matching backup files, sort newest first.
NEWEST_BACKUP=""
while IFS= read -r -d '' f; do
    if [[ -z "$NEWEST_BACKUP" ]]; then
        NEWEST_BACKUP="$f"
    fi
done < <(find "$BACKUP_DIR" -maxdepth 1 \
           \( -name "${POSTGRES_DB}_*.sql.gz" -o -name "${POSTGRES_DB}_*.sql" \) \
           -print0 2>/dev/null \
           | xargs -0 ls -t1 2>/dev/null \
           | while IFS= read -r f; do printf '%s\0' "$f"; done)

# Simpler alternative: use ls + head for portability.
NEWEST_BACKUP=$(find "$BACKUP_DIR" -maxdepth 1 \
    \( -name "${POSTGRES_DB}_*.sql.gz" -o -name "${POSTGRES_DB}_*.sql" \) 2>/dev/null \
    | sort -r | head -1)

if [[ -z "$NEWEST_BACKUP" ]]; then
    fail "No backup files found in ${BACKUP_DIR} matching ${POSTGRES_DB}_*.sql[.gz]"
fi

pass "Most recent backup: ${NEWEST_BACKUP}"

# ── check: file size ──────────────────────────────────────────────────────────

FILE_SIZE=$(stat -c%s "$NEWEST_BACKUP" 2>/dev/null || stat -f%z "$NEWEST_BACKUP" 2>/dev/null || echo 0)

if [[ "$FILE_SIZE" -lt "$BACKUP_MIN_SIZE_BYTES" ]]; then
    fail "Backup is too small (${FILE_SIZE} bytes < ${BACKUP_MIN_SIZE_BYTES} minimum): ${NEWEST_BACKUP}"
fi

pass "Backup size: ${FILE_SIZE} bytes (≥ ${BACKUP_MIN_SIZE_BYTES} minimum)"

# ── check: backup age ─────────────────────────────────────────────────────────

# Get file modification time in seconds since epoch.
FILE_MTIME=$(stat -c%Y "$NEWEST_BACKUP" 2>/dev/null || stat -f%m "$NEWEST_BACKUP" 2>/dev/null || echo 0)
NOW=$(date +%s)
AGE_SECONDS=$(( NOW - FILE_MTIME ))
AGE_HOURS=$(( AGE_SECONDS / 3600 ))
MAX_AGE_SECONDS=$(( BACKUP_MAX_AGE_HOURS * 3600 ))

if [[ "$AGE_SECONDS" -gt "$MAX_AGE_SECONDS" ]]; then
    fail "Backup is too old (${AGE_HOURS}h > ${BACKUP_MAX_AGE_HOURS}h maximum): ${NEWEST_BACKUP}"
fi

pass "Backup age: ${AGE_HOURS}h (≤ ${BACKUP_MAX_AGE_HOURS}h maximum)"

# ── check: gzip integrity ─────────────────────────────────────────────────────

if [[ "$NEWEST_BACKUP" == *.gz ]]; then
    log "Verifying gzip integrity..."
    gunzip -t "$NEWEST_BACKUP" \
        || fail "Backup failed gzip integrity check: ${NEWEST_BACKUP}"
    pass "Gzip integrity: OK"
else
    log "File is not gzip-compressed — skipping gzip integrity check."
    # For uncompressed SQL, check that the file starts with a Postgres dump header.
    HEADER=$(head -c 100 "$NEWEST_BACKUP" 2>/dev/null || echo "")
    if echo "$HEADER" | grep -qi "postgresql\|pg_dump\|SET statement_timeout"; then
        pass "SQL header looks valid (PostgreSQL dump detected)"
    else
        warn "Could not confirm that ${NEWEST_BACKUP} is a valid PostgreSQL dump."
        warn "First bytes: $(head -c 80 "$NEWEST_BACKUP" 2>/dev/null | tr -d '\000' || echo '<unreadable>')"
    fi
fi

# ── summary ───────────────────────────────────────────────────────────────────

log "All freshness checks passed."
log "  Backup:   ${NEWEST_BACKUP}"
log "  Size:     ${FILE_SIZE} bytes"
log "  Age:      ${AGE_HOURS} hour(s)"
