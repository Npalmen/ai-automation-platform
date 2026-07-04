# Current Truth

> **This file contains verified repository truth. It must not contain vision or plans.**
> If something is unverified, it is marked `Unverified`.
> The governing source for product direction is `docs/00-master-plan.md`.

---

## Last verified date

2026-07-05 (Phase 2 prep — first tenant setup path audit, pilot readiness/integration health verification, flaky test fix. Tests run locally on Python 3.14.3. No live server/DB access.)

## Verification method

- `python -m pytest --tb=no -q` — run locally against in-memory/mock DB
- `python -m scripts.run_release_gate_r1` — R1 release gate script
- Static code inspection of `app/main.py`, integration modules, `app/core/config.py`, `app/ui/index.html`
- Glob/search of test files, scripts, and config

---

## Test status

| Claim | Status | Detail |
|-------|--------|--------|
| Test suite runs | `Verified` | 2499 passed, 0 failed, 4 warnings (after Phase 2 prep bug fix) |
| Test count: 2499 tests across 94 test files | `Verified` | Run 2026-07-05 after flaky test fix |
| All policy gate tests pass | `Verified` | Including `test_lead_disabled_for_finance_tenant` and unknown-tenant regression suite |
| R1 release gate (`python -m scripts.run_release_gate_r1`) | `Verified — PASS` | 487 regression + 152 E2E = 639, all passed |
| `httpx` added to `requirements.txt` | `Verified — FIXED` | AUDIT-BUG-01 resolved |
| Unknown tenant IDs fail-closed | `Verified — FIXED` | AUDIT-BUG-02 resolved |
| Customer API key cannot access admin endpoints | `Verified` | `test_tenant_isolation_http.py` — admin endpoints reject tenant keys |
| Admin key not usable as tenant key | `Verified` | `test_tenant_isolation_http.py` — admin key rejected on /jobs |
| Customer endpoints require API key | `Verified` | `/customer/*`, `/integration-events`, `/tenant/context`, `/tenant/memory` all return 401/403 without key |
| Audit events scoped to authenticated tenant | `Verified` | AuditRepository called with verified tenant_id; query param bypass not possible |
| Integration events scoped to authenticated tenant | `Verified` | IntegrationRepository called with verified tenant_id |
| Cross-tenant job isolation | `Verified` | Tenant A cannot read Tenant B's jobs — returns 404 |
| Cross-tenant approval isolation | `Verified` | Tenant A cannot approve Tenant B's approvals — returns 404 |
| Cross-tenant cases isolation | `Verified` | Cases list scoped to authenticated tenant |
| Forged X-Tenant-ID header rejected when auth enabled | `Verified` | Tenant ID resolved from key, not header |
| Inactive tenant key rejected | `Verified` | Returns 403 |
| Dormant unsafe routes not mounted | `Verified` | Legacy approval_routes.py and api/routes/jobs.py not in app routes |
| Customer activity hides internal fields | `Verified` | job_id and payload stripped from /customer/activity |
| Deprecation warnings: `on_event` and `datetime.utcnow()` | `Verified` | 4 warnings per run, non-fatal |
| SLA reminder flaky test fixed | `Verified — FIXED 2026-07-05` | `test_sla_pass_already_run_today_skips` used `date.today()` (local TZ) vs prod code's `datetime.now(UTC)` — fixed to use UTC date |

### Phase 2 prep — First tenant setup path (verified 2026-07-05)

| Item | Status | Notes |
|------|--------|-------|
| `POST /admin/tenants` provisions DB-backed tenant + API key | `Verified` | `test_admin_provisioning.py` — 61 unit tests cover create, duplicate, slug validation, key format |
| Tenant ID derived deterministically from slug | `Verified` | `T_` + `slug.upper().replace("-", "_")` e.g. `slug=intern-pilot` → `T_INTERN_PILOT` |
| API key format: `kw_` + 32 hex chars (35 chars total) | `Verified` | `TenantApiKeyRepository._generate_raw_key()` — tested in `test_admin_provisioning.py` |
| API key shown once in create response, never stored in plaintext | `Verified` | Key is SHA-256 hashed before DB storage |
| `POST /admin/tenants/{id}/rotate-key` revokes all old keys, issues new | `Verified` | Tested — old key fails, new key works |
| `PATCH /admin/tenants/{id}/status` activates/deactivates tenant | `Verified` | Inactive tenant key returns 403 |
| `GET /admin/tenants` lists all tenants, never returns API keys | `Verified` | Tested in provisioning suite |
| `GET /pilot/readiness` — 11 checks, all deterministic, no external calls | `Verified` | `test_production_readiness.py` — 169 unit tests. Without live tokens → `not_ready` or `almost_ready` (expected) |
| `GET /integrations/health` — returns `not_configured` without live tokens | `Verified` | `test_integration_health.py` — Gmail/Monday/Fortnox all return `not_configured` state without crashing |
| Integration health leaks no secrets | `Verified` | No token values in response — tested |
| Integration health is tenant-scoped | `Verified` | Wrong tenant data not returned |
| `GET /onboarding/status` — 8-step checklist, deterministic | `Verified` | `test_onboarding.py` — 119 unit tests |
| `POST /onboarding/test-lead` — creates synthetic lead job, no external calls | `Verified` | Uses deterministic pipeline, bypasses LLM/Gmail |
| `POST /verify/{tenant_id}` — admin-only deterministic pipeline verification | `Verified` | Bypasses LLM, no external calls, returns `completed` or `awaiting_approval` |
| `GET /customer/results` and `/customer/health` — load with empty state | `Verified` | `test_customer_saas_surfaces.py` — endpoints return 200 with empty/zero data |
| Setup wizard `POST /setup/verify` — checks config without external calls | `Verified` | `test_setup_wizard.py` — reports missing modules, warning vs ok |
| `docs/08-runbook.md` — local/pre-live setup section added | `Verified` | Steps 1–11 with concrete curl commands and expected responses |
| `docs/02-first-customer-plan.md` — local pre-live checklist added | `Verified` | 11-item checklist with commands for local verification |

---

## Test environment

| Item | Status | Notes |
|------|--------|-------|
| Python version | `Verified` | Python 3.14.3 |
| pytest config | `Verified` | `pytest.ini`: `testpaths = tests` |
| `httpx` dependency | `Verified — FIXED` | Added to `requirements.txt` (AUDIT-BUG-01) |
| DB in tests | `Verified` | In-memory SQLite (mock/fixture); no Postgres required for unit tests |
| Live Postgres | `Not tested` | Not available in this session |
| Live external APIs | `Not tested` | Gmail, Monday, Fortnox, Visma not called in unit tests |

---

## Production status

| Item | Status | Notes |
|------|--------|-------|
| Server deployment at `api.krowolf.se` | `Unverified` | Was live 2026-05-21; not checked in this audit |
| Local start via `uvicorn app.main:app --reload` | `Verified (code)` | Startup sequence present in `app/main.py` |
| Docker Compose (Postgres only) | `Verified (code)` | `docker-compose.yml` + `docker-compose.prod.yml` + `Dockerfile` all present |
| `ENV=production` disables public docs and dev fallback | `Verified (code)` | `_is_production_env()` and `_openapi_urls_for()` in `main.py` |
| `.env` file present | `Verified` | `.env` exists in repo root |

---

## Repo structure (verified)

| Path | Contents |
|------|----------|
| `app/` | Main application package |
| `app/main.py` | Single-file FastAPI app — all routes defined here (~6900 lines) |
| `app/ui/index.html` | Single-file frontend (~536 KB) |
| `app/core/` | Config, auth, settings, tenancy, audit, logging |
| `app/api/` | `dependencies.py`; `routes/jobs.py` (dead — not mounted) |
| `app/workflows/` | `processors/`, `dispatchers/`, `scanners/`, `validators/`, `pipeline_runner.py`, `policies.py`, `action_executor.py`, `approval_service.py` |
| `app/integrations/` | `google/`, `monday/`, `fortnox/`, `visma/`, `microsoft/`, `slack/`, `crm/`, `accounting/`, `support/` + `factory.py`, `registry.py`, `policies.py`, `enums.py` |
| `app/repositories/postgres/` | SQLAlchemy models and repos for jobs, approvals, audit, tenants, integrations, credentials |
| `app/domain/` | Schema/response models for workflows, integrations, tenants, documents, users |
| `app/admin/`, `app/alerts/`, `app/analytics/`, `app/automation/`, `app/finance/`, `app/health/`, `app/insights/`, `app/lead/`, `app/onboarding/`, `app/support/`, `app/agents/`, `app/ai/`, `app/llm/` | Functional sub-modules |
| `tests/` | 94 test files |
| `scripts/` | `run_release_gate_r1.py`, `smoke_check.py`, `create_tables.py`, `test_db_connection.py`, `dev_https_proxy.py` |
| `docs/` | Governing documentation (this file and peers) |
| `docker-compose.yml` | Postgres service for local dev |
| `docker-compose.prod.yml` | Production compose file |
| `Dockerfile` | App container definition |
| `.env` | Local environment config |

---

## Scripts

| Script | Purpose | Status |
|--------|---------|--------|
| `scripts/run_release_gate_r1.py` | R1 regression + E2E gate | `Verified — present and passes` |
| `scripts/smoke_check.py` | Live server smoke check | `Verified — present`; requires `--base-url`; not run (no live server in this session) |
| `scripts/create_tables.py` | One-time DB table creation | Present |
| `scripts/test_db_connection.py` | Check DB connectivity | Present |
| `scripts/dev_https_proxy.py` | Development HTTPS proxy | Present |

---

## Endpoints (verified — actual routes in `app/main.py`)

### Root and UI

| Endpoint | Method | Auth | Status |
|----------|--------|------|--------|
| `/` | GET | None | `Verified` — returns `{"status":"ok"}` or serves HTML for UI hosts |
| `/ui` | GET | None | `Verified` — returns `app/ui/index.html` |
| `/callback` | GET | None | `Verified` — Visma OAuth callback alias |

### Auth

| Endpoint | Method | Auth | First-customer relevance |
|----------|--------|------|--------------------------|
| `/auth/admin/login` | POST | None | Critical — admin login |
| `/auth/admin/logout` | POST | Session cookie | Critical |
| `/auth/admin/me` | GET | Session cookie | Critical |

### Tenant

| Endpoint | Method | Auth | First-customer relevance |
|----------|--------|------|--------------------------|
| `/tenant` | GET | `X-API-Key` | Critical |
| `/tenant/context` | GET | `X-API-Key` | Critical |
| `/tenant/config/{id}` | GET | `X-Admin-API-Key` | Critical |
| `/tenant/config` (PUT) | PUT | `X-API-Key` | Important |
| `/tenant/config/{id}` (PUT) | PUT | `X-Admin-API-Key` | Important |
| `/tenant` (POST) | POST | `X-Admin-API-Key` | Critical — provisioning |
| `/tenants` | GET | `X-Admin-API-Key` | Important |
| `/tenant/memory` | GET/PUT | `X-API-Key` | Important |
| `/tenant/routing-hint-drafts`, `/tenant/routing-preview/{type}`, `/tenant/routing-readiness` | GET | Various | Important |
| `/admin/tenant-context/{id}` | GET | `X-Admin-API-Key` | Important |

### Jobs

| Endpoint | Method | First-customer relevance |
|----------|--------|--------------------------|
| `/jobs` | GET, POST | Critical |
| `/jobs/{id}` | GET | Critical |
| `/jobs/{id}/actions` | GET | Important |
| `/jobs/{id}/approvals` | GET | Critical |
| `/jobs/{id}/dispatch-policy` | GET | Important |
| `/jobs/{id}/dispatch-preview` | POST | Important |
| `/jobs/{id}/dispatch` | POST | Important |
| `/jobs/{id}/auto-dispatch` | POST | Important |
| `/jobs/{id}/lead-status`, `/jobs/{id}/lead-regenerate` | PATCH/POST | Important |
| `/jobs/{id}/support-status`, `/jobs/{id}/support-regenerate` | PATCH/POST | Important |

### Approvals

| Endpoint | Method | First-customer relevance |
|----------|--------|--------------------------|
| `/approvals/pending` | GET | Critical |
| `/approvals/{id}/approve` | POST | Critical |
| `/approvals/{id}/reject` | POST | Critical |

### Integrations

| Endpoint | Method | First-customer relevance |
|----------|--------|--------------------------|
| `/integrations` | GET | Important |
| `/integrations/{type}/execute` | POST | Critical |
| `/integrations/health` | GET | Critical |
| `/integration-events` | GET | Important |
| `/integrations/fortnox/customers/lookup` | POST | Important |
| `/integrations/fortnox/customers/create` | POST | Important |
| `/integrations/fortnox/invoices/lookup` | POST | Important |

### Dashboard and Cases

| Endpoint group | Status |
|----------------|--------|
| `/dashboard/summary`, `/roi`, `/leads`, `/support`, `/activity`, `/kpis`, `/cockpit`, `/control`, `/sla-breaches`, `/operational-insights` | `Verified (code)` |
| `/cases`, `/cases/{id}`, `/cases/{id}/operations`, `/cases/{id}/followup`, `/cases/{id}/closeout`, `/cases/{id}/finance/export-status` | `Verified (code)` |
| `/cases/{id}/automation-wow` | `Verified (code)` |

### Admin

| Endpoint group | Status |
|----------------|--------|
| `/admin/tenants`, `/admin/tenants/overview`, `/admin/tenants/{id}/rotate-key`, `/admin/tenants/{id}/status` | `Verified (code)` |
| `/admin/tenants/{id}/demo/seed` | `Verified (code)` |
| `/admin/recovery/{id}/retry|replay-dispatch|reclassify|re-extract|resend-approval|reprocess-gmail` | `Verified (code)` |
| `/admin/support/{id}/state|pause-automation|resume-automation|force-inbox-sync|disable-scheduler|enable-scheduler|ack-needs-help|clear-acknowledged` | `Verified (code)` |
| `/admin/usage/analytics`, `/admin/audit-events`, `/admin/operations/needs-help` | `Verified (code)` |
| `/admin/alerts/run-all` | `Verified (code)` |

### Other functional endpoints

| Endpoint group | Status |
|----------------|--------|
| `/gmail/process-inbox` | `Verified (code)` |
| `/scheduler/run-once`, `/scheduler/status` | `Verified (code)` |
| `/alerts/config` (GET/PUT), `/alerts/run` | `Verified (code)` |
| `/setup/status`, `/setup/modules`, `/setup/verify` | `Verified (code)` |
| `/notifications/settings` (GET/PUT), `/notifications/daily-digest/send` | `Verified (code)` |
| `/onboarding/status`, `/onboarding/wizard-state`, `/onboarding/test-lead` | `Verified (code)` |
| `/pilot/readiness` | `Verified (code)` — 11 checks |
| `/verify/{tenant_id}` | `Verified (code)` — deterministic pipeline without LLM |
| `/audit-events` | `Verified (code)` |
| `/workflow-scan/gmail`, `/workflow-scan/{system}`, `/workflow-scan/status` | `Verified (code)` |
| `/dispatch/summary`, `/dispatch/report` | `Verified (code)` |
| `/finance/invoices/{id}/draft|preview|export` | `Verified (code)` |
| `/finance/projects/{id}/profitability` | `Verified (code)` |
| `/customer/account`, `/customer/activity`, `/customer/results`, `/customer/health` | `Verified (code)` |
| `/demo/seed` | `Verified (code)` |
| `/processors` | `Verified (code)` |

### Dead / dormant routes (not mounted in `main.py`)

| File | Status |
|------|--------|
| `app/api/routes/jobs.py` | Dead — not mounted; no runtime effect |
| `app/api/approval_routes.py` | Dormant — has SECURITY WARNING comment; must not be mounted |

---

## UI views (verified — actual `switchView()` calls in `app/ui/index.html`)

| View key | Label | Mode | Status |
|----------|-------|------|--------|
| `dash` | Dashboard / Operationscockpit | Admin + Customer | `Verified (code)` |
| `cases` | Ärenden / Cases | Admin + Customer | `Verified (code)` |
| `results` | Resultat / ROI | Customer only | `Verified (code)` |
| `activity` | Aktivitetslogg | Customer only | `Verified (code)` |
| `customerSettings` | Konto & inställningar | Customer only | `Verified (code)` |
| `account` | Konto & Team | Customer only | `Verified (code)` |
| `wizardflow` | Onboarding wizard | Customer only | `Verified (code)` |
| `ops` | Loggar / Ops (jobs + approvals) | Admin only | `Verified (code)` |
| `ctrl` | Kontrollpanel | Admin only | `Verified (code)` |
| `notif` | Notifieringar | Admin only | `Verified (code)` |
| `setup` | Inställningar / Setup | Admin only | `Verified (code)` |
| `onboarding` | Onboarding / Kunduppsättning | Admin only | `Verified (code)` |
| `memory` | Kundminne | Admin only | `Verified (code)` |
| `readiness` | Redo för drift | Admin only | `Verified (code)` |
| `support` | Supportkonsol | Admin only | `Verified (code)` |
| `admin` | Super Admin overview | Admin only | `Verified (code)` |
| Integration setup | Opens modal/setup (not a switchView) | Admin only | `Verified (code)` |

**UI file size:** 535,991 bytes (single-file architecture).
**Customer-safe:** `Unverified` — admin-only and customer-only views are separated by CSS classes (`admin-only`/`customer-only`) and JS-side role checks. Whether server-side data responses are equally gated has not been verified in this session.

---

## Integrations (verified by code inspection)

### Gmail (Google Mail)

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/google/mail_client.py`, `adapter.py` |
| OAuth exists | `Verified` | Token refresh via `refresh_access_token()` — requires all 4 env vars |
| Read support | `Verified` | `list_messages`, `get_message` |
| Write/dispatch support | `Verified` | `send_email` |
| Approval-gated | No — low-risk email dispatch handled at pipeline level | |
| Tested | `Verified` | `test_google_mail_list_messages.py`, `test_gmail_process_inbox.py`, `test_gmail_oauth_refresh.py`, `test_gmail_scanner.py`, `test_gmail_extraction.py`, and more |
| Token currently valid | `Unverified` | Must check before first customer |
| Production-ready | `Partially verified` | Code complete; live token status unverified |
| First-customer relevance | Critical | Primary intake channel |

### Monday

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/monday/client.py`, `adapter.py`, `mappers.py` |
| OAuth exists | No — API key auth via `MONDAY_BOARD_ID` env var | |
| Read support | `Verified` | Board/item scanning |
| Write/dispatch support | `Verified` | `create_item`, `create_monday_item` |
| Approval-gated | `Unverified` — depends on tenant policy/auto_actions config | |
| Tested | `Verified` | `test_monday_client.py`, `test_monday_scanner.py`, `test_action_executor_monday.py` |
| Current connection valid | `Unverified` | Must check before first customer |
| Production-ready | `Partially verified` | Code complete; live connection unverified |
| First-customer relevance | Important | CRM/operations flow |

### Fortnox

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/fortnox/client.py`, `adapter.py`, `mappers.py` |
| OAuth exists | `Unverified` — uses access token; OAuth flow not observed in this audit | |
| Read support | `Verified` | Customer lookup, article lookup, invoice lookup |
| Write/dispatch support | `Verified (code)` | Invoice export (`/finance/invoices/{id}/fortnox/export`) |
| Approval-gated | `Verified (code)` | `approval_required` flag triggers approval request before export |
| Tested | `Verified` | `test_fortnox_actions.py`, `test_fortnox_scanner.py`, `test_invoice_extraction.py`, `test_finance_micro.py` |
| Access token currently valid | `Unverified` | Must check before first customer |
| Production-ready | `Partially verified` | Code and approval gate present; live token unverified |
| First-customer relevance | Important | Invoice preview/export, approval-gated |

### Visma

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/visma/oauth_service.py`, `oauth_routes.py`, `client.py`, `adapter.py`, `mappers.py` |
| OAuth exists | `Verified (code)` | Full authorize → exchange → refresh flow in `oauth_service.py`; `/callback` route and `/integrations/visma/oauth/callback` mounted |
| Read support | `Unverified` | Client code exists but read actions not confirmed |
| Write/dispatch support | `Not present` | No write actions confirmed in adapter |
| Approval-gated | `Unverified` | |
| Tested | `Partially verified` | `test_visma_oauth.py` exists |
| Production-ready | No — OAuth flow implemented, no confirmed read/write actions | |
| First-customer relevance | Low — not required for first customer |

### Microsoft Mail (Outlook)

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/microsoft/mail_client.py`, `adapter.py` |
| OAuth exists | No — uses raw `access_token` from config; no OAuth flow | |
| Read support | `Unverified` | `get_me` exists; message listing not confirmed |
| Write/dispatch support | `Verified (code)` | `send_email` via Graph API |
| Approval-gated | `Unverified` | |
| Tested | `Unverified` | No dedicated Microsoft mail test file found |
| Production-ready | No — no OAuth flow; token management manual | |
| First-customer relevance | Low — not required for first customer |

### Google Calendar

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/google/calendar_client.py` |
| Integration registered | `Unverified` | Not confirmed in factory/registry for live use |
| Tested | `Unverified` | |
| Production-ready | `Unverified` | |
| First-customer relevance | Low — not required for first customer |

### Microsoft Calendar

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/microsoft/calendar_client.py`; referenced in `adapter.py` |
| Integration registered | `Unverified` | |
| Tested | `Unverified` | |
| Production-ready | `Unverified` | |
| First-customer relevance | Low — not required for first customer |

### Slack

| Check | Status | Notes |
|-------|--------|-------|
| Code exists | `Verified` | `app/integrations/slack/webhook_client.py`, `adapter.py` |
| OAuth exists | No — webhook URL only | |
| Read support | No | Notification only |
| Write/dispatch support | `Verified (code)` | `notify_slack` via webhook |
| Approval-gated | No | |
| Tested | `Unverified` | No dedicated Slack test file found |
| Production-ready | `Partially verified` | Code works; webhook URL must be configured |
| First-customer relevance | Low — optional notification channel |

---

## Automation risk audit

| Area | Status | Notes |
|------|--------|-------|
| Admin endpoint gating (`require_admin_api_key`) | `Verified` | Used 45 times in `main.py` |
| Tenant API key gating (`get_verified_tenant`) | `Verified` | Used on all tenant endpoints |
| Approval queue | `Verified (code)` | `/approvals/pending`, approve/reject endpoints implemented |
| Fortnox export approval gate | `Verified (code)` | `approval_required` flag triggers pre-write approval request |
| Auto-actions per job type per tenant | `Verified (code)` | `auto_actions` dict in tenant config controls what runs automatically |
| Policy gate: `is_job_type_enabled_for_tenant` | `Verified — FAIL-OPEN BUG` | Unknown tenant IDs fall back to TENANT_1001 (full permissions) |
| Audit events | `Verified (code)` | `create_audit_event()` called in flows; `/audit-events` endpoint present |
| Safeguard: email send | `Verified (code)` | No unconditional mass-send; send is dispatched as action via pipeline |
| Safeguard: Fortnox/Visma writes | `Verified (code)` | Invoice export has `approval_required` gate; Visma has no write actions confirmed |
| Safeguard: Monday writes | `Partially verified` | Depends on tenant `auto_actions` config; no hard approval gate in code confirmed |
| Risk boundaries in production | `Unverified` | Depends on correct env var configuration at runtime |

---

## Tenant and auth audit

| Item | Status | Notes |
|------|--------|-------|
| Tenant API keys (`TENANT_API_KEYS` / `X-API-Key`) | `Verified` | Configured via env; `get_verified_tenant()` enforces; tested in `test_auth.py` |
| Admin API key (`ADMIN_API_KEY` / `X-Admin-API-Key`) | `Verified` | Empty key → all admin endpoints return 401 (fail-closed); tested in `test_admin_auth.py` |
| Admin session cookie auth | `Verified (code)` | `ADMIN_USERNAME`/`ADMIN_PASSWORD` optional; fallback to API key mode |
| Multi-tenant isolation — jobs | `Verified` | Tenant A cannot read Tenant B's jobs; returns 404; `test_tenant_isolation_http.py` |
| Multi-tenant isolation — cases | `Verified` | Cases scoped to authenticated tenant; `test_tenant_isolation_http.py` |
| Multi-tenant isolation — approvals | `Verified` | Tenant A cannot approve Tenant B's approvals; `test_tenant_isolation_http.py` |
| Multi-tenant isolation — audit events | `Verified` | AuditRepository.list_events called with verified tenant_id; no query-param bypass |
| Multi-tenant isolation — integration events | `Verified` | IntegrationRepository.list_events called with verified tenant_id |
| Dev mode fallback (`X-Tenant-ID` header) | `Verified` | Ignored when `TENANT_API_KEYS` is configured; tested in `test_auth.py` |
| `ENV=production` enforces auth | `Verified (code)` | Fails closed if no credentials configured |
| Unknown tenant ID policy | `Verified — FIXED` | Returns `_UNKNOWN_TENANT_CONFIG` (empty permissions); AUDIT-BUG-02 |
| Admin key not accepted as tenant key | `Verified` | Admin key on `/jobs` returns 403; `test_tenant_isolation_http.py` |
| Tenant key not accepted on admin endpoints | `Verified` | Returns 401 on `/admin/*`; `test_tenant_isolation_http.py` |
| Customer endpoints require API key | `Verified` | `/customer/*`, `/integration-events`, `/tenant/context`, `/tenant/memory` return 401/403 without key |
| Customer activity hides internal fields | `Verified` | `job_id` and `payload` stripped; `test_customer_saas_surfaces.py` |
| Customer health hides secrets | `Verified (code)` | `get_integration_health` docstring: "No secret values appear in response" |
| Customer UI data isolation — server-side | `Verified` | All `/customer/*` endpoints use `get_verified_tenant()`; scoped at repository level |
| Admin-only data (cross-tenant audit, all tenants list) | `Verified` | `/admin/audit-events` and `/admin/tenants` require `require_admin_api_key` |

---

## Known API contract sharp edges (verified historically)

These have caused real failures and are preserved from the README:

| Area | Sharp edge |
|------|-----------|
| `POST /jobs` | Requires `X-API-Key` header AND `tenant_id` in body — missing either returns error |
| `POST /jobs` | `job_type` is a hint — AI classification may override it |
| `POST /approvals/{id}/approve` | Requires JSON body; minimal working body is `{}` — empty body causes parse error |
| `POST /integrations/{type}/execute` | Body field is `"payload"` not `"input"` — sending `"input"` silently produces empty payload |
| Monday `board_id` | Not a per-request field — fixed from `MONDAY_BOARD_ID` env var at connection time |
| Monday `column_values` | Pass plain dict; platform serializes to JSON string internally |
| Tenant config DB vs static | DB `tenant_configs` row overrides `app/core/config.py` when present |
| Gmail OAuth | All four env vars required for refresh: `GOOGLE_MAIL_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` |
| Auth — `X-Tenant-ID` | Ignored when `TENANT_API_KEYS` is configured; dev-only fallback |
| Production auth | `ENV=production` fails closed if no tenant credentials configured |
| Admin auth | `ADMIN_API_KEY` empty → all admin endpoints return 401 (fail-closed) |

---

## Known inconsistencies

| Item | Note |
|------|------|
| `app/api/routes/jobs.py` | Dead code — not mounted in `main.py`; does not affect runtime |
| `app/api/approval_routes.py` | Dormant — has SECURITY WARNING comment; must not be mounted |
| `create_internal_task` action | Stubbed — no persistence beyond job result payload |
| No DB migration tooling | Schema changes via `create_all` + `ensure_runtime_schema()` at startup |
| No pagination in operator UI jobs list | Backend supports limit/offset; UI does not expose it for all views |
| `on_event("startup")` deprecated | FastAPI deprecation warning; should migrate to lifespan handler; non-fatal |
| `datetime.utcnow()` in test code | Deprecated in Python 3.12+; used in `test_email_approval.py`; non-fatal |

### Fixed inconsistencies (AUDIT-BUG-01, AUDIT-BUG-02)

| Item | Fix | Date |
|------|-----|------|
| `httpx` missing from `requirements.txt` | Added to requirements.txt | 2026-07-04 |
| Unknown tenant IDs fallback to TENANT_1001 (fail-open) | `_UNKNOWN_TENANT_CONFIG` (fail-closed) in `app/core/config.py`; TENANT_3001 added to static config | 2026-07-04 |

---

## First-customer blockers

### Critical

- ~~**AUDIT-BUG-02: Policy gate fails open.**~~ **FIXED 2026-07-04.** Unknown tenant IDs now receive `_UNKNOWN_TENANT_CONFIG` (empty permissions). `TENANT_3001` added to static config as finance-only tenant. All 2481 tests pass.
- ~~**AUDIT-BUG-01: `httpx` missing from `requirements.txt`.**~~ **FIXED 2026-07-04.** `httpx` added to `requirements.txt`.
- **Gmail OAuth token validity unverified.** Must confirm tokens are valid and refresh works before first customer goes live. If token is expired, inbox processing fails silently.

### Important

- **No live server health check performed.** `api.krowolf.se` not verified in this audit. Before first customer, must verify `GET /` returns `{"status":"ok"}` and `GET /pilot/readiness` returns passing state.
- **Monday board connection unverified.** Live API key and board ID not checked. Must verify before enabling Monday dispatch for first customer.
- **Fortnox access token unverified.** Live read/write credentials not checked. Must verify before enabling Fortnox invoice flows for first customer.
- **Customer UI data isolation not server-verified.** Admin-only vs customer-only views separated by JS/CSS, but server-side response filtering not confirmed in this audit. Must verify that customer API key cannot retrieve admin-level data.
- **No DB migration tooling.** Schema is managed via `create_all` + `ensure_runtime_schema()` at startup. Any breaking schema change requires careful coordination. Risk is low for initial pilot but will grow.

### Non-blocking

- `on_event("startup")` deprecated — generates warnings but does not break functionality. Can be migrated later.
- `datetime.utcnow()` deprecated in test code — non-fatal deprecation warning in Python 3.12+.
- `app/api/routes/jobs.py` dead code — not mounted, no runtime risk.
- `app/api/approval_routes.py` dormant — already excluded from `main.py`; has SECURITY WARNING comment for reference.
- Smoke check script (`scripts/smoke_check.py`) not run — requires live server URL.
- Visma write support not confirmed — Visma not required for first customer.
- Microsoft Mail OAuth not implemented — Microsoft Mail not required for first customer.

---

## Unverified claims

- Whether `api.krowolf.se` is currently reachable and healthy.
- Whether Gmail OAuth tokens are currently valid for any connected tenant.
- Whether Monday board connection is current.
- Whether Fortnox access tokens are current.
- Whether Visma OAuth flow works end-to-end. *(deferred — live verification phase)*
- Whether `GET /pilot/readiness` returns a passing state for the pilot tenant. *(deferred)*
- Whether `GET /integrations/health` reflects real Gmail and Monday state. *(deferred)*
- Whether scheduler `run_mode` is set correctly for the pilot tenant. *(deferred)*

---

## Required checks before first customer

- [x] Run `python -m pytest` — **Done. 2499 passed, 0 failed.**
- [x] Run `python -m scripts.run_release_gate_r1` — **Done. PASSED.**
- [x] Fix policy gate fail-open bug. — **Done. AUDIT-BUG-02 fixed.**
- [x] Add `httpx` to `requirements.txt`. — **Done. AUDIT-BUG-01 fixed.**
- [x] Verify local tenant/auth/customer-data isolation. — **Done. All isolation tests pass.**
- [ ] Verify `GET /` returns `{"status":"ok"}` on target instance.
- [ ] Verify `GET /pilot/readiness` returns passing state for pilot tenant.
- [ ] Verify `GET /integrations/health` reflects real Gmail and Monday state.
- [ ] Verify Gmail OAuth token is valid (or document that refresh is needed).
- [ ] Verify `GET /admin/tenants/overview` returns with `X-Admin-API-Key`.
- [ ] Confirm scheduler `run_mode` is set correctly for pilot tenant.
- [ ] Verify customer API key cannot access admin-level data endpoints.
- [ ] Run smoke check: `python scripts/smoke_check.py --base-url <url> --expect-production`.
