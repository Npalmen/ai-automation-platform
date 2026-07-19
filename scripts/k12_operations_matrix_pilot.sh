#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/krowolf
PROD="$ROOT/.env.production"
BROWSER="$ROOT/.env.browser-test"

echo "=== Container start times BEFORE ==="
docker inspect krowolf-app-1 krowolf-db-1 krowolf-caddy-1 --format '{{.Name}} started={{.State.StartedAt}}'

if grep -q '^ADMIN_ROLE=' "$PROD"; then
  sed -i 's/^ADMIN_ROLE=.*/ADMIN_ROLE=operations/' "$PROD"
else
  echo 'ADMIN_ROLE=operations' >> "$PROD"
fi
if grep -q '^K12_BROWSER_ROLE=' "$BROWSER"; then
  sed -i 's/^K12_BROWSER_ROLE=.*/K12_BROWSER_ROLE=operations/' "$BROWSER"
else
  echo 'K12_BROWSER_ROLE=operations' >> "$BROWSER"
fi
if grep -q '^K12_BROWSER_REPORT_PATH=' "$BROWSER"; then
  sed -i 's|^K12_BROWSER_REPORT_PATH=.*|K12_BROWSER_REPORT_PATH=/opt/krowolf/storage/status/k12_browser_operations_report.json|' "$BROWSER"
else
  echo 'K12_BROWSER_REPORT_PATH=/opt/krowolf/storage/status/k12_browser_operations_report.json' >> "$BROWSER"
fi
chown root:root "$PROD" "$BROWSER"
chmod 600 "$PROD" "$BROWSER"

echo "=== Env permissions ==="
stat -c '%U:%G %a %n' "$PROD" "$BROWSER"
echo "ADMIN_ROLE set in production env"
echo "K12_BROWSER_ROLE=operations"
echo "K12_BROWSER_REPORT_PATH=/opt/krowolf/storage/status/k12_browser_operations_report.json"

echo "=== Recreate app container only ==="
cd "$ROOT"
docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate app
sleep 5

echo "=== Container start times AFTER ==="
docker inspect krowolf-app-1 krowolf-db-1 krowolf-caddy-1 --format '{{.Name}} started={{.State.StartedAt}}'

echo "=== Health ==="
curl -sf https://api.krowolf.se/health
echo

echo "=== Browser env verify ==="
python3 "$ROOT/scripts/k12_verify_browser_env.py"

echo "=== Scheduler check ==="
if [[ -f "$ROOT/scripts/k12_check_scheduler_pilot.py" ]]; then
  python3 "$ROOT/scripts/k12_check_scheduler_pilot.py"
else
  docker exec krowolf-db-1 psql -U postgres -d ai_platform -tAc \
    "SELECT COALESCE(settings->'scheduler'->>'run_mode','unknown') FROM tenant_configs LIMIT 5;" \
    | tr '\n' ' '
  echo
fi

echo "=== Server role check ==="
python3 <<'PY'
import sys
sys.path.insert(0, "/opt/krowolf")
from scripts.k12_browser_common import load_browser_env, resolve_env_path
import requests

env = load_browser_env(resolve_env_path())
base = env["K12_BROWSER_BASE_URL"].rstrip("/")
sess = requests.Session()
r = sess.post(
    f"{base}/auth/admin/login",
    json={"username": env["K12_BROWSER_USERNAME"], "password": env["K12_BROWSER_PASSWORD"]},
    headers={"Content-Type": "application/json"},
    timeout=30,
)
if r.status_code != 200:
    print(f"ROLE_CHECK=FAIL login_http={r.status_code}")
    sys.exit(1)
me = sess.get(f"{base}/auth/admin/me", timeout=20)
if me.status_code != 200:
    print(f"ROLE_CHECK=FAIL me_http={me.status_code}")
    sys.exit(1)
role = (me.json().get("operator") or {}).get("role", "")
print(f"ROLE_RETURNED={role}")
if role != "operations":
    print("ROLE_CHECK=FAIL expected=operations")
    sys.exit(1)
print("ROLE_CHECK=PASS")
PY

echo "=== Operations browser matrix ==="
cd "$ROOT"
env K12_BROWSER_CHROME_PATH=/usr/bin/chromium-browser python3 scripts/kapitel12_browser_pilot_verify.py
