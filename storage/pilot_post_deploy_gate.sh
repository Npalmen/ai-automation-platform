#!/usr/bin/env bash
set -euo pipefail

RUN_ID="3fa356a6-1c10-4788-86ba-e691cac5bbbe"
PRE_SNAP="/opt/krowolf/storage/status/slice_c_canonical_pre_20260722T002252Z.json"

echo "=== AUDIT ROW ==="
docker exec krowolf-db-1 psql -U postgres -d ai_platform -c \
  "SELECT id, status, dry_run, report_json->>'tenant_data_changed' AS tdc, report_json->>'tenants_updated' AS tu, report_json->>'actor' AS actor, report_json->>'canonical_commit' AS cc FROM integration_selection_backfill_runs WHERE id='${RUN_ID}';"

echo "=== APP ==="
docker inspect krowolf-app-1 --format 'StartedAt={{.State.StartedAt}} Image={{.Image}}'
docker exec krowolf-app-1 cat /app/build-metadata.json
curl -sf https://api.krowolf.se/health
echo

echo "=== POST SNAPSHOT ==="
docker exec krowolf-db-1 psql -U postgres -d ai_platform -tAc \
  "SELECT json_build_object(
    'jobs', (SELECT COUNT(*) FROM jobs),
    'approvals', (SELECT COUNT(*) FROM approval_requests),
    'config_version', (SELECT config_version FROM tenant_configs WHERE tenant_id='T_NIKLAS_DEMO_001'),
    'scheduler', COALESCE((SELECT settings->'controller'->'scheduler'->>'run_mode' FROM tenant_configs WHERE tenant_id='T_NIKLAS_DEMO_001'), 'paused'),
    'timezone', COALESCE((SELECT settings->'company'->>'timezone' FROM tenant_configs WHERE tenant_id='T_NIKLAS_DEMO_001'), 'Europe/Stockholm'),
    'activation_snapshots', (SELECT COUNT(*) FROM tenant_activation_snapshots WHERE tenant_id='T_NIKLAS_DEMO_001'),
    'onboarding_sessions', (SELECT COUNT(*) FROM onboarding_sessions WHERE tenant_id='T_NIKLAS_DEMO_001'),
    'gmail_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='T_NIKLAS_DEMO_001' AND provider='google_mail'),
    'visma_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='T_NIKLAS_DEMO_001' AND provider='visma')
  );" | tee /opt/krowolf/storage/status/slice_c_canonical_post_20260722T002500Z.json

echo "=== PRE SNAPSHOT ==="
cat "$PRE_SNAP"

echo "=== REPORT_JSON SECRET SCAN ==="
docker exec krowolf-db-1 psql -U postgres -d ai_platform -tAc \
  "SELECT report_json::text FROM integration_selection_backfill_runs WHERE id='${RUN_ID}';" \
  | python3 - <<'PY'
import json, re, sys
raw = sys.stdin.read().strip()
data = json.loads(raw)
text = json.dumps(data)
patterns = [
    r'access_token', r'refresh_token', r'password', r'secret', r'api[_-]?key',
    r'BEGIN (RSA |EC )?PRIVATE KEY', r'Bearer [A-Za-z0-9._-]{20,}'
]
hits = [p for p in patterns if re.search(p, text, re.I)]
print('credentials_exposed=' + ('true' if hits else 'false'))
if hits:
    print('patterns:', hits)
print('keys:', sorted(data.keys()))
PY

echo "=== ADMIN SYSTEM STATUS (commit only) ==="
docker exec krowolf-app-1 python3 - <<'PY'
import json, os, urllib.request
key = os.environ.get('ADMIN_API_KEY','')
req = urllib.request.Request(
    'http://127.0.0.1:8000/admin/system/status',
    headers={'X-Admin-API-Key': key, 'X-Tenant-ID': 'T_NIKLAS_DEMO_001'}
)
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.load(r)
print(json.dumps({
    'commit_sha': data.get('build', {}).get('commit_sha') or data.get('commit_sha'),
    'release_id': data.get('build', {}).get('release_id') or data.get('release_id'),
}, indent=2))
PY

echo "=== DELTA ==="
python3 - <<'PY'
import json
from pathlib import Path
pre = json.loads(Path("/opt/krowolf/storage/status/slice_c_canonical_pre_20260722T002252Z.json").read_text())
post = json.loads(Path("/opt/krowolf/storage/status/slice_c_canonical_post_20260722T002500Z.json").read_text())
for k in sorted(set(pre) | set(post)):
    pv, nv = pre.get(k), post.get(k)
    if pv != nv:
        print(f"CHANGED {k}: {pv!r} -> {nv!r}")
    else:
        print(f"OK {k}: {pv!r}")
PY
