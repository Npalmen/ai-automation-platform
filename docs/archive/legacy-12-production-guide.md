> Archived document. Historical reference only. Current governing source is docs/00-master-plan.md.

# Production Deployment Guide

## Required environment variables

Set these before starting the server. The app will start without them but key features will be disabled or insecure.

### Critical — security

| Variable | Description | Example |
|----------|-------------|---------|
| `TENANT_API_KEYS` | Optional JSON map of tenant-id → API key for legacy/env tenants. Production may also use DB-backed provisioned tenant API keys. Empty is allowed only when active DB-backed keys exist; otherwise production fails closed. | `{"ACME_AB": "key-abc123", "DEMO": "key-xyz456"}` |
| `ADMIN_API_KEY` | Secret for admin endpoints (`X-Admin-API-Key`). Empty = admin access blocked (fail-closed). | `admin-secret-key-prod` |
| `DATABASE_URL` | PostgreSQL connection string. | `postgresql://user:pass@host:5432/ai_platform` |

### Gmail integration

All four required for OAuth token refresh. Missing any one causes `invalid_grant` on first token expiry.

| Variable | Description |
|----------|-------------|
| `GOOGLE_MAIL_ACCESS_TOKEN` | Current OAuth access token |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | OAuth refresh token |
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_MAIL_USER_ID` | Gmail user ID, usually `me` |

### Monday.com integration

| Variable | Description |
|----------|-------------|
| `MONDAY_API_KEY` | Monday API key |
| `MONDAY_BOARD_ID` | Default board ID (integer) |

### Fortnox integration

| Variable | Description |
|----------|-------------|
| `FORTNOX_ACCESS_TOKEN` | Fortnox OAuth access token |
| `FORTNOX_CLIENT_SECRET` | Fortnox client secret |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `AI Automation Platform` | Shown in health endpoint |
| `ENV` | `dev` | Set to `production` in prod |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | Bind port |
| `STORAGE_PATH` | `./storage/local_dev` | File storage root |
| `LLM_API_KEY` | — | OpenAI/LLM key for AI classification |
| `LLM_MODEL` | `gpt-4.1-mini` | LLM model name |
| `SLACK_WEBHOOK_URL` | — | Slack notifications |
| `VISMA_ACCESS_TOKEN` | — | Visma integration |

---

## Pre-launch checklist

1. **Configure tenant auth** — use either DB-backed provisioned tenant API keys or non-empty `TENANT_API_KEYS`. Production must not rely on dev-mode tenant fallback.
2. **Set `ADMIN_API_KEY`** — non-empty; used to gate tenant creation, config writes, and admin overview.
3. **Set `DATABASE_URL`** — point to a real PostgreSQL instance (not localhost defaults).
4. **Run DB migrations** — `python scripts/create_tables.py` (idempotent).
5. **Verify `ENV=production`** — disables dev-mode tenant fallback and public OpenAPI/docs.
6. **Create at least one tenant** — `POST /tenant` with `X-Admin-API-Key` header.
7. **Configure Gmail env vars** — all four OAuth fields or none (partial config causes silent failure).
8. **Check "Redo för drift"** — open the UI, navigate to Konfiguration → Redo för drift. All items should be green or yellow before going live.
9. **Run the release gate and smoke check** — `python scripts/run_release_gate_r1.py --verbose`, `python -m pytest`, then `python scripts/smoke_check.py --base-url <url> --expect-production`.
10. **Check the 5-customer launch checklist** — see `docs/13-5-customer-launch-checklist.md`.

---

## Authentication model

| Caller | Header | Grants access to |
|--------|--------|-----------------|
| Tenant user | `X-API-Key: <key>` | `/tenant`, `/jobs`, `/cases`, `/integrations/health`, all tenant-scoped endpoints |
| Admin operator | `X-Admin-API-Key: <key>` | `/tenant` (create), `/tenant/config/{id}` (read/write), `/tenants` (list), `/verify/{id}`, `/admin/tenants/overview`, all-tenant scheduler trigger |
| No header | — | `GET /` (health), `GET /ui` (operator UI HTML only) |

Tenant auth resolves DB-backed hashed API keys first, then falls back to the `TENANT_API_KEYS` env map. When `ENV=production`, missing tenant credentials fail closed. Dev-mode fallback to `X-Tenant-ID` or `TENANT_1001` is local-only.

When `ADMIN_API_KEY` is empty all admin endpoints return 401 (fail-closed).

Admin UI currently stores the admin key in browser localStorage and sends it via `X-Admin-API-Key`. For the 5-customer pilot, protect `/ui` and admin access with network controls such as VPN, IP allowlist, or a trusted operator machine. Treat this as an MVP/pilot auth model, not enterprise SSO.

---

## Production API surface

When `ENV=production`, public FastAPI docs are disabled:

- `/docs`
- `/redoc`
- `/openapi.json`

Use local/dev environments for schema exploration.

---

## Scheduler trigger

`POST /scheduler/run-once` runs scheduler logic across all configured tenants and therefore requires `X-Admin-API-Key`. Tenant API keys can still read their own `GET /scheduler/status`, but cannot trigger all-tenant scheduler work.

---

## Running the server

```bash
# Install dependencies
pip install -r requirements.txt

# Create DB tables (idempotent)
python scripts/create_tables.py

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The operator UI is available at `/ui`. The API is available at `/`.

---

## Docker deployment baseline

Production-compatible container files are included:

```bash
docker build -t ai-automation-platform:release .
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

After the stack is healthy, run:

```bash
python scripts/smoke_check.py --base-url http://127.0.0.1:8000 --expect-production
```

The compose file expects `.env` to contain real secrets. Keep `ADMIN_API_KEY`, tenant API keys, OAuth tokens and database credentials out of git.

---

## CI release gate

GitHub Actions workflow `.github/workflows/release-gate.yml` runs:

- dependency install on Python 3.10
- `python scripts/run_release_gate_r1.py --verbose`
- full `python -m pytest`
- Docker image build
- `docker compose -f docker-compose.prod.yml config`

Use the workflow as the merge gate for `main`.

---

## Error behaviour

- Backend never returns Python stack traces in HTTP responses.
- Exception details are logged server-side (check `uvicorn` / application logs).
- Customer-facing UI shows generic Swedish error messages. Admin UI shows HTTP status codes.
- The "Redo för drift" view shows a live readiness score — bookmark it for on-call reference.

---

---

## Backup and restore

### Backup schedule (recommended)

| Frequency | Method | Retention |
|-----------|--------|-----------|
| Daily     | `pg_dump` snapshot to a separate volume or object storage (S3/GCS) | 14 days rolling |
| Weekly    | Full `pg_dump` with schema included | 3 months |
| Pre-deploy | Manual `pg_dump` snapshot before every production deploy | Keep until next successful deploy |

Run daily backup (example cron — adapt path/credentials):

```bash
# cron: 02:00 daily
pg_dump "$DATABASE_URL" | gzip > /backups/ai_platform_$(date +%Y%m%d_%H%M).sql.gz
```

### Restore procedure

1. **Stop the application** (or put it in maintenance mode at the proxy layer).
2. Drop and recreate the target database, or restore into a point-in-time recovery slot:
   ```bash
   psql "$DATABASE_URL" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'ai_platform' AND pid <> pg_backend_pid();"
   dropdb ai_platform
   createdb ai_platform
   ```
3. Restore from the backup:
   ```bash
   gunzip -c /backups/ai_platform_20260510_0200.sql.gz | psql "$DATABASE_URL"
   ```
4. Re-run the table creation script (idempotent — safe after restore):
   ```bash
   python scripts/create_tables.py
   ```
5. Restart the application and run the smoke check:
   ```bash
   python scripts/smoke_check.py --base-url https://api.krowolf.se --expect-production
   ```
6. Spot-check the super admin overview (`GET /admin/tenants/overview`) and confirm tenant count matches expectations.

### Restore rehearsal (run monthly)

Before going live with a customer, and every month thereafter, verify that backup/restore works end-to-end:

1. Take a fresh `pg_dump` of the staging database.
2. Create an isolated `ai_platform_restore_test` database.
3. Restore the dump into that database.
4. Run `python -m pytest` against the restored database to confirm all tests pass.
5. Drop the test database.
6. Record date, result, and who ran the rehearsal in the team's incident log.

### Backup validation checklist (pre-launch and monthly)

- [ ] At least one backup exists and is ≤ 24 h old
- [ ] Restore rehearsal completed successfully (this month)
- [ ] Backup files are on a separate volume/account from the application server
- [ ] Backup retention policy is enforced (old backups are pruned)
- [ ] Restore procedure documented above has been tested with this backup format

---

## Failed-job and failed-dispatch triage

Use this checklist when the super admin needs-help queue (`GET /admin/operations/needs-help`) shows failed pipeline jobs or failed integration events.

### Failed job triage

1. Open the Super Admin "Behöver hjälp" queue — click "Öppna ärende" on the failed row.
2. In the case detail, review the `result.error` or `result.message` field.
3. Common root causes:

   | Symptom | Likely cause | Resolution |
   |---------|-------------|------------|
   | `invalid_grant` / OAuth error | Gmail token expired | See `docs/runbook-oauth.md` |
   | `401 Unauthorized` (Monday/Fortnox) | API key rotated/revoked | Update env var and restart |
   | `No matching board` | Monday board not scanned | Re-run Monday scanner in Setup |
   | `Customer not found in Fortnox` | Missing Fortnox customer record | Create customer in Fortnox, then retry export |
   | `LLM quota exceeded` | OpenAI rate limit | Wait and re-trigger job |
   | `DB connection error` | Database unreachable | Check `DATABASE_URL` and connectivity |

4. If the job can be retried, use `POST /jobs/{job_id}/auto-dispatch` (requires tenant API key) or re-process via the UI.
5. If the job is unrecoverable, set its status to `failed` (via the case detail status selector) and log the incident.

### Failed integration event triage

Integration events (dispatches to Monday, Fortnox exports) that show as `failed` in the triage queue:

1. Note the `integration_type` and `last_error` from the triage row.
2. Check integration credentials via the Integration Health admin view.
3. Verify the tenant's integration scan (`GET /setup/verify`) still passes.
4. For Monday: confirm `MONDAY_BOARD_ID` and `MONDAY_API_KEY` are valid. Re-run Monday scanner.
5. For Fortnox: confirm `FORTNOX_ACCESS_TOKEN` is current. Re-run Fortnox scanner.
6. Integration events are not automatically retried after 3 attempts (`dead` state). A supervisor must take a manual action (re-trigger from the case detail or create a manual record).

### Stale approval triage

Approvals pending > 24 h appear in the triage queue:

1. Click "Godkänna" or "Öppna ärende" on the stale row.
2. In the case detail, review the approval context.
3. Either approve, reject, or notify the responsible operator.
4. If the approval is orphaned (no responsible operator), reject it and re-trigger the job with updated routing.

---

## What is NOT in scope for MVP

- HTTPS termination — use a reverse proxy (nginx, Caddy, Traefik) in front.
- Rate limiting — add at the proxy layer.
- Multi-region — single-process, single-database.
- Background worker — the scheduler runs on-demand via `POST /scheduler/run-once`. Wire a cron job or systemd timer to call it.
- Automated backup — the cron command above must be wired externally (cron, systemd timer, cloud scheduler).
- Automated restore rehearsal — run monthly by a named operator, not automated.
- Job replay queue UI — re-triggering failed jobs requires the API or case detail UI; there is no bulk replay tool in the MVP.
