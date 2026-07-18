#!/usr/bin/env bash
set -euo pipefail
curl -sf -o /dev/null -w 'HEALTH_HTTP=%{http_code}\n' https://api.krowolf.se/health
cd /opt/krowolf
sudo docker compose -f docker-compose.prod.yml ps app db caddy
echo "APP_STARTED=$(sudo docker inspect krowolf-app-1 --format '{{.State.StartedAt}}')"
echo "DB_STARTED=$(sudo docker inspect krowolf-db-1 --format '{{.State.StartedAt}}')"
echo "CADDY_STARTED=$(sudo docker inspect krowolf-caddy-1 --format '{{.State.StartedAt}}')"
