# Current Truth

> **This file contains verified repository truth. It must not contain vision or plans.**
> If something is unverified, it is marked `Unverified`.
> The governing source for product direction is `docs/00-master-plan.md`.

---

## Last verified date

2026-07-07 (Post-push deploy/re-run attempt for live verification Phase A-C was blocked before deploy. Local `main` is clean and pushed: `HEAD`/`origin/main` = `8e19622`. Preconditions remain locally true: full suite latest 2746 passed, R1 gate passed, `GET /health` exists locally, `app/ui/index.html` is intentionally an Internal Operator Console, and Phase D has not been run. Deployment could not be performed from this session because `docker` is not available locally, GitHub CLI is not available, `.github/workflows/release-gate.yml` only tests/builds and does not deploy, no `ADMIN_API_KEY`/`ADMIN_API_KEYS` or `DATABASE_URL` is available in the local environment, and non-interactive SSH to `api.krowolf.se` as the default `niklas` user was denied. No production deploy, live `/health` re-test, admin-key success-path check, tenant provisioning, OAuth, inbox sync, integration checks, approval E2E, customer UI/wow stats, or full live smoke was run.)

## Verification method

- `python -m pytest --tb=no -q` — run locally against in-memory/mock DB
- `python -m scripts.run_release_gate_r1` — R1 release gate script
- Static code inspection of `app/main.py`, integration modules, `app/core/config.py`, `app/ui/index.html`
- Glob/search of test files, scripts, and config
- Static code inspection of core intelligence modules: classification, lead/support analyzers, invoice/policy/handoff/action dispatch, and customer reply drafting

---

## Test status

| Claim | Status | Detail |
|-------|--------|--------|
| Test suite runs | `Verified` | 2746 passed, 0 failed, 4 warnings (after `/health` blocker fix and pre-live operator console simplification) |
| Test count: 2746 tests across 101 test files | `Verified` | Run 2026-07-07 during final pre-live UI simplification before Phase A-C re-run |
| All policy gate tests pass | `Verified` | Including `test_lead_disabled_for_finance_tenant` and unknown-tenant regression suite |
| R1 release gate (`python -m scripts.run_release_gate_r1`) | `Verified — PASS` | 2026-07-07: 505 regression + 152 E2E = 657, all passed |
| Root/UI/health/docs targeted tests | `Verified — PASS` | 2026-07-07: `python -m pytest tests/test_root_routing.py -q` — 8 passed, 2 warnings; previous root/health/docs set passed before UI simplification |
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
| Core intelligence quality eval suite | `Verified — ADDED 2026-07-06` | `tests/test_core_intelligence_quality.py` covers Swedish installation-company classification, qualification, missing info, risk/do-not-touch, customer reply, approval/routing, low-risk routing and high-risk handoff |
| Swedish extraction & qualification eval suite | `Verified — ADDED 2026-07-06` | `tests/test_swedish_extraction_quality.py` — 61 tests covering address/location extraction, service type detection, phone/org-number parsing, customer type, lead qualification, support urgency/safety, invoice risk level, OCR extraction, missing fields, and routing hints |
| Swedish address extraction (`extract_swedish_location`) | `Verified — ADDED 2026-07-06` | Deterministic regex: street address, postal code, city, property type, property designation. No LLM required. |
| Swedish org number extraction (`extract_org_number`) | `Verified — ADDED 2026-07-06` | Matches format "NNNNNN-NNNN". |
| OCR/payment reference extraction (`extract_ocr_number`) | `Verified — ADDED 2026-07-06` | Handles "OCR-nummer:", "betalningsref (OCR):", and similar labels. |
| Invoice risk level detection (`detect_invoice_risk_level`) | `Verified — ADDED 2026-07-06` | Returns "high_risk" for inkasso/kronofogden/kravbrev, "medium_risk" for betalningspåminnelse, "normal" otherwise. |
| Lead missing-info address detection from text | `Verified — IMPROVED 2026-07-06` | `_field_present("address")` now runs `extract_swedish_location` over message text when entity dict lacks address/city. |
| Lead analyzer: felsökning, växelriktare, jordfelsbrytare keywords | `Verified — IMPROVED 2026-07-06` | `electrical_work` and `solar_installation` lead types now detect more Swedish fault/service terms. |
| Lead analyzer: lantbruk/gård customer type | `Verified — IMPROVED 2026-07-06` | "lantbruk", "gård", "jordbruk" map to `private` customer type (closest Literal match). |
| Support analyzer: "luktar bränt", "gnistor" → critical | `Verified — IMPROVED 2026-07-06` | Added to `_EMERGENCY_KEYWORDS` and `_URGENCY_KEYWORDS["critical"]`. |
| Support analyzer: electrical fault issue keywords | `Verified — IMPROVED 2026-07-06` | "jordfelsbrytaren löser", "säkringen löser", "växelriktaren", "inga solceller" added to `issue` ticket type. |
| Support analyzer: warranty from post-install failure | `Verified — IMPROVED 2026-07-06` | "ni installerade", "installerade hos oss" added to `warranty` ticket type keywords. |
| Support analyzer: frustrated customers escalated | `Verified — IMPROVED 2026-07-06` | `requires_human` now includes `frustrated` sentiment in addition to `angry`. |
| Service Profiles module (`app/service_profiles/`) | `Verified — ADDED 2026-07-06` | New package: `models.py` (ServiceProfile dataclass), `registry.py` (10 profiles), `qualification.py` (select, compute, build_message, tenant_seam), `__init__.py`. |
| Service profile registry: 10 profiles | `Verified — ADDED 2026-07-06` | Profiles: generic_lead, generic_support, ev_charger_installation, solar_installation, battery_storage, electrical_fault, inverter_support, electrical_panel, invoice_generic, debt_collection_risk. |
| Profile selection (`select_profile`) | `Verified — ADDED 2026-07-06` | Deterministic: invoice path (debt_collection_risk if inkasso/kronofogden), support path (electrical_fault/inverter_support/generic_support by keyword+category), lead path (by lead_type mapping), fallback generic_lead. |
| Profile missing-info computation (`compute_profile_missing_info`) | `Verified — ADDED 2026-07-06` | Returns required_fields, present_fields, missing_fields, completeness_score, schema_source per service type. Handles 20+ field types including new profile-specific fields (safety_risk, desired_location, production_status, etc.). Tenant schema override respected. |
| Profile question messages (`build_profile_question_message`) | `Verified — ADDED 2026-07-06` | Service-specific Swedish follow-up messages with profile-aware intro and field labels. |
| question_generator.py: service_profile parameter | `Verified — IMPROVED 2026-07-06` | `generate_question_message` now accepts optional `service_profile` param; profile intro + questions take priority over generic labels. Fully backward-compatible. |
| Tenant override seam (`apply_tenant_overrides`) | `Verified — ADDED 2026-07-06` | Thin seam: passes profile through unchanged when no tenant context; applies routing_hint overrides when present; documented as future onboarding connection point. |
| Debt collection risk profile always routes manual_review | `Verified` | `default_route`, `complete_action`, `missing_info_action` all = "manual_review". `resolve_action()` always returns "manual_review" for this profile. |
| Electrical fault profile is_high_risk for luktar bränt/gnistor | `Verified` | `is_high_risk()` returns True for any risk_flags keyword; `resolve_action()` returns high_risk_action regardless of completeness. |
| Service profiles eval suite | `Verified — ADDED 2026-07-06` | `tests/test_service_profiles_qualification.py` — 82 tests across 8 test classes. |
| Service profiles wired into lead pipeline | `Verified — WIRED 2026-07-06` | `lead_analyzer_processor.py` now calls `select_profile()` after `analyze_lead()`; passes `service_profile` to `generate_question_message()`; adds `service_profile_type` to payload. |
| Service profiles wired into support pipeline | `Verified — WIRED 2026-07-06` | `support_analyzer_processor.py` now calls `select_profile()` after `analyze_support()`; adds `service_profile_type` to payload. |
| Customer auto-reply uses service-profile questions | `Verified — IMPROVED 2026-07-06` | `action_dispatch_processor._build_lead_default_actions` reads `generated_question_message` from `lead_analyzer_processor`; uses it for the auto-reply body when available; generic fallback maintained. |
| Customer auto-reply (inquiry) uses service-profile questions | `Verified — IMPROVED 2026-07-06` | `action_dispatch_processor._build_inquiry_default_actions` reads `support_generated_question_message` from `support_analyzer_processor`; uses it for the auto-reply body when available. |
| Risk-aware customer replies | `Verified` | Sensitive/high-risk leads and inquiries get `_build_sensitive_customer_ack` with `_needs_approval=True`; no legal/financial commitment in reply body. |
| Tenant routing hints override service profile route | `Verified` | `apply_tenant_overrides()` replaces `default_route` from `tenant_ctx.routing_hints[service_type]`; all other fields preserved. |
| Tenant-specific required fields via schema seam | `Verified` | `compute_profile_missing_info()` checks `tenant_ctx.schema_for(service_type)`; returns `schema_source="tenant_override"` when override present. |
| Company name in follow-up questions | `Verified` | `build_profile_question_message()` personalises intro with company name; `generate_question_message()` passes company_name from `tenant_ctx.company_name`. |
| Debt collection risk: inkassokrav detected | `Verified — FIXED 2026-07-06` | Added "inkassokrav", "inkassobolag", "betalningsanmärkning" to `intelligence_safety._RISK_KEYWORDS["debt_collection"]`. |
| Solar lead detection: plural forms | `Verified — FIXED 2026-07-06` | Added "solceller", "solpaneler" to `lead/analyzer.py` solar_installation keywords. |
| Service profile field presence: phone/email/entity fallback | `Verified — FIXED 2026-07-06` | `_profile_field_present` now handles `phone` and `email` via text regex + entity dict; generic entity fallback added. |
| Pipeline + reply + routing + golden path eval suites | `Verified — ADDED 2026-07-06` | `tests/test_service_profile_pipeline.py` (34 tests after cleanup additions), `tests/test_customer_reply_quality.py` (22 tests), `tests/test_tenant_routing_hints.py` (15 tests), `tests/test_local_golden_path.py` (20 tests). |
| `profile_missing_fields` in lead pipeline payload | `Verified — WIRED 2026-07-06` | `lead_analyzer_processor` calls `compute_profile_missing_info(service_profile, ...)` and exposes `profile_missing_fields` + `profile_completeness_score` in payload; `generate_question_message` uses profile-specific missing fields for question content. |
| Support question generator: service_profile parameter | `Verified — IMPROVED 2026-07-06` | `generate_support_question_message` now accepts optional `service_profile`; uses `build_profile_question_message` for non-emergency/non-safety tickets; emergency and safety ticket types bypass profile and keep AKUT/disclaimer logic. |
| `_has_safety_risk` handles ticket_type=="safety" | `Verified — FIXED 2026-07-06` | `_has_safety_risk` now returns True for ticket_type in ("emergency", "safety"), ensuring safety tickets always get safety disclaimer and bypass profile question generation. |
| Duplicate `_resolve_customer_reply_target` call removed | `Verified — FIXED 2026-07-06` | Redundant second call in `action_dispatch_processor._build_lead_default_actions` removed; behavior unchanged. |

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
| Server deployment at `api.krowolf.se` | `Partially verified` | 2026-07-07 controlled Phase B: root returned HTTP 200 with `env: production`; deeper deploy/image/env inspection requires operator confirmation. |
| Local start via `uvicorn app.main:app --reload` | `Verified (code)` | Startup sequence present in `app/main.py` |
| Docker Compose (Postgres only) | `Verified (code)` | `docker-compose.yml` + `docker-compose.prod.yml` + `Dockerfile` all present |
| `ENV=production` disables public docs and dev fallback | `Verified (code)` | `_is_production_env()` and `_openapi_urls_for()` in `main.py` |
| `.env` file present | `Verified` | `.env` exists in repo root |

### Controlled live verification Phase A-C (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| Local working tree clean / latest code committed | `Failed` | `git status --short` showed modified `app/ui/index.html`; branch `main` tracks `origin/main` with latest commit `7cec357`. |
| Full local test suite | `Verified — PASS` | `python -m pytest --tb=no -q` — 2744 passed, 0 failed, 4 warnings. |
| R1 release gate | `Verified — PASS` | `python -m scripts.run_release_gate_r1` — 505 regression + 152 E2E passed. |
| Live root health | `Verified — PASS` | `GET https://api.krowolf.se/` returned HTTP 200 and `{"status":"ok","app_name":"Krowolf","env":"production"}`. |
| Live `/health` route | `Fixed locally — pending deploy/retest` | Initial live check returned HTTP 404. `GET /health` was added locally on 2026-07-07 and verified by tests; production must be redeployed and B2 re-run before Phase D. |
| Production docs disabled | `Verified — PASS` | `GET /docs` and `GET /openapi.json` both returned HTTP 404. |
| Admin endpoint without key | `Verified — PASS` | `GET /admin/tenants` returned HTTP 401. |
| Admin endpoint with wrong key | `Verified — PASS` | `GET /admin/tenants` with `X-Admin-API-Key: wrong-key` returned HTTP 401. |
| Admin endpoint with correct key | `Blocked` | `ADMIN_API_KEY` was not available in this session. |
| Tenant key against admin endpoint | `Deferred` | No tenant key exists yet; deferred to Phase D/E. |
| Server/deploy env inspection | `Requires operator confirmation` | No SSH/server access in this session to verify production env vars, container image, DB URL, or Caddy process directly. |
| Live verification overall | `Not completed` | Only Phase A-C partial run was performed. Phase D and later were not run. |

### Deploy / Phase A-C re-run attempt (2026-07-07 20:19)

| Check | Status | Detail |
|-------|--------|--------|
| Local preconditions | `Verified` | Latest known full suite: 2746 passed; R1 gate passed; `/health` exists locally; `app/ui/index.html` is intentionally the Internal Operator Console; Phase D not run. |
| Documented deploy procedure | `Blocked` | Repo documents generic Docker Compose production commands only; no server-specific target, SSH host, or deploy script is present. |
| Local deploy tooling | `Blocked` | `docker` and `gh` are not installed in this session. SSH client exists, but no production SSH target/credentials are documented in repo. |
| Production secret availability | `Blocked` | No `ADMIN_API_KEY`, `ADMIN_API_KEYS`, or `DATABASE_URL` present in local environment. No secrets were printed or stored. |
| Production deploy | `Not run` | Stopped before deploy as required when deploy procedure/operator action is missing. |
| Phase A-C re-run | `Not run` | No live checks were run after the blocked deploy attempt. |

### Post-push deploy / Phase A-C re-run attempt (2026-07-07 20:24)

| Check | Status | Detail |
|-------|--------|--------|
| Latest code pushed | `Verified` | Local `main` is clean and synced with `origin/main`; `HEAD` = `8e19622`. |
| SSH access | `Blocked` | `ssh -o BatchMode=yes ... api.krowolf.se` resolved to the default `niklas` user but failed with permission denied. No interactive password prompt was attempted. |
| Local deploy tooling | `Blocked` | `docker` and `gh` remain unavailable in this session. |
| Production secret availability | `Blocked` | No local `ADMIN_API_KEY`, `ADMIN_API_KEYS`, or `DATABASE_URL`. No secrets were printed or stored. |
| Production deploy | `Not run` | Stopped before deploy because production SSH authentication is unavailable. |
| Phase A-C re-run | `Not run` | No live checks were run after the blocked deploy attempt. |

### Phase A-C blocker fix before Phase D (2026-07-07)

| Blocker | Status | Detail |
|---------|--------|--------|
| `/health` returned HTTP 404 on production | `Fixed locally — pending deploy/retest` | Added unauthenticated `GET /health` with public payload only: `status`, `app_name`, `env`. |
| `/health` tests | `Verified — PASS` | `tests/test_root_routing.py` now verifies HTTP 200, public fields, and no secret-like keys. |
| Production docs disablement regression | `Verified — PASS` | Existing docs disablement tests still pass. |
| Dirty `app/ui/index.html` | `Resolved intentionally — pending commit/deploy` | Previous fancy CSS/card-contrast dirty state was replaced with minimal Internal Operator Console styling. Existing functional HTML/JS operator flows were preserved; static structure check passed. |
| Correct admin-key success path | `Pending` | Requires real `ADMIN_API_KEY` provided securely; must be tested against read-only `/admin/tenants` without printing the key. |
| Operator confirmations | `Pending` | Must confirm `ENV=production`, non-empty `ADMIN_API_KEY`, `DATABASE_URL`, latest deployed code/container, Caddy/reverse proxy, and DB backup before Phase D. |

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
| `tests/` | 101 test files (see Test status table above for current count) |
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
| `/health` | GET | None | `Verified (local)` — added 2026-07-07; returns only `status`, `app_name`, `env`; no auth or secrets |
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

**UI file size:** 460,633 bytes after pre-live operator-console CSS simplification (single-file architecture).
**Pre-live UI decision:** `Verified/documented` — `docs/07-decisions.md` DEC-023 locks pre-live UI as an Internal Operator Console; polished customer UI is deferred.
**Customer-safe API responses:** `Verified locally` — server-side tenant/admin/customer isolation confirmed via `test_tenant_isolation_http.py` and `test_customer_saas_surfaces.py`: admin endpoints reject tenant keys, customer endpoints reject admin keys, cross-tenant data returns 404, `/customer/activity` strips internal fields.
**Operator/customer visual UI separation:** `Partially verified (code/static)` — admin-only and customer-only views are separated by CSS classes (`admin-only`/`customer-only`) and JS-side role checks; pre-live shell is intentionally optimized for operator use.
**Live browser/session validation:** `Deferred to live verification` — actual browser session rendering and visual role separation have not been validated against a live server in this session.

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

## Core intelligence quality (verified 2026-07-06, local only)

| Area | Status | Notes |
|------|--------|-------|
| Deterministic classification fallback | `Verified — IMPROVED` | Empty/unclear and wrong-recipient content now falls back to `unknown`; support/risk phrases are prioritized over broad lead keywords; Swedish spam/sales outreach is classified as `spam` |
| Lead qualification | `Verified — IMPROVED` | Local evals verify EV charger lead type, contact/address/property/main-fuse/timeline missing-info behavior, and no free dispatch when auto actions are disabled |
| Support qualification | `Verified — IMPROVED` | Local evals verify solar production outage as high-urgency support with human follow-up and approval-required task behavior |
| Invoice/economy handling | `Verified — IMPROVED` | Invoice-like items remain approval/manual-review gated; inkasso/betalningskrav now force manual review instead of approval-free automation |
| Do-not-touch risk logic | `Verified — ADDED` | Shared deterministic risk detector covers legal threats, reklamation, contract disputes, inkasso/betalningskrav, safety/work-environment risk, sensitive personal data, data deletion, financial changes, and mass-send intent |
| Policy routing | `Verified — IMPROVED` | Risk signals set `decision=hold_for_review`, `needs_human=true`, `approval_required=true`, `route_to=manual_review`, and `next_best_action=manual_review` |
| Customer reply drafts | `Verified — IMPROVED` | Sensitive lead/customer-inquiry auto replies are approval-gated, non-binding acknowledgements that hand off to a responsible human; low-risk inquiries still route to Monday/internal handoff |
| Live verification | `Partially run` | 2026-07-07 controlled Phase A-C only: local gates, production root/docs checks, and negative admin-auth checks. No production DB access, Gmail OAuth, Monday/Fortnox/Visma credentials, scheduler, tenant setup, approval E2E, or smoke check. |

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

- **Production `/health` must be re-tested after deploy.** `GET /` on `api.krowolf.se` returned HTTP 200 with `env: production` during Phase A-C, but `/health` returned HTTP 404 before the local blocker fix. `GET /health` now exists locally and must be deployed/re-tested before Phase D.
- **Monday board connection unverified.** Live API key and board ID not checked. Must verify before enabling Monday dispatch for first customer.
- **Fortnox access token unverified.** Live read/write credentials not checked. Must verify before enabling Fortnox invoice flows for first customer.
- **Customer UI data isolation: server-side verified locally, live browser deferred.** Server-side response isolation confirmed via HTTP isolation tests (tenant/admin/customer API key separation, cross-tenant 404). Visual browser/session rendering not validated against a live server — deferred to live verification.
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

- Whether deployed `api.krowolf.se/health` returns HTTP 200 after the local `/health` blocker fix is deployed.
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
- [x] Verify `GET /` returns `{"status":"ok"}` on target instance. — **Done 2026-07-07.** HTTP 200, `app_name: Krowolf`, `env: production`.
- [ ] Verify `GET /health` returns `{"status":"ok"}` on target instance after deploying the local blocker fix.
- [ ] Verify `GET /pilot/readiness` returns passing state for pilot tenant.
- [ ] Verify `GET /integrations/health` reflects real Gmail and Monday state.
- [ ] Verify Gmail OAuth token is valid (or document that refresh is needed).
- [ ] Verify `GET /admin/tenants/overview` returns with `X-Admin-API-Key`.
- [ ] Confirm scheduler `run_mode` is set correctly for pilot tenant.
- [ ] Verify customer API key cannot access admin-level data endpoints.
- [ ] Run smoke check: `python scripts/smoke_check.py --base-url <url> --expect-production`.
