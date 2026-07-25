#!/usr/bin/env bash
set -euo pipefail
echo "=== OLD bundle rc-967df7a181b7 ==="
docker run --rm krowolf-app:rc-967df7a181b7 sh -c '
JS=/app/frontend/dist/assets/index-CZD0W4zR.js
echo index=$(cat /app/frontend/dist/index.html | grep -o "index-[^\"]*\.js")
grep -c isRoleAllowed "$JS" 2>/dev/null || echo isRoleAllowed_count=0
grep -c "Ny kund" "$JS" || true
grep -c super_admin "$JS" || true
'

echo "=== NEW bundle deployed ==="
docker exec krowolf-app-1 sh -c '
JS=/app/frontend/dist/assets/index-DiSFbwfh.js
grep -c isRoleAllowed "$JS" 2>/dev/null || echo isRoleAllowed_count=0
grep -c "Ny kund" "$JS" || true
grep -c super_admin "$JS" || true
'
