# Runbook: Monitoring and Alerting

> **Goal:** A single operator can run one command and immediately know whether
> the app, database, containers, disk, and backups are healthy.
> **No-secrets rule:** Never commit emails, webhook URLs, API keys, or credentials
> to this runbook or to any script. All sensitive values live in `.env.production`
> on the server.

---

## Overview

The platform ships a single healthcheck script that covers all critical signals
for the first controlled pilot:

| Script | Purpose |
|--------|---------|
| `scripts/check_production_health.sh` | One-command health check: app HTTP, containers, disk, backup freshness |
| `scripts/check_backup_freshness.sh` | Called internally by the health script |

The health check can be run manually, scheduled in cron, and wired to an
alerting hook via `ALERT_COMMAND` without committing any secrets.

---

## Environment variables

Configure these in `/opt/krowolf/.env.production` on the server, or export them
before running the script:

```bash
# ── Application endpoints ───────────────────────────────────────
APP_BASE_URL=https://api.krowolf.se      # Checked on GET /
APP_HEALTH_URL=https://api.krowolf.se/health  # Checked for {"status":"ok"}
HTTP_TIMEOUT=10                           # curl timeout per request (seconds)

# ── Docker containers ────────────────────────────────────────────
DOCKER_APP_CONTAINER=krowolf-app-1       # Name of the app container
DOCKER_DB_CONTAINER=krowolf-db-1         # Name of the DB container

# ── Disk usage ───────────────────────────────────────────────────
DISK_CHECK_PATH=/opt/krowolf             # Filesystem path to check
DISK_USAGE_MAX_PERCENT=80                # Alert when usage >= this value

# ── Backup freshness ─────────────────────────────────────────────
BACKUP_DIR=/opt/krowolf/backups          # Directory containing backup files
POSTGRES_DB=ai_platform                  # Database name for backup file pattern
BACKUP_MAX_AGE_HOURS=25                  # Alert if newest backup is older than this
BACKUP_MIN_SIZE_BYTES=1024               # Alert if newest backup is smaller than this

# ── Compose (optional) ───────────────────────────────────────────
COMPOSE_FILE=/opt/krowolf/docker-compose.prod.yml  # Appends compose ps summary

# ── Alerting ─────────────────────────────────────────────────────
# Command run (with report piped to stdin) when any check fails.
# Set in .env.production — do NOT commit real addresses here.
# Example (email):   ALERT_COMMAND='mail -s "Krowolf alert" ops@krowolf.se'
# Example (webhook): ALERT_COMMAND='curl -sS -X POST https://hooks.slack.com/... -d @-'
ALERT_COMMAND=
```

---

## Daily operator check

Run this every morning before reviewing the approval queue:

```bash
ssh ubuntu@api.krowolf.se

sudo \
  APP_BASE_URL=https://api.krowolf.se \
  DOCKER_APP_CONTAINER=krowolf-app-1 \
  DOCKER_DB_CONTAINER=krowolf-db-1 \
  DISK_CHECK_PATH=/opt/krowolf \
  BACKUP_DIR=/opt/krowolf/backups \
  bash /opt/krowolf/scripts/check_production_health.sh
```

### Expected healthy output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Krowolf production healthcheck — 2026-07-08 10:00:00 UTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

── App root endpoint ──
  [PASS] GET https://api.krowolf.se → 200

── App health endpoint ──
  [PASS] GET https://api.krowolf.se/health → 200, status=ok

── Docker containers ──
  [PASS] App container 'krowolf-app-1' is running (restarts: 0)
  [PASS] DB container 'krowolf-db-1' is running (restarts: 0)

── Disk usage ──
  [PASS] Disk usage 34% < 80% threshold (/opt/krowolf)

── Backup freshness ──
  [PASS] Backup freshness OK — 7h
  [PASS]   Newest: /opt/krowolf/backups/ai_platform_2026-07-08-020001.sql.gz

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HEALTHY — all checks passed at 2026-07-08 10:00:00 UTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Exit code 0 = healthy. Any `[FAIL]` line causes exit code 1.

---

## Cron setup

Schedule the health check to run every 5 minutes during the pilot:

```bash
ssh ubuntu@api.krowolf.se
sudo crontab -e

# Add these lines:

# Health check every 5 minutes — alert on failure
*/5 * * * * \
  APP_BASE_URL=https://api.krowolf.se \
  DOCKER_APP_CONTAINER=krowolf-app-1 \
  DOCKER_DB_CONTAINER=krowolf-db-1 \
  DISK_CHECK_PATH=/opt/krowolf \
  BACKUP_DIR=/opt/krowolf/backups \
  ALERT_COMMAND='mail -s "Krowolf health FAIL" ops@krowolf.se' \
  bash /opt/krowolf/scripts/check_production_health.sh \
  >> /var/log/krowolf-health.log 2>&1

# Daily backup at 02:00 (if not already set)
0 2 * * * \
  DOCKER_DB_CONTAINER=krowolf-db-1 \
  POSTGRES_DB=ai_platform \
  BACKUP_DIR=/opt/krowolf/backups \
  bash /opt/krowolf/scripts/backup_postgres.sh \
  >> /var/log/krowolf-backup.log 2>&1

# Verify cron is active
sudo crontab -l
```

> **Note on ALERT_COMMAND in cron:** Do not put webhook URLs or email addresses
> in the committed crontab if the crontab is tracked in version control.
> Use a wrapper script that sources `/opt/krowolf/.env.production` instead:
>
> ```bash
> #!/usr/bin/env bash
> set -a; source /opt/krowolf/.env.production; set +a
> exec bash /opt/krowolf/scripts/check_production_health.sh
> ```

---

## Alert setup

### Email (requires `mailutils` on server)

```bash
# Install mailutils (one-time)
sudo apt-get install -y mailutils

# Test alert manually
ALERT_COMMAND='mail -s "Krowolf test alert" ops@krowolf.se' \
  APP_BASE_URL=http://intentionally-wrong-host \
  bash /opt/krowolf/scripts/check_production_health.sh || echo "alert should have fired"
```

### Webhook (Slack, Discord, generic)

```bash
# Set in .env.production — not committed here
ALERT_COMMAND='curl -sS -X POST "${SLACK_WEBHOOK_URL}" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"Krowolf health check FAILED. Check /var/log/krowolf-health.log\"}"'
```

### Custom wrapper

```bash
# /opt/krowolf/scripts/alert.sh
#!/usr/bin/env bash
# Read full report from stdin; forward to your preferred channel.
REPORT=$(cat)
echo "$REPORT" | mail -s "Krowolf ALERT" ops@krowolf.se
# Add other channels as needed (Slack webhook, SMS API, etc.)

# Use it:
# ALERT_COMMAND='bash /opt/krowolf/scripts/alert.sh'
```

---

## What to do if app is down

**Symptom:** `[FAIL] GET https://api.krowolf.se → 000` or non-200 HTTP code.

1. **Check container status:**
   ```bash
   sudo docker compose -f /opt/krowolf/docker-compose.prod.yml ps
   sudo docker compose -f /opt/krowolf/docker-compose.prod.yml logs --tail=100 app
   ```

2. **Restart the app container (if container is not running):**
   ```bash
   cd /opt/krowolf
   sudo docker compose -f docker-compose.prod.yml up -d app
   ```
   Wait 30 seconds, then re-run the health check.

3. **If restart doesn't help — check logs for Python errors:**
   ```bash
   sudo docker compose -f /opt/krowolf/docker-compose.prod.yml logs --tail=300 app 2>&1 | grep -Ei "error|exception|traceback|critical"
   ```

4. **If DB is also down, fix DB first** (see DB section below).

5. **Escalate to P2** if app cannot be restarted. See `docs/runbooks/incident-response.md`.

---

## What to do if DB is down

**Symptom:** `[FAIL] DB container 'krowolf-db-1' state=exited` or container not found.

1. **Check container status and logs:**
   ```bash
   sudo docker ps -a | grep db
   sudo docker logs krowolf-db-1 --tail=50
   ```

2. **Restart the DB container:**
   ```bash
   cd /opt/krowolf
   sudo docker compose -f docker-compose.prod.yml up -d db
   ```
   Wait for the DB healthcheck to pass (usually 10–30 seconds):
   ```bash
   sudo docker compose -f docker-compose.prod.yml ps db
   # Expect: Status "healthy"
   ```

3. **Check disk space first if DB failed to start** — a full disk is a common cause.

4. **After DB is up, restart the app** (it may have failed to connect on startup):
   ```bash
   sudo docker compose -f docker-compose.prod.yml up -d app
   ```

5. **Escalate to P1** if the DB volume is corrupt. Take a backup from offsite if needed. See `docs/runbooks/backup-and-restore.md`.

---

## What to do if disk is high

**Symptom:** `[FAIL] Disk usage 85% >= threshold 80% on /opt/krowolf`

1. **Check what is using space:**
   ```bash
   df -h /opt/krowolf
   du -sh /opt/krowolf/backups/* | sort -h | tail -10
   sudo docker system df
   ```

2. **Prune old backups (if retention is not running):**
   ```bash
   # List backups older than 30 days
   find /opt/krowolf/backups -name "*.sql.gz" -mtime +30 -ls

   # Remove them (dry-run first with -ls, then remove)
   find /opt/krowolf/backups -name "*.sql.gz" -mtime +30 -delete
   ```

3. **Prune Docker images and volumes:**
   ```bash
   sudo docker image prune -f
   sudo docker volume prune -f   # CAUTION: only run if you know what volumes exist
   ```

4. **Check log file size:**
   ```bash
   ls -lh /var/log/krowolf-*.log
   # Rotate if large:
   sudo truncate -s 0 /var/log/krowolf-health.log
   ```

5. **Alert threshold:** Raise `DISK_USAGE_MAX_PERCENT` only after adding more storage — do not silence the alert without fixing the root cause.

---

## What to do if backup is stale

**Symptom:** `[FAIL] Backup is too old (Nh > 25h maximum)`

1. **Run a manual backup immediately:**
   ```bash
   sudo \
     DOCKER_DB_CONTAINER=krowolf-db-1 \
     POSTGRES_DB=ai_platform \
     BACKUP_DIR=/opt/krowolf/backups \
     bash /opt/krowolf/scripts/backup_postgres.sh
   ```

2. **Re-run the freshness check to confirm:**
   ```bash
   sudo BACKUP_DIR=/opt/krowolf/backups bash /opt/krowolf/scripts/check_backup_freshness.sh
   ```

3. **Check why the cron job is not running:**
   ```bash
   sudo crontab -l | grep backup
   sudo grep krowolf-backup /var/log/syslog | tail -20  # or journalctl
   ```

4. **Fix the cron job** and verify at least one backup per day is created.

5. **Check offsite upload:** If the freshness check passes locally but offsite is not updated, verify `OFFSITE_BACKUP_COMMAND` in `.env.production`.

---

## What to do if a container keeps restarting

**Symptom:** `[WARN] App container 'krowolf-app-1' has restarted N times` with N > 5.

1. **Check logs for the crash reason:**
   ```bash
   sudo docker logs krowolf-app-1 --tail=100 2>&1 | grep -Ei "error|exception|traceback|exit"
   ```

2. **Common causes:**
   - Missing env var → check `/opt/krowolf/.env.production` is complete
   - DB not ready → check DB container is healthy first
   - Port conflict → check `docker ps` for port 8000 conflicts
   - OOM killed → check `dmesg | grep -i kill | tail -10`

3. **If DB missing → fix DB first, then restart app.**

4. **If env var missing:**
   ```bash
   sudo nano /opt/krowolf/.env.production
   sudo docker compose -f /opt/krowolf/docker-compose.prod.yml up -d app
   ```

5. **Escalate to P2** if restart loop cannot be resolved within 30 minutes. See `docs/runbooks/incident-response.md`.

---

## Escalation / incident severity

| Check | Failure = Severity | Response time |
|-------|-------------------|---------------|
| App root returns non-200 | P2 High | Within 1 hour |
| App health returns non-200 or no status=ok | P2 High | Within 1 hour |
| DB container not running | P1 Critical | Immediate |
| App container not running | P2 High | Within 1 hour |
| Disk usage ≥ 90% | P2 High | Within 1 hour |
| Disk usage ≥ 80% (threshold default) | P3 Medium | Within 4 hours |
| Backup older than 25h | P3 Medium | Within 4 hours |
| Backup older than 48h | P2 High | Within 1 hour |
| Container restart count > 5 | P3 Medium → P2 if increasing | Within 4 hours |

Severity definitions: see `docs/runbooks/incident-response.md`.

---

## Monitoring log

Check the health log for recent history:

```bash
# View last 100 health check results
sudo tail -100 /var/log/krowolf-health.log

# Count failures in the last 24h
sudo grep "UNHEALTHY" /var/log/krowolf-health.log | grep "$(date +%Y-%m-%d)" | wc -l

# View only FAIL lines
sudo grep "\[FAIL\]" /var/log/krowolf-health.log | tail -20
```

---

## No-secrets policy

- Never commit `ALERT_COMMAND` values with real email addresses or webhook URLs.
- Never commit API keys, passwords, or tokens in this runbook or in cron comments.
- Store all secrets exclusively in `/opt/krowolf/.env.production` on the server.
- Rotate `.env.production` values if they are accidentally committed or logged.
- The health script does not print `POSTGRES_PASSWORD`, `ADMIN_API_KEY`, or any other secret — only container names and HTTP status codes appear in output.

---

## Related runbooks

- `docs/runbooks/backup-and-restore.md` — backup procedures and restore rehearsal
- `docs/runbooks/incident-response.md` — P1/P2/P3 incident procedures
- `docs/runbooks/failed-jobs.md` — job failure recovery
- `docs/PILOT_READINESS_CHECKLIST.md` — monitoring items (REQUIRED/RECOMMENDED)

---

## Platform operator alerts (Kapitel 10)

Internal operator alerts (`operator_alerts`) complement external monitoring:

| Signal class | Source | Example |
|--------------|--------|---------|
| `intern_db_detected` | Database queries (jobs, approvals, integration events) | Stale approval, stuck job |
| `intern_metadata_detected` | Operation status files (backup/restore/build metadata) | Stale backup |
| `externally_detected` | **Not** stored in `operator_alerts` | Total app/DB outage via `scripts/check_production_health.sh` |

**Total outage:** Use external health checks and `ALERT_COMMAND` (this runbook). The evaluation engine does not emit internal alerts when the database is unreachable.

**In-app alertcenter:** React operator panel at `/ops/alerts` (summary, list, detail, acknowledge/resolve).

**Email defer policy:** Platform email notifications are deferred until `OPERATOR_ALERT_RECIPIENT` is set in server env. Until then, alerts are in-app only.

**Evaluation model:** One advisory lock per run; short transaction per evaluator; evaluator failures logged in run record and audit (`alert.evaluation_evaluator_failed`) without inline meta-alerts.

**Scheduler alerts:** `tenant.scheduler_failed` only when `scheduler.run_mode=scheduled` (expected_state=running). Paused/manual tenants do not generate scheduler failure alerts.

**Legacy tenant email alerts:** `app/alerts/engine.py` remains for per-tenant `settings.alerts.recipient_email`. `GET /admin/alerts/run-all` runs both platform evaluation and legacy tenant passes.
