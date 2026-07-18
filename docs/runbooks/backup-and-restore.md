# Runbook: Backup and Restore

> **Policy:** Always take a fresh backup before any destructive operation
> (tenant provisioning, DB schema change, credential rotation, deployment).
> **Recovery objective:** Ability to restore DB from backup within 1 hour.
> **No-secrets policy:** Never commit, print, or log database passwords,
> credentials, or access tokens in backup scripts, runbook commands, or test output.

---

## Backup strategy

| Backup type | Frequency | Location | Retention |
|-------------|-----------|----------|-----------|
| Automated daily | Daily at 02:00 server time via cron | `/opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz` | 30 days local (configured via `BACKUP_RETENTION_DAYS`) |
| Manual pre-operation | Before any destructive change | `/opt/krowolf/backups/ai_platform_<timestamp>.sql.gz` | Until operation confirmed stable |
| Offsite copy | After each local backup | Remote storage (see Offsite section) | Configure separately in remote storage |

**Current status:** Local backup script is in `scripts/backup_postgres.sh`.
Offsite upload is **not yet configured** — this is a **BLOCKER before first real customer pilot**.
Set `OFFSITE_BACKUP_COMMAND` in `/opt/krowolf/.env.production` and verify a test upload before pilot (see Offsite section).

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/backup_postgres.sh` | Create timestamped, compressed backup; prune old locals; optionally upload offsite |
| `scripts/restore_postgres_rehearsal.sh` | Restore to a separate DB; verify tables; refuse production target |
| `scripts/restore_from_offsite_rehearsal.sh` | Restore from verified offsite copy; RTO report JSON |
| `scripts/offsite_backup_upload.py` | Offsite copy with checksum verification (use as `OFFSITE_BACKUP_COMMAND`) |
| `scripts/check_backup_freshness.sh` | Verify a recent backup exists, is non-empty, and is not corrupted |

---

## Environment variables

All scripts read configuration from environment variables — no secrets are hardcoded.

Configure these in `/opt/krowolf/.env.production` or export them before running:

```bash
# DB connection — Docker Compose setup
DOCKER_DB_CONTAINER=krowolf-db-1    # docker exec target (compose: krowolf-db-1)
POSTGRES_USER=postgres               # Postgres superuser
POSTGRES_DB=ai_platform              # Production database name
# POSTGRES_PASSWORD is read from the container's environment — not needed here
# when DOCKER_DB_CONTAINER is set (docker exec does not require a password).

# Backup storage
BACKUP_DIR=/opt/krowolf/backups     # Where to store local backups
BACKUP_RETENTION_DAYS=30            # Delete local backups older than N days
STORAGE_DIR=/opt/krowolf/storage    # Shared with app container via bind mount
BACKUP_STATUS_FILE=/opt/krowolf/storage/status/backup_status.json
RESTORE_STATUS_FILE=/opt/krowolf/storage/status/restore_status.json

# App container (.env.production for compose app service) uses container paths:
# BACKUP_STATUS_FILE=/app/storage/status/backup_status.json
# RESTORE_STATUS_FILE=/app/storage/status/restore_status.json

# Offsite upload (required for pilot) — see Offsite section below
OFFSITE_BACKUP_COMMAND=             # Shell command to upload $1 to remote storage

# Freshness check
BACKUP_MAX_AGE_HOURS=25             # Alert if newest backup is older than N hours
BACKUP_MIN_SIZE_BYTES=1024          # Alert if newest backup is smaller than N bytes
```

Add these to `env.example` with empty values — they are documented there.

### Status metadata vs operation result

- Backup/restore **operation** exit code reflects pg_dump/restore success only.
- If the operation succeeds but status JSON cannot be written, the script exits **0** and logs `WARN: metadata write failed` to stderr/cron log.
- The system status API cannot detect metadata-write failures; it shows **stale** or **not_reported** only.

### Status directory permissions

```bash
sudo mkdir -p /opt/krowolf/storage/status
sudo chmod 0750 /opt/krowolf/storage/status
# Ensure backup user and app container share group read (adjust group as needed):
# sudo chgrp krowolf /opt/krowolf/storage/status
# sudo chmod g+rX /opt/krowolf/storage/status
```

Status files are written with mode `0640`.

---

## Daily automated backup (cron)

Set up a cron job on the production server to run daily at 02:00:

```bash
# SSH to server and edit crontab
ssh ubuntu@api.krowolf.se
sudo crontab -e

# Add this line:
0 2 * * * DOCKER_DB_CONTAINER=krowolf-db-1 POSTGRES_DB=ai_platform BACKUP_DIR=/opt/krowolf/backups BACKUP_RETENTION_DAYS=30 BACKUP_STATUS_FILE=/opt/krowolf/storage/status/backup_status.json /opt/krowolf/scripts/backup_postgres.sh >> /var/log/krowolf-backup.log 2>&1

# Verify cron is installed
sudo crontab -l | grep backup
```

> **Note:** The production scripts directory is available at `/opt/krowolf/scripts/` because the Dockerfile copies `scripts/` into the image and the compose setup mounts it. Alternatively, copy the script directly to the server:
> ```bash
> scp scripts/backup_postgres.sh ubuntu@api.krowolf.se:/opt/krowolf/scripts/backup_postgres.sh
> chmod +x /opt/krowolf/scripts/backup_postgres.sh
> ```

---

## Manual backup (pre-operation or on-demand)

```bash
ssh ubuntu@api.krowolf.se

# Run backup script (reads config from environment)
sudo \
  DOCKER_DB_CONTAINER=krowolf-db-1 \
  POSTGRES_DB=ai_platform \
  BACKUP_DIR=/opt/krowolf/backups \
  BACKUP_RETENTION_DAYS=30 \
  bash /opt/krowolf/scripts/backup_postgres.sh

# Verify a new backup was created
ls -lh /opt/krowolf/backups/ | tail -5
# Expect: newest file shows today's timestamp, size > 1KB
```

**Fallback — direct docker exec (if script is unavailable):**
```bash
ssh ubuntu@api.krowolf.se
sudo docker exec krowolf-db-1 pg_dump -U postgres ai_platform \
  | gzip > /opt/krowolf/backups/ai_platform_$(date +%Y-%m-%d-%H%M%S).sql.gz
ls -lh /opt/krowolf/backups/ | tail -3
```

---

## Check backup freshness

Run the freshness check to confirm a recent valid backup exists:

```bash
ssh ubuntu@api.krowolf.se

sudo \
  BACKUP_DIR=/opt/krowolf/backups \
  POSTGRES_DB=ai_platform \
  BACKUP_MAX_AGE_HOURS=25 \
  BACKUP_MIN_SIZE_BYTES=1024 \
  bash /opt/krowolf/scripts/check_backup_freshness.sh
# Expect: all lines show "OK", exit code 0.
# FAIL lines mean: no backup, backup too old, backup too small, or gzip corruption.
```

Add to cron after daily backup to alert on failure:

```bash
# Run freshness check 30 minutes after backup
30 2 * * * BACKUP_DIR=/opt/krowolf/backups POSTGRES_DB=ai_platform bash /opt/krowolf/scripts/check_backup_freshness.sh || echo "BACKUP FRESHNESS CHECK FAILED" | mail -s "ALERT: krowolf backup" admin@krowolf.se
```

---

## Verify backup integrity manually

```bash
# Check gzip integrity of a specific file
gunzip -t /opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz && echo "OK"

# Peek at contents (first 20 lines after decompression)
gunzip -c /opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz | head -20
# Expect: starts with "-- PostgreSQL database dump" or "SET statement_timeout"

# Check file size
ls -lh /opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz
# Expect: > 10KB for a non-trivial database
```

---

## Offsite backup

> **BLOCKER (before first real customer pilot):** Local-only backups are not sufficient.
> A server failure would destroy both the data and the backups simultaneously.
> Offsite upload must be configured and verified before any real customer data enters the system.

### Requirement

After every local backup, the backup file must be copied to a separate storage location (different server, cloud storage bucket, or remote filesystem).

### Configuring offsite upload (generic)

Set `OFFSITE_BACKUP_COMMAND` to any shell command that receives the backup file path as `$1`:

**Example — rclone to a cloud provider:**
```bash
# Install rclone on server (one-time)
curl https://rclone.org/install.sh | sudo bash
rclone config  # configure a remote named "krowolf-backups"

# Set OFFSITE_BACKUP_COMMAND in environment or cron
OFFSITE_BACKUP_COMMAND="rclone copy \$1 krowolf-backups:backups/"
```

**Example — rsync to a separate server:**
```bash
OFFSITE_BACKUP_COMMAND="rsync -az \$1 backup-user@backup-server:/backups/krowolf/"
```

**Example — AWS S3 (requires aws CLI):**
```bash
OFFSITE_BACKUP_COMMAND="aws s3 cp \$1 s3://your-bucket-name/krowolf-backups/"
```

**Example — built-in Python uploader (pilot/staging; destination must differ from `BACKUP_DIR`):**
```bash
OFFSITE_BACKUP_DEST_DIR=/mnt/offsite/krowolf-backups
OFFSITE_STATUS_FILE=/opt/krowolf/storage/status/offsite_status.json
OFFSITE_BACKUP_COMMAND="python3 /opt/krowolf/scripts/offsite_backup_upload.py"
```

The uploader verifies sha256 after copy, writes `.sha256` sidecar offsite, and creates `${BACKUP_FILE}.offsite_verified` locally. Local retention pruning skips files without verified offsite marker when `OFFSITE_BACKUP_COMMAND` is set.

Backup metadata (`backup_status.json`) includes: `checksum_sha256`, `local_status`, `offsite_status`, `offsite_verified`.

### Important notes on offsite

- Do not hardcode bucket names, credentials, or server addresses in scripts committed to the repository.
- Configure via environment variables in `.env.production` on the server.
- Offsite storage must be in a different physical location than the production server.
- Offsite retention must be configured separately in the remote storage provider.
- Verify offsite upload by listing the remote after the first backup:
  ```bash
  rclone ls krowolf-backups:backups/  # or equivalent for your provider
  ```

---

## Restore rehearsal procedure

Run this before the first customer pilot and at least once per month.

### Step 1: SSH to the server

```bash
ssh ubuntu@api.krowolf.se
```

### Step 2: Identify the backup to restore

```bash
ls -lht /opt/krowolf/backups/ | head -10
# Note the filename of the most recent backup
```

### Step 3: Run the rehearsal script

```bash
sudo \
  DOCKER_DB_CONTAINER=krowolf-db-1 \
  POSTGRES_DB=ai_platform \
  RESTORE_SOURCE_FILE=/opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz \
  RESTORE_TARGET_DB=ai_platform_restore_test \
  bash /opt/krowolf/scripts/restore_postgres_rehearsal.sh
```

**Expected output:**
```
[restore] Source file:   /opt/krowolf/backups/ai_platform_...sql.gz
[restore] Target DB:     ai_platform_restore_test
[restore] Production DB: ai_platform (protected from overwrite)
[restore] Creating target database 'ai_platform_restore_test'...
[restore] Decompressing and restoring from: ...
[restore] Restore SQL executed.
[restore] Verifying restored tables...
[restore]   Table 'tenants': N row(s)
[restore]   Table 'jobs': N row(s)
[restore]   Table 'approvals': N row(s)
[restore]   Table 'oauth_credentials': N row(s)
[restore]   Table 'audit_events': N row(s)
[restore]   Table 'integration_events': N row(s)
[restore] All expected tables verified.
[restore] Dropping target database 'ai_platform_restore_test'...
[restore] Rehearsal complete.
```

### Step 4: Compare row counts with production

```bash
# Production row counts (for comparison)
sudo docker exec krowolf-db-1 psql -U postgres -d ai_platform \
  -c "SELECT 'tenants' as t, COUNT(*) FROM tenants UNION ALL
      SELECT 'jobs', COUNT(*) FROM jobs UNION ALL
      SELECT 'approvals', COUNT(*) FROM approvals UNION ALL
      SELECT 'audit_events', COUNT(*) FROM audit_events;"
```

> Rehearsal row counts must match production counts (±0, or ±1 for any job created during the backup window).

### Step 5: Leave target DB for inspection (optional)

```bash
# Keep the restored DB for manual inspection
sudo \
  SKIP_CLEANUP=true \
  RESTORE_SOURCE_FILE=/opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz \
  RESTORE_TARGET_DB=ai_platform_restore_test \
  DOCKER_DB_CONTAINER=krowolf-db-1 \
  bash /opt/krowolf/scripts/restore_postgres_rehearsal.sh

# Manually inspect
sudo docker exec krowolf-db-1 psql -U postgres -d ai_platform_restore_test \
  -c "SELECT tenant_id, name, status FROM tenants;"

# Drop when done
sudo docker exec krowolf-db-1 psql -U postgres \
  -c "DROP DATABASE ai_platform_restore_test;"
```

### Rehearsal log

Document each rehearsal:

```text
Rehearsal date:                    ___________
Operator:                          ___________
Backup file used:                  ___________
Backup file age at time of test:   ___________ hours
Row counts match production:       ⬜ Yes / ⬜ No (detail: ___)
Restore completed without errors:  ⬜ Yes / ⬜ No (detail: ___)
Target DB dropped after rehearsal: ⬜ Yes / ⬜ No
Offsite upload verified:           ⬜ Yes / ⬜ No / ⬜ Not yet configured
Notes:                             ___________
```

---

## Production restore (emergency only)

Only run a production restore after:
1. Taking a fresh forensic backup of the current (broken) state.
2. Confirming the restore file is correct and recent.
3. Stopping the app container to prevent writes during restore.
4. Confirming with the platform team.

```bash
ssh ubuntu@api.krowolf.se
cd /opt/krowolf

# Step 1: Stop app (prevents writes during restore)
sudo docker compose -f docker-compose.prod.yml stop app

# Step 2: Forensic backup of current state
sudo docker exec krowolf-db-1 pg_dump -U postgres ai_platform \
  | gzip > /opt/krowolf/backups/forensic-$(date +%Y-%m-%d-%H%M%S).sql.gz
ls -lh /opt/krowolf/backups/forensic-*.sql.gz | tail -1

# Step 3: Drop and recreate the production database
sudo docker exec krowolf-db-1 psql -U postgres \
  -c "DROP DATABASE ai_platform;"
sudo docker exec krowolf-db-1 psql -U postgres \
  -c "CREATE DATABASE ai_platform;"

# Step 4: Restore from backup
gunzip -c /opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz \
  | sudo docker exec -i krowolf-db-1 psql -U postgres -d ai_platform

# Step 5: Restart app
sudo docker compose -f docker-compose.prod.yml up -d app

# Step 6: Verify
curl -sS https://api.krowolf.se/health
curl -sS https://api.krowolf.se/tenant -H "X-API-Key: TENANT_KEY"
sudo docker exec krowolf-db-1 psql -U postgres -d ai_platform \
  -c "SELECT COUNT(*) FROM jobs;"
```

---

## Common failure modes

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `pg_dump: error: connection to server ...` | Wrong container name or DB is not running | Check `docker ps`; set `DOCKER_DB_CONTAINER` correctly |
| `gunzip: backup file not found` | Wrong path or backup was pruned | Check `ls -lh /opt/krowolf/backups/`; create fresh backup |
| Backup file is 0 bytes | `pg_dump` failed silently (pipe issue) | Check server logs; re-run script and capture stderr |
| `gunzip: not in gzip format` | File is corrupt or incomplete | Discard and create new backup |
| Freshness check fails "too old" | Cron job not running | Verify crontab with `sudo crontab -l`; run manually |
| Restore fails "database already exists" | Target DB left from previous rehearsal | Drop it: `psql -c "DROP DATABASE ai_platform_restore_test;"` |
| Restore fails "table not found" during verify | Schema evolved since backup | Acceptable if new table was added after the backup; verify other tables |
| `RESTORE_TARGET_DB matches POSTGRES_DB` | Safety check triggered | This is correct behavior — use a different `RESTORE_TARGET_DB` |

---

## DB password rotation (planned)

The current `POSTGRES_PASSWORD` is hardcoded in `docker-compose.prod.yml`.
Rotation plan is documented in `docs/PHASE_O_CLOSURE_CHECKLIST.md` (Condition 3).

After rotation, test that the backup script still works with the new credentials before removing the old password from all locations.

---

## Backup verification checklist

**All BLOCKER items below must be completed before first real customer pilot.**
Local-only backups are not sufficient. A server failure destroys both data and local backups.

- [ ] **BLOCKER** — Manual backup created successfully (`backup_postgres.sh` exits 0)
- [ ] **BLOCKER** — Freshness check passes (`check_backup_freshness.sh` exits 0)
- [ ] **BLOCKER** — Offsite backup configured: `OFFSITE_BACKUP_COMMAND` is set and a test upload was verified in remote storage
- [ ] **BLOCKER** — Restore rehearsal completed: `restore_postgres_rehearsal.sh` exits 0, row counts verified against production
- [ ] **REQUIRED** — Cron job scheduled for daily 02:00 backup
- [ ] **REQUIRED** — Backup directory has sufficient disk space (`df -h /opt/krowolf`)
- [ ] **REQUIRED** — Old backups are being pruned (or retention is manually managed)

---

## Related runbooks

- `docs/runbooks/incident-response.md` — P1/P2 incidents requiring production restore
- `docs/PHASE_O_CLOSURE_CHECKLIST.md` — DB password rotation condition
- `docs/PILOT_READINESS_CHECKLIST.md` — backup items (BLOCKER / REQUIRED)
