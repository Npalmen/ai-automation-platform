#!/usr/bin/env bash
# Del D — secret-free server worktree inventory (no pull/reset).
set -euo pipefail
ROOT="/opt/krowolf"
OUT="/opt/krowolf/storage/status/stabilization_server_inventory.json"
GIT=(sudo git -c safe.directory="$ROOT")
DOCKER="sudo docker"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$(dirname "$OUT")"

HEAD="$("${GIT[@]}" -C "$ROOT" rev-parse HEAD 2>/dev/null || echo missing)"
ORIGIN="$("${GIT[@]}" -C "$ROOT" fetch origin main 2>/dev/null && "${GIT[@]}" -C "$ROOT" rev-parse origin/main 2>/dev/null || echo missing)"
AHEAD_BEHIND="$("${GIT[@]}" -C "$ROOT" rev-list --left-right --count HEAD...origin/main 2>/dev/null || echo '0 0')"
MODIFIED="$("${GIT[@]}" -C "$ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
UNTRACKED="$("${GIT[@]}" -C "$ROOT" ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')"
DIFF_STAT="$("${GIT[@]}" -C "$ROOT" diff --stat origin/main 2>/dev/null | tail -1 || true)"

IMAGE="$($DOCKER inspect krowolf-app-1 --format '{{.Config.Image}}' 2>/dev/null || echo missing)"
IMAGE_ID="$($DOCKER inspect krowolf-app-1 --format '{{.Image}}' 2>/dev/null || echo missing)"
CREATED="$($DOCKER inspect krowolf-app-1 --format '{{.Created}}' 2>/dev/null || echo missing)"
BUILD_COMMIT="$($DOCKER exec krowolf-app-1 printenv BUILD_COMMIT_SHA 2>/dev/null || echo missing)"

python3 - <<PY
import json
from pathlib import Path

report = {
    "report": "stabilization_server_inventory",
    "generated_at": "$TS",
    "server_head": "$HEAD",
    "origin_main": "$ORIGIN",
    "ahead_behind": "$AHEAD_BEHIND",
    "tracked_modifications_count": int("$MODIFIED"),
    "untracked_files_count": int("$UNTRACKED"),
    "diff_stat_vs_origin_main": """$DIFF_STAT""".strip(),
    "container": {
        "image": "$IMAGE",
        "image_id": "$IMAGE_ID",
        "created": "$CREATED",
        "build_commit_sha": "$BUILD_COMMIT",
    },
    "preserved_runtime_paths": [
        "/opt/krowolf/.env.production",
        "/opt/krowolf/.env.offsite",
        "/opt/krowolf/.env.browser-test",
        "/opt/krowolf/storage",
        "/opt/krowolf/backups",
    ],
}
Path("$OUT").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"written": "$OUT", "server_head": "$HEAD", "origin_main": "$ORIGIN"}, indent=2))
PY
