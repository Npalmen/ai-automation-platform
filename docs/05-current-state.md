# Current State

## Real-world validation results

The following has been confirmed through real API calls against a running instance — not theoretical.

| What | Status | Notes |
|------|--------|-------|
| Gmail send_email | ✅ LIVE VERIFIED | `POST /integrations/google_mail/execute` → real Gmail delivery |
| Gmail list_messages | ✅ LIVE VERIFIED | returns real inbox messages with message_id, thread_id, from, subject, snippet, received_at, label_ids |
| Gmail get_message | ✅ LIVE VERIFIED | returns full message including body_text (text/plain extracted from MIME tree) |
| Gmail OAuth refresh | ✅ LIVE VERIFIED | token refresh on 401; invalid_grant → 503 |
| Monday create_item (direct) | ✅ LIVE VERIFIED | `POST /integrations/monday/execute` → item appears in real board |
| Monday create_monday_item (workflow) | ✅ LIVE VERIFIED | `/jobs` → action_dispatch → Monday adapter → real board item |
| Full pipeline | ✅ END-TO-END VERIFIED | intake → classification → extraction → decisioning → policy → action_dispatch → human_handoff |
| Multi-action dispatch | ✅ LIVE VERIFIED | multiple actions in `input_data.actions` execute in sequence; partial failure recorded |
| Approval pause/resume | ✅ LIVE VERIFIED | `POST /approvals/{id}/approve` with `{}` resumes job; action executes after |
| Action persistence | ✅ LIVE VERIFIED | `GET /jobs/{job_id}/actions` returns real executed records |
| Multi-tenant auth | ✅ LIVE VERIFIED | `X-API-Key` + body `tenant_id` both required |
| Gmail → lead → Monday flow | ✅ LIVE VERIFIED | list_messages → get_message → map to /jobs → Monday item created |
| Gmail inbox trigger | ✅ PRODUCTION-READY | `POST /gmail/process-inbox` — dedup, mark-as-read, tenant gate, enrichment, phone extraction, Slack notify, dry_run, query override |
| Deterministic classification fallback | ✅ IMPLEMENTED | LLM fallback classifies as `lead` or `customer_inquiry` (keyword-based); no more `"unknown"` |
| 545 tests passing | ✅ | `python -m pytest` |

---

## Known API Contract Gaps

These are sharp edges discovered during live testing. Each one has caused a real failure.

| Endpoint / Area | Sharp edge |
|-----------------|-----------|
| `POST /jobs` | Requires `X-API-Key` header **and** `tenant_id` in the request body. Missing either returns an error. |
| `POST /jobs` | `job_type` is a hint — AI classification may override it. The final job type is in the response. |
| `POST /approvals/{id}/approve` | Requires a JSON body. Minimal working body: `{}`. Empty body causes a parse error. |
| `POST /integrations/{type}/execute` | Body field is `"payload"`, not `"input"`. Sending `"input"` silently produces empty payload → `400`. |
| Monday — `board_id` | Not a per-request payload field. Fixed from `MONDAY_BOARD_ID` env var at connection time. |
| Monday — `column_values` | Pass a plain dict; the platform serializes it to a JSON string internally. monday's GraphQL API requires a JSON string — sending a dict directly caused `Invalid type, expected a JSON string`. |
| Tenant config — DB vs static | The DB `tenant_configs` row overrides `TENANT_CONFIGS` in `app/core/config.py` when a row exists. If an integration appears enabled in code but returns `403`, check the DB row. |
| Tenant config — enum vs string | `allowed_integrations` in static config previously stored `IntegrationType.MONDAY` (enum objects). DB stores `"monday"` (strings). Code normalizes both; the DB row is authoritative when present. |
| Google Mail | All four env vars required for refresh: `GOOGLE_MAIL_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`. Partial config → `invalid_grant` on first token expiry. |
| UTF-8 output | API response is correct UTF-8. Windows terminals (GBK/CP936) misrender Swedish chars as `?` in curl output. The data is correct. Run `chcp 65001` to fix terminal display. |

---

## What works (as of 2026-04-14)

### Core pipeline
- `/jobs` endpoint accepts jobs and runs the full pipeline synchronously
- Pipeline: intake → classification → entity extraction → type-specific processor → decisioning → policy → action_dispatch → human_handoff
- Supported job types with full pipelines: `lead`, `customer_inquiry`, `invoice`
- Classification and extraction use the LLM when `LLM_API_KEY` is set; fall back to deterministic defaults without it — pipeline always completes
- Policy decides: `auto_execute` → action_dispatch → `completed`; `send_for_approval` → paused `awaiting_approval`; `hold_for_review` → `manual_review`
- Failed action dispatch → job status `failed` with error persisted to audit and `action_executions`

### Input handling
- `input_data` is required inside the job request body
- Sender fields support two formats: flat (`sender_name`, `sender_email`, `sender_phone`) or nested (`sender.name`, `sender.email`, `sender.phone`) — both normalized by intake
- Entity extraction uses normalized intake `origin` as fallback for `customer_name`, `email`, `phone` when LLM leaves them null — prevents false `missing_identity` validation errors

### Multi-tenant
- Per-tenant API key auth via `X-API-Key` header; tenant derived from key
- Tenant config stored in `tenant_configs` DB table; static fallback in `TENANT_CONFIGS` when no DB row
- Enabled job types and integrations are per-tenant
- All protected endpoints derive tenant from the key — `X-Tenant-ID` ignored when auth enabled

### Operator UI
- Single-file HTML/CSS/JS at `/ui` — no build toolchain
- Inställningar (Setup) tab: create tenants, configure job types/integrations/automation levels, run verification
- Operationer tab: view jobs, approve/reject
- All reads/writes use explicit `{tenant_id}` endpoints — no silent reversion to API-key tenant

### Verification
- `POST /verify/{tenant_id}` — unauthenticated; runs a deterministic pipeline (no LLM, no external credentials)
- Picks first enabled supported type from tenant DB config (lead > customer_inquiry > invoice)
- Returns `completed` or `awaiting_approval` for valid configured tenants

### Approvals
- Policy can trigger approval pause; human decision via UI or API resumes the pipeline
- Approvals persisted in DB with actor/channel/timestamp

### Integrations

**Google Mail** — ✅ LIVE VERIFIED (read + write)
- `send_email` — delivers to real Gmail inbox; OAuth token refresh on 401; `invalid_grant` surfaces as 503
- `list_messages` — lists inbox messages; returns message_id, thread_id, from, subject, received_at, snippet, label_ids; supports `max_results` and `query` params
- `get_message` — fetches single message by `message_id`; returns all header fields plus `body_text` (text/plain extracted from MIME tree; empty string for HTML-only messages)
- All three actions share the same 401→refresh→retry path

**Monday** — ✅ LIVE VERIFIED
- `create_item` (direct via `/integrations/monday/execute`) — creates real item in the configured board
- `create_monday_item` (workflow via `input_data.actions`) — routes through action_dispatch → MondayAdapter → real board item
- `column_values` serialized to JSON string internally; `board_id` is env-only (`MONDAY_BOARD_ID`)

**All other integrations** (CRM, Slack, Fortnox, Visma, etc.) are stubbed or webhook-based and have not been live-tested.

### Deterministic execution path

`input_data.actions` is the primary control path for action dispatch. When actions are provided explicitly, the workflow engine executes them directly without requiring LLM output. The LLM is used for classification, extraction, and decisioning — but if those processors fall back (no `LLM_API_KEY`), the policy processor still routes to `auto_execute` for `lead` and `customer_inquiry` job types, and action_dispatch runs.

**The workflow does NOT auto-generate actions** — actions must be provided in `input_data.actions` or derived from a future decisioning rule. Without them, action_dispatch runs but executes nothing.

### Audit
- All pipeline steps emit audit events: `step_started`, `step_completed`, `step_failed`, `workflow_completed`, `workflow_failed`

## Verified end-to-end flows

### Flow 1: Gmail read → lead intake → Monday item
1. `POST /integrations/google_mail/execute` with `action: list_messages` → inbox message list
2. `POST /integrations/google_mail/execute` with `action: get_message, message_id: <id>` → full message with body_text
3. Map sender, subject, body_text into `POST /jobs` with `job_type: lead` and `input_data.actions: [{type: create_monday_item, ...}]`
4. Pipeline runs deterministically (no LLM required): intake → classification → extraction → decisioning → policy (auto_execute) → action_dispatch
5. Monday item created in real board; job status: `completed`

This is a complete manual-trigger ingestion → decision → action flow, confirmed live.

### Flow 2: Multi-action dispatch
- Both `create_monday_item` and `send_email` can be listed in `input_data.actions`
- Actions execute in sequence within a single action_dispatch step
- If one fails: job status is `failed`; the successful action's side effect is not rolled back
- Partial success is visible in `GET /jobs/{id}` → `pipeline_state.action_dispatch.actions_taken` vs `actions_failed`

### Flow 3: Approval pause → resume → action
- Include `force_approval_test: true` in `input_data` to force approval pause
- Job enters `awaiting_approval`; `POST /approvals/{id}/approve` with `{}` resumes it
- Post-approval path runs ACTION_DISPATCH only (no re-classification)

## What is limited

- No LLM in dev without `LLM_API_KEY` — processors fall back deterministically (classification → keyword-based lead/inquiry; others → safe defaults); pipeline always completes
- Action dispatch is real for Gmail and Monday only; `notify_slack` is non-fatal (silently no-ops when Slack not configured); other action types (notify_teams, create_internal_task) are stubbed
- Gmail `body_text` is empty for HTML-only emails — no HTML-to-text conversion
- Monday `board_id` is env-only — no per-request override
- No DB migration tooling — schema changes require manual intervention
- No pagination in the UI — API supports it via query params
- No auto-refresh in the UI — all loads are manual
- `app/api/routes/jobs.py` is dead code (not mounted)

---

## Status summary (historical)
The project has passed the concept stage and has a working backend core with real execution capability.

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
- [x] Live-testad Gmail / Google Mail integration: `send_email`, `list_messages`, `get_message`
- [x] Live-testad Monday integration: `create_item` (direct) + `create_monday_item` (workflow)
- [x] Multi-action dispatch verified (lead → Monday + Gmail in single job)

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

## Tenant state fix, label maps, automation levels, live readiness (2026-04-13)

**Root cause fixed:** `saveConfig()` previously called `PUT /tenant/config` (API-key-derived tenant) then `loadSetup()` → `GET /tenant` (also API-key tenant), silently reverting to `TENANT_1001`. Fix: added `PUT /tenant/config/{tenant_id}` (unauthenticated bootstrap endpoint); UI now reads/writes config exclusively via `GET /tenant/config/{id}` and `PUT /tenant/config/{id}` using a single `_activeTenantId` variable.

- [x] `PUT /tenant/config/{tenant_id}` added to `app/main.py` — unauthenticated, 404 if tenant not in DB, upserts to exact tenant; saves `dict[str, bool | str]` auto_actions (accepts both legacy bool and new string levels)
- [x] `TenantConfigUpdateRequest.auto_actions` widened to `dict[str, bool | str]` to support automation level strings
- [x] `app/ui/index.html`:
  - Single `_activeTenantId` state variable — set by `switchTenant()`, `createTenant()`, and initial `loadSetup()`; never overwritten by `saveConfig()` or `loadTenants()`
  - `saveConfig()` calls `PUT /tenant/config/{_activeTenantId}` then reloads from `GET /tenant/config/{_activeTenantId}` — tenant never reverts
  - `JOB_TYPE_LABELS` and `INTEGRATION_LABELS` maps — job types and integrations shown with Swedish customer-friendly labels
  - Auto actions replaced with 3-level radio selector per active job type: Manuellt godkännande / Semi-automatiskt / Fullt automatiskt
  - Readiness panel updated live on every checkbox/radio change via `refreshReadiness()` / `computeReadiness()`
  - Readiness now checks: tenant inläst, ≥1 arbetsflöde, ≥1 system, automationsnivå konfigurerad för alla aktiva jobbtyper
  - Final status text changed from "Redo" → "Redo att köra jobb"
- [x] `tests/test_tenant_config_save_by_id.py` — 14 tests: save endpoint shape, 404 path, upsert args, automation level schema; 202/202 pass

## Verification fix — tenant-aware routing (2026-04-13)

Two live testing failures in the verification flow fixed:

**Root causes:**
1. `POST /jobs` uses `get_verified_tenant` (API-key → `TENANT_1001`) but payload had `tenant_id: "TENANT_2002"` → HTTP 400 tenant mismatch.
2. Hard-coded `customer_inquiry` job type was not in the target tenant's `enabled_job_types` DB row → HTTP 403 job type not enabled.

**Fix:**
- [x] `POST /verify/{tenant_id}` added — unauthenticated; picks first enabled supported type; calls `run_pipeline` with tenant-specific payload
- [x] `app/ui/index.html` — `runVerification()` calls `POST /verify/{_activeTenantId}` with no body
- [x] `tests/test_verify_tenant.py` — 16 tests; 216/216 pass

## Verification fix — deterministic pipeline (2026-04-13)

**Root cause:** `run_pipeline` triggers the classification processor which calls the LLM (`LLM_API_KEY` not set in dev) → falls back to `detected_job_type: "unknown"` → orchestrator routes to `UNKNOWN` pipeline → policy appends `"unknown_job_type"` reason → `manual_review`. All three supported job types (lead, customer_inquiry, invoice) also have LLM-dependent processors that fall back to `low_confidence / manual_review` without credentials.

**Fix:** `_run_verification_pipeline(job, job_type_value, db)` — deterministic pipeline helper that bypasses all LLM calls:
- [x] Runs `intake_processor` (deterministic)
- [x] Injects synthetic `processor_history` entries for all AI steps: `classification_processor` (confidence=0.95, correct `detected_job_type`), `entity_extraction_processor`, type-specific processor (`lead_processor` / `customer_inquiry_processor` / `invoice_processor`), and `decisioning_processor` (for lead/inquiry: `auto_execute`)
- [x] Runs `policy_processor` (deterministic — reads from injected history; routes correctly for lead/inquiry/invoice without LLM)
- [x] Runs `human_handoff_processor` (deterministic — reads from policy)
- [x] Finalises `JobStatus` (`COMPLETED`, `AWAITING_APPROVAL`, or `MANUAL_REVIEW`)
- [x] Supported types: `lead`, `customer_inquiry`, `invoice` — each has a realistic Swedish input payload in `_VERIFICATION_PAYLOADS`
- [x] If no supported type is enabled: 400 with clear message listing supported types
- [x] Response includes `verification_type` field indicating which type was exercised
- [x] `tests/test_verify_tenant.py` — 16 tests: 404, 400 (no types, unsupported-only), success shape, tenant match, supported-type preference; updated for new interface
- [x] `tests/test_verification_pipeline.py` — 19 new tests: end-to-end pipeline for all three types (no mocking), verifies status not failed, no `unknown_job_type` reason, correct `detected_job_type` in history; payload config sanity checks
- [x] 237/237 pass

## MVP stabilization (2026-04-14)

See handoff doc for the full list. Key items:
- Intake normalization supports flat `sender_*` fields
- Entity extraction uses normalized origin as identity fallback
- `/jobs` input contract clarified: `input_data` is required; flat sender keys work
- Verification redesigned: deterministic pipeline, no LLM dependency
- Auth header bug fixed: `X-API-Key` always preserved in `apiFetch`
- 263/263 tests pass

## Live testing and regression hardening (2026-04-14)

Performed real API testing of the full platform. Findings and fixes:

- ✅ Gmail integration confirmed working end-to-end (live send + OAuth refresh)
- ✅ Full approval flow confirmed: `POST /jobs` → `awaiting_approval` → `POST /approvals/{id}/approve` → `completed` → action persisted
- Identified and documented API contract gaps (see "Known API Contract Gaps" section above)
- `POST /integrations/{type}/execute` — `RuntimeError` from Gmail now maps to `503` (not `500`); `ValueError` maps to `400`
- `_mask()` helper and `_log_config_diagnostics()` added to `GoogleMailAdapter` — logs masked OAuth credential presence on every `execute_action` call
- `tests/test_google_mail_runtime_errors.py` — 15 tests covering `_mask`, diagnostics logging, and route error mapping
- `tests/test_integration_execute_contract.py` — 10 tests covering schema field name (`payload` not `input`), valid execute, and all `400` paths
- `tests/test_swedish_char_encoding.py` — 12 tests confirming UTF-8 is preserved through all layers (request schema, adapter call, event payload, response serialization, Starlette bytes)
- 300/300 tests pass

## Monday integration + tenant config normalization (2026-04-14)

Live testing of Monday.com integration and tenant config resolution:

- ✅ Monday `create_item` confirmed working end-to-end — item appears in real monday board
- **Bug fixed:** `allowed_integrations` in static `TENANT_CONFIGS` stored `IntegrationType.MONDAY` (enum objects); route check expected string `"monday"` → `403` even though integration was configured
- **Fix 1 (config.py):** all `IntegrationType.X` in `allowed_integrations` replaced with `IntegrationType.X.value` (plain strings) across all four static tenant configs
- **Fix 2 (policies.py):** defensive normalization added — `allowed = [i.value if hasattr(i, "value") else i for i in raw]` — handles strings, enums, and mixed lists; checks `integration_type.value in allowed`
- **Bug fixed:** `column_values` sent as a Python dict to monday's GraphQL API — monday requires a JSON string → `Invalid type, expected a JSON string` error
- **Fix (client.py):** `column_values` serialized via `json.dumps()` before assignment to variables; `None` maps to `"{}"`, strings pass through unchanged
- **Improvement:** monday API `errors` array now raises `RuntimeError("monday API error: <message>")` instead of `Exception(str(list))` — readable error, correct type for route's `except RuntimeError → 503` handler
- `tests/test_tenant_config.py` — 10 new normalization tests (string list, enum list, mixed, empty, monday in TENANT_1001 / TENANT_2001)
- `tests/test_monday_client.py` — 16 new tests (column_values serialization for all input types, board_id as string, group_id, error handling, adapter routing)
- 326/326 tests pass

## Gmail inbox trigger endpoint (2026-04-21)

- `POST /gmail/process-inbox` added to `app/main.py`
- Reads unread Gmail messages (`is:unread`, configurable `max_results`, default 5)
- For each message: calls `get_message`, maps to lead job payload with `create_monday_item` action, calls `run_pipeline`
- Per-message errors are silently skipped; only `list_messages` failure raises 503
- `_parse_from_header(from_header)` helper added: parses `"Name <email>"` or bare `"email"` into `(name, email)`
- Response: `{"processed": int, "created_jobs": [{"message_id": ..., "job_id": ..., "status": ...}]}`
- **Known limitations:** no deduplication, does not mark messages as read, `job_type` hardcoded as `lead`, `create_monday_item` hardcoded as the sole action
- `tests/test_gmail_process_inbox.py` — 14 new tests
- 371/371 tests pass

## Gmail inbox hardening (2026-04-22)

Seven production-readiness slices applied to `POST /gmail/process-inbox`:

### Deduplication
- `JobRepository.get_by_gmail_message_id(db, tenant_id, message_id)` — queries `jobs` table for existing records with matching Gmail message ID
- Already-processed messages skipped with `reason: "duplicate"` in `skipped_messages`; `skipped` counter incremented
- `tests/test_gmail_process_inbox_dedup.py` — 12 tests

### Mark-as-read after successful processing
- `GoogleMailClient.mark_as_read(message_id)` added — `POST /users/{uid}/messages/{id}/modify` with `{"removeLabelIds": ["UNREAD"]}`; uses same 401→refresh→retry path
- `GoogleMailAdapter` dispatches `mark_as_read` action
- Called (non-fatally) after successful pipeline run; `marked_handled` flag in response per message
- `tests/test_gmail_mark_handled.py` — 12 tests

### Tenant config lead gate
- `get_tenant_config(tenant_id, db)` called at inbox entry; job creation skipped if `"lead"` not in `enabled_job_types`
- Gated messages appear in `skipped_messages` with `reason: "lead_disabled"`
- `tests/test_gmail_tenant_config_gate.py` — 11 tests

### Improved Monday item naming and column_values
- `_make_monday_item_name(subject, sender_name)` — uses subject (truncated to 60 chars), falls back to sender name, then `"Ny förfrågan"`
- `_infer_priority(subject, body)` — deterministic priority (`"High"` on Swedish/English urgency keywords, `"Medium"` otherwise)
- `column_values` built from `sender_email`, `sender_phone`, `priority`, `body_text` (truncated) — mapped to monday column IDs
- `tests/test_gmail_lead_enrichment.py` — 37 tests

### Improved From-header and phone extraction
- `_parse_from_header` replaced by `email.utils.parseaddr` — correctly handles RFC 2822 `"Name <email>"` and bare addresses
- `_extract_phone(text)` — regex-based extraction of Swedish/international phone numbers from subject+body
- Extracted phone fed into `column_values` and `input_data.sender`
- `tests/test_gmail_extraction.py` — 26 tests

### Slack notification after lead creation
- `dispatch_action("notify_slack", ...)` called (non-fatally) after successful pipeline run
- Notification includes tenant ID, message ID, job ID, sender name, subject
- `notified` flag per message in response
- `tests/test_gmail_notification.py` — 20 tests

### Scheduler-safe mode (dry_run + query override)
- `GmailProcessInboxRequest` extended: `dry_run: bool = False`, `query: str | None = None`
- `dry_run=True` — reads messages but skips all writes (no job creation, no pipeline, no mark-as-read, no Slack notify); response entries have `status: "dry_run"`, `job_id: null`
- Default query `"is:unread"` used when `query` is absent; custom query forwarded to `list_messages`
- Response extended with: `dry_run`, `query_used`, `max_results`, `scanned`
- `tests/test_gmail_scheduler_mode.py` — 24 tests

**545/545 tests pass after all seven slices.**

## Deterministic classification fallback (2026-04-22)

DEL 1 — Slice 1: Classification fallback replaced `"unknown"` with keyword-based intent detection.

- `_LEAD_KEYWORDS` set added to `classification_processor.py`: Swedish (`offert`, `pris`, `köpa`, `intresserad`) + English (`quote`, `pricing`, `buy`, `purchase`, `interested`, `demo`, `trial`)
- `_classify_deterministic(subject, body) -> str` — case-insensitive substring match; returns `"lead"` on any keyword hit, `"customer_inquiry"` otherwise
- `process_classification_job` `fallback_payload_builder` now calls `_classify_deterministic` instead of returning `"unknown"`; fallback sets `confidence=0.5`, `reasons=["deterministic_fallback", "llm_unavailable"]`
- Classification fallback applies to **all job sources** (not just Gmail inbox) — `POST /jobs`, inbox trigger, and future sources all benefit
- `orchestrator` routing unchanged; `"customer_inquiry"` and `"lead"` already have defined post-classification pipelines
- `tests/test_classification_deterministic.py` — 33 tests covering all keyword variants, fallback path, and inbox routing
- `tests/test_ai_processors.py` updated: stale `"unknown"` / `0.0` / no-reasons assertions replaced
- 545/545 tests pass

## Monday workflow wiring (2026-04-20)

- `create_monday_item` added to `SUPPORTED_ACTIONS` in `app/workflows/action_executor.py`
- `_build_monday_item_result()` handler added — mirrors `_build_email_result` pattern; routes to `MondayAdapter`
- `is_integration_configured()` in `app/integrations/service.py` extended: `api_key + board_id` → configured (previously only checked token-based or webhook-based configs)
- `tests/test_action_executor_monday.py` — 9 new tests
- Monday is now fully wired into both the direct integration path and the workflow pipeline

## Gmail read actions (2026-04-20)

- `list_messages` action added to `GoogleMailClient` and `GoogleMailAdapter`
  - Fetches inbox stubs then enriches each with metadata headers in one pass
  - Returns: `message_id`, `thread_id`, `from`, `subject`, `received_at`, `snippet`, `label_ids`
  - Supports `max_results` (default 10) and `query` (Gmail search string)
  - 401→refresh→retry path shared with send
- `get_message` action added to `GoogleMailClient` and `GoogleMailAdapter`
  - Fetches single message with `format=full`
  - Extracts `body_text` by walking MIME part tree depth-first; returns first `text/plain` part, base64-decoded
  - Returns: `message_id`, `thread_id`, `from`, `to`, `subject`, `received_at`, `snippet`, `label_ids`, `body_text`
  - `body_text` is empty string for HTML-only messages
- `tests/test_google_mail_list_messages.py` — 11 new tests
- `tests/test_google_mail_get_message.py` — 11 new tests
- 371/371 tests pass

## All MVP slices complete
All items from the original backlog are implemented and tested.

## Known issues / filesystem
- `pyproject.toml` is a directory (not a file) in the local filesystem — not tracked in git; does not affect runtime
- `.env.example` is an empty directory in the local filesystem — use `env.example` (no dot prefix)
- `app/api/routes/jobs.py` is dead code (not mounted in `main.py`) — not a blocker
- No DB migration tooling — tables created via `create_all` on startup; schema changes require manual intervention