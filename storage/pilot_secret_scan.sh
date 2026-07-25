#!/usr/bin/env bash
set -euo pipefail
RUN_ID="3fa356a6-1c10-4788-86ba-e691cac5bbbe"

echo "=== REPORT_JSON SECRET SCAN ==="
docker exec krowolf-db-1 psql -U postgres -d ai_platform -tAc \
  "SELECT report_json::text FROM integration_selection_backfill_runs WHERE id='${RUN_ID}';" \
  > /tmp/report_json.txt
python3 -c "
import json, re
text = open('/tmp/report_json.txt').read().strip()
data = json.loads(text)
blob = json.dumps(data)
patterns = [r'access_token', r'refresh_token', r'password', r'secret', r'api[_-]?key', r'BEGIN (RSA |EC )?PRIVATE KEY', r'Bearer [A-Za-z0-9._-]{20,}']
hits = [p for p in patterns if re.search(p, blob, re.I)]
print('credentials_exposed=' + ('true' if hits else 'false'))
print('top_keys=' + ','.join(sorted(data.keys())))
"

echo "=== ADMIN SYSTEM STATUS (build only) ==="
docker exec krowolf-app-1 python3 -c "
import json, os, urllib.request
key = os.environ.get('ADMIN_API_KEY','')
req = urllib.request.Request(
    'http://127.0.0.1:8000/admin/system/status',
    headers={'X-Admin-API-Key': key, 'X-Tenant-ID': 'T_NIKLAS_DEMO_001'}
)
with urllib.request.urlopen(req, timeout=10) as r:
    data = json.load(r)
build = ((data.get('deployment') or {}).get('current_build') or {})
print(json.dumps({'commit_sha': build.get('commit_sha'), 'release_id': build.get('release_id'), 'status': build.get('status')}, indent=2))
"
