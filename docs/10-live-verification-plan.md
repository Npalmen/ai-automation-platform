# Live Verification Plan

> **Status: ALL phases A–O now PASSED. Phase O: CONDITIONAL GO (2026-07-08). Gmail inbox sync working — 8 real jobs created. 29/29 Phase O checks passed. Production is pilot-ready subject to: set support email, review pending email_send approval, rotate DB password.**
> Production deploy completed on `/opt/krowolf`; live commit `87d9369`; Docker Compose file `/opt/krowolf/docker-compose.prod.yml`; containers `krowolf-app-1`, `krowolf-db-1`, and `krowolf-caddy-1` running.
> Phase B passed: `/` and `/health` returned HTTP 200 with `env: production`; `/docs` and `/openapi.json` returned HTTP 404.
> Phase C passed: `/admin/tenants` returned 401 without key, 401 with wrong key, and 200 with correct key.
> Phase D passed: DB backup taken; `T_LIVE_TEST_001` created (HTTP 201); listed in admin; tenant key works; pilot readiness `almost_ready`; integration health has no secrets; tenant key rejected on admin endpoint (401); no cross-tenant data.
> Phase E passed: all tenant-scoped endpoints return 200 with correct key and 401 without; admin key rejected on tenant endpoint (403); tenant key rejected on admin endpoint (401); no secrets or cross-tenant data in any response; no 500s or stack traces in logs.
> Phase F passed: synthetic lead job created (job_id bea23f74-...); pipeline completed; status completed; requires_human_review False; 0 external actions; full isolation and auth-negative checks passed (20/20).
> Phase G passed: synthetic customer_inquiry created with force_approval_test:true; job_id 8b2d53d2-...; status awaiting_approval; approval created (approval_id f5d27fc3-..., next_on_approve action_dispatch); pending queue returned 200 scoped to T_LIVE_TEST_001; no key �?401; reject returned 200; approval removed from pending; no external writes; audit/integration events clean; 24/24 checks passed.
> Pre-live UI is now an Internal Operator Console; polished customer UI is deferred.
> Phase H, I, J, L, M, and N passed. Phase K BLOCKED — Gmail GOOGLE_OAUTH_REFRESH_TOKEN invalid_grant. Full live verification is not complete. Phase O cannot be GO until Phase K passes. Next: fix Gmail tokens → rerun Phase K → Phase O.
> Governing authority: `docs/00-master-plan.md`.
> Execute this plan only after all local preconditions are satisfied.
> After execution, record results in the Evidence Log at the end of this file.

---

## Purpose

Provide a complete, sequential, and executable verification plan for the first internal pilot tenant go-live.

This plan covers:
- Production server health
- Admin and tenant authentication
- Tenant provisioning
- Customer endpoint access
- Integration health (without destructive actions)
- Gmail OAuth and inbox sync
- Monday/Fortnox/Visma safe read-only checks
- Approval queue end-to-end
- Internal operator console and minimal customer-safe UI/status checks
- Smoke check
- Rollback and escalation

---

## Preconditions

All must be true before live verification begins.

- [x] Latest code deployed to production server �?live commit `87d9369` on `/opt/krowolf`.
- [x] Full local test suite passes: `python -m pytest --tb=no -q` �?2746 passed, 0 failed.
- [x] R1 release gate passes: `python -m scripts.run_release_gate_r1`.
- [ ] `ADMIN_API_KEY` set to a strong random value (not empty, not dev-mode default).
- [ ] `ENV=production` set in production environment.
- [ ] `APP_NAME` set (e.g. `Krowolf`).
- [ ] Database is a real PostgreSQL instance (not SQLite or in-memory).
- [ ] `python scripts/create_tables.py` run against production DB (idempotent).
- [ ] `python -m scripts.test_db_connection` returns `DB OK: 1`.
- [ ] DNS for `api.krowolf.se` and `app.krowolf.se` points to production server.
- [ ] Caddy/reverse proxy is running and HTTPS is active.
- [ ] Database backup completed before this session (see Backup section in `docs/08-runbook.md`).
- [ ] Support owner assigned for pilot tenant (person responsible for escalation).
- [ ] Restore rehearsal completed within the last 30 days.
- [ ] `/docs`, `/redoc`, `/openapi.json` are **not** accessible in production (`ENV=production` disables them).

### Operator confirmation required before Phase D

Before tenant provisioning or any Phase D step, an operator must confirm all of:

- `ENV=production` is set in the running production app/container.
- `ADMIN_API_KEY` or `ADMIN_API_KEYS` is set and non-empty.
- `DATABASE_URL` is set and points to the intended production PostgreSQL database.
- The app/container is running live commit `87d9369`, including `GET /health`.
- The app/container is running the latest deployed `app/ui/index.html` Internal Operator Console.
- Caddy/reverse proxy is running and HTTPS is active.
- A DB backup has completed before live tenant provisioning.
- Correct admin-key success path was verified with a real admin key against a read-only endpoint such as `GET /admin/tenants`; do not record the key in reports.

---

## Required secrets and environment variables

Variables verified in `app/core/settings.py`. Set all required ones before live verification.

### Always required

```env
ENV=production
APP_NAME=Krowolf
DATABASE_URL=postgresql://<user>:<pass>@<host>:5432/<dbname>
ADMIN_API_KEY=<strong-random-key>
ADMIN_KEYS=                          # optional: comma-separated list (takes precedence over ADMIN_API_KEY if set)
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<bcrypt hash>    # generate: python -c "from app.core.admin_session import hash_password; print(hash_password('your-pw'))"
SESSION_SECRET_KEY=<32-byte base64>  # generate: python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### Gmail (all four required for token auto-refresh)

```env
GOOGLE_MAIL_ACCESS_TOKEN=<access token from OAuth flow>
GOOGLE_OAUTH_REFRESH_TOKEN=<refresh token>
GOOGLE_OAUTH_CLIENT_ID=<client id from Google Cloud Console>
GOOGLE_OAUTH_CLIENT_SECRET=<client secret>
GOOGLE_MAIL_USER_ID=me
GOOGLE_MAIL_API_URL=https://gmail.googleapis.com/gmail/v1    # default, usually unchanged
```

Missing any one of the four Gmail vars causes silent `invalid_grant` on first token expiry.

### Monday

```env
MONDAY_API_KEY=<Monday API key>
MONDAY_BOARD_ID=<integer board ID>
MONDAY_API_URL=https://api.monday.com/v2                     # default
```

### Fortnox

```env
FORTNOX_ACCESS_TOKEN=<access token>
FORTNOX_CLIENT_SECRET=<client secret>
FORTNOX_API_URL=https://api.fortnox.se/3                     # default
```

### Visma (required only if Visma is enabled for pilot tenant)

```env
VISMA_CLIENT_ID=<client id>
VISMA_CLIENT_SECRET=<client secret>
VISMA_ACCESS_TOKEN=<access token>
VISMA_REDIRECT_URI=<redirect URI registered in Visma Dev Portal>
VISMA_SCOPES=ea:api, ea:sales, ea:purchase, ea:accounting, vls:api, offline_access
VISMA_API_URL=https://eaccountingapi.vismaonline.com/v2       # default
```

### LLM (optional �?falls back to deterministic without it)

```env
LLM_API_KEY=<OpenAI API key>
LLM_MODEL=gpt-4.1-mini                                        # default
```

### Optional integrations (not required for first pilot)

```env
SLACK_WEBHOOK_URL=<webhook URL>
CRM_WEBHOOK_URL=<webhook>
CRM_API_KEY=<key>
ACCOUNTING_WEBHOOK_URL=<webhook>
SUPPORT_WEBHOOK_URL=<webhook>
MICROSOFT_MAIL_ACCESS_TOKEN=<token>       # not required for first customer
```

---

## Required access

- SSH or shell access to production server (for env var verification and log inspection).
- Admin API key (`ADMIN_API_KEY`) �?must be kept secret.
- A Google account to complete Gmail OAuth consent for pilot tenant.
- Monday API key and board ID for pilot.
- Fortnox access token (read-only is sufficient for pilot).
- A safe test email address for inbox sync verification (not a customer-facing inbox).

---

## Stop conditions

**Immediately pause live verification if any of the following are true:**

1. Production server does not respond to `GET https://api.krowolf.se/` within 10 seconds.
2. `GET https://api.krowolf.se/health` returns non-200 or `"env"` is not `"production"`.
3. `GET /admin/tenants` succeeds without an `X-Admin-API-Key` header (auth fail-open).
4. A tenant API key can reach any `/admin/*` endpoint with 2xx response.
5. An unknown/test tenant ID receives permissions (not fail-closed).
6. A customer endpoint returns raw job payload, internal IDs, or routing internals not meant for customer.
7. `GET /integrations/health` response includes any actual token or secret value.
8. Gmail OAuth fails with `invalid_client` (client ID/secret mismatch �?requires Google Cloud Console fix before retry).
9. Gmail OAuth fails with consent loop requiring manual re-consent on Google account.
10. Any Fortnox/Visma action writes real data without prior approval gate confirmation.
11. Smoke check fails on a critical step (auth, tenant, pilot readiness).
12. Unexpected 500 responses on any step that should succeed.
13. Database is unreachable mid-session.
14. Backup is found to be missing or corrupted before starting live tenant provisioning.

**After hitting a stop condition:**
- Do not continue to the next phase.
- Document the condition and actual response in the Evidence Log.
- Contact platform team immediately.
- Do not attempt workarounds that bypass auth or approval gates.

---

## Phase A �?Pre-flight local checks

Run before touching production. Should already be done, but confirm before starting.

```bash
# A1: Full test suite
python -m pytest --tb=no -q
# Expected: 2499 passed, 0 failed

# A2: R1 release gate
python -m scripts.run_release_gate_r1
# Expected: R1 release gate passed (all requested phases)

# A3: DB connection (local or production tunnel)
python -m scripts.test_db_connection
# Expected: DB OK: 1

# A4: Tables created (idempotent)
python scripts/create_tables.py
# Expected: no errors
```

**Stop if:** A1 or A2 fails. Fix locally before proceeding.

---

## Phase B �?Production health checks

```bash
# B1: Root health check
curl -i https://api.krowolf.se/
# Expected: HTTP 200
# Expected body: {"status":"ok","app_name":"Krowolf","env":"production"}
# STOP if: env != "production" or HTTP != 200

# B2: Health endpoint
curl -i https://api.krowolf.se/health
# Expected: HTTP 200 with status ok

# B3: Docs are disabled in production
curl -i https://api.krowolf.se/docs
# Expected: HTTP 404 (disabled when ENV=production)
curl -i https://api.krowolf.se/openapi.json
# Expected: HTTP 404
# STOP if: /docs or /openapi.json returns 200 in production

# B4: UI is accessible
curl -i https://app.krowolf.se/ui
# or: https://api.krowolf.se/ui
# Expected: HTTP 200, HTML response containing index.html content
```

---

## Phase C �?Admin/auth checks

```bash
export BASE=https://api.krowolf.se
export ADMIN_KEY=<your ADMIN_API_KEY value>

# C1: Admin endpoint without any key �?must reject
curl -i $BASE/admin/tenants
# Expected: HTTP 401
# STOP if: 200 returned (auth fail-open)

# C2: Admin endpoint with wrong key �?must reject
curl -i $BASE/admin/tenants -H "X-Admin-API-Key: wrong-key-value"
# Expected: HTTP 401
# STOP if: 200 returned

# C3: Admin endpoint with correct key �?must succeed
curl -i $BASE/admin/tenants -H "X-Admin-API-Key: $ADMIN_KEY"
# Expected: HTTP 200, JSON list of tenants

# C4: Tenant endpoint without key �?must reject
curl -i $BASE/jobs
# Expected: HTTP 401 or 403

# C5: Admin key on tenant endpoint �?must reject (admin key is not a tenant key)
curl -i $BASE/jobs -H "X-API-Key: $ADMIN_KEY"
# Expected: HTTP 401 or 403 (admin key is not a valid tenant API key)

# C6: Admin session login check (browser admin UI)
# Navigate to: https://api.krowolf.se/admin/login (or /ui)
# Log in with ADMIN_USERNAME / password
# Expected: session cookie set, admin dashboard accessible
# Note: if ADMIN_PASSWORD_HASH is empty, session login is disabled �?document as TODO
```

---

## Phase D �?Tenant provisioning checks

```bash
export BASE=https://api.krowolf.se
export ADMIN_KEY=<your ADMIN_API_KEY value>

# D1: Create internal pilot tenant
curl -s -X POST $BASE/admin/tenants \
  -H "X-Admin-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Intern Pilot AB",
    "slug": "intern-pilot",
    "enabled_job_types": ["lead", "customer_inquiry"],
    "allowed_integrations": ["google_mail", "monday"],
    "auto_actions": {"lead": false, "customer_inquiry": false}
  }'
# Expected: HTTP 201
# Expected body: {"tenant_id":"T_INTERN_PILOT","name":"Intern Pilot AB","slug":"intern-pilot","api_key":"kw_...","status":"active"}
# IMPORTANT: record tenant_id and api_key �?api_key is shown ONCE and never again

# Record: TENANT_ID=T_INTERN_PILOT
# Record: TENANT_KEY=kw_<...>   �?save this securely NOW

export TENANT_ID=T_INTERN_PILOT
export TENANT_KEY=<api_key from D1 response>

# D2: Verify tenant appears in admin list
curl -s $BASE/admin/tenants -H "X-Admin-API-Key: $ADMIN_KEY" | python -m json.tool
# Expected: T_INTERN_PILOT in items list
# Expected: api_key NOT present in response (never returned after creation)

# D3: Verify tenant API key works
curl -i $BASE/tenant \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, {"current_tenant":"T_INTERN_PILOT",...}

# D4: Verify tenant API key cannot access admin endpoints
curl -i $BASE/admin/tenants \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 401 or 403
# STOP if: 200 returned

# D5: Pilot readiness initial state (expected: not_ready before integrations)
curl -s $BASE/pilot/readiness \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: overall_status: "not_ready" or "almost_ready"
# Expected: list of which checks pass/fail �?document the actual state
# NOT a stop condition �?not_ready is expected at this stage

# D6: Key rotation test (ONLY if this step is planned and safe)
# NOTE: rotating the key immediately requires using the new key for all subsequent steps
# Only rotate if this step is explicitly part of the plan for this session
# curl -s -X POST $BASE/admin/tenants/$TENANT_ID/rotate-key \
#   -H "X-Admin-API-Key: $ADMIN_KEY"
# Expected: {"tenant_id":"T_INTERN_PILOT","api_key":"kw_<new>"}
# Record new key if rotated
```

---

## Phase E �?Customer endpoint checks

```bash
export BASE=https://api.krowolf.se
export TENANT_KEY=<tenant api key from Phase D>

# E1: Customer account endpoint
curl -i $BASE/customer/account \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, tenant-scoped account data
# Expected: no raw job IDs in response payload
# Expected: no routing internals, env details, or raw LLM payloads

# E2: Customer activity
curl -i $BASE/customer/activity \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, empty or minimal activity for new tenant
# Expected: no job_id, no internal fields
# Acceptable: empty list []

# E3: Customer results (wow-statistics)
curl -i $BASE/customer/results \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, zero or empty stats for new tenant �?no crash

# E4: Customer health
curl -i $BASE/customer/health \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200

# E5: Tenant context
curl -i $BASE/tenant/context \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, tenant-scoped context

# E6: Tenant memory
curl -i $BASE/tenant/memory \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, tenant-scoped memory or empty

# E7: Integration events (scoped to tenant)
curl -i "$BASE/integration-events" \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, empty list for new tenant
# Expected: only events for T_INTERN_PILOT

# E8: Audit events (scoped to tenant)
curl -i $BASE/audit-events \
  -H "X-API-Key: $TENANT_KEY"
# Expected: HTTP 200, events scoped to T_INTERN_PILOT only

# E9: No endpoint without API key
curl -i $BASE/customer/account
curl -i $BASE/customer/activity
curl -i $BASE/integration-events
# Expected: HTTP 401 or 403 for all
# STOP if: any returns 200 without API key
```

---

## Phase F �?Integration health checks

```bash
export BASE=https://api.krowolf.se
export TENANT_KEY=<tenant api key>

# F1: Integration health before live tokens
curl -s $BASE/integrations/health \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: overall_status: "not_configured" or "warning"
# Expected: gmail.status: "not_configured" (if GOOGLE_MAIL_ACCESS_TOKEN not set)
# Expected: monday.status: "not_configured" (if MONDAY_API_KEY not set)
# Expected: NO token values in response body
# STOP if: actual token/key strings appear in response

# F2: After Gmail token is configured (Phase G), re-run to confirm status lifts
# (Document this as TODO until Phase G completes)

# F3: After Monday token is configured (Phase H), re-run to confirm monday.status updates
# (Document as TODO until Phase H completes)

# F4: Confirm overall_status is not "error" before pilot go-live
# "warning" is acceptable; "error" requires investigation before customer go-live
```

---

## Phase G �?Gmail OAuth and inbox sync checks

> **Only proceed here once Phase D (tenant provisioning) is complete.**
> Use a safe internal test Google account �?not a customer-facing inbox.
> Do not use a shared corporate mailbox that forwards to real customers.

```bash
export BASE=https://api.krowolf.se
export TENANT_ID=T_INTERN_PILOT
export TENANT_KEY=<tenant api key>

# G1: Start OAuth flow �?get authorization URL
curl -s "$BASE/auth/gmail/start?tenant_id=$TENANT_ID"
# Expected: redirect URL to accounts.google.com
# Action: open the URL in a browser, log in with the pilot Google account
# Action: grant all requested scopes (read, send �?as required by platform)
# Action: copy the `code` parameter from the callback URL after consent

# G2: Submit authorization code
curl -s -X POST $BASE/auth/gmail/callback \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"<authorization_code>\", \"tenant_id\": \"$TENANT_ID\"}"
# Expected: HTTP 200, token stored
# STOP if: invalid_client error (client ID/secret mismatch �?fix in Google Cloud Console)
# STOP if: consent loop �?user already revoked, require re-consent

# G3: Verify Gmail health lifted
curl -s $BASE/integrations/health \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: gmail.status: "healthy" or at minimum not "not_configured"
# Expected: no token values in response

# G4: Check scheduler status
curl -s $BASE/scheduler/status \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: run_mode and last_run information

# G5: Manual inbox sync trigger (admin)
curl -s -X POST $BASE/scheduler/run-once \
  -H "X-Admin-API-Key: $ADMIN_KEY"
# Expected: HTTP 200, sync triggered
# Check logs for scheduler_pass or inbox_sync errors

# G6: Send test email to inbox (manually, from a different email account)
# Action: send one test email to the pilot Google account inbox
# Subject: "Test from live verification �?[date]"
# Wait 1�? minutes or trigger sync manually again (G5)

# G7: Verify case created
curl -s $BASE/jobs \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: at least one job_id visible
# Expected: job_type matches classification of the test email
# Expected: status != "error"

# G8: Verify no unintended outbound email was sent
# Action: check the test Google account's Sent folder �?should be empty
# Check approval queue before any email send action

# G9: Verify outbound email requires approval
curl -s $BASE/approvals/pending \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: if email-send action triggered, it appears here as pending
# Expected: NOT auto-sent without approval (auto_actions: lead: false)
```

**Gmail stop conditions:**
- `invalid_grant` on G3 �?refresh token revoked. Re-run OAuth flow from G1.
- `invalid_client` �?check Google Cloud Console client ID/secret �?STOP.
- `gmail.send` scope missing �?check Google Cloud Console OAuth scopes �?STOP.

---

## Phase H �?Monday/Fortnox/Visma safe checks

> **Only safe read/status checks in this phase. No write actions. No export. No invoice creation.**
> Fortnox export must remain approval-gated. Never bypass this.

### Monday

```bash
export BASE=https://api.krowolf.se
export TENANT_KEY=<tenant api key>
export ADMIN_KEY=<admin api key>

# H1: Integration health shows Monday status
curl -s $BASE/integrations/health \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: monday.status: "healthy" if MONDAY_API_KEY is set and valid
# Expected: monday.status: "not_configured" if MONDAY_API_KEY is empty

# H2: Monday board scanner (if available as safe endpoint)
# TODO: verify exact endpoint from docs/runbook or main.py routes
# GET /monday/scan or similar �?check main.py for actual route name
# Expected: returns board columns/groups �?no write action

# H3: Check routing hints saved (if scanner has been run)
curl -s $BASE/onboarding/status \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: routing_hints_saved step shows "complete" if Monday scanner was run
```

### Fortnox

```bash
# H4: Integration health shows Fortnox status
curl -s $BASE/integrations/health \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: fortnox.status: "healthy" or "not_configured"

# H5: Fortnox dry-run / preview check only
# DO NOT run actual Fortnox export in this phase
# Preview is approval-gated �?only inspect, do not approve Fortnox export
# If Fortnox status endpoint exists: GET /integrations/fortnox/status
# TODO: verify exact endpoint �?document as TODO if not found

# H6: Confirm Fortnox export is approval-gated
# Action: inspect a test case that has underlag ready
# Action: trigger "Förhandsvisa i Fortnox" via UI if available
# Expected: preview shows data but does not submit
# STOP if: Fortnox export runs without approval gate
```

### Visma

```bash
# H7: Visma integration health
curl -s $BASE/integrations/health \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: visma.status: "not_configured" (Visma not required for first pilot customer)
# If Visma IS configured: "healthy" or "warning" �?document actual state
# No write actions to Visma in this phase
```

---

## Phase I �?Approval queue end-to-end checks

```bash
export BASE=https://api.krowolf.se
export TENANT_KEY=<tenant api key>

# I1: Create test lead with forced approval
curl -s -X POST $BASE/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $TENANT_KEY" \
  -d '{
    "tenant_id": "T_INTERN_PILOT",
    "job_type": "lead",
    "input_data": {
      "subject": "Live verification test lead",
      "message_text": "This is a live verification test. No real action required.",
      "sender_name": "Live Test",
      "sender_email": "livetest@internal.example.com",
      "force_approval_test": true
    }
  }'
# Expected: {"status":"awaiting_approval","job_id":"<job_id>"}
# Record job_id

export JOB_ID=<job_id from I1>

# I2: Check pending approvals
curl -s $BASE/approvals/pending \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: items list contains approval for JOB_ID
# Record approval_id

export APPROVAL_ID=<approval_id from I2>

# I3: Approve (body {} is required)
curl -s -X POST $BASE/approvals/$APPROVAL_ID/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $TENANT_KEY" \
  -d '{}'
# Expected: status changed to "approved" or "completed"
# Expected: if email send is approval type, email goes to test address only

# I4: Verify job completed
curl -s $BASE/jobs/$JOB_ID \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: status: "completed" or "done"

# I5: Verify job actions recorded
curl -s $BASE/jobs/$JOB_ID/actions \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: action list shows what was dispatched

# I6: Verify audit event created
curl -s $BASE/audit-events \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: audit event for the approval action is present
# Expected: tenant_id matches T_INTERN_PILOT only

# I7: Reject path test (optional �?confirm reject works)
# (Create another test job with force_approval_test, then reject)
# POST /jobs �?get approval_id
# POST /approvals/<approval_id>/reject  -d '{}'
# Expected: status: "rejected" or job moves to needs-help

# I8: Cross-tenant isolation check (if a second test tenant exists)
# Attempt to approve T_INTERN_PILOT's approval using a different tenant's key
# Expected: HTTP 404 (approval not visible to other tenants)
```

---

## Phase J �?Operator console and minimal customer-safe UI checks

```bash
export BASE=https://api.krowolf.se
export TENANT_KEY=<tenant api key>

# J1: Customer-safe status endpoint
curl -s $BASE/customer/results \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: HTTP 200
# Expected: returns minimal status/stats (possibly zero for new tenant �?acceptable)
# Expected: no admin-only data (no raw tenant configs, no other tenants' data)

# J2: Customer activity after test jobs
curl -s $BASE/customer/activity \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: test lead from Phase I appears here as an activity entry
# Expected: no job_id, no internal fields, no raw payload
# Expected: customer-readable format only

# J3: Open admin UI in browser
# Navigate to: https://api.krowolf.se/ui (or https://app.krowolf.se)
# Log in as admin (ADMIN_USERNAME/password)
# Expected: Internal Operator Console loads
# Expected: Super Admin / operator views are readable and functional
# Expected: T_INTERN_PILOT visible in tenant list
# Expected: "Behöver hjälp" queue shows any failed jobs

# J4: Open customer-safe UI mode (as pilot tenant)
# Navigate to: https://api.krowolf.se/ui
# Expected: minimal customer-safe views load
# Expected: activity/results visible after test jobs
# Expected: no admin-only data visible in customer view
# Expected: no raw JSON payloads in customer-visible sections

# J5: Pilot readiness check after setup
curl -s $BASE/pilot/readiness \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: overall_status: "ready" or "almost_ready" (after Gmail configured)
# If "not_ready": document which checks still fail and whether they block go-live
```

---

## Phase K �?Smoke check

```bash
# K1: Basic production smoke check
python scripts/smoke_check.py \
  --base-url https://api.krowolf.se \
  --expect-production
# Expected: all steps pass

# K2: With admin surface check
python scripts/smoke_check.py \
  --base-url https://api.krowolf.se \
  --expect-production \
  --admin-api-key $ADMIN_KEY
# Expected: admin endpoints respond correctly

# K3: With tenant surface check
python scripts/smoke_check.py \
  --base-url https://api.krowolf.se \
  --tenant-api-key $TENANT_KEY
# Expected: tenant endpoints respond correctly

# If smoke check script arguments differ from above, document actual args:
# TODO: verify exact script args before running �?see scripts/smoke_check.py --help
```

**Stop if:** any critical step of smoke check fails.

---

## Phase L �?Go/no-go decision

Before declaring Fas 2 pilot ready, verify all of the following are green:

| Gate | Check | Expected |
|------|-------|---------|
| L01 | Phase B: Production responds | `env: production`, HTTP 200 |
| L02 | Phase C: Admin auth works | Correct key �?200, wrong key �?401 |
| L03 | Phase D: Tenant provisioned | T_INTERN_PILOT exists, key works |
| L04 | Phase D: Pilot readiness | `not_error` (not_ready acceptable pre-Gmail) |
| L05 | Phase E: Customer endpoints require auth | All return 401/403 without key |
| L06 | Phase E: No secrets in customer responses | Manual inspection passes |
| L07 | Phase F: Integration health no secrets | No token values in response |
| L08 | Phase G: Gmail OAuth completed | `gmail.status: healthy` |
| L09 | Phase G: Inbox sync creates cases | Test email �?job created |
| L10 | Phase G: Outbound email requires approval | No unintended sends |
| L11 | Phase H: Fortnox remains approval-gated | No write without approval |
| L12 | Phase I: Approval queue works | Create �?pending �?approve �?completed |
| L13 | Phase I: Audit events created | Visible per-tenant after approval |
| L14 | Phase J: Customer UI loads | No crash, no admin-only data |
| L15 | Phase K: Smoke check passes | All steps green |
| L16 | Needs-help queue is empty | No critical failed jobs before pilot |

**Pilot is go-live ready only when all 16 gates pass.**

If any gate is red, document it in the Evidence Log and address it before declaring ready.

---

## Rollback / recovery

### If production is broken after a failed deployment

```bash
# 1. Revert to last known good Docker image
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build    # with previous Dockerfile/code

# 2. If DB schema was changed, restore from backup
# See: docs/08-runbook.md �?Backup and restore
```

### If tenant was provisioned with wrong config

```bash
# Deactivate bad tenant
curl -s -X PATCH https://api.krowolf.se/admin/tenants/<TENANT_ID>/status \
  -H "X-Admin-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "inactive"}'

# Create a new tenant with correct config (new slug �?new tenant_id)
```

### If Gmail OAuth token expired during pilot

See `docs/08-runbook.md` �?How to check OAuth/token issues.

```bash
# Re-run OAuth flow
GET /auth/gmail/start?tenant_id=<TENANT_ID>
# Follow redirect, complete consent, submit code via /auth/gmail/callback
# Verify: GET /integrations/health �?gmail.status: healthy
```

### If Monday API key is invalid

```bash
# Update MONDAY_API_KEY in production env, restart app
docker compose -f docker-compose.prod.yml restart
# Verify: GET /integrations/health �?monday.status: healthy or not_configured
```

### If critical job failure floods the needs-help queue

```bash
# Inspect:
GET /admin/operations/needs-help
Header: X-Admin-API-Key: <ADMIN_API_KEY>

# Retry a single job:
POST /admin/recovery/<job_id>/retry_job
Header: X-Admin-API-Key: <ADMIN_API_KEY>
Header: X-Tenant-ID: <TENANT_ID>

# If systemic: pause scheduler
PUT /dashboard/control
Header: X-API-Key: <TENANT_KEY>
Body: {"scheduler": {"run_mode": "paused"}}
# Contact platform team
```

### Escalation contacts

- System down or DB unreachable �?platform team immediately.
- OAuth token revoked �?platform team within 1h.
- Customer email sent incorrectly �?platform team + pilot customer immediately.
- Misclassification �?report via case detail, manual review during normal hours.

See `docs/08-runbook.md` �?Escalation rules.

---

## Evidence log template

Use this table when executing the plan. Fill in the Actual and Status columns as you run each step.

```markdown
| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| B1   | GET /          | HTTP 200, env:production | | �?| |
| B2   | GET /health    | HTTP 200 | | �?| |
| B3   | GET /docs      | HTTP 404 | | �?| |
| C1   | GET /admin/tenants (no key) | 401 | | �?| |
| C2   | GET /admin/tenants (wrong key) | 401 | | �?| |
| C3   | GET /admin/tenants (correct key) | 200 | | �?| |
| C4   | GET /jobs (no key) | 401/403 | | �?| |
| C5   | GET /jobs (admin key as tenant key) | 401/403 | | �?| |
| D1   | POST /admin/tenants | 201, api_key in body | | �?| Record key |
| D2   | GET /admin/tenants | 200, T_INTERN_PILOT listed, no api_key | | �?| |
| D3   | GET /tenant (tenant key) | 200, current_tenant:T_INTERN_PILOT | | �?| |
| D4   | GET /admin/tenants (tenant key) | 401/403 | | �?| |
| D5   | GET /pilot/readiness | not_ready/almost_ready | | �?| Document checks |
| E1   | GET /customer/account | 200, no secrets | | �?| |
| E2   | GET /customer/activity | 200, no internal fields | | �?| |
| E3   | GET /customer/results | 200, empty ok | | �?| |
| E4   | GET /customer/health | 200 | | �?| |
| E5   | GET /tenant/context | 200 | | �?| |
| E6   | GET /tenant/memory | 200 | | �?| |
| E7   | GET /integration-events | 200, tenant-scoped | | �?| |
| E8   | GET /audit-events | 200, tenant-scoped | | �?| |
| E9   | GET /customer/account (no key) | 401/403 | | �?| |
| F1   | GET /integrations/health | not_configured/warning, no secrets | | �?| |
| G1   | GET /auth/gmail/start | OAuth URL returned | | �?| |
| G2   | POST /auth/gmail/callback | 200, token stored | | �?| |
| G3   | GET /integrations/health (after Gmail) | gmail:healthy | | �?| |
| G5   | POST /scheduler/run-once | 200 | | �?| |
| G7   | GET /jobs (after test email) | job created | | �?| |
| G9   | GET /approvals/pending | email approval pending if triggered | | �?| |
| H1   | Integration health (Monday) | healthy/not_configured | | �?| |
| H4   | Integration health (Fortnox) | healthy/not_configured | | �?| |
| H7   | Integration health (Visma) | not_configured | | �?| |
| I1   | POST /jobs (force_approval) | awaiting_approval | | �?| Record job_id |
| I2   | GET /approvals/pending | approval listed | | �?| Record approval_id |
| I3   | POST /approvals/<id>/approve | approved/completed | | �?| |
| I4   | GET /jobs/<id> | completed | | �?| |
| I5   | GET /jobs/<id>/actions | action recorded | | �?| |
| I6   | GET /audit-events | audit event present | | �?| |
| J1   | GET /customer/results | 200, no admin data | | �?| |
| J2   | GET /customer/activity | activity visible | | �?| |
| J5   | GET /pilot/readiness (after setup) | ready/almost_ready | | �?| |
| K1   | smoke_check.py --expect-production | all steps pass | | �?| |
| K2   | smoke_check.py --admin-api-key | pass | | �?| |
| K3   | smoke_check.py --tenant-api-key | pass | | �?| |
```

Status key: �?Not run | �?Pass | �?Fail | ⚠️ Warning | 🛑 Stop condition hit

## Evidence log �?2026-07-07 controlled Phase A-C run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| A0 | `git status --short`; `git status --branch --short` | Clean working tree / latest code deployable | Modified `app/ui/index.html`; branch `main...origin/main`; latest commit `7cec357` | �?Fail | Local working tree is not clean, so latest local code is not fully committed/deployable. |
| A1 | `python -m pytest --tb=no -q` | Full suite passes | 2744 passed, 0 failed, 4 warnings | �?Pass | Python 3.14.3. |
| A2 | `python -m scripts.run_release_gate_r1` | R1 release gate passes | 505 regression + 152 E2E passed | �?Pass | 657 total gate tests passed. |
| A3 | Inspect `docs/01-current-truth.md` | Latest local status documented | Latest status updated with this controlled Phase A-C run | �?Pass | Live verification overall remains not completed. |
| A4 | Confirm `docs/10-live-verification-plan.md` exists | Plan exists | File exists and is being used for this run | �?Pass | This evidence log records only Phase A-C. |
| A5 | Inspect `docs/06-backlog.md` | No local blockers | Local blockers section says none; pre-live blockers require live environment | �?Pass | Dirty working tree found separately in A0. |
| A6 | Check live verification completion state | Not marked completed | Not marked completed; only Phase A-C partial run documented | �?Pass | Phase D+ remains not run. |
| A7 | Server/deploy env inspection | `ENV`, `ADMIN_API_KEY`, `DATABASE_URL`, image/code, Caddy confirmed | Requires operator confirmation | ⚠️ Warning | No SSH/server access available in this session. |
| B1 | `curl.exe -i --max-time 10 https://api.krowolf.se/` | HTTP 200, `env: production` | HTTP 200, `{"status":"ok","app_name":"Krowolf","env":"production"}` | �?Pass | No stack trace or secrets observed. |
| B2 | `curl.exe -i --max-time 10 https://api.krowolf.se/health` | HTTP 200 | HTTP 404, `{"detail":"Not Found"}` | �?Fail | Live verification plan expected `/health` to return HTTP 200. Code inspection showed no generic `/health` route. Response was controlled and did not leak internals. |
| B3 | `curl.exe -i --max-time 10 https://api.krowolf.se/docs` | HTTP 404 in production | HTTP 404, `{"detail":"Not Found"}` | �?Pass | Production docs are not exposed. |
| B4 | `curl.exe -i --max-time 10 https://api.krowolf.se/openapi.json` | HTTP 404 in production | HTTP 404, `{"detail":"Not Found"}` | �?Pass | OpenAPI schema is not exposed. |
| C1 | `curl.exe -i --max-time 10 https://api.krowolf.se/admin/tenants` | HTTP 401/403 | HTTP 401 | �?Pass | Admin endpoint rejects missing admin key. |
| C2 | `curl.exe -i --max-time 10 https://api.krowolf.se/admin/tenants -H "X-Admin-API-Key: wrong-key"` | HTTP 401/403 | HTTP 401 | �?Pass | Admin endpoint rejects wrong admin key. |
| C3 | `GET /admin/tenants` with correct `X-Admin-API-Key` | HTTP 200 | Blocked | �?Not run | `ADMIN_API_KEY` was not available in this session. |
| C4 | `GET /admin/tenants` with tenant key | HTTP 401/403 | Deferred | �?Not run | No tenant key exists yet; deferred to Phase D/E. |

## Blocker fix log �?2026-07-07 before Phase D

| Blocker | Fix/action | Local verification | Remaining before Phase D |
|---------|------------|--------------------|---------------------------|
| `/health` returned HTTP 404 in production | Added unauthenticated `GET /health` in `app/main.py`; returns only `status`, `app_name`, `env`. | `python -m pytest tests/test_root_routing.py tests/test_production_hardening.py -q` �?10 passed, 2 warnings. Full suite: 2746 passed, 4 warnings. R1 gate passed. | Completed after deploy: Phase B2 returned HTTP 200 with `env: production`. |
| Dirty `app/ui/index.html` | Resolved intentionally by replacing the previous fancy CSS/card-contrast dirty state with a minimal Internal Operator Console. Functional HTML/JS views and operator flows were preserved. | UI static structure check passed; `python -m pytest tests/test_root_routing.py -q` passed; full suite passed with 2746 tests; R1 gate passed. | Included in production deploy for live commit `87d9369`. |
| Correct admin-key success path not verified | Added explicit pending instruction: use real `ADMIN_API_KEY` only in secure environment against read-only `GET /admin/tenants`. | Verified after deploy: correct admin key returned HTTP 200 from `GET /admin/tenants`. | Completed for Phase C. Do not print or record the key. |
| Server/container deployment state unknown | Added required operator confirmation list. | Verified after deploy: `/opt/krowolf`, live commit `87d9369`, `/opt/krowolf/docker-compose.prod.yml`, and app/db/caddy containers running. | DB backup/support owner and Phase D-specific operator confirmations remain before tenant provisioning. |

## Deploy / Phase A-C re-run attempt �?2026-07-07 20:19

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| DPL-0 | Inspect deploy docs/tooling | Documented deploy path and available tooling | Only generic Docker Compose deploy commands exist; no server-specific SSH/deploy target found. `docker` and `gh` are unavailable in this session. | 🛑 Stop condition hit | Stopped before deploy as instructed when deploy procedure requires operator action. |
| DPL-1 | Check secret availability without printing values | `ADMIN_API_KEY` available for Phase C3 | No local `ADMIN_API_KEY` or `ADMIN_API_KEYS`; no local `DATABASE_URL`. | �?Not run | Correct admin-key success path remains blocked until key is provided/used securely. |
| DPL-2 | Deploy latest local code | Production app/container updated | Not run | �?Not run | Requires operator with Docker/server access or documented deploy automation. |
| DPL-3 | Re-run Phase A-C after deploy | Phase A-C pass/fail evidence | Not run | �?Not run | No live checks were run after blocked deploy attempt. |

## Post-push deploy / Phase A-C re-run attempt �?2026-07-07 20:24

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| DPL-4 | Verify pushed code | `main` clean and pushed | `HEAD` and `origin/main` are `8e19622`; working tree clean before this documentation update. | �?Pass | Latest local fixes are in GitHub. |
| DPL-5 | Test non-interactive SSH to production host | SSH command can run production deploy commands | `ssh -o BatchMode=yes ... api.krowolf.se` resolved to default user `niklas` and returned permission denied. | 🛑 Stop condition hit | No interactive password prompt attempted; no deploy command run. |
| DPL-6 | Check secret availability without printing values | `ADMIN_API_KEY` available for Phase C3 | No local `ADMIN_API_KEY`, `ADMIN_API_KEYS`, or `DATABASE_URL`. | �?Not run | Correct admin-key success path remains blocked until key is provided/used securely on server or in session. |
| DPL-7 | Deploy latest pushed code | Production app/container updated | Not run | �?Not run | Requires valid SSH/server access or operator-run deploy. |
| DPL-8 | Re-run Phase A-C after deploy | Phase A-C pass/fail evidence | Not run | �?Not run | No live checks were run after blocked deploy attempt. |

## Evidence log �?2026-07-07 post-deploy Phase A-C run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| A0 | Production deploy | Latest code deployed to production server | Deployed on `/opt/krowolf`; live commit `87d9369`; Docker Compose file `/opt/krowolf/docker-compose.prod.yml` | �?Pass | Phase A marked passed for this checkpoint. |
| A1 | Container status after deploy | App, DB, and reverse proxy running | `krowolf-app-1 running`; `krowolf-db-1 running`; `krowolf-caddy-1 running` | �?Pass | Server-side container state confirmed after deploy. |
| B1 | `GET https://api.krowolf.se/` | HTTP 200, `env: production` | HTTP 200, `{"status":"ok","app_name":"Krowolf","env":"production"}` | �?Pass | Public root health is healthy. |
| B2 | `GET https://api.krowolf.se/health` | HTTP 200, `env: production` | HTTP 200, `{"status":"ok","app_name":"Krowolf","env":"production"}` | �?Pass | `/health` blocker fixed and verified live. |
| B3 | `GET https://api.krowolf.se/docs` | HTTP 404 in production | HTTP 404 | �?Pass | Production docs disabled. |
| B4 | `GET https://api.krowolf.se/openapi.json` | HTTP 404 in production | HTTP 404 | �?Pass | OpenAPI schema disabled. |
| C1 | `GET /admin/tenants` without key | HTTP 401 | HTTP 401 | �?Pass | Admin endpoint rejects missing key. |
| C2 | `GET /admin/tenants` with wrong key | HTTP 401 | HTTP 401 | �?Pass | Admin endpoint rejects wrong key. |
| C3 | `GET /admin/tenants` with correct key | HTTP 200 | HTTP 200 | �?Pass | Existing tenants returned: `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1`. Admin key was not recorded. |
| D0 | Phase D �?tenant provisioning | Not run until Phase A-C and operator confirmations are complete | Not run | �?Not run | Do not mark full live verification complete. |

## Evidence log �?2026-07-07 Phase D run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| D-pre | DB backup | Recent backup confirmed | `pre-phase-d-20260707-190618.sql` (677 KB); automated daily backups also present through `ai_platform_2026-07-07-0200.sql.gz` | �?Pass | Backup verified before any write action. |
| D1 | `GET /admin/tenants` with admin key | HTTP 200 | HTTP 200 | �?Pass | Admin access confirmed. |
| D2 | Check existing tenants | `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1` untouched | All three listed as active; none modified | �?Pass | No real customer tenant was affected. |
| D3 | Check if `T_LIVE_TEST_001` exists | Check before create | Not found �?proceed to create | �?Pass | No duplicate created. |
| D4 | `POST /admin/tenants` (T_LIVE_TEST_001) | HTTP 201, tenant_id/name/slug/status in response, api_key one-time-only | HTTP 201; `tenant_id: T_LIVE_TEST_001`, `name: Live Test Tenant`, `slug: live-test-001`, `status: active`; `api_key` present (masked, length 35) | �?Pass | Key not recorded in report. `auto_actions` contract uses booleans `false`, not string `"manual"`. |
| D5 | `GET /admin/tenants` �?verify `T_LIVE_TEST_001` listed | Tenant listed, T_ELITGRUPPEN untouched | T_LIVE_TEST_001 listed (status active); T_ELITGRUPPEN untouched | �?Pass | |
| D5b | Rotate `T_LIVE_TEST_001` key | HTTP 200, fresh key | HTTP 200; fresh key (length 35) | �?Pass | Key used only in-memory during D5c–D7; cleared immediately after. |
| D5c | `GET /tenant` with T_LIVE_TEST_001 key | HTTP 200 | HTTP 200 | �?Pass | Tenant endpoint accessible with correct key. |
| D5d | `GET /pilot/readiness` with T_LIVE_TEST_001 key | not_ready or almost_ready (no integrations) | `almost_ready`; 6 pass, 5 warnings, 0 failures | �?Pass | Expected for new tenant without integrations. |
| D5e | `GET /integrations/health` with T_LIVE_TEST_001 key | overall_status warning/not_configured; no secrets | `overall_status: warning`; no token/key/secret in response | �?Pass | `NO_SECRETS_IN_RESPONSE=ok`. |
| D6 | `GET /admin/tenants` with T_LIVE_TEST_001 tenant key | HTTP 401 or 403 | HTTP 401 | �?Pass | ISOLATION=OK �?tenant key cannot access admin endpoints. |
| D7 | `GET /jobs` with T_LIVE_TEST_001 key �?no T_ELITGRUPPEN data | Empty jobs list; no cross-tenant leakage | Empty list (expected for new tenant); no T_ELITGRUPPEN data | �?Pass | Cross-tenant isolation confirmed. |
| D8 | Clear secrets | All keys unset from environment | `unset ADMIN_KEY && unset TENANT_KEY` run; temp scripts removed from server | �?Pass | No secrets persisted. |
| D-end | Phase D overall | All D-checks pass | All pass | �?Pass | Phase D complete 2026-07-07. |

## Evidence log �?2026-07-07 Phase E run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| E-pre | Preconditions | Phase A-D passed; T_LIVE_TEST_001 active; fresh key | All confirmed; key rotated HTTP 200; key length 35 | �?Pass | |
| E1 | `GET /tenant` with key | 200; no secrets; scoped | 200; no secrets | �?Pass | Confirmed in server logs. |
| E1b | `GET /tenant` without key | 401 | 401 | �?Pass | |
| E2a | `GET /customer/health` with key | 200; no secrets | 200; no secrets | �?Pass | |
| E2b | `GET /customer/health` without key | 401 | 401 | �?Pass | |
| E2c | `GET /customer/results` with key | 200; no secrets | 200; no secrets | �?Pass | |
| E2d | `GET /customer/activity` with key | 200; no secrets | 200; no secrets | �?Pass | |
| E2e | `GET /customer/account` with key | 200; no secrets | 200; no secrets | �?Pass | |
| E3 | `GET /pilot/readiness` with key | 200; almost_ready | 200; almost_ready | �?Pass | |
| E4a | `GET /integrations/health` with key | 200; no secrets | 200; overall_status warning; no secrets | �?Pass | |
| E4b | `GET /integrations/health` without key | 401 | 401 | �?Pass | |
| E5a | `GET /jobs` with key | 200; empty; no cross-tenant | 200; empty list | �?Pass | |
| E5b | `GET /jobs` without key | 401 | 401 | �?Pass | |
| E6a | `GET /audit-events` with key | 200; no cross-tenant | 200; no cross-tenant data | �?Pass | |
| E6b | `GET /audit-events` without key | 401 | 401 | �?Pass | |
| E6c | `GET /integration-events` with key | 200; no cross-tenant | 200; no cross-tenant data | �?Pass | |
| E6d | `GET /integration-events` without key | 401 | 401 | �?Pass | |
| E7a | `GET /tenant/context` with key | 200; no secrets | 200; no secrets | �?Pass | |
| E7b | `GET /tenant/context` without key | 401 | 401 | �?Pass | |
| E7c | `GET /tenant/memory` with key | 200; no secrets | 200; no secrets | �?Pass | |
| E7d | `GET /tenant/memory` without key | 401 | 401 | �?Pass | |
| E8a | `X-Tenant-ID: T_ELITGRUPPEN` + T_LIVE_TEST_001 key | 401 or 403 (expected) �?OR 200 (if header ignored per design) | 200 | �?Pass (design) | `X-Tenant-ID` is ignored when `TENANT_API_KEYS` configured; tenant resolved from key only; response scoped to T_LIVE_TEST_001 not T_ELITGRUPPEN. Correct and documented behavior. |
| E8b | Admin key on `GET /jobs` | 401 or 403 | 403 | �?Pass | Admin key correctly rejected as tenant key. |
| E8c | Tenant key on `GET /admin/tenants` | 401 or 403 | 401 | �?Pass | Tenant key correctly rejected on admin endpoint. |
| E9 | App logs review | No 500s, no stack traces, no leaked secrets | No errors; 200/401/403 only; SQL echo verbose but no secrets; key stored as SHA-256 hash | �?Pass | Non-blocking: SQL echo verbosity noted as cleanup item. |
| E-end | Phase E overall | All E-checks pass | All pass | �?Pass | Phase E complete 2026-07-07. |

## Evidence log �?2026-07-07 Phase F run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| F1 | Tenant safety config | auto_actions false/manual for all; no ext integrations | `auto_actions: {lead:false, customer_inquiry:false, invoice:false}`; no integrations configured | �?Pass | |
| F2 | `POST /jobs` synthetic lead | HTTP 200/201; job_id returned; no secrets | HTTP 200; `job_id: bea23f74-1dbe-4424-a8cb-60262da92f9b`; `tenant_id: T_LIVE_TEST_001`; no secrets | �?Pass | Pipeline ran synchronously to completion. |
| F2b | Pipeline result | status completed; no external actions | `status: completed`; `result.status: completed`; `requires_human_review: False`; `summary: "Ingen manuell överlämning behövs."`; 0 external actions | �?Pass | `auto_actions:false` blocked any dispatch. |
| F3 | `GET /jobs/:id` with key | 200; scoped to T_LIVE_TEST_001; no secrets | 200; `tenant_id: T_LIVE_TEST_001`; `job_type: lead`; `status: completed`; no secrets; no cross-tenant data | �?Pass | |
| F4 | `GET /jobs` list | 200; synthetic job present; no cross-tenant | 200; job listed; T_ELITGRUPPEN/TENANT_2001/T_TEST1 absent | �?Pass | |
| F5 | `GET /audit-events` | 200; no cross-tenant; no external write events | 200; no cross-tenant data; no gmail/monday/fortnox/visma write events | �?Pass | |
| F5b | `GET /integration-events` | 200; no external write events | 200; no external write events | �?Pass | |
| F6 | App logs review | No external writes; no 500s; no stack traces | No Gmail/Monday/Fortnox/Visma patterns; no 500s or stack traces | �?Pass | |
| F7 | `GET /jobs/:id` without key | 401 | 401 | �?Pass | |
| F7b | Wrong X-Tenant-ID + correct key on specific job | 401/403/404 or 200 scoped to T_LIVE_TEST_001 | 200 scoped to T_LIVE_TEST_001 | �?Pass (design) | X-Tenant-ID header ignored per auth design. |
| F-end | Phase F overall | 20/20 pass | 20 pass, 0 fail, 0 warn | �?Pass | Phase F complete 2026-07-07. |


## Evidence log — 2026-07-07 Phase G run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| G1 | Approval endpoint contract | Endpoints identified; auth confirmed | `GET /approvals/pending`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`, `GET /jobs/{id}/approvals` — all tenant-scoped via `get_verified_tenant` | ✅ Pass | Reject body: `{actor?,channel?,note?}`; reject never sends email or dispatches action. |
| G2 | `POST /jobs` force_approval_test:true | HTTP 200; status awaiting_approval; no secrets | HTTP 200; `job_id: 8b2d53d2-cc44-4d45-a11b-5a4a60654bb0`; `status: awaiting_approval`; no secrets | ✅ Pass | `force_approval_test: true` is the deterministic trigger. |
| G3 | `GET /jobs/:id` | 200; awaiting_approval; scoped to T_LIVE_TEST_001; no secrets | 200; `status: awaiting_approval`; `result.summary: "Approval dispatched via dashboard."`; no cross-tenant data; no secrets | ✅ Pass | Job status correctly reflects approval gate. |
| G4 | `GET /approvals/pending` | 200; synthetic approval visible; no cross-tenant | 200; 2 pending for T_LIVE_TEST_001; `approval_id: f5d27fc3-071c-41f0-ba65-c9f052f591b3`; `next_on_approve: action_dispatch`; no cross-tenant; no secrets | ✅ Pass | Second pending is Phase F email_send (eml_adeaf87...); cleanup item. |
| G5a | `/approvals/pending` without key | 401 | 401 | ✅ Pass | |
| G5b | `X-Tenant-ID: T_ELITGRUPPEN` + T_LIVE_TEST_001 key | 401/403 or scoped only to T_LIVE_TEST_001 | 200 scoped to T_LIVE_TEST_001; T_ELITGRUPPEN absent | ✅ Pass (design) | Header ignored per auth design; tenant resolved from key only. |
| G6 | `POST /approvals/:id/reject` | 200/204; no external write | HTTP 200; job status -> `manual_review`; no email_sent/monday/fortnox markers | ✅ Pass | Reject is safe; no external write path executed. |
| G7 | `GET /approvals/pending` after reject | Synthetic approval no longer pending | Approval removed; T_ELITGRUPPEN/TENANT_2001/T_TEST1 absent | ✅ Pass | |
| G8a | `GET /audit-events` | 200; no cross-tenant; no external writes | 200; no cross-tenant data; no external write events | ✅ Pass | |
| G8b | `GET /integration-events` | 200; no external write events | 200; no external write events | ✅ Pass | |
| G9 | App logs | No 500s; no stack traces; no external writes | `POST /approvals/.../reject 200 OK`; no errors; no external writes | ✅ Pass | |
| G-end | Phase G overall | All checks pass | 24 pass, 0 fail, 0 warn | ✅ Pass | Phase G complete 2026-07-07. Phase H not run. |


## Evidence log — 2026-07-07 Phase H run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| H1 | `GET /integrations/health` with key | 200; safe status; no secrets; no cross-tenant | 200; `overall_status: warning`; `gmail.status: warning` (configured, not synced); no secrets; no cross-tenant | ✅ Pass | Warning is expected — OAuth not yet connected. `warning` is a safe/controlled state. |
| H2a | `GET /integrations` with key | 200; list of enabled integrations; no secrets | 200; 2 items: Monday.com, Google Mail; no secrets; no cross-tenant | ✅ Pass | |
| H2b | `GET /setup/status` with key | 200; readiness overview; no secrets | 200; `readiness.score: 90, status: ready`; `google_mail: true, monday: true, fortnox: false, visma: false`; `missing: ["Support email not configured"]` | ✅ Pass | `google_mail: true, monday: true` means env credentials present but OAuth not yet performed. |
| H2c | `GET /pilot/readiness` with key | 200; almost_ready/ready | 200; `almost_ready` | ✅ Pass | |
| H3a | `GET /integrations/visma/status` with key | 200; disconnected safe state | 200; `status: disconnected, connected: false` | ✅ Pass | No tokens; Visma not connected. |
| H3b | `GET /integrations/visma/oauth/url` with key | 503 or URL without client_secret | 503; `"Visma OAuth is not configured"` | ✅ Pass | VISMA_CLIENT_ID not set; safe not-configured response. |
| H3-skip | `/oauth/start`, `/oauth/callback` | Not tested | Not tested | ✅ Skipped | Redirect/token-exchange endpoints out of scope per plan. |
| H4 | `GET /integration-events` with key | 200; no external writes; no cross-tenant | 200; no gmail/monday/fortnox write events; no cross-tenant | ✅ Pass | |
| H5 | `GET /audit-events` with key | 200; no cross-tenant; no secrets | 200; T_LIVE_TEST_001 data only; no secrets | ✅ Pass | |
| H6a | `/integrations/health` without key | 401 | 401 | ✅ Pass | |
| H6b | `X-Tenant-ID: T_ELITGRUPPEN` + T_LIVE_TEST_001 key | 401/403 or scoped to T_LIVE_TEST_001 only | 200 scoped to T_LIVE_TEST_001 only; T_ELITGRUPPEN absent | ✅ Pass (design) | Header ignored per auth design. |
| H7 | `GET /approvals/pending` — Phase F cleanup check | 200; document Phase F email_send approval | 200; `eml_adeaf87ada864e66bbb6` (job bea23f74..., next_on_approve: email_send) found; rejected via cleanup → HTTP 200 | ✅ Pass + Cleanup | Phase F email_send approval cleaned up. No external write triggered on reject. |
| H8 | App logs | No 500s; no secrets; no external writes | All endpoints logged cleanly; 401 for no-key; 200 for valid; 503 for unconfigured Visma; no errors | ✅ Pass | |
| H-end | Phase H overall | All checks pass | 42 pass, 0 fail, 1 warn (expected cleanup) | ✅ Pass | Phase H complete 2026-07-07. Phase I not run. |

## Evidence log — 2026-07-07 Phase I run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| I1a | `GET https://app.krowolf.se/ui` | 200; operator console HTML; no secrets | 200; "Internal Operator Console" in HTML; operator sections present | ✅ Pass | Script false-positive: `password` matched CSS `input[type="password"]` and JS var names — not actual secret values. Verified separately. |
| I1b | `GET https://api.krowolf.se/ui` | 200; same HTML | 200 | ✅ Pass | Same HTML served from api.krowolf.se/ui as well. |
| I1c | Cache-bust request | 200; same content | 200 | ✅ Pass | |
| I2 | Static HTML content sanity | All section markers present; no embedded secrets | "Internal Operator Console", "Tenants", "Readiness", "Integrations", "Jobs", "Approvals", "Activity", "Setup" all present (460 KB HTML); no actual secret values embedded | ✅ Pass | Script false-positive on variable NAMES in JS (`access_token`, `client_secret`) and config help text — not actual values. |
| I3 | No-key: /tenant, /jobs, /approvals/pending | 401/403 | All → 401 | ✅ Pass | |
| I4 | /tenant, /customer/health, /customer/results, /customer/activity, /customer/account with key | 200; scoped; no secrets | All 200; T_LIVE_TEST_001 scoped; no secrets; no cross-tenant | ✅ Pass | |
| I5a | /pilot/readiness with key | 200; almost_ready | 200; almost_ready | ✅ Pass | |
| I5b | /integrations/health with key | 200; safe state | 200; overall_status: warning | ✅ Pass | |
| I5c | /jobs with key | 200; only T_LIVE_TEST_001 jobs | 200; total=2 (Phase F + G synthetic jobs); no cross-tenant | ✅ Pass | |
| I5d | /approvals/pending with key | 200; empty after H cleanup | 200; 0 pending | ✅ Pass | Queue empty after Phase H cleanup. |
| I5e | /audit-events with key | 200; no cross-tenant | 200; T_LIVE_TEST_001 only; no secrets | ✅ Pass | |
| I6a | /admin/tenants without key | 401 | 401 | ✅ Pass | |
| I6b | /admin/tenants with admin key | 200; no api_key values; tenants listed | 200; tenants: T_ELITGRUPPEN, TENANT_2001, T_LIVE_TEST_001, T_TEST1; no api_key values in list; no secrets | ✅ Pass | |
| I7 | Browser UI check (app.krowolf.se/ui) | "Internal Operator Console" title; login form; no plaintext keys; minimal internal UI | ✅ Confirmed: "Internal Operator Console" title; Admin/Kund tabs; login form (username/password inputs, no values shown); no plaintext API keys; no old fancy SaaS dashboard; minimal operator UI | ✅ Pass | Screenshot taken. UI correct post-deploy. |
| I8 | App logs | No 500s; no secrets; no external writes | All endpoints 200; 401 for no-key; no errors; no secrets | ✅ Pass | |
| I-end | Phase I overall | All checks pass | 58 pass, 0 true fail, 0 warn; 3 script false-positives explained | ✅ Pass | False-positives: HTML `input[type="password"]` CSS selector, JS variable names `access_token`/`client_secret`, config help text "FORTNOX_ACCESS_TOKEN är konfigurerade" — none are actual values. Phase I complete 2026-07-07. Phase J not run. |

### Phase I false-positive note

The script's secret detection pattern (`access_token|client_secret|password`) is too broad for HTML content. It matched:
- `input[type="password"]` — standard HTML login form CSS selector (safe)
- JS variable names `admin_api_key`, `PasswordInput` — code variable names (not values)
- UI help text: `"FORTNOX_ACCESS_TOKEN och FORTNOX_CLIENT_SECRET är konfigurerade"` — config status display text showing env var NAMES, not VALUES

None of these contain actual secret values. Browser inspection confirmed no secrets are visible in the rendered UI.

## Evidence log — 2026-07-07 Phase J run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| J1 | Gmail OAuth config inspection (masked) | Env vars present/absent; secrets masked | `GOOGLE_MAIL_ACCESS_TOKEN=SET (len=253)`, `GOOGLE_OAUTH_REFRESH_TOKEN=SET`, `GOOGLE_OAUTH_CLIENT_ID=SET (visible, safe)`, `GOOGLE_OAUTH_CLIENT_SECRET=SET (masked)`, `GOOGLE_MAIL_API_URL=SET`, `GOOGLE_MAIL_USER_ID=SET`; `GOOGLE_CALENDAR_ACCESS_TOKEN=EMPTY` | ✅ Pass | All required Gmail credentials present. Env var names confirmed to match `settings.py` exactly. No secrets printed. |
| J2 | Route/code inspection | Sync routes identified; OAuth routes noted | Sync: `POST /gmail/process-inbox`, `POST /workflow-scan/gmail`, `POST /dashboard/inbox-sync` (NOT called). No Google OAuth consent URL routes exist. Gmail uses static token model (not consent flow). Token refresh internal only. | ✅ Pass | Gmail design: tokens set as env vars; no browser OAuth redirect needed. |
| J3 | `GET /integrations/health` (Gmail) | 200; safe status; no secrets | 200; `gmail.status: warning, configured: True`; `monday.status: warning, configured: True`; `fortnox.status: not_configured`; no secrets | ✅ Pass | `warning` = token set but scanner not yet run. Expected for new tenant. |
| J4a | `GET /setup/status` | 200; Gmail readiness clear | 200; `google_mail: True, email_connected: True`; `readiness.score: 90, status: ready`; `missing: ["Support email not configured"]` | ✅ Pass | Gmail is connected at config level. |
| J4b | `GET /pilot/readiness` | 200; almost_ready/ready | 200; `almost_ready`; warnings: onboarding 4/8 steps, no routing hints, no integration events yet | ✅ Pass | Expected pre-scan state. |
| J5 | OAuth auth-url endpoint check | 404 (no such routes) | `/integrations/google/oauth/url` → 404; `/integrations/google/oauth/start` → 404; `/integrations/google_mail/oauth/url` → 404; `/integrations/gmail/oauth/url` → 404 | ✅ Pass | Confirmed: Gmail has no OAuth consent URL route. Static token model only. |
| J6 | Gmail callback route check | 404 (not implemented) | `/integrations/google/oauth/callback?code=SYNTHETIC_INVALID&state=SYNTHETIC_INVALID` → 404 | ✅ Pass | No Gmail callback route. No token exchange. No real code used. |
| J7 | Inbox sync routes + workflow-scan/status | Routes identified; not called | Sync routes documented (NOT called); `GET /workflow-scan/status` → 200; `status: never_run, last_scan_at: null, systems_scanned: []` | ✅ Pass | Scanner never run. No inbox data read. |
| J8a | `GET /integration-events` | 200; no Gmail events; no secrets | 200; no gmail_send/inbox_sync events; no secrets; no cross-tenant | ✅ Pass | |
| J8b | `GET /audit-events` | 200; no secrets; T_LIVE_TEST_001 only | 200; no secrets; no cross-tenant | ✅ Pass | |
| J9 | App logs | No 500s; no Gmail actions; no secrets | No 500s; no stack traces; no OAuth tokens; 404s for non-existent OAuth routes as expected | ✅ Pass | WARN false-positive: `gmail.*inbox` matched function name `_run_gmail_inbox_sync` in log context — no actual inbox sync ran. |
| J-end | Phase J overall | All checks pass | 32 pass, 0 fail, 1 warn (false positive) | ✅ Pass | Phase J complete 2026-07-07. Phase K not run. |

### Gmail OAuth configuration summary (T_LIVE_TEST_001, 2026-07-07)

- **Token model:** Static env-var tokens (not browser consent flow). No OAuth redirect URL needed.
- **`GOOGLE_MAIL_ACCESS_TOKEN`:** SET, length 253 — valid token present.
- **`GOOGLE_OAUTH_REFRESH_TOKEN`:** SET — auto-refresh enabled when access token expires.
- **`GOOGLE_OAUTH_CLIENT_ID`:** SET — visible, safe (public OAuth client ID).
- **`GOOGLE_OAUTH_CLIENT_SECRET`:** SET (masked) — required for token refresh.
- **`GOOGLE_MAIL_USER_ID`:** SET (`me`) — correct for Gmail API user context.
- **`GOOGLE_MAIL_API_URL`:** `https://gmail.googleapis.com/gmail/v1` — standard Gmail API.
- **Env var names:** All match `app/core/settings.py` exactly — no mismatch.
- **Calendar:** `GOOGLE_CALENDAR_ACCESS_TOKEN` empty — calendar not configured (not in scope).
- **Inbox sync:** Token present; scanner never run; `workflow-scan/status = never_run`.
- **Next step:** Inbox sync (`POST /gmail/process-inbox` or `POST /workflow-scan/gmail`) requires explicit approval and is blocked until Phase K is approved.

## Evidence log — 2026-07-07 Phase K run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| Preconditions | auto_actions safety check | auto_actions false for all types | `{lead: False, customer_inquiry: False, invoice: False}` | ✅ Pass | Safe to proceed with sync attempt. |
| K1 | `POST /gmail/process-inbox` dry_run=true | 200; preview; no side effects | HTTP 200; `dry_run: True`; 0 new jobs; no side effects | ✅ Pass | |
| K2 | `POST /gmail/process-inbox` dry_run=false | 200; jobs created | HTTP 200; `dry_run: False`; **8 new jobs created** | ✅ Pass | `jobs_before=2 → jobs_after=10`. |
| K3 | Jobs list after sync | New jobs present | 10 total (2 synthetic + 8 from Gmail inbox) | ✅ Pass | |
| K4 | `auto_actions` safety | No external dispatch | `auto_actions: {lead: False, customer_inquiry: False, invoice: False}` — no dispatch triggered | ✅ Pass | |
| K5 | App logs | No errors; 200 OK | `POST /gmail/process-inbox HTTP/1.1 200 OK` ×2; no errors; no leaked tokens | ✅ Pass | |
| K-end | Phase K overall | Gmail inbox sync working | **PASSED** — 8 real jobs from Gmail inbox, token refresh works | ✅ PASSED | New OAuth client `502012997563-gp9iku5erqff3u8tad923pk8mb7fsp8m` configured. |

**Phase K resolution (2026-07-08):**
- New Google OAuth 2.0 client created in Google Cloud Console
- `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_MAIL_ACCESS_TOKEN` all updated in `.env.production`
- Container recreated with `docker compose up -d` (not `restart` — env vars require container recreation)
- Token refresh pre-validated against Google API: `PASS, expires_in=3599`
- Real inbox sync: 8 jobs created, `auto_actions=false`, no external writes

**Lesson recorded:** `docker compose restart` does NOT re-read `.env.production`. Must use `docker compose up -d` after env changes.

### Phase K blocker: Gmail token invalid_grant

**Error:** `Gmail token refresh failed (400): {"error": "invalid_grant", "error_description": "Bad Request"}`

**Root cause:** `GOOGLE_OAUTH_REFRESH_TOKEN` in `.env.production` is invalid or has been revoked by Google. Common causes:
1. The Google account owner manually revoked app access in Google Account Security settings
2. The OAuth refresh token expired (Google can revoke tokens after ~6 months of inactivity)
3. `GOOGLE_OAUTH_CLIENT_ID` or `GOOGLE_OAUTH_CLIENT_SECRET` changed after the token was issued
4. Too many refresh tokens issued for the same OAuth client

**What is NOT a problem:**
- The code handles this correctly (503, not 500)
- No partial Gmail API calls were made
- No inbox data was read or written
- No jobs were created from bad state
- No secrets were leaked

**Required fix (operator action):**
1. Go to Google Cloud Console → APIs & Services → OAuth consent
2. Verify the OAuth app is still approved and scopes unchanged
3. Re-run the OAuth consent flow for the Gmail account used by T_LIVE_TEST_001
4. Obtain a fresh `access_token` and `refresh_token`
5. Update `.env.production`: set `GOOGLE_MAIL_ACCESS_TOKEN=<new_token>` and `GOOGLE_OAUTH_REFRESH_TOKEN=<new_refresh_token>`
6. Restart the app container: `sudo docker compose -f /opt/krowolf/docker-compose.prod.yml restart app`
7. Rerun Phase K
### Phase L — Monday readiness/no-write verification (2026-07-07) — PASSED

| Check | Step | Expected | Actual | Status | Notes |
|-------|------|----------|--------|--------|-------|
| L1 | Monday config inspection | Token masked; key present or absent clear | `MONDAY_API_KEY` SET (len=227); `MONDAY_BOARD_ID` SET (len=11); `MONDAY_API_URL` set; no token value printed | ✅ Pass | `MONDAY_WORKSPACE_ID` absent — not required. |
| L2 | Monday routes identified | Write routes identified; no write called | 6 routes documented; `POST /integrations/{type}/execute` noted but not called with real payload | ✅ Pass | |
| L3 | `GET /integrations/health` | 200; monday.status visible; no secrets | HTTP 200; `monday.status: warning, configured: True`; no tokens; T_LIVE_TEST_001 only | ✅ Pass | Warning expected — no dispatch event yet. |
| L4a | `GET /setup/status` | 200; monday readiness visible | HTTP 200; `connections.monday: True`; score 90; no secrets | ✅ Pass | |
| L4b | `GET /pilot/readiness` | 200; readiness state clear | HTTP 200; `almost_ready`; script FAIL = false positive (matched "TENANT_API_KEYS konfigurerat.") | ✅ Pass | FP confirmed by direct response inspection. |
| L5 | Monday-specific status endpoints | 200/404/405 controlled | `/integrations/monday/status` → 404; `/integrations/monday/health` → 404 | ✅ Pass | Correct — no Monday-specific route; health bundled in `/integrations/health`. |
| L6 | Execute endpoint protection | 401/403/400/422; no write | `POST /integrations/monday/execute` (no key) → 401; no real payload sent | ✅ Pass | |
| L7a | `GET /integration-events` | No monday write events; no secrets | HTTP 200; no monday_create/update/delete; no secrets; T_LIVE_TEST_001 only | ✅ Pass | |
| L7b | `GET /audit-events` | No monday write events; no secrets | HTTP 200; script FAIL = false positive (matched `action: "api_key_rotated"`); no write events | ✅ Pass | FP confirmed by direct response inspection. |
| L8a | No-key auth | 401/403 | HTTP 401 | ✅ Pass | |
| L8b | Cross-tenant isolation | 401/403 or T_LIVE_TEST_001 scoped only | HTTP 200 scoped to T_LIVE_TEST_001; T_ELITGRUPPEN state not exposed | ✅ Pass (design) | `X-Tenant-ID` header ignored when API key is set — correct auth design. |
| L9 | App logs | No 500s; no Monday writes; no tokens | No 500s; no stack traces; no Monday write events; no leaked tokens; 2 Phase K WARNs (expected historical) | ✅ Pass | |
| L-end | Phase L overall | PASSED / FAILED / BLOCKED | **PASSED** — 30 pass, 0 true fail, 2 false-positive script FAILs | ✅ PASSED | Monday config verified read-only; no writes. |

**Monday config summary:**
- `MONDAY_API_KEY`: SET (len=227)
- `MONDAY_BOARD_ID`: SET (11 chars)
- `MONDAY_API_URL`: `https://api.monday.com/v2`
- Auth model: API key (no OAuth)
- No write executed; `auto_actions` remain `false`
- Phase K Gmail blocker remains unresolved

### Phase M — Final pre-pilot cleanup/status consolidation (2026-07-07) — PASSED

| Check | Step | Expected | Actual | Status | Notes |
|-------|------|----------|--------|--------|-------|
| M1 | Server/container status | Commit `87d9369`+; app/db/caddy Up; no restart; no 500s | Commit `87d9369`; app Up 2h; db Up 2mo; caddy Up 2mo; no restart; no 500s | ✅ Pass | |
| M2 | Production health | `/` 200 prod; `/health` 200 prod; `/docs` 404; `/openapi.json` 404 | All as expected | ✅ Pass | |
| M3a | `GET /tenant` | 200; T_LIVE_TEST_001 active; no cross-tenant | 200; name: Live Test Tenant; no cross-tenant | ✅ Pass | |
| M3b | `GET /setup/status` | 200; readiness understood; no secrets | 200; score 90; status ready; google_mail+monday connected; fortnox/visma not configured; missing: Support email | ✅ Pass | |
| M3c | `GET /pilot/readiness` | 200; status understood | 200; `almost_ready`; 7 pass, 4 warn, 0 fail | ✅ Pass | Warnings expected: onboarding 4/8, no routing hints, integration warnings. |
| M3d | `GET /integrations/health` | 200; integration states visible; no secrets | 200; `overall: warning`; gmail: warning+configured; monday: warning+configured; fortnox: not_configured | ✅ Pass | Warnings expected for pre-dispatch state. |
| M4a | `GET /jobs` | Phase F+G synthetic jobs; no new; no cross-tenant | job_count=2; T_LIVE_TEST_001 only; no secrets | ✅ Pass | Evidence retained. |
| M4b | `GET /approvals/pending` | 0 pending | pending_count=0 | ✅ Pass | Queue clean. |
| M5a | `GET /audit-events` | No external writes; T_LIVE_TEST_001 only | No gmail_send/monday_write/fortnox/visma events; no secrets; scoped | ✅ Pass | |
| M5b | `GET /integration-events` | No external writes; T_LIVE_TEST_001 only | No write events; no cross-tenant; no secrets | ✅ Pass | |
| M6 | Backups/operational files | Pre-Phase-D backup; daily backups; .env; compose; Caddyfile | All present; 16 daily backups `2026-06-22` → `2026-07-07`; pre-Phase-D 677 KB; all operational files confirmed | ✅ Pass | |
| M7 | Cleanup list confirmed | 8 known items documented | All 8 confirmed recorded in docs | ✅ Pass | |
| M8 | Logs risk search (tail=1000) | No critical matches | No Traceback, 500, tokens, Gmail send, Monday write, Fortnox, Visma in tail-1000 | ✅ Pass | Phase K `invalid_grant` in earlier log window (not in tail-1000). |
| M-end | Phase M overall | PASSED / FAILED / BLOCKED | **PASSED** — 50 pass, 0 fail, 0 warn | ✅ PASSED | Pre-pilot system state confirmed clean and stable. |

**Blocker summary carried to Phase N:**
- Phase K: `GOOGLE_OAUTH_REFRESH_TOKEN` invalid/revoked — Gmail inbox sync blocked.
- Fix: regenerate Google OAuth tokens → update `.env.production` → restart app → rerun Phase K.
- **Phase O cannot be GO until Phase K passes.**

**Known cleanup items for Phase N:**
1. Gmail `invalid_grant` — Phase K blocker (blocking).
2. DB password in `docker-compose.prod.yml` — move to `.env.production` (important).
3. SQLAlchemy verbose SQL echo in production (non-blocking).
4. Support email not configured (non-blocking).
5. `MONDAY_WORKSPACE_ID` absent — not required for item creation (non-blocking).
6. `GOOGLE_CALENDAR_ACCESS_TOKEN` empty — calendar not in scope (non-blocking).

### Phase N — Production hardening cleanup (2026-07-07) — PASSED

| Check | Step | Expected | Actual | Status | Notes |
|-------|------|----------|--------|--------|-------|
| N1 | Hardening inventory | Commit; containers Up; env vars masked | Commit `87d9369`→`01f5763`; app/db/caddy Up; ENV=production; all key vars SET | ✅ Pass | |
| N2 | SQL echo source | Identify hardcoded vs env-controlled | `database.py` line 8: `echo=True` hardcoded; `session.py`: no echo | Identified | Required code fix. |
| N3 | SQL echo fix (code) | `DB_ECHO: bool = False` in settings; `echo=settings.DB_ECHO` in database.py | Fixed; 2746 tests pass; committed `01f5763` | ✅ Pass | `git push origin main` succeeded. |
| N3 | SQL echo fix (deploy) | Docker image rebuilt; SQL echo absent | Image rebuilt (pip layer cached); container recreated; `sql_echo_count_tail30=0` | ✅ Pass | Production SQL logging silenced. |
| N3 | Post-rebuild health | / 200; /health 200; /docs 404; tenant 200 | All as expected | ✅ Pass | |
| N4 | Support email | Value or absence documented | Empty `''`; set via `PUT /dashboard/control` (DB, not env); operator must confirm address | ⚠️ Partial | Not set — no confirmed email address. Suggested: `support@krowolf.se`. |
| N5 | DB password hardening | Plan documented; no unsafe rotation | `POSTGRES_PASSWORD` hardcoded in compose line 19; rotation plan written in docs | ⚠️ Partial | Not executed — requires maintenance window. |
| N6 | Gmail token blocker plan | Fix steps documented | Fix steps documented in docs | ✅ Pass | Not executed — Phase K rerun required. |
| N7 | Post-hardening health | All endpoints 200/404 | `/` 200; `/health` 200; `/docs` 404; `/openapi.json` 404; `/tenant` 200; `/approvals/pending` 200; `/integrations/health` 200 | ✅ Pass | |
| N8 | Logs risk search | No secrets, 500s, writes; SQL echo gone | No risky patterns; `sql_echo_count_tail30=0` | ✅ Pass | |
| N-end | Phase N overall | PASSED / PARTIAL / BLOCKED | **PASSED** (SQL echo fix fully deployed; support email + DB password rotation partial — require operator actions) | ✅ PASSED | |

**Hardening actions completed in Phase N:**
- `echo=True` → `echo=settings.DB_ECHO` (default `False`) — SQL echo eliminated in production.
- Live commit: `01f5763`. Docker image rebuilt and deployed.

**Remaining hardening items (operator action required):**
1. Set support email: `PUT /dashboard/control {"support_email": "<confirmed-email>"}` for T_LIVE_TEST_001.
2. DB password rotation: follow safe maintenance plan in `docs/01-current-truth.md`.
3. Gmail token refresh: required before Phase K rerun and Phase O.

### Phase G cleanup notes

- Phase F email_send approval (`eml_adeaf87ada864e66bbb6`, job_id `bea23f74-...`) remains pending — non-blocking; consider rejecting via dashboard before pilot.
- Synthetic Phase G job (`8b2d53d2-...`) and approval evidence retained as verification proof.
- All temporary scripts removed from server and local; all shell variables unset.
### Important cleanup after checkpoint

- Production `docker-compose` currently contains DB password directly. Rotate and move DB password to `.env.production` after live verification checkpoint.
- SQLAlchemy/DB query logging appears verbose in production logs. Review and disable/minimize production SQL echo if not needed.

---

### Phase O — Final go/no-go pilot checklist (2026-07-08) — CONDITIONAL GO

| Check | Step | Expected | Actual | Status | Notes |
|-------|------|----------|--------|--------|-------|
| O1 | Production health | / 200 prod; /health 200 prod; /docs 404; /openapi.json 404 | All as expected | ✅ Pass | |
| O2 | Tenant status/readiness | active; auto_actions=false; score≥80; no secrets | T_LIVE_TEST_001 active; auto_actions all false; score=90; pilot/readiness=almost_ready (7p 4w 0f); no secrets | ✅ Pass | Gmail+monday configured (warning expected); fortnox not_configured |
| O3 | Gmail jobs verification | total=10 (2 synthetic + 8 Gmail); ext_actions=0; T_LIVE_TEST_001 only; no secrets | 10 total; types: unknown×4, invoice×2, lead×2, customer_inquiry×1 + 1 synthetic evidence; all ext_actions=0; no cross-tenant; no secrets | ✅ Pass | All jobs in manual_review or completed; requires_human_review correctly set |
| O4 | Pending approvals | count known; no external approve executed | 1 pending: eml_5d69..., action_dispatch, state=pending, next_on_approve=email_send; not approved; no cross-tenant | ✅ Pass | Operator must review before approving — would trigger email send |
| O5 | Events | no external writes; no secrets | 50 audit events (step/workflow only); 0 integration events; no gmail_send/monday_create/fortnox | ✅ Pass | |
| O6 | Cross-tenant isolation | 401/403 or T_LIVE_TEST_001 scoped only | 200 scoped to T_LIVE_TEST_001; T_ELITGRUPPEN data not exposed; header ignored per design | ✅ Pass (design) | Correct behavior confirmed |
| O7 | Operator UI | 200; Operator Console visible; no secrets | app.krowolf.se/ui → 200; "Operator Console" in HTML; 460 KB; no secret values | ✅ Pass | |
| O8 | Logs risk search (tail=1200) | no risky patterns | No Traceback, 500 Internal, leaked tokens, write events | ✅ Pass | All HTTP 200/404/401 as expected |
| O9 | Cleanup review | documented | FIXED: SQL echo, Gmail token. PARTIAL: support email, DB password. NOTED: Monday write, Fortnox/Visma | ✅ Pass | |
| O-end | Phase O overall | GO / CONDITIONAL GO / NO-GO | **CONDITIONAL GO — 29 pass, 0 fail, 0 warn** | ✅ CONDITIONAL GO | All GO criteria met; 3 conditions before first pilot run |

**GO criteria check (all ✅):**
- ✅ Production health OK
- ✅ Gmail sync OK (8 real jobs, token refresh working)
- ✅ Tenant isolation OK
- ✅ No external writes
- ✅ Operator can review jobs (10 jobs visible, approvals functional)
- ✅ Pending approvals manageable (1 pending, email_send — not yet approved)
- ✅ No critical secrets/logging issue

**NO-GO criteria check (all ✅ absent):**
- ✅ invalid_grant resolved (no longer present)
- ✅ No cross-tenant data
- ✅ No unexpected external write
- ✅ Approvals functional (1 pending, controllable)
- ✅ No 500s/stack traces/secrets in logs
- ✅ Operator can inspect results

**CONDITIONAL GO conditions:**
1. ⬜ Set support email: `PUT /dashboard/control {"support_email": "support@krowolf.se"}` for T_LIVE_TEST_001
2. ⬜ Review pending approval `eml_5d69...` (action_dispatch, next_on_approve=email_send) — reject if not intentional before pilot
3. ⬜ DB password rotation (maintenance window, plan in `docs/01-current-truth.md`)
4. ⬜ Monday live item-creation test before enabling auto_actions.lead for any real tenant

**Remaining cleanup (non-blocking):**
- Monday write not live-tested (code verified; auto_actions=false; safe)
- Fortnox/Visma not configured (not required for pilot)
- pilot/readiness=almost_ready (expected warnings; not a blocker)
- GOOGLE_CALENDAR_ACCESS_TOKEN empty (calendar out of scope)

**Secrets handling:** Admin key and tenant key used in-memory only; cleared with `unset`; temp scripts removed from server and local.

---

## Final report template

Use this format when submitting the live verification result:

```text
Live verification run date: YYYY-MM-DD
Run by: <name/role>
Environment: api.krowolf.se

Completed:
- Phase A: Pre-flight local checks
- Phase B: Production health checks
- Phase C: Admin/auth checks
- Phase D: Tenant provisioning checks
- Phase E: Customer endpoint checks
- Phase F: Integration health checks
- Phase G: Gmail OAuth and inbox sync checks
- Phase H: Monday/Fortnox/Visma safe checks
- Phase I: Approval queue end-to-end checks
- Phase J: Customer UI/wow statistics checks
- Phase K: Smoke check
- Phase L: Go/no-go decision

Live checks run:
- <list each step run>

Passed:
- <list each passed step>

Failed:
- <list each failed step with actual response>

Blocked:
- <list any step that could not be run and why>

Secrets/config issues:
- <any env var missing or incorrect>

Integration status:
- Gmail: healthy / not_configured / error �?<details>
- Monday: healthy / not_configured / error �?<details>
- Fortnox: healthy / not_configured / error �?<details>
- Visma: healthy / not_configured / error �?<details>

First pilot readiness:
- Ready / Not ready
- Pilot readiness check result: <overall_status from GET /pilot/readiness>
- Failing checks (if any): <list>

Stop conditions hit:
- <none / or describe each>

Fixes required before pilot:
- <list any required fixes>

Next allowed work:
- <if ready: begin Fas 2 First Customer Pilot>
- <if not ready: fix <item> and re-run from Phase <X>>

Evidence log location:
- <link or path to filled evidence log>
```
