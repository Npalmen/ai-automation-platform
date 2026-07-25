#!/usr/bin/env bash
set -euo pipefail
ROOT=/opt/krowolf
TENANT=T_NIKLAS_DEMO_001
TS=$(date -u +%Y%m%dT%H%M%SZ)
REPORT_DIR=$ROOT/storage/status
BACKUP=$ROOT/backups/pre-customer-settings-role-matrix-${TS}.sql.gz
DRY=$REPORT_DIR/customer_settings_pilot_role_dry_run.json
FULL=$REPORT_DIR/customer_settings_pilot_role_report.json
APP_STARTED=$(docker inspect krowolf-app-1 --format '{{.State.StartedAt}}')
DB_STARTED=$(docker inspect krowolf-db-1 --format '{{.State.StartedAt}}')
CADDY_STARTED=$(docker inspect krowolf-caddy-1 --format '{{.State.StartedAt}}')

echo "=== PREFLIGHT ==="
curl -sf https://api.krowolf.se/health
docker exec krowolf-app-1 cat /app/build-metadata.json | grep -q 967df7a181b7da43d9a45f2c9a01eff3aa920e62
test -f "$ROOT/.env.production"
test -f "$ROOT/.env.browser-test"
stat -c '%a' "$ROOT/.env.browser-test" | grep -q '^600$'
which chromium-browser >/dev/null
bash "$ROOT/scripts/k12_inspect_admin_role_pilot.sh" | sed -n '1,5p'
sudo python3 "$ROOT/scripts/k12_verify_browser_env.py"

echo "=== BACKUP ==="
DOCKER_DB_CONTAINER=krowolf-db-1 BACKUP_DIR=$ROOT/backups bash "$ROOT/scripts/backup_postgres.sh"
LATEST=$(ls -1t "$ROOT/backups"/ai_platform_*.sql.gz | head -1)
cp -f "$LATEST" "$BACKUP"
gunzip -t "$BACKUP"
echo "BACKUP=$BACKUP"

echo "=== SYNC ==="
cd "$ROOT"
git -c safe.directory=/opt/krowolf fetch origin main
git -c safe.directory=/opt/krowolf checkout origin/main -- \
  scripts/customer_settings_pilot_role_verify.py \
  scripts/k12_customer_settings_role_matrix_pilot.sh \
  scripts/k12_sync_browser_scripts_pilot.sh
bash scripts/k12_sync_browser_scripts_pilot.sh
python3 -m py_compile scripts/customer_settings_pilot_role_verify.py

echo "=== DRY-RUN ==="
sudo -E python3 scripts/customer_settings_pilot_role_verify.py \
  --dry-run --role all --tenant-id "$TENANT" --report-path "$DRY"

echo "=== FULL MATRIX ==="
set +e
sudo bash scripts/k12_customer_settings_role_matrix_pilot.sh \
  --role all --tenant-id "$TENANT" --report-path "$FULL"
MATRIX_EXIT=$?
set -e

echo "=== POST ==="
bash scripts/k12_inspect_admin_role_pilot.sh | sed -n '1,8p'
curl -sf https://api.krowolf.se/health
APP_STARTED_AFTER=$(docker inspect krowolf-app-1 --format '{{.State.StartedAt}}')
echo "APP_STARTED_BEFORE=$APP_STARTED"
echo "APP_STARTED_AFTER=$APP_STARTED_AFTER"
echo "DB_STARTED=$DB_STARTED CADDY_STARTED=$CADDY_STARTED"
echo "MATRIX_EXIT=$MATRIX_EXIT"

python3 /opt/krowolf/storage/parse_cs_report.py "$FULL" || python3 - <<'PY'
import json, pathlib
p = pathlib.Path("/opt/krowolf/storage/status/customer_settings_pilot_role_report.json")
d = json.loads(p.read_text())
print("overall_status", d.get("overall_status"))
print("restore_status", d.get("restore_status"))
print("runtime_code_sha", d.get("runtime_code_sha"))
print("credentials_exposed", d.get("credentials_exposed"))
print("external_side_effects", d.get("external_side_effects"))
se = d.get("side_effects") or {}
print("side_effects_ok", se.get("ok"))
for role in ("read_only", "operations", "admin", "super_admin"):
    r = (d.get("roles") or {}).get(role) or {}
    api = r.get("api") or {}
    browser = r.get("browser") or {}
    fails = []
    for block in (api, browser):
        for name, chk in (block.get("checks") or {}).items():
            if isinstance(chk, dict) and chk.get("status") == "FAIL":
                fails.append(name)
    print(role, "status", r.get("status"), "fails", fails[:8])
PY

exit "$MATRIX_EXIT"
