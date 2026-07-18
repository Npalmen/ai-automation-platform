#!/usr/bin/env bash
# Deploy clean RC commit to pilot (scheduler stays paused).
set -euo pipefail
RC_SHA="${1:?RC SHA required}"
RC_SHORT="${RC_SHA:0:12}"
PREV_RC_TAG="${2:-krowolf-app:rc-865b87165eda}"
RC_TAG="krowolf-app:rc-${RC_SHORT}"
ROLLBACK_TAG="krowolf-app:rollback-${RC_SHORT}"
ROOT="/opt/krowolf"
BUNDLE="/tmp/k12-rc-bundle.tar.gz"

sudo docker tag krowolf-app:latest "$PREV_RC_TAG" 2>/dev/null || true
sudo docker tag "$PREV_RC_TAG" "krowolf-app:rollback-before-${RC_SHORT}" 2>/dev/null || true

sudo bash "$ROOT/scripts/k12_pilot_sync_bundle.sh" "$BUNDLE"
sudo bash "$ROOT/scripts/k12_pilot_rc_deploy.sh" "$RC_SHA"

sudo docker tag "krowolf-app:rc-${RC_SHORT}" "$ROLLBACK_TAG" 2>/dev/null || true

echo "=== Smoke ==="
sudo python3 "$ROOT/scripts/k12_rc_endpoint_verify.py"
SMOKE=$?

echo "=== Rollback to $PREV_RC_TAG ==="
RB_START=$(date +%s)
sudo bash "$ROOT/scripts/k12_pilot_rollback.sh" "$PREV_RC_TAG"
sleep 8
python3 -c "
from urllib.error import HTTPError
from urllib.request import urlopen
for p in ['/admin/operations/overview','/admin/system/status']:
    try:
        r=urlopen(f'https://api.krowolf.se{p}', timeout=15)
        print('rollback', p, r.status)
    except HTTPError as e:
        print('rollback', p, e.code)
"
RB_END=$(date +%s)

echo "=== Forward to $RC_TAG ==="
FW_START=$(date +%s)
sudo docker tag "$RC_TAG" krowolf-app:latest
sudo docker compose -f "$ROOT/docker-compose.prod.yml" up -d app
sleep 12
sudo python3 "$ROOT/scripts/k12_rc_endpoint_verify.py"
FW_END=$(date +%s)

echo "RC_TAG=$RC_TAG"
echo "ROLLBACK_TAG=$ROLLBACK_TAG"
echo "PREV_RC=$PREV_RC_TAG"
echo "smoke_exit=$SMOKE"
echo "rollback_sec=$((RB_END-RB_START))"
echo "forward_sec=$((FW_END-FW_START))"
