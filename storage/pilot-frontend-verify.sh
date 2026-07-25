#!/usr/bin/env bash
set -euo pipefail
ROOT="/opt/krowolf"
KEY="$(grep ^ADMIN_API_KEY= "${ROOT}/.env.production" | cut -d= -f2- | tr -d '"' | tr -d "'")"

echo "=== origin/main on server ==="
cd "$ROOT" && git rev-parse HEAD

echo "=== system status ==="
curl -sk "https://api.krowolf.se/admin/system/status" -H "X-Admin-API-Key: ${KEY}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);cb=d['deployment']['current_build'];print('current_build.commit_sha',cb.get('commit_sha'));print('current_build.release_id',cb.get('release_id'));print('runtime.api',d['runtime']['api']['details'].get('commit_sha'))"

echo "=== build-metadata.json ==="
docker exec krowolf-app-1 cat /app/build-metadata.json

echo "=== container ==="
docker inspect -f 'started={{.State.StartedAt}} image={{.Config.Image}}' krowolf-app-1
docker images krowolf-app --format '{{.Repository}}:{{.Tag}} {{.ID}}' | head -6

echo "=== index.html asset refs ==="
docker exec krowolf-app-1 cat /app/frontend/dist/index.html

echo "=== bundle grep (container) ==="
JS="$(docker exec krowolf-app-1 sh -c 'ls /app/frontend/dist/assets/index-*.js | head -1')"
echo "js_file=$JS"
docker exec krowolf-app-1 sh -c "grep -o 'isRoleAllowed' '$JS' | head -1 || true"
docker exec krowolf-app-1 sh -c "grep -o 'super_admin' '$JS' | head -1 || true"
docker exec krowolf-app-1 sh -c "grep -o 'Ny kund' '$JS' | head -1 || true"
docker exec krowolf-app-1 sh -c "grep -o 'customers/new' '$JS' | head -1 || true"
docker exec krowolf-app-1 sh -c "grep -E 'role===\\\"admin\\\"|role===\\\"operations\\\"' '$JS' | head -3 || true"

echo "=== source on server checkout ==="
grep -n 'isRoleAllowed\|Ny kund' "$ROOT/frontend/src/features/customers/CustomersListPage.tsx" || true
