# Live Verification Plan

> **Status: Phase A-C partially run 2026-07-07; blocker fix completed locally before Phase D.**
> Phase A and Phase B were executed; Phase C negative auth checks were executed, but correct admin-key validation was blocked because `ADMIN_API_KEY` was not available in the session.
> `GET /health` has been added and tested locally; production must be redeployed and Phase B2 re-run before Phase D.
> Pre-live UI is now an Internal Operator Console; polished customer UI is deferred.
> No Phase D or later live verification steps have been executed.
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

- [ ] Latest code deployed to production server.
- [ ] Full local test suite passes: `python -m pytest --tb=no -q` — latest final pre-live UI simplification run: 2746 passed, 0 failed.
- [ ] R1 release gate passes: `python -m scripts.run_release_gate_r1`.
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
- The app/container is running the latest deployed code that includes `GET /health`.
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

### LLM (optional — falls back to deterministic without it)

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
- Admin API key (`ADMIN_API_KEY`) — must be kept secret.
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
8. Gmail OAuth fails with `invalid_client` (client ID/secret mismatch — requires Google Cloud Console fix before retry).
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

## Phase A — Pre-flight local checks

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

## Phase B — Production health checks

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

## Phase C — Admin/auth checks

```bash
export BASE=https://api.krowolf.se
export ADMIN_KEY=<your ADMIN_API_KEY value>

# C1: Admin endpoint without any key — must reject
curl -i $BASE/admin/tenants
# Expected: HTTP 401
# STOP if: 200 returned (auth fail-open)

# C2: Admin endpoint with wrong key — must reject
curl -i $BASE/admin/tenants -H "X-Admin-API-Key: wrong-key-value"
# Expected: HTTP 401
# STOP if: 200 returned

# C3: Admin endpoint with correct key — must succeed
curl -i $BASE/admin/tenants -H "X-Admin-API-Key: $ADMIN_KEY"
# Expected: HTTP 200, JSON list of tenants

# C4: Tenant endpoint without key — must reject
curl -i $BASE/jobs
# Expected: HTTP 401 or 403

# C5: Admin key on tenant endpoint — must reject (admin key is not a tenant key)
curl -i $BASE/jobs -H "X-API-Key: $ADMIN_KEY"
# Expected: HTTP 401 or 403 (admin key is not a valid tenant API key)

# C6: Admin session login check (browser admin UI)
# Navigate to: https://api.krowolf.se/admin/login (or /ui)
# Log in with ADMIN_USERNAME / password
# Expected: session cookie set, admin dashboard accessible
# Note: if ADMIN_PASSWORD_HASH is empty, session login is disabled — document as TODO
```

---

## Phase D — Tenant provisioning checks

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
# IMPORTANT: record tenant_id and api_key — api_key is shown ONCE and never again

# Record: TENANT_ID=T_INTERN_PILOT
# Record: TENANT_KEY=kw_<...>   ← save this securely NOW

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
# Expected: list of which checks pass/fail — document the actual state
# NOT a stop condition — not_ready is expected at this stage

# D6: Key rotation test (ONLY if this step is planned and safe)
# NOTE: rotating the key immediately requires using the new key for all subsequent steps
# Only rotate if this step is explicitly part of the plan for this session
# curl -s -X POST $BASE/admin/tenants/$TENANT_ID/rotate-key \
#   -H "X-Admin-API-Key: $ADMIN_KEY"
# Expected: {"tenant_id":"T_INTERN_PILOT","api_key":"kw_<new>"}
# Record new key if rotated
```

---

## Phase E — Customer endpoint checks

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
# Expected: HTTP 200, zero or empty stats for new tenant — no crash

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

## Phase F — Integration health checks

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

## Phase G — Gmail OAuth and inbox sync checks

> **Only proceed here once Phase D (tenant provisioning) is complete.**
> Use a safe internal test Google account — not a customer-facing inbox.
> Do not use a shared corporate mailbox that forwards to real customers.

```bash
export BASE=https://api.krowolf.se
export TENANT_ID=T_INTERN_PILOT
export TENANT_KEY=<tenant api key>

# G1: Start OAuth flow — get authorization URL
curl -s "$BASE/auth/gmail/start?tenant_id=$TENANT_ID"
# Expected: redirect URL to accounts.google.com
# Action: open the URL in a browser, log in with the pilot Google account
# Action: grant all requested scopes (read, send — as required by platform)
# Action: copy the `code` parameter from the callback URL after consent

# G2: Submit authorization code
curl -s -X POST $BASE/auth/gmail/callback \
  -H "Content-Type: application/json" \
  -d "{\"code\": \"<authorization_code>\", \"tenant_id\": \"$TENANT_ID\"}"
# Expected: HTTP 200, token stored
# STOP if: invalid_client error (client ID/secret mismatch — fix in Google Cloud Console)
# STOP if: consent loop — user already revoked, require re-consent

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
# Subject: "Test from live verification — [date]"
# Wait 1–2 minutes or trigger sync manually again (G5)

# G7: Verify case created
curl -s $BASE/jobs \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: at least one job_id visible
# Expected: job_type matches classification of the test email
# Expected: status != "error"

# G8: Verify no unintended outbound email was sent
# Action: check the test Google account's Sent folder — should be empty
# Check approval queue before any email send action

# G9: Verify outbound email requires approval
curl -s $BASE/approvals/pending \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: if email-send action triggered, it appears here as pending
# Expected: NOT auto-sent without approval (auto_actions: lead: false)
```

**Gmail stop conditions:**
- `invalid_grant` on G3 → refresh token revoked. Re-run OAuth flow from G1.
- `invalid_client` → check Google Cloud Console client ID/secret — STOP.
- `gmail.send` scope missing → check Google Cloud Console OAuth scopes — STOP.

---

## Phase H — Monday/Fortnox/Visma safe checks

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
# GET /monday/scan or similar — check main.py for actual route name
# Expected: returns board columns/groups — no write action

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
# Preview is approval-gated — only inspect, do not approve Fortnox export
# If Fortnox status endpoint exists: GET /integrations/fortnox/status
# TODO: verify exact endpoint — document as TODO if not found

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
# If Visma IS configured: "healthy" or "warning" — document actual state
# No write actions to Visma in this phase
```

---

## Phase I — Approval queue end-to-end checks

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

# I7: Reject path test (optional — confirm reject works)
# (Create another test job with force_approval_test, then reject)
# POST /jobs → get approval_id
# POST /approvals/<approval_id>/reject  -d '{}'
# Expected: status: "rejected" or job moves to needs-help

# I8: Cross-tenant isolation check (if a second test tenant exists)
# Attempt to approve T_INTERN_PILOT's approval using a different tenant's key
# Expected: HTTP 404 (approval not visible to other tenants)
```

---

## Phase J — Operator console and minimal customer-safe UI checks

```bash
export BASE=https://api.krowolf.se
export TENANT_KEY=<tenant api key>

# J1: Customer-safe status endpoint
curl -s $BASE/customer/results \
  -H "X-API-Key: $TENANT_KEY" | python -m json.tool
# Expected: HTTP 200
# Expected: returns minimal status/stats (possibly zero for new tenant — acceptable)
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

## Phase K — Smoke check

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
# TODO: verify exact script args before running — see scripts/smoke_check.py --help
```

**Stop if:** any critical step of smoke check fails.

---

## Phase L — Go/no-go decision

Before declaring Fas 2 pilot ready, verify all of the following are green:

| Gate | Check | Expected |
|------|-------|---------|
| L01 | Phase B: Production responds | `env: production`, HTTP 200 |
| L02 | Phase C: Admin auth works | Correct key → 200, wrong key → 401 |
| L03 | Phase D: Tenant provisioned | T_INTERN_PILOT exists, key works |
| L04 | Phase D: Pilot readiness | `not_error` (not_ready acceptable pre-Gmail) |
| L05 | Phase E: Customer endpoints require auth | All return 401/403 without key |
| L06 | Phase E: No secrets in customer responses | Manual inspection passes |
| L07 | Phase F: Integration health no secrets | No token values in response |
| L08 | Phase G: Gmail OAuth completed | `gmail.status: healthy` |
| L09 | Phase G: Inbox sync creates cases | Test email → job created |
| L10 | Phase G: Outbound email requires approval | No unintended sends |
| L11 | Phase H: Fortnox remains approval-gated | No write without approval |
| L12 | Phase I: Approval queue works | Create → pending → approve → completed |
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
# See: docs/08-runbook.md — Backup and restore
```

### If tenant was provisioned with wrong config

```bash
# Deactivate bad tenant
curl -s -X PATCH https://api.krowolf.se/admin/tenants/<TENANT_ID>/status \
  -H "X-Admin-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status": "inactive"}'

# Create a new tenant with correct config (new slug → new tenant_id)
```

### If Gmail OAuth token expired during pilot

See `docs/08-runbook.md` — How to check OAuth/token issues.

```bash
# Re-run OAuth flow
GET /auth/gmail/start?tenant_id=<TENANT_ID>
# Follow redirect, complete consent, submit code via /auth/gmail/callback
# Verify: GET /integrations/health → gmail.status: healthy
```

### If Monday API key is invalid

```bash
# Update MONDAY_API_KEY in production env, restart app
docker compose -f docker-compose.prod.yml restart
# Verify: GET /integrations/health → monday.status: healthy or not_configured
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

- System down or DB unreachable → platform team immediately.
- OAuth token revoked → platform team within 1h.
- Customer email sent incorrectly → platform team + pilot customer immediately.
- Misclassification → report via case detail, manual review during normal hours.

See `docs/08-runbook.md` — Escalation rules.

---

## Evidence log template

Use this table when executing the plan. Fill in the Actual and Status columns as you run each step.

```markdown
| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| B1   | GET /          | HTTP 200, env:production | | ☐ | |
| B2   | GET /health    | HTTP 200 | | ☐ | |
| B3   | GET /docs      | HTTP 404 | | ☐ | |
| C1   | GET /admin/tenants (no key) | 401 | | ☐ | |
| C2   | GET /admin/tenants (wrong key) | 401 | | ☐ | |
| C3   | GET /admin/tenants (correct key) | 200 | | ☐ | |
| C4   | GET /jobs (no key) | 401/403 | | ☐ | |
| C5   | GET /jobs (admin key as tenant key) | 401/403 | | ☐ | |
| D1   | POST /admin/tenants | 201, api_key in body | | ☐ | Record key |
| D2   | GET /admin/tenants | 200, T_INTERN_PILOT listed, no api_key | | ☐ | |
| D3   | GET /tenant (tenant key) | 200, current_tenant:T_INTERN_PILOT | | ☐ | |
| D4   | GET /admin/tenants (tenant key) | 401/403 | | ☐ | |
| D5   | GET /pilot/readiness | not_ready/almost_ready | | ☐ | Document checks |
| E1   | GET /customer/account | 200, no secrets | | ☐ | |
| E2   | GET /customer/activity | 200, no internal fields | | ☐ | |
| E3   | GET /customer/results | 200, empty ok | | ☐ | |
| E4   | GET /customer/health | 200 | | ☐ | |
| E5   | GET /tenant/context | 200 | | ☐ | |
| E6   | GET /tenant/memory | 200 | | ☐ | |
| E7   | GET /integration-events | 200, tenant-scoped | | ☐ | |
| E8   | GET /audit-events | 200, tenant-scoped | | ☐ | |
| E9   | GET /customer/account (no key) | 401/403 | | ☐ | |
| F1   | GET /integrations/health | not_configured/warning, no secrets | | ☐ | |
| G1   | GET /auth/gmail/start | OAuth URL returned | | ☐ | |
| G2   | POST /auth/gmail/callback | 200, token stored | | ☐ | |
| G3   | GET /integrations/health (after Gmail) | gmail:healthy | | ☐ | |
| G5   | POST /scheduler/run-once | 200 | | ☐ | |
| G7   | GET /jobs (after test email) | job created | | ☐ | |
| G9   | GET /approvals/pending | email approval pending if triggered | | ☐ | |
| H1   | Integration health (Monday) | healthy/not_configured | | ☐ | |
| H4   | Integration health (Fortnox) | healthy/not_configured | | ☐ | |
| H7   | Integration health (Visma) | not_configured | | ☐ | |
| I1   | POST /jobs (force_approval) | awaiting_approval | | ☐ | Record job_id |
| I2   | GET /approvals/pending | approval listed | | ☐ | Record approval_id |
| I3   | POST /approvals/<id>/approve | approved/completed | | ☐ | |
| I4   | GET /jobs/<id> | completed | | ☐ | |
| I5   | GET /jobs/<id>/actions | action recorded | | ☐ | |
| I6   | GET /audit-events | audit event present | | ☐ | |
| J1   | GET /customer/results | 200, no admin data | | ☐ | |
| J2   | GET /customer/activity | activity visible | | ☐ | |
| J5   | GET /pilot/readiness (after setup) | ready/almost_ready | | ☐ | |
| K1   | smoke_check.py --expect-production | all steps pass | | ☐ | |
| K2   | smoke_check.py --admin-api-key | pass | | ☐ | |
| K3   | smoke_check.py --tenant-api-key | pass | | ☐ | |
```

Status key: ☐ Not run | ✅ Pass | ❌ Fail | ⚠️ Warning | 🛑 Stop condition hit

## Evidence log — 2026-07-07 controlled Phase A-C run

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| A0 | `git status --short`; `git status --branch --short` | Clean working tree / latest code deployable | Modified `app/ui/index.html`; branch `main...origin/main`; latest commit `7cec357` | ❌ Fail | Local working tree is not clean, so latest local code is not fully committed/deployable. |
| A1 | `python -m pytest --tb=no -q` | Full suite passes | 2744 passed, 0 failed, 4 warnings | ✅ Pass | Python 3.14.3. |
| A2 | `python -m scripts.run_release_gate_r1` | R1 release gate passes | 505 regression + 152 E2E passed | ✅ Pass | 657 total gate tests passed. |
| A3 | Inspect `docs/01-current-truth.md` | Latest local status documented | Latest status updated with this controlled Phase A-C run | ✅ Pass | Live verification overall remains not completed. |
| A4 | Confirm `docs/10-live-verification-plan.md` exists | Plan exists | File exists and is being used for this run | ✅ Pass | This evidence log records only Phase A-C. |
| A5 | Inspect `docs/06-backlog.md` | No local blockers | Local blockers section says none; pre-live blockers require live environment | ✅ Pass | Dirty working tree found separately in A0. |
| A6 | Check live verification completion state | Not marked completed | Not marked completed; only Phase A-C partial run documented | ✅ Pass | Phase D+ remains not run. |
| A7 | Server/deploy env inspection | `ENV`, `ADMIN_API_KEY`, `DATABASE_URL`, image/code, Caddy confirmed | Requires operator confirmation | ⚠️ Warning | No SSH/server access available in this session. |
| B1 | `curl.exe -i --max-time 10 https://api.krowolf.se/` | HTTP 200, `env: production` | HTTP 200, `{"status":"ok","app_name":"Krowolf","env":"production"}` | ✅ Pass | No stack trace or secrets observed. |
| B2 | `curl.exe -i --max-time 10 https://api.krowolf.se/health` | HTTP 200 | HTTP 404, `{"detail":"Not Found"}` | ❌ Fail | Live verification plan expected `/health` to return HTTP 200. Code inspection showed no generic `/health` route. Response was controlled and did not leak internals. |
| B3 | `curl.exe -i --max-time 10 https://api.krowolf.se/docs` | HTTP 404 in production | HTTP 404, `{"detail":"Not Found"}` | ✅ Pass | Production docs are not exposed. |
| B4 | `curl.exe -i --max-time 10 https://api.krowolf.se/openapi.json` | HTTP 404 in production | HTTP 404, `{"detail":"Not Found"}` | ✅ Pass | OpenAPI schema is not exposed. |
| C1 | `curl.exe -i --max-time 10 https://api.krowolf.se/admin/tenants` | HTTP 401/403 | HTTP 401 | ✅ Pass | Admin endpoint rejects missing admin key. |
| C2 | `curl.exe -i --max-time 10 https://api.krowolf.se/admin/tenants -H "X-Admin-API-Key: wrong-key"` | HTTP 401/403 | HTTP 401 | ✅ Pass | Admin endpoint rejects wrong admin key. |
| C3 | `GET /admin/tenants` with correct `X-Admin-API-Key` | HTTP 200 | Blocked | ☐ Not run | `ADMIN_API_KEY` was not available in this session. |
| C4 | `GET /admin/tenants` with tenant key | HTTP 401/403 | Deferred | ☐ Not run | No tenant key exists yet; deferred to Phase D/E. |

## Blocker fix log — 2026-07-07 before Phase D

| Blocker | Fix/action | Local verification | Remaining before Phase D |
|---------|------------|--------------------|---------------------------|
| `/health` returned HTTP 404 in production | Added unauthenticated `GET /health` in `app/main.py`; returns only `status`, `app_name`, `env`. | `python -m pytest tests/test_root_routing.py tests/test_production_hardening.py -q` — 10 passed, 2 warnings. Full suite: 2746 passed, 4 warnings. R1 gate passed. | Deploy latest code, then re-run Phase B2: `curl -i https://api.krowolf.se/health`; expected HTTP 200 and `status: ok`. |
| Dirty `app/ui/index.html` | Resolved intentionally by replacing the previous fancy CSS/card-contrast dirty state with a minimal Internal Operator Console. Functional HTML/JS views and operator flows were preserved. | UI static structure check passed; `python -m pytest tests/test_root_routing.py -q` passed; full suite passed with 2746 tests; R1 gate passed. | Commit/deploy latest code, then re-run Phase A-C. |
| Correct admin-key success path not verified | Added explicit pending instruction: use real `ADMIN_API_KEY` only in secure environment against read-only `GET /admin/tenants`. | Not run; no key available. | Re-run Phase C3 after key is provided securely. Do not print the key in report. |
| Server/container deployment state unknown | Added required operator confirmation list. | Not locally verifiable without server access. | Operator confirms `ENV=production`, non-empty admin key, `DATABASE_URL`, latest code/container, Caddy/reverse proxy, and DB backup before Phase D. |

## Deploy / Phase A-C re-run attempt — 2026-07-07 20:19

| Step | Command/action | Expected | Actual | Status | Evidence/notes |
|------|----------------|----------|--------|--------|----------------|
| DPL-0 | Inspect deploy docs/tooling | Documented deploy path and available tooling | Only generic Docker Compose deploy commands exist; no server-specific SSH/deploy target found. `docker` and `gh` are unavailable in this session. | 🛑 Stop condition hit | Stopped before deploy as instructed when deploy procedure requires operator action. |
| DPL-1 | Check secret availability without printing values | `ADMIN_API_KEY` available for Phase C3 | No local `ADMIN_API_KEY` or `ADMIN_API_KEYS`; no local `DATABASE_URL`. | ☐ Not run | Correct admin-key success path remains blocked until key is provided/used securely. |
| DPL-2 | Deploy latest local code | Production app/container updated | Not run | ☐ Not run | Requires operator with Docker/server access or documented deploy automation. |
| DPL-3 | Re-run Phase A-C after deploy | Phase A-C pass/fail evidence | Not run | ☐ Not run | No live checks were run after blocked deploy attempt. |

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
- Gmail: healthy / not_configured / error — <details>
- Monday: healthy / not_configured / error — <details>
- Fortnox: healthy / not_configured / error — <details>
- Visma: healthy / not_configured / error — <details>

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
