#!/usr/bin/env bash
# Create RC bundle tarball from local repo (excludes secrets, node_modules, storage).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/k12-rc-bundle.tar.gz}"
cd "$ROOT"
tar -czf "$OUT" \
  --exclude='node_modules' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/dist' \
  --exclude='.git' \
  --exclude='storage' \
  --exclude='.env*' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  app frontend scripts migrations infra requirements.txt Dockerfile docker-compose.prod.yml
echo "BUNDLE=$OUT"
sha256sum "$OUT" 2>/dev/null || shasum -a 256 "$OUT"
