#!/usr/bin/env bash
set -euo pipefail
TAG="${1:-krowolf-app:rollback-e77b045d33c1}"
DOCKER="sudo docker"
COMPOSE="sudo docker compose -f /opt/krowolf/docker-compose.prod.yml"
log() { echo "[rollback] $*"; }
log "Rolling back to $TAG"
$DOCKER tag "$TAG" krowolf-app:latest
cd /opt/krowolf && $COMPOSE up -d app
sleep 10
$DOCKER exec krowolf-app-1 python -c "import urllib.request; print('health', urllib.request.urlopen('http://127.0.0.1:8000/health').status)"
