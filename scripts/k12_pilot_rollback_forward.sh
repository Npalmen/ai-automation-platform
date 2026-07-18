#!/usr/bin/env bash
set -euo pipefail
sudo cp /tmp/k12_rc_endpoint_verify.py /opt/krowolf/scripts/ 2>/dev/null || true
echo "=== RC endpoint verify (before rollback) ==="
sudo python3 /opt/krowolf/scripts/k12_rc_endpoint_verify.py || true

echo "=== ROLLBACK ==="
ROLLBACK_START=$(date +%s)
sudo bash /opt/krowolf/scripts/k12_pilot_rollback.sh krowolf-app:rollback-e77b045d33c1
sleep 8
ROLLBACK_END=$(date +%s)
echo "rollback_duration_sec=$((ROLLBACK_END-ROLLBACK_START))"

python3 - <<'PY'
from urllib.error import HTTPError
from urllib.request import urlopen
for p in ["/health", "/admin/operations/overview", "/admin/system/status"]:
    try:
        r = urlopen(f"https://api.krowolf.se{p}", timeout=15)
        print(p, r.status)
    except HTTPError as e:
        print(p, e.code)
PY

echo "=== REDEPLOY RC ==="
FORWARD_START=$(date +%s)
sudo docker tag krowolf-app:rc-865b87165eda krowolf-app:latest
sudo docker compose -f /opt/krowolf/docker-compose.prod.yml up -d app
sleep 12
FORWARD_END=$(date +%s)
echo "forward_duration_sec=$((FORWARD_END-FORWARD_START))"

echo "=== RC endpoint verify (after redeploy) ==="
sudo python3 /opt/krowolf/scripts/k12_rc_endpoint_verify.py

echo "=== Build metadata ==="
sudo docker exec krowolf-app-1 cat /app/build-metadata.json 2>/dev/null || echo missing

echo "=== Image tags ==="
sudo docker images krowolf-app --format '{{.Repository}}:{{.Tag}} {{.ID}}'
