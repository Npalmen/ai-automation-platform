#!/usr/bin/env bash
set -euo pipefail
# Set ADMIN_ROLE in .env.production only; restart app container only.
ROLE="${1:-read_only}"
ENV_FILE="/opt/krowolf/.env.production"
if ! grep -q '^ADMIN_ROLE=' "$ENV_FILE" 2>/dev/null; then
  echo "ADMIN_ROLE=$ROLE" | sudo tee -a "$ENV_FILE" >/dev/null
else
  sudo sed -i "s/^ADMIN_ROLE=.*/ADMIN_ROLE=$ROLE/" "$ENV_FILE"
fi
echo "SET_ADMIN_ROLE=$ROLE"
grep '^ADMIN_ROLE=' "$ENV_FILE"
cd /opt/krowolf
sudo docker compose -f docker-compose.prod.yml up -d --no-deps app
sleep 3
sudo docker compose -f docker-compose.prod.yml ps app
sudo docker inspect krowolf-app-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep '^ADMIN_ROLE=' || echo ADMIN_ROLE=missing_after_restart
