# Runbook

> Operational procedures for the platform. For strategy and product decisions, see `docs/00-master-plan.md`.
> Detailed historical runbooks are in `docs/archive/legacy-runbook-*.md`.
> **Live verification plan (first pilot tenant go-live):** see `docs/10-live-verification-plan.md`.

---

## Pre-live UI mode

`app/ui/index.html` is the Internal Operator Console for live verification and first pilot operations.

- Use it for admin/operator tasks: tenant provisioning, tenant selection, readiness, integration health, approvals, jobs/cases, setup/onboarding, support/needs-help, and safe test-lead flow.
- Treat polished customer-facing UI as deferred. The current UI prioritizes function, clarity, secure configuration, and troubleshooting.
- Store one-time tenant API keys securely when shown. Do not paste or record secrets in reports.
- Before Phase D, deploy the latest code and re-run Phase A-C with the correct `ADMIN_API_KEY`.

---

## First internal pilot tenant setup — local/pre-live

Complete this sequence before any live tenant onboarding.
No live tokens are needed. All steps work against the local dev server.

### Prerequisites
- Local server running (`uvicorn app.main:app --reload` or Docker).
- `ADMIN_API_KEY` env var set (any non-empty string for local dev).
- DB initialized: `python scripts/create_tables.py`.

### Step 1 — Provision tenant
```bash
curl -s -X POST http://localhost:8000/admin/tenants \
  -H "X-Admin-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Intern Pilot AB",
    "slug": "intern-pilot",
    "enabled_job_types": ["lead", "customer_inquiry"],
    "allowed_integrations": ["google_mail", "monday"],
    "auto_actions": {"lead": false, "customer_inquiry": false}
  }'
# Response: {"tenant_id": "T_INTERN_PILOT", "api_key": "kw_xxx...", "status": "active"}
# IMPORTANT: save the api_key — it is shown exactly once
```

Tenant ID derived from slug: `T_` + `slug.upper().replace("-", "_")` → `T_INTERN_PILOT`

### Step 2 — Verify tenant was created
```bash
curl -s http://localhost:8000/admin/tenants \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
# → T_INTERN_PILOT must be listed
```

### Step 3 — Verify tenant API key
```bash
export TENANT_KEY="kw_xxx..."   # key from step 1

curl -s http://localhost:8000/tenant \
  -H "X-API-Key: $TENANT_KEY"
# → {"current_tenant": "T_INTERN_PILOT", ...}
```

### Step 4 — Check pilot readiness (expected: not_ready before live)
```bash
curl -s http://localhost:8000/pilot/readiness \
  -H "X-API-Key: $TENANT_KEY"
# → overall_status: not_ready or almost_ready (no live tokens yet — expected)
# Inspect each of the 11 checks to identify what is missing for live go-live
```

Pilot readiness checks (11 total, all deterministic — no external API calls):
1. `auth_configured` — tenant DB key active
2. `tenant_exists` — tenant row in DB
3. `onboarding_ready` — onboarding checklist complete
4. `integrations_health_not_error` — integration health not "error"
5. `routing_ready_for_lead` — routing preview for lead is ready
6. `dispatch_duplicate_protection` — idempotency column exists
7. `dispatch_observability` — at least one integration event
8. `scheduler_safe` — run_mode != scheduled OR Gmail configured
9. `required_env_present` — APP_NAME + at least one integration env set
10. `ui_available` — `app/ui/index.html` present on disk
11. `test_lead_exists` — at least one lead job exists for tenant

### Step 5 — Check integration health (expected: not_configured before live)
```bash
curl -s http://localhost:8000/integrations/health \
  -H "X-API-Key: $TENANT_KEY"
# → overall_status: not_configured — Gmail, Monday, Fortnox all show not_configured
# No secrets in response — verified
```

Without live tokens (`GOOGLE_MAIL_ACCESS_TOKEN`, `MONDAY_API_KEY`, etc.):
- Gmail → `not_configured`
- Monday → `not_configured`
- Fortnox → `not_configured`

This is expected and safe. The endpoint will not crash.

### Step 6 — Run onboarding test lead (no external calls)
```bash
curl -s -X POST http://localhost:8000/onboarding/test-lead \
  -H "X-API-Key: $TENANT_KEY"
# → {"job_id": "...", "status": "completed" or "awaiting_approval"}
# Uses deterministic pipeline — no LLM or external calls
```

### Step 7 — Run deterministic pipeline verification (admin)
```bash
curl -s -X POST http://localhost:8000/verify/T_INTERN_PILOT \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
# → {"status": "completed" or "awaiting_approval", ...}
# No LLM, no external calls — safe for local use
```

### Step 8 — Check customer dashboard loads (empty state)
```bash
curl -s http://localhost:8000/customer/results \
  -H "X-API-Key: $TENANT_KEY"

curl -s http://localhost:8000/customer/health \
  -H "X-API-Key: $TENANT_KEY"
# → HTTP 200, empty/zero-state data — no crash
```

### Step 9 — Check onboarding status
```bash
curl -s http://localhost:8000/onboarding/status \
  -H "X-API-Key: $TENANT_KEY"
# → {"status": "in_progress" or "not_started", "steps": [...]}
# Shows which of 8 onboarding steps are complete/incomplete
```

### Step 10 — Rotate API key (if needed)
```bash
curl -s -X POST http://localhost:8000/admin/tenants/T_INTERN_PILOT/rotate-key \
  -H "X-Admin-API-Key: $ADMIN_API_KEY"
# → {"tenant_id": "T_INTERN_PILOT", "api_key": "kw_new..."}
# Old key is immediately revoked. Save the new key.
```

### Step 11 — Set tenant status (if needed)
```bash
# Deactivate
curl -s -X PATCH http://localhost:8000/admin/tenants/T_INTERN_PILOT/status \
  -H "X-Admin-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "inactive"}'

# Reactivate
curl -s -X PATCH http://localhost:8000/admin/tenants/T_INTERN_PILOT/status \
  -H "X-Admin-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "active"}'
```

### Pre-live readiness checklist
Before connecting live tokens:

- [ ] Steps 1–11 above completed locally.
- [ ] Core intelligence quality evals pass: `python -m pytest tests/test_core_intelligence_quality.py -q`.
- [ ] Test suite passes: `python -m pytest --tb=no -q`.
- [ ] R1 gate passes: `python -m scripts.run_release_gate_r1`.
- [ ] `ADMIN_API_KEY` set to a strong random value in production env.
- [ ] `APP_NAME` set in production env.
- [ ] DB backup completed before first live onboarding.

### Live-only steps (deferred — requires real OAuth)
```text
TODO: verify during live phase
```
- Gmail OAuth: `GET /auth/gmail/start?tenant_id=T_INTERN_PILOT` → follow redirect.
- Verify inbox sync creates cases: send test mail, confirm case created.
- Verify scheduler: `GET /scheduler/status` shows `run_mode: scheduled` or equivalent.
- Run smoke check: `python scripts/smoke_check.py --base-url https://your-domain.com --expect-production`.

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

> **Canonical procedures (Kapitel 12):** `docs/runbooks/backup-and-restore.md` — backup, offsite, restore. Release gate: `python scripts/kapitel12_slice3_verify.py` → `kapitel12_slice3_report.json`.

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

### Service profiles — local developer / demo note

Service profiles control which fields are required, what follow-up questions are asked, and how jobs are routed, based on the type of work. The 10 first profiles are:

| Profile | Detects | Route |
|---------|---------|-------|
| ev_charger_installation | laddbox, wallbox | sales |
| solar_installation | solcell, solpanel, pv | sales |
| battery_storage | batteri, energilager, powerwall | sales |
| electrical_fault | jordfelsbrytare, felsökning, kortslutning | support |
| inverter_support | växelriktare, inverter | support |
| electrical_panel | elcentral, proppskåp, gruppcent | sales |
| invoice_generic | faktura, invoice | invoice |
| debt_collection_risk | inkasso, kravbrev, kronofogden | manual_review |
| generic_lead | (fallback for leads) | sales |
| generic_support | (fallback for support) | support |

Debt-collection and safety-risk profiles always force `manual_review` — they cannot enter low-risk automation.

To see which profile would be selected for a message, use `select_profile()` from `app/service_profiles` in a Python shell or test fixture. To override routing for a tenant, add entries to `routing_hints` in the tenant memory config.

---

## Local golden path demo — service-profile aware

Run this checklist to verify the full local pipeline before live verification.
No live credentials needed. All steps use deterministic/mock flows.

### Prerequisites
```bash
python -m pytest --tb=no -q          # must pass, 0 failures
python -m scripts.run_release_gate_r1  # must pass
```

### 1. Run the targeted pipeline test suites
```bash
# Service profile pipeline wiring
python -m pytest tests/test_service_profile_pipeline.py -v

# Customer reply quality
python -m pytest tests/test_customer_reply_quality.py -v

# Tenant-aware routing hints
python -m pytest tests/test_tenant_routing_hints.py -v

# Full golden path scenarios
python -m pytest tests/test_local_golden_path.py -v
```

All 82 tests must pass before proceeding to live verification.

### 2. Golden path scenarios (verified locally)

**EV charger lead (low risk, incomplete info)**
```
Input: "Hej, vi vill ha offert på laddbox till villa i Uppsala."
→ classification: lead
→ service_profile_type: ev_charger_installation
→ missing_fields: [address, main_fuse, desired_location, ...]
→ question_message: "För att kunna ta fram rätt underlag för laddboxinstallationen..."
→ customer auto-reply: profile-specific follow-up, non-binding
→ no booking confirmation, no price commitment
```

**Solar installation lead**
```
Input: "Vi vill installera solceller på taket."
→ classification: lead
→ service_profile_type: solar_installation
→ missing_fields: [roof_type, annual_consumption, ...]
→ question_message: "För att kunna bedöma solcellsförutsättningarna..."
→ customer auto-reply: solar-profile-specific follow-up
```

**Debt collection / high-risk invoice**
```
Input: "Inkassokrav. Betala din skuld omgående."
→ risk_detected: True (debt_collection)
→ service_profile_type: debt_collection_risk
→ customer auto-reply: sensitive ack with _needs_approval=True
→ routes to manual_review, NOT low-risk automation
```

**Electrical fault with safety risk**
```
Input: "Det luktar bränt från eluttaget och det gnistrar."
→ risk_detected: True (safety_risk)
→ service_profile_type: electrical_fault
→ support analyzer: escalate/manual_review
→ customer auto-reply: sensitive ack with _needs_approval=True
```

**Tenant routing hint override**
```
tenant_ctx.routing_hints = {"ev_charger_installation": "sales_team"}
→ select_profile("lead", lead_type="ev_charger", tenant_ctx=ctx).default_route == "sales_team"
→ service_type and required_fields unchanged
```

### 3. Local HTTP smoke check (if server is running)

```bash
# 1. Check integration health (expects not_configured without live tokens)
curl -s http://localhost:8000/integrations/health \
  -H "X-API-Key: <TENANT_API_KEY>" | python -m json.tool

# 2. Submit a test lead (uses deterministic pipeline)
curl -s -X POST http://localhost:8000/onboarding/test-lead \
  -H "X-API-Key: <TENANT_API_KEY>" \
  -H "Content-Type: application/json" | python -m json.tool

# 3. Check approvals queue
curl -s http://localhost:8000/approvals/pending \
  -H "X-API-Key: <TENANT_API_KEY>" | python -m json.tool

# 4. Check customer activity
curl -s "http://localhost:8000/customer/activity" \
  -H "X-API-Key: <TENANT_API_KEY>" | python -m json.tool
```

### Definition of done (local)

- [ ] All 82 golden-path + pipeline tests pass
- [ ] Full test suite: 2735 passed, 0 failed
- [ ] R1 release gate: 505 regression + 152 E2E = 657 passed
- [ ] No live credentials used
- [ ] No external API calls made

---

## Security hardening (Kapitel 11)

Detailed procedures: **`docs/runbooks/security-hardening.md`**

Quick reference:

- Critical admin writes require operator role + same-origin (cookie auth).
- `read_only` cannot mutate (including legacy `/admin/*` recovery/support routes).
- Login throttled: 5/min per IP (in-memory; per-instance).
- Legacy Visma OAuth (`state=tenant_id`) disabled — use onboarding wizard.
- `GET /admin/alerts/run-all` removed; use `POST /admin/alerts/run-all`.
- Security headers on API responses; `no-store` on `/ops`, `/auth/admin`, `/ui`.
- Audit fail-closed on recovery and operator-alert mutations.

---

## Pilot stabilization baseline (2026-07-20)

**Canonical:** Git tag `krowolf-pilot-baseline-20260720`; document index `docs/DOCUMENT_INDEX.md`.

| Check | Expected |
|-------|----------|
| Tenants | Exactly `T_NIKLAS_DEMO_001` |
| Scheduler | `paused` (all tenants) |
| Gmail | `credential_source=tenant_oauth`; test-read PASS |
| External writes | Disabled; no Gmail scan during stabilization |
| Backup | Offsite verified before any operational reset |

**Scripts (run inside app container with `PYTHONPATH=/app`):**

```bash
python3 scripts/ops/stabilization_preflight.py
python3 scripts/ops/pre_live_niklas_archive.py T_NIKLAS_DEMO_001
python3 scripts/ops/niklas_operational_reset.py --dry-run
python3 scripts/ops/niklas_operational_reset.py --confirm-production-cleanup --execute
python3 scripts/ops/niklas_live_clean_baseline.py T_NIKLAS_DEMO_001
```

**Deploy from canonical commit (on server):**

```bash
sudo bash /opt/krowolf/scripts/k12_pilot_sync_bundle.sh /tmp/k12-rc-bundle.tar.gz
sudo bash /opt/krowolf/scripts/k12_pilot_rc_deploy.sh <COMMIT_SHA>
```

Preserves: `.env.production`, `.env.offsite`, `.env.browser-test`, `storage/`, `backups/`, tenant key files.

### Deploy model A (canonical)

Server Git HEAD **must** match `origin/main` canonical commit. Product code is deployed via:

1. `k12_create_rc_bundle.sh` → tarball (excludes `.env*`, `storage/`, `node_modules`)
2. `k12_pilot_sync_bundle.sh` → sync `app/`, `frontend/`, `scripts/`, etc. to `/opt/krowolf`
3. `k12_pilot_rc_deploy.sh <COMMIT_SHA>` → build image with `BUILD_COMMIT_SHA`, recreate `krowolf-app-1` only

**Git reconciliation on server** (after inventory + backup):

```bash
cd /opt/krowolf
sudo git -c safe.directory=/opt/krowolf fetch origin main
sudo git -c safe.directory=/opt/krowolf reset --hard origin/main
```

Runtime files (`.env.*`, `storage/`, `backups/`, `tenant_keys/`) are gitignored and preserved. Caddy config outside repo is unchanged unless explicitly updated.

**Do not** use server Git HEAD as deploy source if it diverges — always deploy from canonical `origin/main` commit via bundle.
