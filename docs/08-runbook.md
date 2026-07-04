# Runbook

> Operational procedures for the platform. For strategy and product decisions, see `docs/00-master-plan.md`.
> Detailed historical runbooks are in `docs/archive/legacy-runbook-*.md`.

---

## How to check failed jobs

### Via UI
1. Open Super Admin view → "Behöver hjälp" queue.
2. Look for rows with `severity: high` or `critical`.
3. Click "Öppna ärende" to see the case detail.

### Via API
```bash
# Needs-help queue (admin)
GET /admin/operations/needs-help
Header: X-Admin-API-Key: <ADMIN_API_KEY>

# Operational insights (tenant)
GET /dashboard/operational-insights
Header: X-API-Key: <TENANT_API_KEY>

# Job detail
GET /cases/<job_id>
Header: X-API-Key: <TENANT_API_KEY>

# Job actions (what was dispatched)
GET /jobs/<job_id>/actions
Header: X-API-Key: <TENANT_API_KEY>
```

### Recovery actions
```bash
# Retry a failed job (admin)
POST /admin/recovery/<job_id>/retry_job
Header: X-Admin-API-Key: <ADMIN_API_KEY>
Header: X-Tenant-ID: <TENANT_ID>

# Replay a dispatch
POST /admin/recovery/<job_id>/replay_dispatch
Header: X-Admin-API-Key: <ADMIN_API_KEY>
Header: X-Tenant-ID: <TENANT_ID>

# Reclassify
POST /admin/recovery/<job_id>/reclassify
Header: X-Admin-API-Key: <ADMIN_API_KEY>
Header: X-Tenant-ID: <TENANT_ID>
```

---

## How to check integration health

```bash
GET /integrations/health
Header: X-API-Key: <TENANT_API_KEY>
```

Response shape:
```json
{
  "overall_status": "healthy|warning|error",
  "systems": {
    "gmail": { "status": "...", "checks": [...], "runbook_signals": [...] },
    "monday": { "status": "...", "checks": [...], "runbook_signals": [...] }
  },
  "recent_errors": [...]
}
```

Signals to act on:
- `overall_status: error` → investigate immediately.
- `runbook_signals` with `severity: high` → follow the `action` field.

---

## How to check OAuth/token issues

### Detect
```bash
# Integration health shows gmail.status = error
GET /integrations/health
Header: X-API-Key: <TENANT_API_KEY>

# Pilot readiness shows auth issue
GET /pilot/readiness
Header: X-API-Key: <TENANT_API_KEY>
```

Signs of expired token:
- `gmail.status = error` in integration health.
- Recent errors contain `401 Unauthorized` or `invalid_grant`.
- Scheduler log shows `GmailAuthError`.

### Manual refresh
```bash
# Start OAuth flow
GET /auth/gmail/start?tenant_id=<TENANT_ID>
# Follow redirect to Google, copy authorization_code from callback URL

# Submit code
POST /auth/gmail/callback
{ "code": "<authorization_code>", "tenant_id": "<TENANT_ID>" }

# Verify
GET /integrations/health
Header: X-API-Key: <TENANT_API_KEY>
# gmail.status should be "healthy"
```

### Required env vars for auto-refresh
All four are required. Missing any one causes `invalid_grant` on next token expiry:
```
GOOGLE_MAIL_ACCESS_TOKEN
GOOGLE_OAUTH_REFRESH_TOKEN
GOOGLE_OAUTH_CLIENT_ID
GOOGLE_OAUTH_CLIENT_SECRET
```

### Common errors

| Error | Cause | Fix |
|-------|-------|-----|
| `invalid_grant` | Refresh token expired or revoked | Re-run OAuth flow |
| `invalid_client` | Client ID/secret changed | Update env vars, restart |
| Gmail reads but not writes | Missing `gmail.send` scope | Check Google Cloud Console → OAuth scopes |

---

## How to check scheduler / inbox sync

```bash
# Scheduler status (tenant)
GET /scheduler/status
Header: X-API-Key: <TENANT_API_KEY>

# Control panel (set run_mode)
GET /dashboard/control
Header: X-API-Key: <TENANT_API_KEY>

# Set scheduler to active
PUT /dashboard/control
Header: X-API-Key: <TENANT_API_KEY>
Body: {"scheduler": {"run_mode": "scheduled"}}

# Manual trigger (admin only)
POST /scheduler/run-once
Header: X-Admin-API-Key: <ADMIN_API_KEY>
```

Scheduler logs to stdout. Check logs for `scheduler_pass` or `inbox_sync` errors:
```bash
tail -f storage/local_dev/logs/app.log | grep scheduler
```

External cron (production recommended):
```bash
# Every 5 minutes
*/5 * * * * curl -s -X POST -H "X-Admin-API-Key: $ADMIN_API_KEY" https://your-domain.com/scheduler/run-once
```

---

## How to inspect approvals

```bash
# List pending approvals (all types)
GET /approvals/pending
Header: X-API-Key: <TENANT_API_KEY>

# Approve (body {} is required)
POST /approvals/<approval_id>/approve
Header: X-API-Key: <TENANT_API_KEY>
Body: {}

# Reject
POST /approvals/<approval_id>/reject
Header: X-API-Key: <TENANT_API_KEY>
Body: {}
```

Approval types:
- `next_on_approve: "pipeline"` — resumes job pipeline.
- `next_on_approve: "controlled_dispatch"` — runs dispatch adapter.
- `next_on_approve: "email_send"` — sends the held email.

---

## How to handle first customer issue

### Morning routine (5–10 min)
1. Open Operationscockpit → check "Kräver åtgärd" and "Riskerar SLA".
2. Review pending approvals (mail, dispatch).
3. Check SLA risks — respond to leads waiting > 24h.

### During the day
- When AI proposes a reply: review → approve or edit.
- Update work order status when technicians report (Starta / Klart / Blockerad).
- Add material and time in operations workspace.

### End of day / invoicing
1. Check that underlag-status is "Redo".
2. Open case → "Sammanställ projekt" → review.
3. Click "Förhandsvisa i Fortnox" → confirm data is correct.
4. Approve Fortnox export.

---

## Escalation rules

| Situation | Action | Timeframe |
|-----------|--------|-----------|
| API/system down | Contact platform team | Immediately |
| OAuth token revoked | Contact platform team | Within 1h |
| Customer email sent incorrectly | Contact platform team + pilot customer | Immediately |
| Database problem | Contact platform team | Immediately |
| Misclassification | Report via case detail → Manual review | Normal hours |
| Monday API key invalid | Update `MONDAY_API_KEY`, restart | Within 1h |
| Fortnox token expired | Update `FORTNOX_ACCESS_TOKEN`, restart | Within business hours |

---

## Do-not-do rules in production

- **Never** merge `server-local-hotfix-backup` branch over `main` — it is a historical checkpoint only.
- **Never** expose raw API keys in responses or logs.
- **Never** run the scheduler with `run_mode: manual` in production unless explicitly pausing for maintenance.
- **Never** delete jobs or approvals from the DB directly without backup.
- **Never** trust `X-Tenant-ID` header in production (`ENV=production` enforces fail-closed auth).
- **Never** expose `/docs`, `/redoc`, or `/openapi.json` in production (disabled when `ENV=production`).
- **Never** run bookkeeping actions (Fortnox export) without first doing a dry-run preview.
- **Never** send customer email without approval gate.
- **Never** leave `ADMIN_API_KEY` empty in production.

---

## API key rotation

```bash
# Rotate tenant API key (admin only — new key shown once)
POST /admin/tenants/<TENANT_ID>/rotate-key
Header: X-Admin-API-Key: <ADMIN_API_KEY>
```

Store the new key immediately. It is shown only once.

---

## Backup and restore

### Daily backup (run as cron at 02:00)
```bash
pg_dump "$DATABASE_URL" | gzip > /backups/ai_platform_$(date +%Y%m%d_%H%M).sql.gz
```

### Pre-deploy manual backup
```bash
pg_dump "$DATABASE_URL" > /backups/pre_deploy_$(date +%Y%m%d_%H%M).sql
```

### Restore procedure
1. Stop the application.
2. Drop and recreate the database:
   ```bash
   dropdb ai_platform && createdb ai_platform
   ```
3. Restore:
   ```bash
   gunzip -c /backups/ai_platform_YYYYMMDD_HHMM.sql.gz | psql "$DATABASE_URL"
   ```
4. Re-run table creation (idempotent):
   ```bash
   python scripts/create_tables.py
   ```
5. Restart and smoke check:
   ```bash
   python scripts/smoke_check.py --base-url https://your-domain.com --expect-production
   ```

Rehearse restore monthly. Record date and result.

---

## Onboarding new pilot customer

- [ ] Create tenant via `/admin/tenants` (Super Admin UI or API).
- [ ] Store one-time API key securely.
- [ ] Configure Gmail OAuth (run OAuth flow, verify token).
- [ ] Configure Monday (run scanner, set routing hints).
- [ ] Configure Fortnox API token (run scanner if needed).
- [ ] Set automation policy in Control Panel.
- [ ] Run pilot readiness check: `GET /pilot/readiness`.
- [ ] Verify inbox sync: send test mail, confirm case created.
- [ ] Set notification recipient and daily digest hour.
- [ ] Inform customer about what AI does and does not do automatically.
