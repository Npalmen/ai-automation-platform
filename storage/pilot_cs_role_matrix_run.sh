#!/usr/bin/env bash
set -euo pipefail
TS="$(date -u +%Y%m%dT%H%M%SZ)"
ROOT="/opt/krowolf"
TENANT="T_NIKLAS_DEMO_001"
REPORT_DIR="/opt/krowolf/storage/status"
PRE_SNAP="${REPORT_DIR}/cs_role_pre_${TS}.json"
BACKUP="${ROOT}/backups/pre-customer-settings-role-matrix-${TS}.sql.gz"
DRY_REPORT="${REPORT_DIR}/customer_settings_pilot_role_dry_run.json"
FULL_REPORT="${REPORT_DIR}/customer_settings_pilot_role_report.json"

log() { echo "[cs-role-matrix] $*"; }

log "=== PREFLIGHT ==="
curl -sf https://api.krowolf.se/health
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'krowolf-(app|db|caddy)'
RUNTIME="$(docker exec krowolf-app-1 cat /app/build-metadata.json)"
echo "BUILD_METADATA=$RUNTIME"
echo "$RUNTIME" | grep -q '967df7a181b7da43d9a45f2c9a01eff3aa920e62'
APP_STARTED="$(docker inspect krowolf-app-1 --format '{{.State.StartedAt}}')"
DB_STARTED="$(docker inspect krowolf-db-1 --format '{{.State.StartedAt}}')"
CADDY_STARTED="$(docker inspect krowolf-caddy-1 --format '{{.State.StartedAt}}')"
log "APP_STARTED=$APP_STARTED DB_STARTED=$DB_STARTED CADDY_STARTED=$CADDY_STARTED"
test -f "${ROOT}/.env.production"
test -f "${ROOT}/.env.browser-test"
stat -c '%a %U:%G' "${ROOT}/.env.browser-test" | grep -q '^600'
which chromium-browser || which chromium || which google-chrome
bash "${ROOT}/scripts/k12_inspect_admin_role_pilot.sh"
sudo python3 "${ROOT}/scripts/k12_verify_browser_env.py"

log "=== PRE-SNAPSHOT ==="
docker exec krowolf-db-1 psql -U postgres -d ai_platform -tAc \
  "SELECT json_build_object(
    'jobs', (SELECT COUNT(*)::int FROM jobs),
    'approvals', (SELECT COUNT(*)::int FROM approval_requests),
    'config_version', (SELECT config_version FROM tenant_configs WHERE tenant_id='${TENANT}'),
    'timezone', COALESCE((SELECT settings->'company'->>'timezone' FROM tenant_configs WHERE tenant_id='${TENANT}'), 'Europe/Stockholm'),
    'scheduler', COALESCE((SELECT settings->'controller'->'scheduler'->>'run_mode' FROM tenant_configs WHERE tenant_id='${TENANT}'), 'paused'),
    'gmail_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='${TENANT}' AND provider='google_mail'),
    'visma_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='${TENANT}' AND provider='visma'),
    'activation_snapshots', (SELECT COUNT(*)::int FROM tenant_activation_snapshots WHERE tenant_id='${TENANT}'),
    'onboarding_sessions', (SELECT COUNT(*)::int FROM onboarding_sessions WHERE tenant_id='${TENANT}')
  );" | tee "${PRE_SNAP}"
grep -q '"scheduler" : "paused"' "${PRE_SNAP}" || grep -q '"scheduler":"paused"' "${PRE_SNAP}"

log "=== BACKUP ==="
DOCKER_DB_CONTAINER=krowolf-db-1 BACKUP_DIR=/opt/krowolf/backups bash "${ROOT}/scripts/backup_postgres.sh"
LATEST="$(ls -1t /opt/krowolf/backups/ai_platform_*.sql.gz | head -1)"
cp -f "$LATEST" "$BACKUP"
gunzip -t "$BACKUP"
log "BACKUP=$BACKUP"

log "=== SYNC SCRIPTS ==="
cd "$ROOT"
GIT=(git -c safe.directory=/opt/krowolf)
"${GIT[@]}" fetch origin main
bash scripts/k12_sync_browser_scripts_pilot.sh
test -f scripts/customer_settings_pilot_role_verify.py
test -f scripts/k12_customer_settings_role_matrix_pilot.sh
python3 -m py_compile scripts/customer_settings_pilot_role_verify.py

log "=== DRY-RUN ==="
sudo -E python3 scripts/customer_settings_pilot_role_verify.py \
  --dry-run \
  --role all \
  --tenant-id "$TENANT" \
  --report-path "$DRY_REPORT"

log "=== FULL MATRIX ==="
sudo bash scripts/k12_customer_settings_role_matrix_pilot.sh \
  --role all \
  --tenant-id "$TENANT" \
  --report-path "$FULL_REPORT"
MATRIX_EXIT=$?

log "=== POST CHECKS ==="
bash scripts/k12_inspect_admin_role_pilot.sh
curl -sf https://api.krowolf.se/health
docker exec krowolf-db-1 psql -U postgres -d ai_platform -tAc \
  "SELECT json_build_object(
    'jobs', (SELECT COUNT(*)::int FROM jobs),
    'approvals', (SELECT COUNT(*)::int FROM approval_requests),
    'config_version', (SELECT config_version FROM tenant_configs WHERE tenant_id='${TENANT}'),
    'timezone', COALESCE((SELECT settings->'company'->>'timezone' FROM tenant_configs WHERE tenant_id='${TENANT}'), 'Europe/Stockholm'),
    'scheduler', COALESCE((SELECT settings->'controller'->'scheduler'->>'run_mode' FROM tenant_configs WHERE tenant_id='${TENANT}'), 'paused'),
    'gmail_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='${TENANT}' AND provider='google_mail'),
    'visma_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='${TENANT}' AND provider='visma'),
    'activation_snapshots', (SELECT COUNT(*)::int FROM tenant_activation_snapshots WHERE tenant_id='${TENANT}'),
    'onboarding_sessions', (SELECT COUNT(*)::int FROM onboarding_sessions WHERE tenant_id='${TENANT}')
  );" | tee "${REPORT_DIR}/cs_role_post_${TS}.json"

python3 - <<'PY'
import json, re, sys
from pathlib import Path
report = Path("/opt/krowolf/storage/status/customer_settings_pilot_role_report.json")
pre = Path(sorted(Path("/opt/krowolf/storage/status").glob("cs_role_pre_*.json"))[-1])
post = Path(sorted(Path("/opt/krowolf/storage/status").glob("cs_role_post_*.json"))[-1])
text = report.read_text(encoding="utf-8")
patterns = [r'access_token', r'refresh_token', r'password', r'Bearer [A-Za-z0-9._-]{20,}']
if any(re.search(p, text, re.I) for p in patterns):
    print('SECRET_SCAN_FAIL')
    sys.exit(3)
data = json.loads(text)
print('OVERALL', data.get('overall_status'))
print('RESTORE', data.get('restore_status'))
print('RUNTIME', data.get('runtime_code_sha'))
for role, payload in (data.get('roles') or {}).items():
    print('ROLE', role, payload.get('status'))
print('PRE', pre.read_text(encoding='utf-8')[:200])
print('POST', post.read_text(encoding='utf-8')[:200])
PY

exit "$MATRIX_EXIT"
