#!/usr/bin/env bash
# One-shot: sync browser matrix scripts from origin/main without touching other server changes.
set -euo pipefail
cd /opt/krowolf
GIT=(sudo git -c safe.directory=/opt/krowolf)
echo "OLD_HEAD=$("${GIT[@]}" rev-parse HEAD)"
"${GIT[@]}" fetch origin main
FILES=(
  scripts/k12_verify_browser_env.py
  scripts/k12_browser_common.py
  scripts/k12_browser_cdp.py
  scripts/k12_browser_approval_fixture.py
  scripts/kapitel12_browser_pilot_verify.py
  scripts/kapitel12_browser_aggregate.py
  scripts/env.browser-test.example
  docs/runbooks/kapitel12-browser-matrix.md
)
"${GIT[@]}" checkout origin/main -- "${FILES[@]}"
chmod +x scripts/k12_verify_browser_env.py scripts/kapitel12_browser_pilot_verify.py scripts/kapitel12_browser_aggregate.py 2>/dev/null || true
echo "ORIGIN_MAIN=$("${GIT[@]}" rev-parse origin/main)"
echo "WORKTREE_HEAD=$("${GIT[@]}" rev-parse HEAD)"
for f in scripts/k12_verify_browser_env.py scripts/k12_browser_common.py scripts/k12_browser_cdp.py scripts/k12_browser_approval_fixture.py scripts/kapitel12_browser_pilot_verify.py scripts/kapitel12_browser_aggregate.py; do
  if test -f "$f"; then
    echo "FOUND /opt/krowolf/$f"
  else
    echo "MISSING /opt/krowolf/$f"
  fi
done
stat -c '%U:%G %a' /opt/krowolf/.env.browser-test
