#!/usr/bin/env bash
set -euo pipefail
DOCKER="sudo docker"
GIT="sudo git -c safe.directory=/opt/krowolf -C /opt/krowolf"
echo "=== GIT ==="
$GIT rev-parse HEAD
$GIT status --porcelain | wc -l
echo "=== IMAGE ==="
$DOCKER inspect krowolf-app-1 --format 'image={{.Config.Image}} digest={{.Image}}'
$DOCKER exec krowolf-app-1 cat /app/build-metadata.json
echo
echo "=== PREFLIGHT ==="
$DOCKER exec -e PYTHONPATH=/app krowolf-app-1 python3 scripts/ops/stabilization_preflight.py
echo "=== BASELINE ==="
$DOCKER exec -e PYTHONPATH=/app krowolf-app-1 python3 scripts/ops/niklas_live_clean_baseline.py T_NIKLAS_DEMO_001
echo "=== DB ==="
$DOCKER exec krowolf-db-1 psql -U postgres -d ai_platform -tAc "
SELECT 'tenants', count(*) FROM tenant_configs
UNION ALL SELECT 'jobs', count(*) FROM jobs
UNION ALL SELECT 'approvals', count(*) FROM approval_requests
UNION ALL SELECT 'tenant_alerts_open', count(*) FROM operator_alerts WHERE tenant_id='T_NIKLAS_DEMO_001' AND status='open'
UNION ALL SELECT 'oauth_source', credential_source FROM oauth_credentials WHERE provider='google_mail' LIMIT 1;
" 2>/dev/null || $DOCKER exec krowolf-db-1 psql -U postgres -d ai_platform -tAc "
SELECT 'tenants', count(*) FROM tenant_configs
UNION ALL SELECT 'jobs', count(*) FROM jobs
UNION ALL SELECT 'approvals', count(*) FROM approval_requests;
"
