#!/usr/bin/env bash
# K12 RC deploy to pilot — run ON SERVER as root/sudo.
set -euo pipefail

ROOT="/opt/krowolf"
DOCKER="sudo docker"
COMPOSE="sudo docker compose -f ${ROOT}/docker-compose.prod.yml"
RC_SHA="${1:?RC SHA required}"
RC_TAG="krowolf-app:rc-${RC_SHA:0:12}"
ROLLBACK_TAG="krowolf-app:rollback-e77b045d33c1"
ROLLBACK_IMAGE="e77b045d33c1"
LOG="/tmp/k12_rc_deploy.log"

exec > >(tee "$LOG") 2>&1
log() { echo "[rc-deploy] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

log "=== 1. Tag rollback image ==="
$DOCKER tag "krowolf-app@${ROLLBACK_IMAGE}" "$ROLLBACK_TAG" 2>/dev/null \
  || $DOCKER tag krowolf-app:latest "$ROLLBACK_TAG"
$DOCKER images krowolf-app --format '{{.Repository}}:{{.Tag}} {{.ID}}' | head -10

log "=== 2. Pause schedulers (all tenants) ==="
$DOCKER exec krowolf-db-1 psql -U postgres -d ai_platform -c \
  "UPDATE tenant_configs SET settings = jsonb_set(COALESCE(settings::jsonb,'{}'), '{scheduler,run_mode}', '\"paused\"')::json WHERE settings IS NOT NULL OR settings IS NULL;" \
  >/dev/null 2>&1 || true

log "=== 3. Build RC image ==="
cd "$ROOT"
export DOCKER_BUILDKIT=1
$DOCKER build \
  --build-arg BUILD_COMMIT_SHA="$RC_SHA" \
  --build-arg BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg RELEASE_ID="rc-${RC_SHA:0:12}" \
  -t krowolf-app:latest \
  -t "$RC_TAG" \
  -f Dockerfile .

log "=== 4. Deploy RC ==="
$COMPOSE up -d app
sleep 12

log "=== 5. Verify health ==="
$DOCKER exec krowolf-app-1 python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"

log "=== 6. Migration version ==="
$DOCKER exec krowolf-db-1 psql -U postgres -d ai_platform -tAc \
  "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;" | tr '\n' ' '
echo

log "Deploy complete: $RC_TAG"
echo "RC_TAG=$RC_TAG"
echo "ROLLBACK_TAG=$ROLLBACK_TAG"
