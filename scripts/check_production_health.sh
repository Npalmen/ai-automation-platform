#!/usr/bin/env bash
# check_production_health.sh — Single-command operator healthcheck.
#
# Checks app HTTP endpoints, Docker container status, disk usage, and backup
# freshness. Prints a concise PASS/FAIL summary. Exits non-zero if any
# required check fails. Sends an alert via ALERT_COMMAND when any check fails.
#
# Usage:
#   bash scripts/check_production_health.sh
#
# Quick production run:
#   APP_BASE_URL=https://api.krowolf.se \
#   DOCKER_APP_CONTAINER=krowolf-app-1 \
#   DOCKER_DB_CONTAINER=krowolf-db-1 \
#   DISK_CHECK_PATH=/opt/krowolf \
#   BACKUP_DIR=/opt/krowolf/backups \
#   bash /opt/krowolf/scripts/check_production_health.sh
#
# Environment variables:
#
#   APP_BASE_URL          Base URL of the application (default: http://localhost:8000)
#                         Used to check GET / — expects HTTP 200.
#
#   APP_HEALTH_URL        Full URL of the health endpoint
#                         (default: APP_BASE_URL/health)
#                         Expected response body: {"status":"ok",...}
#
#   HTTP_TIMEOUT          Curl timeout in seconds for each HTTP check (default: 10)
#
#   DOCKER_APP_CONTAINER  Name of the app Docker container.
#                         If set, checks that the container is in "running" state.
#                         Example: krowolf-app-1
#
#   DOCKER_DB_CONTAINER   Name of the DB Docker container.
#                         If set, checks that the container is in "running" state.
#                         Example: krowolf-db-1
#
#   DISK_CHECK_PATH       Filesystem path to check disk usage on (default: /)
#                         If set, alerts when usage >= DISK_USAGE_MAX_PERCENT.
#
#   DISK_USAGE_MAX_PERCENT  Max disk usage % before alerting (default: 80)
#
#   BACKUP_DIR            If set, runs scripts/check_backup_freshness.sh.
#                         Requires BACKUP_FRESHNESS_SCRIPT to be set or
#                         the script to be found relative to this script.
#
#   BACKUP_FRESHNESS_SCRIPT  Path to check_backup_freshness.sh
#                             (default: same dir as this script)
#
#   POSTGRES_DB           Database name passed to the freshness script (default: ai_platform)
#   BACKUP_MAX_AGE_HOURS  Max acceptable backup age in hours (default: 25)
#   BACKUP_MIN_SIZE_BYTES Min acceptable backup size in bytes (default: 1024)
#
#   ALERT_COMMAND         Optional shell command run when any check fails.
#                         The full summary is piped to it via stdin.
#                         Example: 'mail -s "Krowolf health alert" ops@krowolf.se'
#                         Example: 'curl -sS -X POST $SLACK_WEBHOOK -d @-'
#                         If unset or empty, no alert is sent (check still fails).
#
#   COMPOSE_FILE          Path to docker-compose.prod.yml for docker compose ps summary.
#                         If set, a compose ps table is appended to the report.
#
# Exit codes:
#   0  — all checks passed
#   1  — one or more checks failed

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────

APP_BASE_URL="${APP_BASE_URL:-http://localhost:8000}"
APP_HEALTH_URL="${APP_HEALTH_URL:-${APP_BASE_URL}/health}"
HTTP_TIMEOUT="${HTTP_TIMEOUT:-10}"

DOCKER_APP_CONTAINER="${DOCKER_APP_CONTAINER:-}"
DOCKER_DB_CONTAINER="${DOCKER_DB_CONTAINER:-}"

DISK_CHECK_PATH="${DISK_CHECK_PATH:-/}"
DISK_USAGE_MAX_PERCENT="${DISK_USAGE_MAX_PERCENT:-80}"

BACKUP_DIR="${BACKUP_DIR:-}"
POSTGRES_DB="${POSTGRES_DB:-ai_platform}"
BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS:-25}"
BACKUP_MIN_SIZE_BYTES="${BACKUP_MIN_SIZE_BYTES:-1024}"

ALERT_COMMAND="${ALERT_COMMAND:-}"
COMPOSE_FILE="${COMPOSE_FILE:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_FRESHNESS_SCRIPT="${BACKUP_FRESHNESS_SCRIPT:-${SCRIPT_DIR}/check_backup_freshness.sh}"

# ── state tracking ────────────────────────────────────────────────────────────

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %Z')"
FAILURES=0
WARNINGS=0
REPORT_LINES=()

# ── helpers ───────────────────────────────────────────────────────────────────

_pass() {
    local msg="  [PASS] $*"
    echo "$msg"
    REPORT_LINES+=("$msg")
}

_fail() {
    local msg="  [FAIL] $*"
    echo "$msg" >&2
    REPORT_LINES+=("$msg")
    FAILURES=$(( FAILURES + 1 ))
}

_warn() {
    local msg="  [WARN] $*"
    echo "$msg"
    REPORT_LINES+=("$msg")
    WARNINGS=$(( WARNINGS + 1 ))
}

_section() {
    local msg=""
    local msg2="── $* ──"
    echo ""
    echo "$msg2"
    REPORT_LINES+=("$msg")
    REPORT_LINES+=("$msg2")
}

# ── header ────────────────────────────────────────────────────────────────────

HEADER="Krowolf production healthcheck — ${TIMESTAMP}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "$HEADER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
REPORT_LINES+=("$HEADER")

# ── CHECK 1: App root endpoint ────────────────────────────────────────────────

_section "App root endpoint"
HTTP_CODE=$(curl -o /dev/null -s -w "%{http_code}" \
    --max-time "$HTTP_TIMEOUT" \
    --connect-timeout "$HTTP_TIMEOUT" \
    "$APP_BASE_URL" 2>/dev/null || echo "000")

if [[ "$HTTP_CODE" == "200" ]]; then
    _pass "GET ${APP_BASE_URL} → ${HTTP_CODE}"
else
    _fail "GET ${APP_BASE_URL} → ${HTTP_CODE} (expected 200)"
fi

# ── CHECK 2: /health endpoint ─────────────────────────────────────────────────

_section "App health endpoint"
HEALTH_BODY=$(curl -s --max-time "$HTTP_TIMEOUT" --connect-timeout "$HTTP_TIMEOUT" \
    "$APP_HEALTH_URL" 2>/dev/null || echo "")
HEALTH_CODE=$(curl -o /dev/null -s -w "%{http_code}" \
    --max-time "$HTTP_TIMEOUT" --connect-timeout "$HTTP_TIMEOUT" \
    "$APP_HEALTH_URL" 2>/dev/null || echo "000")

if [[ "$HEALTH_CODE" == "200" ]]; then
    # Verify {"status":"ok"} in response body
    if echo "$HEALTH_BODY" | grep -q '"status".*"ok"' 2>/dev/null; then
        _pass "GET ${APP_HEALTH_URL} → 200, status=ok"
    else
        _warn "GET ${APP_HEALTH_URL} → 200 but response body did not contain status=ok"
        _warn "  Body: $(echo "$HEALTH_BODY" | tr -d '\n' | head -c 120)"
    fi
else
    _fail "GET ${APP_HEALTH_URL} → ${HEALTH_CODE} (expected 200)"
fi

# ── CHECK 3: Docker app container ────────────────────────────────────────────

_section "Docker containers"

if [[ -n "$DOCKER_APP_CONTAINER" ]]; then
    if command -v docker &>/dev/null; then
        CONTAINER_STATE=$(docker inspect --format '{{.State.Status}}' \
            "$DOCKER_APP_CONTAINER" 2>/dev/null || echo "not_found")
        RESTART_COUNT=$(docker inspect --format '{{.RestartCount}}' \
            "$DOCKER_APP_CONTAINER" 2>/dev/null || echo "?")
        if [[ "$CONTAINER_STATE" == "running" ]]; then
            if [[ "$RESTART_COUNT" != "?" && "$RESTART_COUNT" -gt 5 ]]; then
                _warn "App container '${DOCKER_APP_CONTAINER}' is running but has restarted ${RESTART_COUNT} times"
            else
                _pass "App container '${DOCKER_APP_CONTAINER}' is ${CONTAINER_STATE} (restarts: ${RESTART_COUNT})"
            fi
        else
            _fail "App container '${DOCKER_APP_CONTAINER}' state=${CONTAINER_STATE} (expected running)"
        fi
    else
        _warn "docker not in PATH — cannot check DOCKER_APP_CONTAINER=${DOCKER_APP_CONTAINER}"
    fi
else
    _warn "DOCKER_APP_CONTAINER not set — skipping app container check"
fi

# ── CHECK 4: Docker DB container ─────────────────────────────────────────────

if [[ -n "$DOCKER_DB_CONTAINER" ]]; then
    if command -v docker &>/dev/null; then
        DB_STATE=$(docker inspect --format '{{.State.Status}}' \
            "$DOCKER_DB_CONTAINER" 2>/dev/null || echo "not_found")
        DB_RESTARTS=$(docker inspect --format '{{.RestartCount}}' \
            "$DOCKER_DB_CONTAINER" 2>/dev/null || echo "?")
        if [[ "$DB_STATE" == "running" ]]; then
            if [[ "$DB_RESTARTS" != "?" && "$DB_RESTARTS" -gt 5 ]]; then
                _warn "DB container '${DOCKER_DB_CONTAINER}' is running but has restarted ${DB_RESTARTS} times"
            else
                _pass "DB container '${DOCKER_DB_CONTAINER}' is ${DB_STATE} (restarts: ${DB_RESTARTS})"
            fi
        else
            _fail "DB container '${DOCKER_DB_CONTAINER}' state=${DB_STATE} (expected running)"
        fi
    else
        _warn "docker not in PATH — cannot check DOCKER_DB_CONTAINER=${DOCKER_DB_CONTAINER}"
    fi
else
    _warn "DOCKER_DB_CONTAINER not set — skipping DB container check"
fi

# ── CHECK 5: Disk usage ───────────────────────────────────────────────────────

_section "Disk usage"
if command -v df &>/dev/null; then
    # Get usage percent for the specified path — strip % sign.
    DISK_PCT=$(df "$DISK_CHECK_PATH" 2>/dev/null \
        | awk 'NR==2 {gsub(/%/,""); print $5}' || echo "")
    if [[ -z "$DISK_PCT" ]]; then
        _warn "Could not determine disk usage for path: ${DISK_CHECK_PATH}"
    elif [[ "$DISK_PCT" -ge "$DISK_USAGE_MAX_PERCENT" ]]; then
        _fail "Disk usage ${DISK_PCT}% >= threshold ${DISK_USAGE_MAX_PERCENT}% on ${DISK_CHECK_PATH}"
    else
        _pass "Disk usage ${DISK_PCT}% < ${DISK_USAGE_MAX_PERCENT}% threshold (${DISK_CHECK_PATH})"
    fi
else
    _warn "df not available — skipping disk check"
fi

# ── CHECK 6: Backup freshness ────────────────────────────────────────────────

_section "Backup freshness"
if [[ -n "$BACKUP_DIR" ]]; then
    if [[ -f "$BACKUP_FRESHNESS_SCRIPT" ]]; then
        FRESHNESS_OUTPUT=$(BACKUP_DIR="$BACKUP_DIR" \
            POSTGRES_DB="$POSTGRES_DB" \
            BACKUP_MAX_AGE_HOURS="$BACKUP_MAX_AGE_HOURS" \
            BACKUP_MIN_SIZE_BYTES="$BACKUP_MIN_SIZE_BYTES" \
            bash "$BACKUP_FRESHNESS_SCRIPT" 2>&1) \
            && FRESHNESS_EXIT=0 || FRESHNESS_EXIT=$?
        if [[ "$FRESHNESS_EXIT" -eq 0 ]]; then
            # Extract the summary line (last OK line)
            NEWEST=$(echo "$FRESHNESS_OUTPUT" | grep "Most recent backup:" | sed 's/.*Most recent backup: //')
            AGE=$(echo "$FRESHNESS_OUTPUT" | grep "Backup age:" | sed 's/.*Backup age: //')
            _pass "Backup freshness OK — ${AGE:-see below}"
            if [[ -n "$NEWEST" ]]; then
                _pass "  Newest: ${NEWEST}"
            fi
        else
            # Extract FAIL lines from freshness output
            FAIL_MSG=$(echo "$FRESHNESS_OUTPUT" | grep '\[freshness\] FAIL' | head -3 \
                | sed 's/\[freshness\] FAIL: //' || echo "see freshness script output")
            _fail "Backup freshness check failed: ${FAIL_MSG}"
        fi
    else
        _warn "BACKUP_FRESHNESS_SCRIPT not found: ${BACKUP_FRESHNESS_SCRIPT}"
        _warn "  Manually check: ls -lh ${BACKUP_DIR}/"
    fi
else
    _warn "BACKUP_DIR not set — skipping backup freshness check"
fi

# ── CHECK 7: Docker Compose status (optional summary) ────────────────────────

if [[ -n "$COMPOSE_FILE" ]] && command -v docker &>/dev/null; then
    _section "Docker Compose status"
    COMPOSE_OUT=$(docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || echo "unavailable")
    echo "$COMPOSE_OUT"
    REPORT_LINES+=("$COMPOSE_OUT")
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$FAILURES" -eq 0 && "$WARNINGS" -eq 0 ]]; then
    SUMMARY="HEALTHY — all checks passed at ${TIMESTAMP}"
    echo "  ${SUMMARY}"
elif [[ "$FAILURES" -eq 0 ]]; then
    SUMMARY="WARNING — ${WARNINGS} warning(s), 0 failures at ${TIMESTAMP}"
    echo "  ${SUMMARY}"
else
    SUMMARY="UNHEALTHY — ${FAILURES} failure(s), ${WARNINGS} warning(s) at ${TIMESTAMP}"
    echo "  ${SUMMARY}" >&2
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
REPORT_LINES+=("$SUMMARY")

# ── Alert hook ────────────────────────────────────────────────────────────────

if [[ "$FAILURES" -gt 0 && -n "$ALERT_COMMAND" ]]; then
    FULL_REPORT="$(printf '%s\n' "${REPORT_LINES[@]}")"
    echo ""
    echo "  Sending alert via ALERT_COMMAND..."
    echo "$FULL_REPORT" | eval "$ALERT_COMMAND" 2>/dev/null \
        || echo "  [WARN] Alert command failed or produced no output." >&2
fi

# ── Exit code ────────────────────────────────────────────────────────────────

if [[ "$FAILURES" -gt 0 ]]; then
    exit 1
fi
exit 0
