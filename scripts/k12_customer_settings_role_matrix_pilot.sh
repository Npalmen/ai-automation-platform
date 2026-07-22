#!/usr/bin/env bash
set -euo pipefail
ROOT=/opt/krowolf
cd "$ROOT"
echo "=== Customer Settings pilot role matrix ==="
if ! curl -sf -o /dev/null https://api.krowolf.se/health; then
  echo "PREFLIGHT_FAIL health"
  exit 1
fi
if test -f scripts/k12_verify_browser_env.py; then
  sudo python3 scripts/k12_verify_browser_env.py || exit 1
fi
sudo -E python3 scripts/customer_settings_pilot_role_verify.py "$@"
STATUS=$?
echo "REPORT=/opt/krowolf/storage/status/customer_settings_pilot_role_report.json"
exit "$STATUS"
