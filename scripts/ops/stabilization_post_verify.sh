#!/usr/bin/env bash
set -euo pipefail
DOCKER="sudo docker"
echo "=== IMAGE ==="
$DOCKER inspect krowolf-app-1 --format 'image={{.Config.Image}} id={{.Image}} created={{.Created}}'
echo "=== BUILD METADATA ==="
$DOCKER exec krowolf-app-1 cat /app/build-metadata.json
echo
echo "=== STATUS FILES ==="
ls -la /opt/krowolf/storage/status/pre_live_niklas_archive.json \
  /opt/krowolf/storage/status/niklas_live_clean_baseline.json \
  /opt/krowolf/storage/status/stabilization_server_inventory.json 2>/dev/null || true
echo "=== DB COUNTS ==="
$DOCKER exec krowolf-db-1 psql -U postgres -d ai_platform -tAc "
SELECT 'tenants', count(*) FROM tenant_configs
UNION ALL SELECT 'jobs', count(*) FROM jobs
UNION ALL SELECT 'approvals', count(*) FROM approval_requests
UNION ALL SELECT 'alerts_open', count(*) FROM operator_alerts WHERE status='open'
UNION ALL SELECT 'incidents', count(*) FROM incidents
UNION ALL SELECT 'oauth_google', count(*) FROM oauth_credentials WHERE provider='google_mail';
"
echo "=== PREFLIGHT ==="
$DOCKER exec -e PYTHONPATH=/app krowolf-app-1 python3 scripts/ops/stabilization_preflight.py
