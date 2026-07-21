#!/usr/bin/env bash
set -euo pipefail

IMAGE="${1:?image tag required}"
CONTAINER_NAME="${CONTAINER_NAME:-ai-platform-ci-health}"
STORAGE_MOUNT="${STORAGE_MOUNT:-}"
DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:5432/ai_platform}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"

if [[ -z "${STORAGE_MOUNT}" ]]; then
  STORAGE_MOUNT="$(mktemp -d)"
  REMOVE_MOUNT=1
else
  REMOVE_MOUNT=0
fi

cleanup() {
  status=$?
  echo "--- container logs (${CONTAINER_NAME}) ---"
  docker logs "${CONTAINER_NAME}" 2>&1 || true
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  if [[ "${REMOVE_MOUNT}" -eq 1 ]]; then
    rm -rf "${STORAGE_MOUNT}" || true
  fi
  exit "${status}"
}
trap cleanup EXIT

mkdir -p "${STORAGE_MOUNT}"
if [[ -n "$(ls -A "${STORAGE_MOUNT}")" ]]; then
  echo "storage mount must start empty: ${STORAGE_MOUNT}" >&2
  exit 1
fi

echo "Starting ${IMAGE} with empty storage mount at ${STORAGE_MOUNT}"
docker run -d \
  --name "${CONTAINER_NAME}" \
  --network host \
  -v "${STORAGE_MOUNT}:/app/storage" \
  -e ENV=test \
  -e DATABASE_URL="${DATABASE_URL}" \
  -e ADMIN_API_KEY=ci-admin-key \
  -e TENANT_API_KEYS='{"TENANT_1001":"ci-tenant-key"}' \
  "${IMAGE}"

ready=0
for _ in $(seq 1 45); do
  if curl -sf "${HEALTH_URL}" >/tmp/ci_health.json 2>/dev/null; then
    ready=1
    break
  fi
  sleep 2
done

if [[ "${ready}" -ne 1 ]]; then
  echo "/health did not become reachable at ${HEALTH_URL}" >&2
  exit 1
fi

python - <<'PY'
import json
import sys

with open("/tmp/ci_health.json", encoding="utf-8") as handle:
    payload = json.load(handle)
if payload.get("status") != "ok":
    raise SystemExit(f"/health payload unexpected: {payload!r}")
print("/health returned 200 with status=ok")
PY

for relative in status tenant_keys local_dev/logs; do
  host_path="${STORAGE_MOUNT}/${relative}"
  if [[ ! -d "${host_path}" ]]; then
    echo "missing storage directory after bootstrap: ${host_path}" >&2
    exit 1
  fi
  mode="$(stat -c '%a' "${host_path}")"
  if [[ "${mode}" != "750" ]]; then
    echo "unexpected mode for ${host_path}: ${mode} (expected 750)" >&2
    exit 1
  fi
  echo "verified ${host_path} mode=${mode}"
done

echo "Docker runtime health verification passed"
