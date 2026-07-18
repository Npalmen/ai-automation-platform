#!/usr/bin/env bash
set -euo pipefail
echo "=== ALLOWED_ORIGINS (not a secret) ==="
sudo grep '^ALLOWED_ORIGINS=' /opt/krowolf/.env.production 2>/dev/null || echo 'ALLOWED_ORIGINS=not_set'
echo "=== ADMIN_USERNAME (not a secret) ==="
sudo grep '^ADMIN_USERNAME=' /opt/krowolf/.env.production 2>/dev/null || echo 'ADMIN_USERNAME=not_set'
echo "=== SESSION AUTH CONFIGURED ==="
sudo grep -c '^ADMIN_PASSWORD_HASH=' /opt/krowolf/.env.production 2>/dev/null || true
sudo grep -c '^ADMIN_PASSWORD=' /opt/krowolf/.env.production 2>/dev/null || true
