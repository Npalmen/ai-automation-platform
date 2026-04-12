# Current State

## Status summary
Projektet har passerat konceptstadiet och har en fungerande backend-kärna med riktig exekveringsförmåga.

## Confirmed implemented
- [x] FastAPI API
- [x] PostgreSQL persistence
- [x] SQLAlchemy repository layer
- [x] Multi-tenant with per-tenant API key auth (`X-API-Key`); `X-Tenant-ID` fallback in dev mode
- [x] Orchestrator-baserad workflow pipeline
- [x] AI-processorer med typed outputs
- [x] Approval flow med pause/resume
- [x] Action dispatch
- [x] Audit events
- [x] Approval persistence i DB
- [x] Action execution persistence i DB
- [x] Read-endpoints för approvals och actions
- [x] Live-testad Gmail / Google Mail integration för `send_email`

## Confirmed API surface
### Core
- [x] `GET /`
- [x] `GET /tenant`
- [x] `GET /jobs`
- [x] `GET /jobs/{job_id}`
- [x] `POST /jobs`

### Actions / approvals
- [x] `GET /jobs/{job_id}/actions`
- [x] `GET /jobs/{job_id}/approvals`
- [x] `GET /approvals/pending`
- [x] `POST /approvals/{approval_id}/approve`
- [x] `POST /approvals/{approval_id}/reject`

### Integrations
- [x] `GET /integrations`
- [x] `POST /integrations/{integration_type}/execute`

### Audit
- [x] `GET /audit-events`

## MVP flow verification (2026-04-09)
- [x] Official lead flow traced end-to-end: intake → classification → entity_extraction → lead → decisioning → policy → action_dispatch / human_handoff → approval pause/resume → Gmail action
- [x] Three critical bugs patched:
  - `asyncio.run()` removed from sync `run_pipeline` call in `main.py`
  - `action_executor.send_email` fixed to use `IntegrationType.GOOGLE_MAIL` (was referencing non-existent `EMAIL`)
  - `is_integration_configured` extended to recognise token-based integrations (Google Mail now activates when `access_token` + `api_url` are set)
- [x] Duplicate assertion block removed from `test_invoice_duplicate_detection`
- [x] `tests/test_mvp_flow.py` added: 23 new tests covering policy, human_handoff, approval helpers, orchestrator skip-step logic, integration config, and action executor email routing
- [x] All 36 tests pass

## Read endpoint hardening (2026-04-09)
- [x] Root cause identified: `main.py` called `list_jobs`, `count_jobs`, `list_events`, `count_events` — names that did not exist on any repository
- [x] Six missing alias methods added across three repositories:
  - `JobRepository.list_jobs` / `count_jobs` (aliases for `list_jobs_for_tenant` / `count_jobs_for_tenant`)
  - `AuditRepository.list_events` / `count_events` (aliases for `list_events_for_tenant` / `count_events_for_tenant`)
  - `IntegrationRepository.list_events` / `count_events` (static wrappers over instance methods)
- [x] `tests/test_repository_aliases.py` added: 10 tests for all new aliases + `_to_domain` regression
- [x] All 46 tests pass

## Schema and table bootstrap hardening (2026-04-09)
- [x] `JobListResponse` schema fixed: was `{tenant_id, limit, offset, jobs}`, now `{items, total}` matching all other list endpoints and what `main.py` actually returns
- [x] `main.py` startup `Base` import fixed: was importing from `app.repositories.postgres.base` (empty declarative base), now imports from `app.repositories.postgres.database` (the base all models inherit from) — all four tables (`jobs`, `approval_requests`, `audit_events`, `action_executions`) are now created on startup via `create_all`
- [x] Verified: `Base.metadata.tables` now contains all four expected tables after startup import
- [x] All 46 tests still pass

## Action error handling hardening (2026-04-09)
- [x] `action_dispatch_processor`: result `status` is now `"failed"` (not `"completed"`) when any action fails
- [x] `action_dispatch_processor`: audit event `action_dispatch_failed` emitted on failure (with failed action types and error strings)
- [x] `orchestrator._finalize_success`: detects `failed_count > 0` in action_dispatch payload → routes to `_finalize_failure` → job status `FAILED` (not `MANUAL_REVIEW`)
- [x] `get_db` dependency: added `except: db.rollback(); raise` to prevent dirty sessions after partial commits
- [x] `tests/test_action_failure.py` added: 11 tests covering failure shape, audit event, orchestrator routing, and success/non-action-dispatch paths
- [x] All 68 tests pass

## Operator UI (2026-04-10)
- [x] `app/ui/index.html` — thin single-file operator UI served by FastAPI
- [x] `GET /ui` route added to `app/main.py` (reads HTML from disk, no static mount needed)
- [x] Jobs list with status badges, click to open job detail
- [x] Job detail: id, status, type, tenant, timestamps, result payload, per-job approvals, per-job actions
- [x] Pending approvals tab with Approve/Reject buttons
- [x] All fetches send `X-API-Key` from an editable key input (updated in UI auth slice)
- [x] Approve/Reject POSTs to existing endpoints; UI refreshes after decision
- [x] No React, no Vite, no separate frontend toolchain — pure HTML/CSS/JS inline
- [x] 74/74 tests at time of implementation

**UI limitations (by design — out of MVP scope):**
- No pagination controls — UI fetches first 100 jobs/approvals; backend supports pagination
- No filtering or search
- No audit log view in the UI (data exists in API at `GET /audit-events`)
- No job creation form
- No retries or advanced action controls
- No auto-refresh — operator triggers all loads manually

## UI auth alignment (2026-04-11)
- [x] `app/ui/index.html` — API key input added to header (replaces tenant ID input)
- [x] All fetch calls now send `X-API-Key` header instead of `X-Tenant-ID`
- [x] Key persisted to `localStorage` — survives page refresh
- [x] Warning banner shown when no key is entered
- [x] Auto-load on page open only fires when a saved key exists (avoids immediate 401)
- [x] Dev mode (auth disabled server-side) still works — key field can be left empty
- [x] 88/88 tests pass; no backend changes

## Auth / API key enforcement (2026-04-11)
- [x] `app/core/auth.py` — `get_verified_tenant` FastAPI dependency added
- [x] `app/core/settings.py` — `TENANT_API_KEYS` setting added (JSON string, loaded from env)
- [x] All protected endpoints updated to use `Depends(get_verified_tenant)` instead of `x_tenant_id: str = Header(...)`
- [x] Auth behaviour: when `TENANT_API_KEYS` is set, `X-API-Key` header required; tenant derived from key; `X-Tenant-ID` ignored
- [x] Auth disabled mode: when `TENANT_API_KEYS` is empty, `X-Tenant-ID` trusted directly (dev mode); warning logged
- [x] Missing key → `401`; invalid key → `403`; malformed config → `RuntimeError` at startup
- [x] `tests/test_auth.py` added: 14 tests covering all auth paths (disabled/enabled/missing/invalid/malformed)
- [x] `env.example` updated with `TENANT_API_KEYS` entry and documentation
- [x] README updated: Authentication section, smoke test curl commands use `X-API-Key`, UI limitation noted
- [x] 88/88 tests pass; no business logic changed

**UI auth:** operator UI sends `X-API-Key` on all requests. Key is entered in the header field and persisted to `localStorage`. A warning banner is shown when no key is set. Works in both authenticated mode and dev mode (auth disabled).

## Operability and docs hardening (2026-04-10)
- [x] `requirements.txt` created — all runtime and test dependencies pinned
- [x] `docker-compose.yml` written — starts Postgres 15 on port 5432 with correct DB name
- [x] `env.example` created — full environment variable template with inline docs
- [x] `scripts/create_tables.py` fixed — now imports all four model modules so standalone table creation works; must be run as `python -m scripts.create_tables` from repo root
- [x] README fully rewritten — concrete local setup, DB verification step, full golden-path smoke test with curl commands, Gmail notes, API reference table, known limitations
- [x] `force_approval_test` flag documented in README smoke test
- [x] 74/74 tests still pass; no code logic changed

## DB-driven tenant config (2026-04-12)
- [x] `tenant_configs` table created via `TenantConfigRecord` model; picked up by `create_all` on startup
- [x] `TenantConfigRepository` — `get` / `upsert` / `to_dict`
- [x] `get_tenant_config(tenant_id, db=None)` — reads from DB when `db` provided; falls back to `TENANT_CONFIGS` static dict when no row exists or DB is unavailable
- [x] `/tenant` endpoint now passes DB session — returns DB-stored config when present
- [x] All existing callers (`policies.py`, `integrations/policies.py`) unchanged — they call without `db`, get static fallback
- [x] 105/105 tests pass

## Integration event persistence (2026-04-12)
- [x] `IntegrationEvent` model fixed to use `database.Base` — `integration_events` table now created by `create_all`
- [x] `POST /integrations/{type}/execute` persists a real `IntegrationEvent` row; response built from the saved record
- [x] Payload shape: `{"action": ..., "request": ..., "result": ...}` — captures full round-trip
- [x] `GET /integration-events` lists persisted records (was already wired; now has real data)
- [x] 122/122 tests pass

## Gmail OAuth token refresh (2026-04-12)
- [x] `refresh_access_token()` in `mail_client.py` — calls `https://oauth2.googleapis.com/token` with `refresh_token`, `client_id`, `client_secret`; returns new access token or raises `RuntimeError`
- [x] `GoogleMailClient.send_message` — on 401, attempts refresh and retries once if credentials are present; 403 is not retried (permissions error, not expiry); falls back to raising if refresh is unavailable or retry fails
- [x] Credentials configured via `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` env vars; all default to empty (no breaking change)
- [x] 141/141 tests pass

## Setup UI slice (2026-04-12)
- [x] `GET /tenant` extended — now returns `enabled_job_types`, `auto_actions`, and normalises `allowed_integrations` to plain strings
- [x] `PUT /tenant/config` added — accepts `{enabled_job_types, allowed_integrations, auto_actions}`, calls `TenantConfigRepository.upsert`, returns `{status, tenant_id}`
- [x] `app/ui/index.html` — "Setup" tab added alongside existing "Operations" tab; loads current config from `GET /tenant`; renders checkbox lists for job types and integrations; renders auto-action toggles per enabled job type; single "Save Configuration" button POSTs to `PUT /tenant/config` and reloads
- [x] `tests/test_setup_ui_endpoints.py` — 15 new tests; 156/156 pass

## Setup Status / Readiness panel (2026-04-12)
- [x] `app/ui/index.html` — readiness summary panel added inside the Setup tab; rendered before config checkboxes
- [x] Four checks computed from already-loaded config: Tenant loaded, ≥1 job type enabled, ≥1 integration enabled, auto-actions configured (warn-only — does not block overall readiness)
- [x] Overall status: "Ready" (green) when tenant + job types + integrations all present; "Not Ready" (red) otherwise
- [x] Frontend-only change; no backend or test changes; 156/156 pass

## Tenant creation (2026-04-12)
- [x] `POST /tenant` added — accepts `{tenant_id, name}`; rejects duplicates with 400; creates DB row via `TenantConfigRepository.upsert` with empty job types, integrations, auto actions; no auth required (bootstrap endpoint)
- [x] `TenantCreateRequest` Pydantic schema added to `app/main.py`
- [x] `app/ui/index.html` — "Create Tenant" section added at top of Setup tab; two inputs (Tenant ID, Name) + "Create Tenant" button; POSTs to `POST /tenant`, shows inline success/error, reloads config on success
- [x] `tests/test_tenant_creation.py` — 10 tests: success shape, duplicate 400, upsert args, schema validation; 166/166 pass

## Verification / Test Run UI (2026-04-12)
- [x] `app/ui/index.html` — "Verification" section added at bottom of Setup tab; frontend-only, no backend changes
- [x] "Run Verification Test" button submits a minimal `customer_inquiry` job for the active tenant via `POST /jobs`
- [x] Result panel shows: job ID, status (colour-coded), job type, summary, and condensed payload JSON
- [x] Tenant ID captured from loaded config (`_verifyTenantId`); shows clear error if Setup not loaded first
- [x] Uses existing AI fallback path — completes without external credentials
- [x] 166/166 tests pass; no backend changes

## UI polish, Swedish localisation, and tenant switcher (2026-04-12)
- [x] `app/ui/index.html` fully rewritten with Swedish UI text throughout (headings, buttons, messages, empty states, labels)
- [x] Tenant switcher added to Inställningar tab — input + "Ladda tenant" button loads config for any tenant via `GET /tenant/config/{tenant_id}`; clears input and confirms success inline
- [x] Full CSS/layout polish: consistent card system (`.setup-card`, `.readiness-card`), form field helpers (`.form-field`, `.form-inline`), improved tab styling, better header layout, cleaner spacing throughout
- [x] `GET /tenant/config/{tenant_id}` added to `app/main.py` — unauthenticated, returns same shape as `GET /tenant` for any tenant ID; used by the tenant switcher in the UI
- [x] `tests/test_tenant_config_by_id.py` — 8 tests; 174/174 pass

## Tenant listing and dropdown switcher (2026-04-12)
- [x] `TenantConfigRepository.list_all(db)` added — queries `tenant_configs` table ordered by `tenant_id`; returns only real DB rows, no static fallback
- [x] `GET /tenants` added to `app/main.py` — unauthenticated; returns `{items: [{tenant_id, name}], total}`; no static/fallback tenants included
- [x] `app/ui/index.html` — tenant switcher upgraded from free-text input to `<select>` dropdown populated from `GET /tenants`; only existing DB tenants can be selected; error shown if no tenant selected
- [x] `loadTenants()` called on `loadSetup()` (tab open) and after `createTenant()` (new tenant pre-selected in dropdown immediately)
- [x] `tests/test_tenant_listing.py` — 14 tests: shape, field content, no-fallback guarantee, repository method; 188/188 pass

## All MVP slices complete
All items from the original backlog are implemented and tested.

## Known risks / filesystem issues
- `pyproject.toml` is a directory (not a file) in the local filesystem — not tracked in git; does not affect runtime but cannot be used as a package manifest
- `.env.example` is an empty directory in the local filesystem — workaround: use `env.example` (no dot prefix) as the template file
- `docker-compose.yml` was previously an empty tracked file — now contains a working Postgres definition
- `app/api/routes/jobs.py` is dead code (not mounted in `main.py`) — not a blocker, noted for future cleanup
- No DB migration tooling — tables are created via `create_all` on startup; schema changes require manual intervention
- Gmail access tokens expire (~1 hour); no OAuth refresh flow is built