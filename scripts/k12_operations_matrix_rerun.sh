#!/usr/bin/env bash
set -euo pipefail
ROOT=/opt/krowolf
cd "$ROOT"
echo "=== Operations matrix rerun (no env changes) ==="
env K12_BROWSER_CHROME_PATH=/usr/bin/chromium-browser python3 scripts/kapitel12_browser_pilot_verify.py
