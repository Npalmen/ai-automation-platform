#!/bin/sh
set -eu

STORAGE_ROOT="/app/storage"
for relative in status tenant_keys local_dev/logs; do
  dir="${STORAGE_ROOT}/${relative}"
  mkdir -p "${dir}"
  chmod 0750 "${dir}"
done

exec "$@"
