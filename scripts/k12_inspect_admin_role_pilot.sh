#!/usr/bin/env bash
set -euo pipefail
cd /opt/krowolf

echo "=== COMPOSE ADMIN_ROLE ==="
grep -n ADMIN_ROLE docker-compose.prod.yml 2>/dev/null || echo "none_in_compose"

echo "=== ENV PRODUCTION ADMIN_ROLE ==="
if sudo grep -q '^ADMIN_ROLE=' /opt/krowolf/.env.production 2>/dev/null; then
  sudo grep '^ADMIN_ROLE=' /opt/krowolf/.env.production
else
  echo "ADMIN_ROLE=not_set"
fi

echo "=== COMPOSE OVERRIDES ==="
for f in docker-compose.override.yml docker-compose.prod.override.yml; do
  if test -f "$f"; then
    echo "FILE=$f"
    grep -n ADMIN_ROLE "$f" || echo "none"
  fi
done

echo "=== CONTAINER ADMIN_ROLE ==="
sudo docker inspect krowolf-app-1 --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep '^ADMIN_ROLE=' || echo "ADMIN_ROLE=not_in_container"

echo "=== COMPOSE ENV_FILE REF ==="
grep -n env_file docker-compose.prod.yml | head -5
