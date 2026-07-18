#!/usr/bin/env bash
set -euo pipefail
# Extract RC bundle preserving .env.production
BUNDLE="${1:-/tmp/k12-rc-bundle.tar.gz}"
ROOT="/opt/krowolf"
STAGING="/tmp/k12-rc-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"
tar -xzf "$BUNDLE" -C "$STAGING"
for item in app frontend scripts migrations infra requirements.txt Dockerfile docker-compose.prod.yml; do
  if [[ -e "$STAGING/$item" ]]; then
    rm -rf "${ROOT:?}/$item"
    cp -a "$STAGING/$item" "$ROOT/"
  fi
done
# Normalize line endings for shell scripts
find "$ROOT/scripts" -name '*.sh' -exec sed -i 's/\r$//' {} +
echo "Synced RC bundle to $ROOT"
