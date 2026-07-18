#!/usr/bin/env bash
# restore_from_offsite_rehearsal.sh — Restore from verified offsite copy (Kapitel 12).
#
# 1. Select offsite backup (OFFSITE_BACKUP_DEST_DIR or RESTORE_SOURCE_FILE)
# 2. Verify sha256 sidecar
# 3. Restore to separate RESTORE_TARGET_DB via restore_postgres_rehearsal.sh
# 4. Emit timing metrics to RESTORE_REHEARSAL_REPORT (JSON)
#
# Required when using offsite dir:
#   OFFSITE_BACKUP_DEST_DIR
#   RESTORE_TARGET_DB (must differ from POSTGRES_DB)
#
# Optional:
#   RESTORE_SOURCE_FILE — explicit offsite file path (overrides dir scan)
#   RESTORE_REHEARSAL_REPORT — JSON report path (default: ./storage/status/restore_rehearsal_report.json)
#   SKIP_CLEANUP — pass through to restore_postgres_rehearsal.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OFFSITE_DIR="${OFFSITE_BACKUP_DEST_DIR:-}"
RESTORE_SOURCE_FILE="${RESTORE_SOURCE_FILE:-}"
RESTORE_TARGET_DB="${RESTORE_TARGET_DB:-}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
REPORT_FILE="${RESTORE_REHEARSAL_REPORT:-${STORAGE_DIR:-./storage}/status/restore_rehearsal_report.json}"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RESTORE_START_EPOCH=$(date +%s)

log() { echo "[offsite-restore] $*"; }
fail() { echo "[offsite-restore] FAIL: $*" >&2; exit 1; }

[[ -n "$RESTORE_TARGET_DB" ]] || fail "RESTORE_TARGET_DB is required"
[[ "$RESTORE_TARGET_DB" != "$POSTGRES_DB" ]] || fail "RESTORE_TARGET_DB must differ from POSTGRES_DB"

if [[ -z "$RESTORE_SOURCE_FILE" ]]; then
    [[ -n "$OFFSITE_DIR" && -d "$OFFSITE_DIR" ]] || fail "OFFSITE_BACKUP_DEST_DIR missing or not a directory"
    RESTORE_SOURCE_FILE=$(find "$OFFSITE_DIR" -maxdepth 1 -name "${POSTGRES_DB}_*.sql.gz" 2>/dev/null | sort -r | head -1)
    [[ -n "$RESTORE_SOURCE_FILE" ]] || fail "No offsite backup files found"
fi

[[ -f "$RESTORE_SOURCE_FILE" ]] || fail "Offsite source file not found"

SIDECAR="${RESTORE_SOURCE_FILE}.sha256"
if [[ -f "$SIDECAR" ]]; then
    EXPECTED=$(awk '{print $1}' "$SIDECAR")
    if command -v sha256sum >/dev/null 2>&1; then
        ACTUAL=$(sha256sum "$RESTORE_SOURCE_FILE" | awk '{print $1}')
    else
        ACTUAL=$(python3 -c "import hashlib,sys; h=hashlib.sha256();
with open(sys.argv[1],'rb') as f:
  [h.update(b) for b in iter(lambda: f.read(1048576), b'')]
print(h.hexdigest())" "$RESTORE_SOURCE_FILE")
    fi
    [[ "$EXPECTED" == "$ACTUAL" ]] || fail "Checksum mismatch for offsite backup"
    log "Checksum verified."
else
    log "WARN: no sha256 sidecar — gunzip -t only"
    gunzip -t "$RESTORE_SOURCE_FILE" || fail "gzip integrity failed"
fi

FETCH_START_EPOCH=$(date +%s)
# Source is already local in offsite dir; fetch duration = selection overhead
FETCH_END_EPOCH=$(date +%s)

export RESTORE_SOURCE_FILE
bash "${SCRIPT_DIR}/restore_postgres_rehearsal.sh"
RESTORE_END_EPOCH=$(date +%s)

BACKUP_ID=$(basename "$RESTORE_SOURCE_FILE" .sql.gz)
BACKUP_ID="${BACKUP_ID%.sql}"
SIZE_BYTES=$(stat -c%s "$RESTORE_SOURCE_FILE" 2>/dev/null || stat -f%z "$RESTORE_SOURCE_FILE" 2>/dev/null || echo 0)
RTO_SECONDS=$((RESTORE_END_EPOCH - RESTORE_START_EPOCH))
FETCH_SECONDS=$((FETCH_END_EPOCH - FETCH_START_EPOCH))

python3 - <<'PY' "$REPORT_FILE" "$BACKUP_ID" "$STARTED_AT" "$SIZE_BYTES" "$RTO_SECONDS" "$FETCH_SECONDS" "$RESTORE_SOURCE_FILE"
import json, os, sys
from datetime import datetime, timezone
path, backup_id, started_at, size_bytes, rto_s, fetch_s, source = sys.argv[1:8]
payload = {
    "schema_version": 1,
    "backup_id": backup_id,
    "started_at": started_at,
    "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "source_type": "offsite",
    "size_bytes": int(size_bytes),
    "rto_seconds": int(rto_s),
    "offsite_fetch_seconds": int(fetch_s),
    "rpo_note": "RPO = age of selected offsite backup at restore start (see backup completed_at)",
    "restore_target_db": os.environ.get("RESTORE_TARGET_DB"),
    "status": "success",
}
os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
with open(path, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
print(f"[offsite-restore] report: {path}")
PY

log "Offsite restore rehearsal complete. RTO=${RTO_SECONDS}s"
