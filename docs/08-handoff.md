# Handoff

## Project
AI Automation Platform — multi-tenant backend-first plattform för AI-driven workflow automation.

## Current objective
MVP is complete and stabilized. The platform is in a demonstrable state.
Pipeline runs end-to-end, verification is deterministic, intake normalization is correct, and docs reflect actual behavior.

## Read these first
1. docs/02-mvp-scope.md
2. docs/03-system-architecture.md
3. docs/05-current-state.md
4. docs/06-backlog.md
5. docs/07-decisions.md

## What is already true
- Backend foundation exists
- Multi-tenant with per-tenant API key auth (`X-API-Key`); `X-Tenant-ID` fallback in dev mode only
- Workflow/job model exists
- Approval persistence and action persistence exist
- Gmail integration has been live-tested
- Read-endpoints exist for jobs, approvals, actions and audit

## What must not happen
- Do not rewrite the architecture from scratch
- Do not expand scope beyond MVP
- Do not treat all architecture-level integrations as production-ready
- Do not build broad frontend before official backend MVP flow is verified
- Do not let chat history become the source of truth

## Completed slice (2026-04-09)
MVP flow verification and hardening. All tasks completed:
- Official lead flow traced and verified end-to-end
- Three critical bugs patched (asyncio.run on sync fn, EMAIL enum missing, is_integration_configured blind to token auth)
- 23 new tests in tests/test_mvp_flow.py; 36/36 pass
- Docs updated

## Completed slice (2026-04-09 — read endpoint hardening)
All MVP read endpoints were 500ing at runtime due to missing repository method names.
Six alias methods added; 10 new tests; 46/46 pass.

## Completed slice (2026-04-09 — schema and table bootstrap hardening)
Two more runtime blockers patched:
- JobListResponse schema aligned with main.py (items/total)
- main.py Base import fixed to database.Base so create_all creates all four tables
46/46 tests pass.

## Completed slice (2026-04-09 — action error handling hardening)
- action_dispatch_processor now sets status="failed" and emits audit event when actions fail
- orchestrator routes to FAILED (not MANUAL_REVIEW) on action dispatch failure
- get_db rolls back session on exception
- 11 new tests; 68/68 pass.

## Completed slice (2026-04-10 — thin operator/admin UI)
- `GET /ui` serves `app/ui/index.html` — single-file HTML/CSS/JS, no build toolchain
- Jobs list, job detail (approvals + actions), pending approvals tab, approve/reject
- 74/74 tests pass; no backend business logic changed

## How to use the operator UI

**Start the backend:**
```
uvicorn app.main:app --reload
```

**Open the UI:**
```
http://localhost:8000/ui
```

**API Key:**
Enter your API key in the header input field. The key is saved to `localStorage` and reloaded on next visit. Every API request sends this value as `X-API-Key`. If left empty, a warning banner is shown; the UI still functions against a server with auth disabled.

**View jobs:**
The Jobs tab loads automatically on page open. Click "Load Jobs" to refresh. Each row shows job ID, type, status, and timestamp.

**Open a job:**
Click any row in the jobs list. The right panel shows job detail: id, status, type, tenant, timestamps, result payload JSON, approvals for that job, and actions for that job.

**View pending approvals:**
Click the "Pending Approvals" tab. Press "Load Pending" to fetch all pending approvals across all jobs.

**Approve or reject:**
Pending approvals show Approve (green) and Reject (red) buttons. Clicking either POSTs to the existing API endpoint with `{"actor": "operator", "channel": "ui"}`. The UI refreshes the relevant view automatically after the decision.

**UI limitations:**
- No filtering or search — all jobs/approvals are returned in a flat list
- No pagination controls — UI fetches first 100 records; backend supports pagination via query params but the UI does not expose it
- No audit log view — audit data exists at `GET /audit-events` but is not surfaced in the UI
- No retries or re-run controls for failed jobs
- No auto-refresh — all data loads are triggered manually

## Completed slice (2026-04-10 — operability and docs hardening)
- `requirements.txt` created; `docker-compose.yml` filled in (Postgres 15); `env.example` written
- `scripts/create_tables.py` fixed to import all four model modules
- README fully rewritten with concrete setup, DB verification step, and curl smoke test
- `force_approval_test` flag documented as the official golden-path trigger
- 74/74 tests pass; no code logic changed

## Completed slice (2026-04-11 — auth / API key enforcement)
- `app/core/auth.py` created — `get_verified_tenant` FastAPI dependency
- `TENANT_API_KEYS` env var added to settings; all protected endpoints updated
- Auth disabled (empty key map) → dev mode with logged warning; no breaking change locally
- 14 new auth tests; 88/88 pass; no business logic changed

## Completed slice (2026-04-11 — UI auth alignment)
- `app/ui/index.html` updated: API key input replaces tenant ID input
- All fetch calls now send `X-API-Key`; key persisted in `localStorage`
- Warning banner shown when no key is set; auto-load deferred until key is present
- 88/88 tests pass; no backend changes

## Completed slice (2026-04-11 — UI rendering and approval visibility fixes)
- Layout height fixed: `body` uses `flex-direction:column; height:100vh`; `.layout` uses `flex:1; overflow:hidden` — auth banner no longer causes overflow
- HTML escaping added: `escapeHtml()` helper applied to `JSON.stringify` output in `<pre>` blocks — prevents DOM corruption from AI processor output containing `<`, `>`, `&`
- Approval visibility in job detail fixed: `loadJobDetail` now fetches from `GET /approvals/pending` and filters by `job_id`; fallback synthesises approval card from `job.result.payload.approval_request` when job is `awaiting_approval` and pending list returns no match
- 88/88 tests pass; no backend changes

## Completed slice (2026-04-12 — DB-driven tenant config)
- `tenant_configs` table added; `TenantConfigRecord` model + `TenantConfigRepository` created
- `get_tenant_config(tenant_id, db=None)` reads from DB first, falls back to static `TENANT_CONFIGS`
- `/tenant` endpoint passes DB session — live DB rows returned when present
- Workflow/integration policy callers unchanged (no `db` arg → static fallback, backward compatible)
- 17 new tests; 105/105 pass

## Completed slice (2026-04-25 — Control Panel)
- `settings` JSON column added to `TenantConfigRecord` (picked up by `create_all` on startup — no manual migration needed)
- `TenantConfigRepository.get_settings` / `update_settings` added
- `GET /dashboard/control` — returns tenant-scoped automation flags, support_email, scheduler.run_mode; defaults all-enabled/manual
- `PUT /dashboard/control` — validates run_mode (manual|scheduled|paused) and email format; persists to `settings` column
- `POST /dashboard/inbox-sync` — returns `not_available` (scheduler not wired yet); honest response, not a fake success
- `ControlPanelRequest` Pydantic model with nested `_Automation` and `_Scheduler`
- `app/ui/index.html` — "Kontrollpanel" tab added; toggles for all four automation flags; support email input; run_mode select; Save + Trigger sync buttons; Swedish labels
- `tests/test_control_panel.py` — 21 tests: shape, stored-settings, defaults, persist, validation, tenant isolation, inbox-sync
- 801/801 tests pass

## Completed slice (2026-04-25 — Customer Notifications / Daily Digest)
- Refactored: `_compute_summary(db, tenant_id)` and `_compute_roi(db, tenant_id)` extracted as module-level helpers; `dashboard_summary` and `dashboard_roi` endpoints now delegate to them; digest reuses the same functions
- `GET /notifications/settings` — returns `{enabled, recipient_email, frequency, send_hour}` from `settings.notifications`; defaults to `{enabled:false, frequency:"daily", send_hour:8}`
- `PUT /notifications/settings` — validates frequency (daily|weekly|off), send_hour (0–23), email required when enabled; persists to `settings.notifications` via `update_settings` (merges into full settings dict to avoid clobbering control panel keys)
- `POST /notifications/daily-digest/send` — 400 if no recipient; calls `_compute_summary` + `_compute_roi`; `_build_digest_body` formats Swedish plain-text report; dispatches via `dispatch_action(send_email)` which falls back to stub if Gmail not configured
- `NotificationSettingsRequest` Pydantic model
- `app/ui/index.html` — Notifieringar tab: enabled toggle, recipient email, frequency dropdown, send_hour input, Spara inställningar + Skicka testrapport nu buttons; result card shows status/recipient/subject
- `tests/test_notifications.py` — 36 tests: GET shape/defaults/stored, PUT persists/validates (frequency, send_hour bounds, email required, format), send success (dispatch called, correct recipient/type, body contains summary+ROI values, subject), missing recipient 400, dispatch failure 500, tenant isolation
- 942/942 tests pass

## Completed slice (2026-04-25 — Manual Inbox Sync Wiring)
- Extracted `_run_gmail_inbox_sync(tenant_id, db, max_results, query, dry_run)` from `gmail_process_inbox` — contains all processing logic (dedup, thread continuation, job creation, mark-as-read, Slack notify)
- `gmail_process_inbox` is now a thin wrapper calling `_run_gmail_inbox_sync`; its response shape is unchanged
- `trigger_inbox_sync` (POST /dashboard/inbox-sync) now calls `_run_gmail_inbox_sync` with `max_results=10, query=None, dry_run=False`; returns structured `{status, processed, created_jobs, continued_threads, deduped, errors, message}`; raises 503 with clean JSON if `GOOGLE_MAIL_ACCESS_TOKEN` is empty; passes through `HTTPException`; wraps unexpected exceptions as 500
- UI updated: `triggerInboxSync()` shows colour-coded result, counts (nya jobb / trådar / dubbletter / fel), then refreshes Dashboard and Cases if open
- `tests/test_inbox_sync.py` — 24 tests: missing credentials (6), response shape (5), success path (9), processor raises (3), tenant isolation (1)
- 3 outdated stub tests in `test_control_panel.py` replaced with 7 tests for the new behavior
- 906/906 tests pass

## Completed slice (2026-04-25 — Setup / Onboarding Wizard)
- `GET /setup/status` — tenant-scoped readiness overview: modules (sales/support/finance derived from `enabled_job_types`), connections (env-credential-based: google_mail, microsoft_mail, monday, fortnox, visma), automation (scheduler_mode + followups_enabled from `settings` column), readiness score (0–100) and status (needs_setup/almost_ready/ready), missing items list
- Scoring: email +30, any module enabled +20, scheduler not paused +20, support_email configured +10, destination integration +20; clamped to 0–100
- `PUT /setup/modules` — persists sales/support/finance checkboxes to `enabled_job_types` via `TenantConfigRepository.upsert`; preserves non-module job types
- `POST /setup/verify` — 5 lightweight checks (tenant config in DB, modules, email, scheduler, destination integration); returns `ok/warning/failed` with per-check details
- `_build_setup_status()` pure helper for easy unit testing (no DB call inside)
- `app/ui/index.html` — Onboarding tab: readiness score card + status badge + missing list; module checkboxes with Save; connection badges (Ansluten/Ej ansluten); automation display; Verifiera system button with detailed check result
- `tests/test_setup_wizard.py` — 45 tests: shape, module derivation, connection detection, scoring (additive, bounds, per-factor), PUT modules, POST verify
- 878/878 tests pass

## Completed slice (2026-04-25 — Case View)
- `GET /cases` — tenant-scoped paginated list; optional `status`/`type` filters; derives `subject` from `input_data.subject` or `latest_message_subject`; derives `customer_name` from entity extraction → intake origin → sender dict; derives `priority` from action_dispatch processor_history
- `GET /cases/{job_id}` — full detail: `original_message` (from/email/body), `extracted_data` (from entity extraction payload), `thread_messages` (from `conversation_messages`), `actions` (from `action_executions` table), `errors` (from `error_message` on failed actions + processor error entries); 404 on unknown job_id
- No new DB tables or columns — all data derived from existing `jobs` and `action_executions` tables
- `app/ui/index.html` — Ärenden tab added; case list table (date/type/subject/status/customer, clickable rows); detail panel (Ursprungligt mail, Extraherad data, Trådhistorik, Åtgärder, Fel sections); back button
- `tests/test_cases.py` — 32 tests: list shape, derivation logic, tenant isolation, 404, detail content
- 833/833 tests pass

## Completed slice (2026-04-24 — Scheduler for Inbox Sync + Daily Digest)
- `_run_scheduler_pass(tenant_id, db, now_utc)` — pure helper; reads run_mode + notifications from `settings`; runs inbox sync when `run_mode=scheduled` (skips if Gmail not configured); sends digest when `enabled`, `frequency != off`, `now_utc.hour >= send_hour`, and not already sent today (dedup by date comparison of `last_digest_sent_at`); persists `scheduler_state` (last_inbox_sync_at, last_digest_sent_at, last_scheduler_run_at, last_status, last_error) back to `settings` column; on exception: captures error, sets last_status=failed, still persists state
- `POST /scheduler/run-once` — iterates all tenants via `TenantConfigRepository.list_all`; calls `_run_scheduler_pass` per tenant; returns `{status, run_at, tenants_checked, inbox_syncs_run, digests_sent, skipped, errors, tenant_results}`; status=warning when any tenant errors
- `GET /scheduler/status` — tenant-scoped; returns `{run_mode, notifications_enabled, notifications_frequency, send_hour, last_inbox_sync_at, last_digest_sent_at, last_scheduler_run_at, last_status, last_error}`
- `app/ui/index.html` — Scheduler-status card added inside Kontrollpanel tab: last_status (colour-coded), last_inbox_sync_at, last_digest_sent_at, last_scheduler_run_at, Kör scheduler nu button; `loadControl()` now also fetches `/scheduler/status`; `runSchedulerOnce()` calls `POST /scheduler/run-once`, shows aggregate counts, refreshes status + dashboard
- `tests/test_scheduler.py` — 41 tests: GET status (shape/defaults/stored/tenant isolation), `_run_scheduler_pass` (run_mode gates, digest dedup by date, before/after send_hour, state persistence, error capture), `POST /scheduler/run-once` (tenant count, sync count, digest count, skip count, status=warning on error)
- 983/983 tests pass

## Completed slice (2026-04-25 — Hotfix BUG-001: settings column migration)
- **Root cause**: `create_all` creates missing tables but does not add missing columns to existing tables. The `settings` JSON column added in Slice 3 was absent from any DB created before that slice, causing 500s on all settings-dependent endpoints (`/dashboard/control`, `/notifications/settings`, `/scheduler/status`, `/setup/status`, etc.)
- **Fix**: `app/repositories/postgres/schema_migrations.py` — `ensure_runtime_schema(engine)` runs `ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS settings JSON` at startup, after `create_all`. Uses `IF NOT EXISTS` — idempotent on every restart. Fails startup with a clear `RuntimeError` if the migration cannot run.
- **Wired in**: `on_startup()` in `app/main.py` calls `ensure_runtime_schema(engine)` immediately after `create_all`
- `_REQUIRED_COLUMNS` registry — future additive columns can be appended to the list without touching startup logic
- `tests/test_schema_migrations.py` — 17 tests: happy path, idempotency, error wrapping, error logging, registry shape, startup ordering
- 1000/1000 tests pass

## Current state
Scheduler (inbox sync + daily digest), Customer Notifications, Manual inbox sync, Setup Wizard, Case View, Control Panel, Activity dashboard, ROI dashboard, thread continuation, and follow-up engine are complete. BUG-001 hotfix applied. **1000/1000 tests pass.**

All three intake flows (lead, customer inquiry, invoice) are implemented and production-ready. Each flow evaluates completeness deterministically (no LLM) and sends a Swedish-language follow-up email to the customer when required information is missing.

`POST /gmail/process-inbox` infers job_type from message content before creating the job — lead, customer_inquiry, and invoice are each routed to the correct pipeline and default actions.

All processors fall back deterministically (no LLM required): classification uses invoice > lead > customer_inquiry keyword matching; invoice extraction uses regex; inquiry priority uses keyword detection; completeness evaluation uses field-presence rules.

## Completed slice (2026-04-12 — integration event persistence)
- `IntegrationEvent` model base fixed to `database.Base` — table now in `create_all`
- `POST /integrations/{type}/execute` saves real DB row; returns response from persisted record
- 11 new tests; 122/122 pass

## Completed slice (2026-04-12 — Gmail OAuth token refresh)
- `refresh_access_token()` added to `mail_client.py`
- `GoogleMailClient` accepts `refresh_token`, `client_id`, `client_secret`; retries once after 401
- Credentials flow: settings → `service.py` connection config → `adapter.py` → `GoogleMailClient`
- `env.example` updated with three new OAuth vars
- 19 new tests; 141/141 pass

## Completed slice (2026-04-12 — Setup UI)
- `GET /tenant` now returns `enabled_job_types`, `auto_actions`, and normalised `allowed_integrations` (strings, not enum objects)
- `PUT /tenant/config` added — saves job types, integrations, auto actions to `tenant_configs` table via upsert
- `app/ui/index.html` — "Setup" top-level tab added; loads tenant config, renders checkboxes and toggles, saves via single button; no page reload required
- 15 new tests; 156/156 pass

## Completed slice (2026-04-12 — Setup Status / Readiness panel)
- `app/ui/index.html` — readiness summary panel added at the top of the Setup tab
- Four checks: Tenant loaded, ≥1 job type enabled, ≥1 integration enabled, auto-actions configured (warn-only)
- Overall "Ready / Not Ready" indicator derived from first three checks; frontend-only, no backend changes
- 156/156 pass

## Completed slice (2026-04-12 — Tenant creation)
- `POST /tenant` added — `{tenant_id, name}` body; 400 on duplicate; creates row via `TenantConfigRepository.upsert` with empty collections; no auth required
- `app/ui/index.html` — "Create Tenant" section at top of Setup tab; inline success/error; reloads config after creation
- 10 new tests in `tests/test_tenant_creation.py`; 166/166 pass

## Completed slice (2026-04-12 — Verification / Test Run UI)
- `app/ui/index.html` — "Verification" section added at bottom of Setup tab; frontend-only, no backend changes
- "Run Verification Test" button POSTs a minimal `customer_inquiry` job for the active tenant
- Result panel shows job ID, status, job type, summary, and payload JSON (capped height)
- Uses AI fallback path — completes without external credentials; safe to run during onboarding
- 166/166 pass; no backend changes

## Completed slice (2026-04-12 — UI polish, Swedish localisation, tenant switcher)
- `app/ui/index.html` fully rewritten — Swedish UI text throughout; consistent card-based layout; cleaner CSS; improved tab styling, spacing, form alignment
- Tenant switcher added to Inställningar tab — `GET /tenant/config/{tenant_id}` call with inline confirmation; reloads readiness + verification context for the selected tenant
- `GET /tenant/config/{tenant_id}` added to `app/main.py` — unauthenticated operator bootstrap endpoint; returns same shape as `GET /tenant`
- 8 new tests in `tests/test_tenant_config_by_id.py`; 174/174 pass

## Completed slice (2026-04-12 — Tenant listing and dropdown switcher)
- `TenantConfigRepository.list_all(db)` added — DB-only, no static fallback
- `GET /tenants` added — unauthenticated; `{items: [{tenant_id, name}], total}`; only real DB rows
- Tenant switcher in Inställningar upgraded from free-text to `<select>` populated from `GET /tenants`; arbitrary tenant IDs can no longer be entered; "Ingen tenant vald" shown when nothing selected
- Dropdown refreshes on tab open and after tenant creation; newly created tenant pre-selected automatically
- 14 new tests in `tests/test_tenant_listing.py`; 188/188 pass

## Completed slice (2026-04-13 — Tenant state fix, label maps, automation levels, live readiness)
- **Root cause:** `saveConfig()` saved to API-key tenant and reloaded from API-key tenant — silently reverting any non-TENANT_1001 selection. Fixed by: (1) `PUT /tenant/config/{tenant_id}` unauthenticated endpoint, (2) single `_activeTenantId` JS variable as sole source of truth, (3) all read/write paths use `{id}`-explicit endpoints
- `PUT /tenant/config/{tenant_id}` added — unauthenticated; 404 if tenant not in DB
- `TenantConfigUpdateRequest.auto_actions` widened to `dict[str, bool | str]`
- UI: `JOB_TYPE_LABELS` / `INTEGRATION_LABELS` maps for Swedish customer-friendly display
- UI: binary auto-action checkbox replaced with 3-level radio per active job type (Manuellt / Semi-automatiskt / Fullt automatiskt)
- UI: readiness panel recomputed live from form state on every change; final status "Redo att köra jobb"
- 14 new tests in `tests/test_tenant_config_save_by_id.py`; 202/202 pass

## Completed slice (2026-04-13 — Verification fix: tenant routing)
- **Root causes:** (1) `POST /jobs` derives tenant from API key → mismatch when UI tenant ≠ API-key tenant; (2) hard-coded `customer_inquiry` may not be in the tenant's enabled job types
- `POST /verify/{tenant_id}` added — unauthenticated; reads `tenant_configs` row; picks first supported enabled type; runs pipeline; 404/400 guards
- `app/ui/index.html` — `runVerification()` calls `POST /verify/{_activeTenantId}` with no body

## Completed slice (2026-04-13 — Verification fix: deterministic pipeline)
- **Root cause:** Without `LLM_API_KEY`, classification falls back to `detected_job_type: "unknown"` → policy appends `unknown_job_type` reason → `manual_review`. Lead/inquiry/invoice processors also fall back to `low_confidence / manual_review`.
- `_run_verification_pipeline(job, job_type_value, db)` added to `app/main.py` — runs intake, injects synthetic AI processor history (classification @ 0.95 confidence, entity extraction, type processor, decisioning), then runs deterministic policy + human_handoff. No LLM calls.
- `_VERIFICATION_SUPPORTED_TYPES = ["lead", "customer_inquiry", "invoice"]` — endpoint picks first enabled type from this list; 400 if none enabled
- `_VERIFICATION_PAYLOADS` — realistic Swedish input payload per supported type; ensures meaningful intake content
- Response now includes `verification_type` field
- `tests/test_verify_tenant.py` updated — 16 tests (added unsupported-type 400, verification_type key, supported-type preference)
- `tests/test_verification_pipeline.py` added — 19 tests exercising all three types end-to-end without mocking
- 237/237 pass

## How to use the Inställningar (Setup) tab
1. Open `http://localhost:8000/ui`
2. Click **Inställningar** in the top navigation
3. **Byt tenant:** enter a tenant ID in the switcher at the top and click "Ladda tenant" — config reloads for that tenant without a page refresh
4. **Skapa tenant:** fill in Tenant-ID + Namn in the creation form and click "Skapa tenant"
5. The **Konfigurationsstatus** panel shows readiness at a glance (job types, integrations, auto-actions)
6. Toggle job types, integrations, and auto-action settings
7. Click **Spara konfiguration** — persists to the `tenant_configs` DB table and reloads
8. Click **Kör verifieringstest** — calls `POST /verify/{tenant_id}`, which picks the tenant's first enabled job type and runs the pipeline; shows the result inline (no external credentials required)

## Completed slice (2026-04-14 — MVP stabilization & API readiness)

Six fixes applied after live testing revealed integration issues:

1. **Tenant state fix** — `saveConfig()` silently reverted to API-key tenant. Fixed by `PUT /tenant/config/{tenant_id}` (unauthenticated, explicit path) and `_activeTenantId` as single JS source of truth.

2. **Verification redesign** — Old flow used `run_pipeline` → LLM failure → `unknown` / `manual_review`. New `POST /verify/{tenant_id}` runs `_run_verification_pipeline`: deterministic, no LLM, injects synthetic processor history. Returns `completed` or `awaiting_approval` for valid tenants.

3. **Auth header bug** — `apiFetch` calls in `runVerification()` / `createTenant()` passed `headers: { 'Content-Type': ... }` which overwrote `X-API-Key`. Fixed by removing redundant `headers:` key.

4. **`/jobs` input contract clarified** — `input_data` is required as a nested object. Fields at top-level of the request body (outside `input_data`) are not passed to processors. README now includes a WARNING block.

5. **Intake mapping fix** — `intake_processor` now supports flat `sender_name` / `sender_email` / `sender_phone` keys at `input_data` root, in addition to the nested `sender` dict. Normalized into `origin`.

6. **Entity extraction fallback** — When LLM extraction leaves `customer_name` / `email` / `phone` null, they are now filled from normalized intake `origin` (`sender_name` / `sender_email` / `sender_phone`). Prevents false `missing_identity` validation errors.

- 263/263 tests pass
- README, docs/05-current-state.md, and docs/08-handoff.md updated to reflect real behavior

## What is actually working now (live-verified)

Confirmed through real API calls — not theoretical:

- **Gmail send** (`send_email`) — `POST /integrations/google_mail/execute` reaches the Gmail API and delivers email; OAuth refresh validated
- **Gmail read** (`list_messages`) — returns real inbox messages with message_id, thread_id, from, subject, received_at, snippet, label_ids; supports max_results and query filter
- **Gmail read** (`get_message`) — returns full message by message_id including body_text (text/plain extracted from MIME tree)
- **Monday item creation** (direct) — `POST /integrations/monday/execute` with `action: create_item` creates a real item in the configured board
- **Monday item creation** (workflow) — `/jobs` → action_dispatch → `create_monday_item` action type → real board item
- **Full pipeline** — intake → classification → extraction → decisioning → policy → action_dispatch → human_handoff; all stages execute with real data; verified without LLM
- **Multi-action dispatch** — `input_data.actions` with multiple entries executes them in sequence; partial failure recorded; no rollback
- **Approval pause/resume** — job enters `awaiting_approval`; `POST /approvals/{id}/approve` with `{}` resumes it; action executes after approval; result persisted
- **Action persistence** — `GET /jobs/{job_id}/actions` returns the executed action record
- **Gmail → lead → Monday flow** — list_messages → get_message → map to /jobs → Monday item created (full manual ingestion flow confirmed)
- **Gmail inbox trigger** (`POST /gmail/process-inbox`) — production-ready: dedup, mark-as-read, tenant gate, Monday enrichment, phone extraction, Slack notify, dry_run, query override
- **Deterministic classification** — LLM fallback produces `lead` or `customer_inquiry` (not `"unknown"`) for all job sources
- **545 tests passing**

## Verified production behavior

### Gmail
- `send_email`, `list_messages`, `get_message` all confirmed against live Gmail account
- OAuth 401→refresh→retry works for all three actions
- `invalid_grant` (expired/revoked refresh token) surfaces as 503 with descriptive message
- `body_text` extracted from text/plain MIME part; empty for HTML-only messages

### Monday
- `create_item` confirmed live — item appears in real board
- `create_monday_item` in workflow confirmed — action_dispatch routes to MondayAdapter correctly
- `column_values` serialized to JSON string internally; board_id is env-only

### Multi-action dispatch behavior
- Actions in `input_data.actions` execute in order within action_dispatch
- If one action fails, job status is `failed` — even if earlier actions succeeded
- No rollback — successful side effects (Monday item, sent email) persist regardless of later failures
- Results visible in `GET /jobs/{id}` → pipeline_state.action_dispatch

### Partial failure example (confirmed live)
Job with `[create_monday_item, send_email]`:
- Monday item created ✅
- Gmail failed (invalid_grant) ❌
- Job status: `failed`
- Monday item not rolled back

---

## How to test the system via API (step-by-step)

**1a. Direct Gmail send (requires OAuth env vars):**
```bash
curl -s -X POST http://localhost:8000/integrations/google_mail/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{"action": "send_email", "payload": {"to": "you@example.com", "subject": "Test", "body": "Hello"}}'
```

**1b. Gmail list messages:**
```bash
curl -s -X POST http://localhost:8000/integrations/google_mail/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{"action": "list_messages", "payload": {"max_results": 5}}'
```

**1c. Gmail get full message (use message_id from list_messages):**
```bash
curl -s -X POST http://localhost:8000/integrations/google_mail/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{"action": "get_message", "payload": {"message_id": "<id>"}}'
```

**2. Direct Monday item creation (requires MONDAY_API_KEY + MONDAY_BOARD_ID env vars):**
```bash
curl -s -X POST http://localhost:8000/integrations/monday/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{"action": "create_item", "payload": {"item_name": "Test item from AI Platform"}}'
```

**3. Create a job (triggers full pipeline; add force_approval_test to pause for approval):**
```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "tenant_id": "TENANT_1001",
    "job_type": "lead",
    "input_data": {
      "subject": "Test lead",
      "message_text": "Interested in your services.",
      "sender_name": "Test User",
      "sender_email": "test@example.com",
      "force_approval_test": true
    }
  }'
```

**4. List pending approvals and approve (body {} is required — empty body causes parse error):**
```bash
curl -s http://localhost:8000/approvals/pending -H "X-API-Key: key-abc123"

curl -s -X POST http://localhost:8000/approvals/<approval_id>/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{}'
```

**5. Inspect job result and executed actions:**
```bash
curl -s http://localhost:8000/jobs/<job_id> -H "X-API-Key: key-abc123"
curl -s http://localhost:8000/jobs/<job_id>/actions -H "X-API-Key: key-abc123"
```

---

## Known limitations / sharp edges (do not assume)

These are real behaviors observed during live testing. Each one has caused a failure at least once.

1. **`POST /jobs` requires `tenant_id` in the body** — not just the `X-API-Key` header. Both are required. The key determines auth; the body field routes the job.

2. **`job_type` in `/jobs` is overrideable** — the AI classifier may change it. The actual type used is in the response. Do not assume the input type matches the executed pipeline.

3. **`POST /approvals/{id}/approve` requires `{}`** — not an empty body. Sending no body at all causes a JSON parse error. Always include `{}` at minimum.

4. **`POST /integrations/{type}/execute` uses `"payload"`, not `"input"`** — sending `"input"` silently results in an empty payload and the adapter returns `400`. There is no warning in the response that the wrong key was used.

5. **Gmail needs all four OAuth vars** — `GOOGLE_MAIL_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`. Setting only some of them will work until the access token expires, then fail with `invalid_grant` (503).

6. **Monday `board_id` is env-only** — `MONDAY_BOARD_ID` in `.env` is the only way to set the target board. There is no per-request override. All `create_item` calls go to this board.

7. **Monday `column_values` must be a dict in the request** — the platform serializes it to a JSON string before sending to monday's GraphQL API. Do not pre-serialize. Sending a dict directly to monday's API without this serialization causes `Invalid type, expected a JSON string`.

8. **DB tenant config overrides static config** — if `monday` appears in `TENANT_CONFIGS` but the route returns `403 Integration not enabled`, check the DB row for that tenant. The DB row is authoritative when present. Update via `PUT /tenant/config/{tenant_id}`.

9. **Windows terminal (GBK) misrenders UTF-8** — Swedish characters in the API response are correct UTF-8. The Windows GBK code page can't display them and shows `?`. The data is not corrupted. Run `chcp 65001` to fix the terminal.

---

## Completed slice (2026-04-14 — live testing and regression hardening)

- Full end-to-end live testing performed: Gmail send, pipeline, approval flow, action persistence
- API contract gaps identified and documented
- `RuntimeError` from Gmail routes maps to `503`; `ValueError` maps to `400`
- `_mask()` helper and `_log_config_diagnostics()` added to `GoogleMailAdapter`
- `tests/test_google_mail_runtime_errors.py` — 15 tests
- `tests/test_integration_execute_contract.py` — 10 tests
- `tests/test_swedish_char_encoding.py` — 12 tests (UTF-8 round-trip proof)
- 300/300 tests pass

## Completed slice (2026-04-14 — Monday integration live testing and config fixes)

- Monday `create_item` live-tested — item confirmed created in real monday.com board
- **Bug fixed:** `allowed_integrations` in static `TENANT_CONFIGS` stored enum objects (`IntegrationType.MONDAY`); route check expected strings → `403` even though integration was configured
  - `app/core/config.py` — all `IntegrationType.X` → `IntegrationType.X.value` across all four tenant configs
  - `app/integrations/policies.py` — defensive normalization: `allowed = [i.value if hasattr(i, "value") else i for i in raw]`
- **Bug fixed:** `column_values` sent as Python dict to monday GraphQL API; monday requires a JSON string → `Invalid type, expected a JSON string`
  - `app/integrations/monday/client.py` — `json.dumps(column_values)` before variable assignment; `None` → `"{}"`, string pass-through
- **Improvement:** monday API errors now raise `RuntimeError("monday API error: <message>")` instead of raw `Exception(str(list))` — readable message, correctly caught by route as 503
- `tests/test_tenant_config.py` — 10 new normalization tests
- `tests/test_monday_client.py` — 16 new tests (serialization, error handling, adapter routing)
- README, docs/05-current-state.md, docs/08-handoff.md updated with Monday live status and all sharp edges
- 326/326 tests pass

---

## Completed slice (2026-04-21 — Gmail inbox trigger — initial)
- `POST /gmail/process-inbox` added — reads unread messages, creates lead jobs with `create_monday_item`, returns processed count and job IDs
- `_parse_from_header` helper; 14 tests in `tests/test_gmail_process_inbox.py`
- 371/371 tests pass (initial state for this session)

## Completed slices (2026-04-22 — Gmail inbox hardening)

Seven production-readiness slices completed in a single session:

1. **Deduplication** — `JobRepository.get_by_gmail_message_id`; `skipped_messages` with `reason: "duplicate"` (12 tests)
2. **Mark-as-read** — `GoogleMailClient.mark_as_read` + adapter dispatch; called non-fatally after pipeline; `marked_handled` in response (12 tests)
3. **Tenant config lead gate** — `get_tenant_config` checked before job creation; `reason: "lead_disabled"` when not enabled (11 tests)
4. **Monday enrichment** — `_make_monday_item_name`, `_infer_priority`, rich `column_values` with email/phone/priority/body (37 tests)
5. **From-header + phone extraction** — `email.utils.parseaddr`; `_extract_phone()` regex; phone fed into `column_values` and `input_data.sender` (26 tests)
6. **Slack notification** — `dispatch_action("notify_slack", ...)` non-fatal; `notified` flag in response (20 tests)
7. **Scheduler-safe mode** — `dry_run`, `query` override, richer response (`dry_run`, `query_used`, `max_results`, `scanned`) (24 tests)

## Completed slice (2026-04-22 — DEL 1 Slice 1: Deterministic classification fallback)

- `_LEAD_KEYWORDS` + `_classify_deterministic()` added to `classification_processor.py`
- Fallback now returns `"lead"` or `"customer_inquiry"` with `confidence=0.5`, `reasons=["deterministic_fallback", "llm_unavailable"]`
- Applies to all job sources — not just Gmail inbox
- `tests/test_classification_deterministic.py` — tests; `tests/test_ai_processors.py` updated

## Completed slices (2026-04-23 — Sellable MVP: all three intake flows)

### DEL 1 Slice 2: Customer inquiry default actions
- `_build_inquiry_default_actions(job)` — `create_monday_item` (priority, email, phone, subject, message) + `send_email` to `support@company.com`
- `classify_inquiry_priority(subject, message_text)` — `akut`, `snabbt`, `problem` → HIGH; else NORMAL
- `normalize_sender()`, `extract_phone()` shared helpers in `ai_processor_utils.py`
- `tests/test_inquiry_default_actions.py` — 76 tests

### DEL 1 Slice 3: Structured inquiry data
- Sender normalized (nested or flat keys); phone extracted from body; column_values and email body enriched

### DEL 1 Slice 4: Inquiry priority
- HIGH/NORMAL surfaced in item_name prefix, email subject, column_values, and body

### DEL 2 Slice 1: Invoice classification
- `_INVOICE_KEYWORDS` added; priority order: invoice > lead > customer_inquiry
- `classify_email_type()` extracted as public function — single source of truth for all callers

### DEL 2 Slice 2: Invoice default actions
- `_build_invoice_default_actions(job)` — `create_monday_item` + `create_internal_task`
- `tests/test_invoice_default_actions.py` — 32 tests

### DEL 2 Slice 3: Invoice extraction
- `extract_invoice_amount`, `extract_invoice_number`, `extract_due_date`, `extract_invoice_data` in `ai_processor_utils.py`
- Wired into `_build_invoice_default_actions` — amount, invoice_number, due_date, supplier_name, raw_text
- `tests/test_invoice_extraction.py` — 47 tests

### Inbox type inference
- `/gmail/process-inbox` calls `classify_email_type(subject, body)` before job creation
- Gate checks inferred type against `enabled_job_types`; skips with `"{type}_disabled"`
- Job created with inferred `JobType`; no hardcoded `actions` in `input_data`
- `tests/test_gmail_tenant_config_gate.py` — fully rewritten (17 tests)

**702/702 tests pass.**

## Completed slice (2026-04-24 — Follow-up Question Engine)

Deterministic completeness evaluation and automatic follow-up action injection. No LLM.

- `evaluate_information_completeness(job_type, input_data)` in `ai_processor_utils.py`
  - `lead`: requires `email` + (`message_text ≥ 10 chars` OR meaningful subject); `phone` is soft (missing but not blocking)
  - `customer_inquiry`: requires `email` + `message_text ≥ 15 chars`
  - `invoice`: requires `supplier_name` + at least one of `amount / invoice_number / due_date`
  - Returns: `is_complete`, `missing_fields`, `follow_up_questions` (Swedish), `recommended_status`
- `_build_lead_default_actions(job)` — new first-class builder for leads (previously fell through to generic fallback)
- `_build_follow_up_email(sender_email, questions)` — builds a `send_email` action; no new integration type
- All three builders surface `completeness_status` and `missing_fields` in Monday `column_values`
- Invoice incomplete info included in `create_internal_task` description (`SAKNAD INFORMATION: ...`) and metadata
- Explicit `input_data.actions` or `decisioning_processor` actions still override all defaults
- `tests/test_followup_engine.py` — 23 tests; `tests/test_inquiry_default_actions.py` — 1 test fixed
- 725/725 tests pass

## Completed slice (2026-04-24 — Thread continuation)

- `JobRepository.get_by_source_thread_id(db, tenant_id, source_system, thread_id)` — generic lookup by source system + thread_id
- `gmail_process_inbox` order: dedup → get_message → thread continuation → new-job path
- Continuation: merges into `conversation_messages`, updates `latest_*` fields, resets history, re-runs pipeline, marks as read
- `dry_run` detects continuation but makes no writes; response includes `continued`, `continuation_reason`
- `tests/test_thread_continuation.py` — 18 tests; 743/743 pass

## Completed slice (2026-04-24 — ROI Dashboard)

- `GET /dashboard/roi` — today's counts + estimated time/value savings
- Fixed assumptions: lead=10 min, support=8 min, invoice=6 min, follow-up=5 min, 500 SEK/h (constants `_ROI_*` in `main.py`)
- `followups_sent` counted from `action_executions` table (action_type=send_email on lead/inquiry jobs today)
- ROI section in Dashboard tab: 2 highlight cards (hours + SEK), 4 count cards, collapsible assumptions
- `tests/test_dashboard_roi.py` — 19 tests; 780/780 pass

## Completed slice (2026-04-24 — Activity Dashboard)

- `GET /dashboard/summary` — tenant-scoped: leads_today, inquiries_today, invoices_today, waiting_customer, ready_cases, completed_today
- `GET /dashboard/activity` — recent jobs with type, status, latest_action, priority, created_at; supports limit/offset
- Dashboard tab in operator UI (`/ui`): 6 summary cards + activity table; Swedish labels; empty + error states
- `tests/test_dashboard.py` — 18 tests; 761/761 pass

## Next steps

### Most likely next slice
1. **Scheduler / cron trigger** — wire a periodic external trigger to call `POST /gmail/process-inbox`
2. **Dashboard polish** — date-range filters, charts, auto-refresh

### After that
3. **HTML-to-text** — `body_text` is empty for HTML-only Gmail messages
4. **Monday per-request board_id override** — currently env-only
5. **Gmail credential health check** — proactive `invalid_grant` surface before ingestion run

## Remaining work
All original MVP backlog items are complete. The platform is live-verified, stable, and demonstrable.

## Expected output from next implementation chat
- Continue from this repo state; 761/761 tests are current
- Dashboard (summary + activity) and thread continuation are implemented
- Next logical slice: scheduler trigger or dashboard polish
## Completed slice (2026-04-25 — Customer Auto-Reply + Internal Handoff)

- `send_customer_auto_reply` (Swedish confirmation to sender) + `send_internal_handoff` (structured summary to internal team) injected as first two actions in lead and inquiry fallback pipelines
- Gated by `followups_enabled` setting and presence of customer email; skipped conditions produce `_skip` sentinel persisted as `status=skipped`
- `skipped_actions` / `skipped_count` added to dispatch result payload
- UI Case View: `ACTION_LABELS` map; shows recipient and Gmail message_id when available
- `tests/test_auto_reply_handoff.py` — 22 tests; 1022/1022 pass

## Completed slice (2026-04-25 — Classification v2 / Better Inbox Taxonomy)

### Problem solved
Real-world inbox classification was too broad: partnerships/collaborations were classified as lead, newsletters became customer_inquiry, supplier order confirmations had no distinct routing.

### New taxonomy (9 types)
| Type | Trigger | Automation |
|------|---------|------------|
| `lead` | Quote/price/booking/installation request | Full: auto-reply + handoff + Monday |
| `customer_inquiry` | Existing customer support/help/status question | Full: auto-reply + handoff + Monday |
| `invoice` | Invoice/faktura/payment request | Full: Monday + internal task |
| `partnership` | Samarbete/collaboration/B2B proposal | Visibility-only (skipped) |
| `supplier` | Order confirmation/delivery/kvitto | Visibility-only (skipped) |
| `newsletter` | Nyhetsbrev/unsubscribe/kampanjer | Visibility-only (skipped) |
| `internal` | Intern notering/internal memo | Visibility-only (skipped) |
| `spam` | You won/lottery/phishing | Visibility-only (skipped) |
| `unknown` | LLM fallback only | Generic internal task |

### Priority order (deterministic classifier)
spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry

### Files changed
- `app/domain/workflows/enums.py` — 5 new JobType values
- `app/ai/schemas.py` — 5 new AllowedJobType literals
- `app/workflows/processors/classification_processor.py` — v2 keyword sets + extended `classify_email_type`
- `app/workflows/processors/action_dispatch_processor.py` — `_VISIBILITY_ONLY_TYPES` + `_build_visibility_only_actions`
- `app/ui/index.html` — Swedish labels in `JOB_TYPE_LABELS` + `CASE_TYPE_LABELS`
- `tests/test_classification_v2.py` — 52 new tests
- `tests/test_gmail_notification.py` — regression test subject updated (service → customer_inquiry phrase)

### Tests
1074/1074 pass
## Completed slice (2026-04-25 — Cases UX Upgrade)

- GET /cases extended: q search (ILIKE on job_id + input_data blob), type filter, status filter, sort_by (received_at/created_at/status/type), sort_dir (asc/desc), limit, offset
- Response now includes: received_at, processed_at, customer_email, limit, offset per item
- received_at stored in input_data during Gmail inbox ingestion (from Gmail Date header)
- GET /cases/{job_id} includes received_at + processed_at
- Ärenden tab UI: search input, type/status/sort dropdowns, pagination (Föregående/Nästa), Visar X–Y av Z; shows received_at as primary timestamp
- 33 new tests in test_cases.py; 1107/1107 pass

### received_at behavior
- New Gmail inbox jobs: received_at stored in input_data from Gmail Date header
- Existing jobs (created before this slice): received_at=null; UI falls back to processed_at
- sort_by=received_at proxies to created_at at DB level (DB sort); frontend shows received_at when available
- No schema migration needed — received_at lives in existing input_data JSON column

## Completed slice (2026-04-26 — Tenant Memory Foundation + Workflow Scan Status)

### Problem solved
Platform had no persistent memory for tenant business context — company name, industry, services, communication tone, system integrations discovered, and routing hints per job type were not stored anywhere.

### What was built
- `GET /tenant/memory` — returns tenant-scoped memory merged with defaults; always returns a complete shape even for tenants with no stored memory
- `PUT /tenant/memory` — persists `business_profile`, `system_map`, `routing_hints` into `settings.memory`; merges into existing settings (does not clobber notifications/scheduler/other keys); each of the three top-level keys is optional in the PUT body
- `GET /workflow-scan/status` — returns last scan metadata: `last_scan_at`, `systems_scanned`, `status`, `summary`; defaults to `never_run` when no scan has run; scan state populated by a future workflow scanner
- `_DEFAULT_MEMORY` constant + `_get_memory(settings_dict)` pure helper — merges stored memory over defaults; importable for testing
- `TenantMemoryRequest` Pydantic model — all three fields optional; safe to call with partial body
- Kundminne tab in operator UI — Företagsprofil (company name, industry, services, tone inputs), Systemkarta (editable JSON textarea), Routing-hints (editable JSON textarea), Upptäckta system (rendered from scan summary), Senaste scanning card
- `tests/test_tenant_memory.py` — 23 tests

### Storage
Memory lives in the existing `tenant_configs.settings` JSON column under the `memory` key. No schema change needed. Compatible with all existing settings keys.

### Memory shape
```json
{
  "business_profile": { "company_name": "", "industry": "", "services": [], "tone": "professional" },
  "system_map": {
    "gmail": { "known_senders": [], "subject_patterns": [], "detected_mail_types": [] },
    "monday": { "boards": [], "groups": [], "columns": [] }
  },
  "routing_hints": { "lead": null, "customer_inquiry": null, "invoice": null, "partnership": null, "supplier": null }
}
```

### Tests
23 new tests in `tests/test_tenant_memory.py`. **1130/1130 pass.**

### Next likely slice
- Workflow Scanner v2 — Monday board scanner (system_map.monday); AI-assisted pattern suggestions based on system_map data

## Completed slice (2026-04-26 — Gmail Workflow Scanner v1)

### Problem solved
Tenant memory had a `system_map.gmail` placeholder but no mechanism to populate it. Platform had no way to observe what kinds of emails it had already processed.

### What was built
- `POST /workflow-scan/gmail` — tenant-scoped; queries jobs table for Gmail-sourced records (up to 250, ordered by created_at desc); no live Gmail API calls
- `_scan_gmail_jobs(records)` — pure analysis function:
  - `known_senders`: top 20 by occurrence, `{email, count}` shape
  - `subject_patterns`: strips Re:/Fwd:/Fw:/Sv:/Aw: prefixes, collapses whitespace, top 20 by frequency, `{pattern, count}` shape
  - `detected_mail_types`: unique sorted list of job_type values present in the sample
- Persists result into two places in `settings`:
  - `memory.system_map.gmail` — replaces gmail sub-dict only; business_profile and routing_hints untouched
  - `workflow_scan` — `{last_scan_at, systems_scanned, status, summary.gmail}`
- Failure path: catches any exception, preserves existing memory exactly as-is, sets `workflow_scan.status = "failed"`, raises HTTP 500
- `GET /workflow-scan/status` now returns real persisted scan state (was already reading from `settings.workflow_scan`)
- UI: "Skanna Gmail" button in Kundminne tab with inline running indicator; post-scan displays messages_scanned / senders_detected / patterns_detected / mail_types in card; reloads system_map textarea automatically

### Tests
25 new tests in `tests/test_gmail_scanner.py`. **1155/1155 pass.**

### Constraints respected
- No live Gmail API calls — reads only stored jobs
- No auto-routing triggered
- No AI/LLM calls — pure deterministic analysis
- Bounded to 250 records
- Monday scanner not included (next slice)

## Completed slice (2026-04-26 — Generic Workflow Scanner Engine)

### Problem solved
The Gmail scanner in Slice 2 was inlined directly in `main.py` with no extension points. Every future system (Monday, Visma, Fortnox, Microsoft Mail) would have required copy-pasted boilerplate. The scanning framework is now a proper engine with a clean adapter contract.

### What was built

**`app/workflows/scanners/` package**

| File | Role |
|------|------|
| `base.py` | `ScanResult` dataclass + `BaseWorkflowScannerAdapter` interface |
| `gmail_adapter.py` | `GmailWorkflowScannerAdapter` — extracted Gmail logic; `analyse_records()` public pure function |
| `engine.py` | `WorkflowScannerEngine` — registry lookup, adapter dispatch, persistence, no-clobber merge; `ADAPTER_REGISTRY` dict; `list_supported_systems()` |

**main.py changes**
- `_scan_gmail_jobs` re-exported from `gmail_adapter.analyse_records` — existing tests unbroken
- `scan_gmail` delegates to engine via `_make_scan_engine()`
- `scan_workflow_system(system)` — new generic endpoint `POST /workflow-scan/{system}`; 404 with supported system list for unknown keys
- `_scan_result_to_response()` shared formatter

**Engine behaviour**
- Success: `system_map[system]` updated, other systems' entries untouched; `workflow_scan.summary` merged (running gmail does not wipe monday state)
- Failure: existing memory preserved exactly; `workflow_scan.status = "failed"`; `RuntimeError` raised → HTTP 500

**UI**
- `scanWorkflowSystem(system)` generic JS function
- `scanGmail()` now calls `scanWorkflowSystem('gmail')`

### Adding a future adapter
1. Create `app/workflows/scanners/monday_adapter.py` implementing `BaseWorkflowScannerAdapter`
2. Add one line to `ADAPTER_REGISTRY` in `engine.py`
3. `POST /workflow-scan/monday` is immediately live

### Tests
32 new tests in `tests/test_workflow_scanner_engine.py`. All 1155 pre-existing tests still pass. **1187/1187 total.**

## Completed slice (2026-04-26 — Monday Workflow Scanner Adapter v1)

### Problem solved
Monday.com board structure was not visible to the AI memory system. Operators had no way to tell the platform what Monday boards exist, what they are called, or what they are used for. The Monday scanner adds a read-only snapshot of all boards/groups/columns and classifies their purpose automatically.

### What was built

**`app/workflows/scanners/monday_adapter.py`** — new file

| Function / Class | Role |
|-----------------|------|
| `detect_board_purpose(board)` | Deterministic keyword scan of board name + description + group titles + column titles; returns first matching purpose from: lead, customer_inquiry, invoice, support, partnership, supplier, internal, or "unknown" |
| `analyse_boards(raw_boards)` | Pure function; builds `boards_out` (each with `detected_purpose`), `flat_groups`, `flat_columns`; returns `(monday_map, monday_summary)` |
| `_build_monday_client(settings)` | Returns `MondayClient` if `MONDAY_API_KEY` is set, else `None` |
| `MondayWorkflowScannerAdapter` | `BaseWorkflowScannerAdapter` implementation; calls `client.get_boards(limit=50)`, delegates to `analyse_boards()`; missing API key → `ScanResult(status="failed")` which engine converts to HTTP 500 |

**`app/integrations/monday/client.py`**
- `get_boards(limit)` added — read-only GraphQL query returning id/name/description/groups/columns for each board

**`app/workflows/scanners/engine.py`**
- `MondayWorkflowScannerAdapter` registered in `ADAPTER_REGISTRY`
- Engine `run()` now also raises `RuntimeError` when adapter returns `ScanResult(status="failed")` (not just on exception) — consistent failure handling regardless of how the adapter signals failure

**`app/ui/index.html`**
- "Skanna Monday" button in Kundminne tab calling `scanWorkflowSystem('monday')`
- Monday summary card rendered by `_renderScanStatus()`: boards_scanned, groups_detected, columns_detected, detected_purposes

### Behaviour
- `POST /workflow-scan/monday` calls `MondayWorkflowScannerAdapter.run()`
- Persists into `settings.memory.system_map.monday` and `settings.workflow_scan`
- No-clobber: running Monday scan does not touch `system_map.gmail` or `business_profile`
- Multi-system summary merge: `workflow_scan.summary` is a dict keyed by system — running Monday does not wipe Gmail entry
- Missing API key → HTTP 500 with clear error message

### Tests
46 new tests in `tests/test_monday_scanner.py`. All 1187 pre-existing tests still pass. **1233/1233 total.**

## Completed slice (2026-04-26 — Routing Hint Drafts + Review-first apply)

### Problem solved
Scanner results were informational only — operators could see board structure but had no workflow to convert that knowledge into actionable routing. This slice adds a review-first suggestion loop: the platform generates draft hints, the operator reviews them in the UI, and only explicitly saved hints become active. No auto-routing, no external writes.

### What was built

**`app/workflows/scanners/routing_hint_drafts.py`** — new file

| Function | Role |
|----------|------|
| `generate_routing_hint_drafts(tenant_memory)` | Pure function; inspects `system_map.monday.boards`; for each of 7 supported job types returns a hint dict or null |
| `_best_monday_candidate(boards, job_type)` | Prioritizes `detected_purpose` exact match (high confidence) over board name keyword match (medium/low); multiple candidates → first wins, confidence reduced |
| `_board_name_matches(board_name, job_type)` | Keyword lookup from `_NAME_KEYWORDS` dict — same vocabulary as the Monday scanner |

Confidence rules:
- 1 board with matching purpose → `high`
- 2+ boards with matching purpose → `medium`, first board chosen
- 1 board with matching name → `medium`
- 2+ boards with matching name → `low`, first board chosen
- No match → `null`

**`app/main.py`** — two new endpoints

| Endpoint | Behaviour |
|----------|-----------|
| `GET /tenant/routing-hint-drafts` | Reads tenant memory, calls `generate_routing_hint_drafts()`, returns drafts. Read-only. |
| `POST /tenant/routing-hints/apply` | Validates hint shape (422 on unsupported job type, non-dict hint, missing `system`, bad `confidence`, unknown keys); merges only provided keys into `memory.routing_hints`; preserves `business_profile` and `system_map`; no external writes |

**`app/ui/index.html`** — Kundminne tab additions
- "Föreslå routing" button calls `GET /tenant/routing-hint-drafts`, populates editable textarea
- "Spara routing-hints" button calls `POST /tenant/routing-hints/apply` with textarea contents, reloads memory on success

### Important constraints
- Routing hints are **suggestions only** — operators must explicitly save/apply them
- `POST /tenant/routing-hints/apply` modifies only `memory.routing_hints` — no other memory keys, no external systems, no Monday items
- No auto-routing behavior changed
- Scanner system_map is read-only input to the hint generator

### Tests
34 new tests in `tests/test_routing_hint_drafts.py`. All 1233 pre-existing tests still pass. **1267/1267 total.**

## Completed slice (2026-04-26 — Routing Preview + Readiness)

### Problem solved
Routing hints were saved but invisible inside operations. Operators had no way to verify whether routing was correctly configured for each job type, and case detail gave no indication of where a job would be routed. This slice makes routing hints operationally visible — still preview only, no external writes.

### What was built

**`app/workflows/scanners/routing_preview.py`** — new file

| Function | Role |
|----------|------|
| `resolve_routing_preview(routing_hints, job_type)` | Pure; returns `{job_type, status, system, target, message}`; ready when hint exists and is valid; missing_hint when null/absent; invalid_hint when malformed |
| `resolve_routing_readiness(routing_hints)` | Pure; iterates all 7 supported job types; returns `{ready, missing, invalid, score:{ready_count, total, percent}}` |

Validation rules for `ready`:
- hint must be a dict
- must have non-empty `system`
- must have `target` dict with non-empty `board_id`

**`app/main.py`** — two new endpoints + case detail enrichment

| Endpoint | Behaviour |
|----------|-----------|
| `GET /tenant/routing-preview/{job_type}` | Reads tenant memory, calls `resolve_routing_preview()`; 400 for unsupported job_type |
| `GET /tenant/routing-readiness` | Reads tenant memory, calls `resolve_routing_readiness()` |
| `GET /cases/{job_id}` | Now includes `routing_preview` field (null when job_type not in supported list) |

**`app/ui/index.html`** — UI additions
- Case detail: colour-coded Routing Preview card (✅ Klar / ⚠ Saknas / ❌ Fel) with message and system/board info
- Kundminne tab: "Testa routing" section with per-type buttons + readiness score (`N / 7 jobbtyper klara`)

### Important constraints
- All preview only — no auto-routing, no external writes
- Case detail `routing_preview` is purely additive; all existing fields unchanged
- `GET /tenant/routing-readiness` is informational only

### Tests
30 new tests in `tests/test_routing_preview.py`. All 1267 pre-existing tests still pass. **1297/1297 total.**

## Completed slice (2026-04-26 — Generic Controlled Dispatch Engine + Monday Lead Adapter v1)

### Problem solved
The platform had routing hints, routing preview, and readiness scores — but no way to actually execute a dispatch. This slice adds the first controlled execution layer: operators can trigger dispatch of a lead job to Monday.com via a dedicated endpoint, with a dry-run preview before committing.

### What was built

**`app/workflows/dispatchers/` package** — new

| File | Role |
|------|------|
| `base.py` | `DispatchResult` dataclass + `BaseDispatchAdapter` contract (system_key, job_type_key, dispatch()) |
| `engine.py` | `ControlledDispatchEngine` — hint validation, duplicate guard, adapter lookup, persist; `DISPATCH_REGISTRY` keyed by (system, job_type) |
| `monday_lead_adapter.py` | `MondayLeadDispatchAdapter` — derives item name (company→customer→sender→email→subject→"New lead"), builds minimal column_values, calls `MondayClient.create_item()` |

**Duplicate guard**
- Uses existing `integration_events` table + idempotency key `dispatch:{tenant}:{job_id}:{system}:{job_type}`
- Successful dispatch persisted as `IntegrationEvent(integration_type="controlled_dispatch", status="success")`
- Repeated dispatch on same job → `status="skipped"` (not an error)

**`app/main.py`** — two new endpoints

| Endpoint | Behaviour |
|----------|-----------|
| `POST /jobs/{job_id}/dispatch-preview` | Dry-run: resolves hint, returns what would happen; never calls external API |
| `POST /jobs/{job_id}/dispatch` | Live: validates hint → duplicate check → adapter → persist; 400 on failure; 404 if job not found |

**`app/ui/index.html`** — case detail additions
- "Förhandsvisa dispatch" + "Skicka till system" buttons (shown only when routing status is `ready`)
- Result shown inline with colour-coded status (success/dry_run/skipped/failed)
- Confirm dialog before live dispatch

### Adding a future adapter
1. Create `app/workflows/dispatchers/hubspot_lead_adapter.py` implementing `BaseDispatchAdapter`
2. Add `("hubspot", "lead"): HubSpotLeadDispatchAdapter()` to `DISPATCH_REGISTRY`
3. `POST /jobs/{job_id}/dispatch` is immediately available for that system once the tenant saves a hint with `system="hubspot"`

### Constraints preserved
- No auto-routing — dispatch only via explicit endpoint call
- No column mapping engine — basic item creation only
- Dry-run always available before live dispatch

### Tests
33 new tests in `tests/test_dispatch_engine.py`. All 1297 pre-existing tests still pass. **1330/1330 total.**

## Completed slice (2026-04-26 — Dispatch Control Policy Integration)

Connects the existing `auto_actions` tenant config (Control Panel toggles) to the dispatch endpoints so that operator-set automation levels gate live dispatch.

### What was added

**`app/workflows/dispatchers/policy.py`** — new pure module
- `resolve_dispatch_policy(tenant_config, job_type)` — maps `auto_actions[job_type]` to normalized policy dict
- `manual`/`False`/`None`/unknown → `"manual"` (safe default)
- `"semi"` → `"approval_required"`
- `"auto"`/`True` → `"full_auto"`
- Returns `{policy_mode, requires_approval, can_dispatch_now}`

**`app/main.py`** — three additions

| Endpoint / function | Behaviour |
|---------------------|-----------|
| `_get_dispatch_policy(db, tenant_id, job_type)` | Internal helper: fetches tenant config + resolves policy |
| `GET /jobs/{job_id}/dispatch-policy` | Returns `{job_id, job_type, policy_mode, requires_approval, can_dispatch_now}`; 404 on unknown job |
| `POST /jobs/{job_id}/dispatch-preview` | Merges policy fields (`policy_mode`, `requires_approval`, `can_dispatch_now`) into dry-run response |
| `POST /jobs/{job_id}/dispatch` | Checks policy before adapter call; returns `{status:"approval_required", policy_mode, message}` when `can_dispatch_now` is False — no adapter called, no DB write |

**`app/ui/index.html`** — case detail additions
- Fetches `GET /jobs/{job_id}/dispatch-policy` when opening a case
- Shows "Dispatch-policy: Manuellt / Godkännande krävs / Helautomatisk" label in Swedish
- `_showDispatchResult()` handles `approval_required` status with ⚠ icon and Swedish message

### Tests
35 new tests in `tests/test_dispatch_policy.py`:
- `TestResolveDispatchPolicy` (9) — pure function, all input variants
- `TestGetDispatchPolicyEndpoint` (5) — shape, modes, 404
- `TestDispatchPreviewWithPolicy` (8) — policy fields present, dry_run unaffected
- `TestDispatchLiveWithPolicy` (9) — allow/block by mode, adapter not called on block, tenant isolation
- `TestExistingBehaviorPreserved` (3) — routing preview, readiness, dispatch-preview 404

**1365/1365 total tests pass.**

### Policy decision table

| `auto_actions[job_type]` value | `policy_mode` | `can_dispatch_now` | Adapter called? |
|-------------------------------|--------------|-------------------|-----------------|
| `"manual"` / `False` / `None` / missing | `"manual"` | `True` | Yes |
| `"semi"` | `"approval_required"` | `False` | No |
| `"auto"` / `True` | `"full_auto"` | `True` | Yes |
| Any other value | `"manual"` | `True` | Yes |

### Constraints preserved
- Policy is read-only from the dispatch side — Control Panel is still the only write path
- `approval_required` returns a clean JSON response (not an HTTP error) so clients can display a UI prompt
- Duplicate guard and all existing routing/preview behavior unchanged

## Completed slice (2026-04-26 — Dispatch Approval Queue)

Completes the semi-automatic dispatch flow. When an operator triggers dispatch on a job with `approval_required` policy, a real approval record is created and must be approved before any external system is written.

### What was added

**`app/repositories/postgres/approval_repository.py`**
- `ApprovalRequestRepository.find_pending_dispatch_approval(db, tenant_id, job_id, system, job_type)` — returns existing pending dispatch approval for same job/system/job_type, enabling deduplication

**`app/workflows/approval_service.py`**
- Module-level `from app.core.settings import get_settings as _get_settings` — patchable in tests
- `build_dispatch_approval_request(job_id, tenant_id, job_type, system, routing_hint, dry_run_result)` — builds approval dict with `next_on_approve="controlled_dispatch"`, `dispatch_context` containing job_id/tenant_id/job_type/system/target, and Swedish title/summary
- `resolve_dispatch_approval(db, tenant_id, approval_id, actor, channel, note, approved)` — on approve: runs `ControlledDispatchEngine.run(dry_run=False)`, persists audit event, returns dispatch result + approval_id; on reject: marks approval rejected, returns `{status:"rejected"}` without calling any adapter

**`app/main.py`** — updated `dispatch_job`, `approve_request`, `reject_request`
- `dispatch_job` (approval_required path):
  1. Runs dry-run to identify system/job_type
  2. Calls `find_pending_dispatch_approval` — returns existing approval_id if already queued
  3. Builds and upserts new approval record via `build_dispatch_approval_request`
  4. Returns `{status, approval_id, policy_mode, message}`
- `approve_request`: detects `next_on_approve=="controlled_dispatch"` → routes to `resolve_dispatch_approval` instead of `resolve_approval`
- `reject_request`: same detection → routes to `resolve_dispatch_approval(approved=False)`

**`app/ui/index.html`** — `renderApprovalCards()` updated
- Detects dispatch approvals via `next_on_approve === "controlled_dispatch"`
- Shows "Dispatch-godkännande" badge with job_type / system / board_name
- Button label: "Godkänn dispatch" instead of "Godkänn"

### Approval flow (end to end)

```
Operator: POST /jobs/{id}/dispatch  (with semi policy)
  → dry run to identify system/target
  → find_pending_dispatch_approval → none
  → build_dispatch_approval_request → upsert to approval_requests
  → return {status:"approval_required", approval_id:"..."}

Operator sees approval in Väntande godkännanden tab (badge: Dispatch-godkännande)

Operator: POST /approvals/{approval_id}/approve
  → get_by_approval_id → next_on_approve=="controlled_dispatch"
  → resolve_dispatch_approval(approved=True)
      → marks approval "approved" in DB
      → ControlledDispatchEngine.run(job, memory, dry_run=False)
          → existing duplicate guard (integration_events idempotency_key)
          → MondayLeadDispatchAdapter.dispatch() → real Monday item
          → _persist_dispatch → integration_events row
      → create_audit_event
      → return {status:"success", approval_id, policy_mode, ...}

Repeated dispatch call → find_pending_dispatch_approval returns existing → same approval_id returned
Repeated approve after success → engine sees existing dispatch → returns {status:"skipped"}
```

### Key design decisions
- Reuses existing `approval_requests` table and `ApprovalRequestRepository` — no new schema
- Discriminated by `next_on_approve="controlled_dispatch"` (vs pipeline's `"action_dispatch"`)
- Dispatch approval resolution does NOT call `orchestrator.resume_after_approval()` — runs engine directly
- Approve/reject endpoints remain untyped (no `response_model=JobResponse`) since dispatch approvals return a different shape

### Tests
33 new tests in `tests/test_dispatch_approval.py`:
- `TestBuildDispatchApprovalRequest` (9) — shape, context fields, title, summary
- `TestDispatchApprovalCreation` (11) — creates approval, does not live-dispatch, upserts with controlled_dispatch marker, duplicate reuse
- `TestImmediateDispatchPolicies` (2) — manual/auto still execute immediately
- `TestApproveDispatchApproval` (7) — engine called, live (not dry run), returns result, failure/skip pass-through
- `TestRejectDispatchApproval` (2) — returns rejected, engine not called
- `TestExistingPipelineApprovals` (1) — pipeline approve still uses resolve_approval
- `TestTenantIsolation` (1) — cross-tenant 404

**1398/1398 total tests pass.**

## Completed slice (2026-04-26 — Auto Dispatch Pipeline Hook v1)

Adds the first real automatic dispatch trigger. When a lead job completes with full_auto policy, it is automatically dispatched to Monday without any operator action.

### What was added

**`app/workflows/dispatchers/auto_dispatch.py`** — new module
- `AutoDispatchResult` dataclass: `status` / `reason` / `dispatch_result`
- `maybe_auto_dispatch_job(db, tenant_id, job, settings)` — pure-function guard chain:
  1. job_type must be "lead" (only supported type)
  2. policy_mode must be "full_auto" (manual/semi → skipped)
  3. routing_preview status must be "ready" (missing/invalid → skipped)
  4. routing_hint system must be "monday" (other systems → skipped)
  5. DISPATCH_REGISTRY must have (monday, lead) adapter
  6. Calls `ControlledDispatchEngine.run(dry_run=False)` — engine handles duplicate guard
  7. Returns `AutoDispatchResult` — **never raises**; exceptions caught and returned as `status="failed"`

**`app/workflows/orchestrator.py`** — pipeline hook
- Module-level import of `maybe_auto_dispatch_job` (patchable in tests)
- `_finalize_success` calls `self._maybe_auto_dispatch(final_job)` when `status == COMPLETED`
- `_maybe_auto_dispatch(job)` — short-circuits when `self.db is None`; swallows all exceptions; audit-records failures

**`app/main.py`** — endpoint
- `POST /jobs/{job_id}/auto-dispatch` — calls `maybe_auto_dispatch_job` with the same logic; 404 if job not found; returns `{status, reason, dispatch_result}`

**`app/ui/index.html`** — case detail
- "Testa auto-dispatch" button (shown when routing is ready)
- `autoDispatch(jobId)` JS function; shows ✅/ℹ/❌ result with Swedish labels

### Decision: pipeline hook vs endpoint-only

Added both. The pipeline hook fires automatically for every new job that completes with `status=COMPLETED` when conditions are met. The endpoint provides a manual trigger for existing jobs and testing.

### Supported auto-dispatch matrix

| job_type | system | policy needed | Notes |
|----------|--------|---------------|-------|
| lead     | monday | full_auto     | ✅ Implemented |
| any other | any   | any           | skipped — not implemented |

### Safety guarantees
- No external write unless ALL 5 conditions pass
- Duplicate guard via `ControlledDispatchEngine` (integration_events idempotency_key)
- `_maybe_auto_dispatch` swallows all exceptions — pipeline jobs retain COMPLETED status even if auto-dispatch fails
- Failure recorded in audit only, not in job status

### Tests
29 new tests in `tests/test_auto_dispatch.py`:
- `TestMaybeAutoDispatch` (16) — all skip/pass conditions, engine called live, duplicate handled, exception safety
- `TestAutoDispatchEndpoint` (6) — endpoint shape, 404, manual policy, calls maybe_auto_dispatch
- `TestPipelineHook` (4) — _maybe_auto_dispatch called, tenant_id passed, exception safety, db=None guard
- `TestTenantIsolation` (2) — isolation structural tests
- `TestNoSecretLeakage` (1) — reason field contains class name only

**1427/1427 total tests pass.**

## Completed slice (2026-04-26 — Dispatch Observability + ROI Attribution)

Every dispatch event is now annotated with its automation mode, and operators can view aggregated dispatch statistics directly in the Dashboard.

### What was added

**`app/workflows/dispatchers/engine.py`** — `dispatch_mode` metadata
- `_persist_dispatch(db, tenant_id, job_id, result, dispatch_mode="unknown")` — new `dispatch_mode` parameter; stored as JSON field in `IntegrationEvent.payload`
- `ControlledDispatchEngine.run(job, memory, dry_run, dispatch_mode="unknown")` — passes mode through to persist

**Callers updated (3 sites)**
| Caller | dispatch_mode value |
|--------|---------------------|
| `dispatch_job` in `main.py` | `policy.get("policy_mode", "unknown")` |
| `resolve_dispatch_approval` in `approval_service.py` | `"approval_required"` |
| `maybe_auto_dispatch_job` in `auto_dispatch.py` | `"full_auto"` |

**`app/workflows/dispatchers/observability.py`** — new module
- `MINUTES_SAVED_PER_SUCCESS = 5` — deterministic ROI constant
- `get_dispatch_summary(db, tenant_id, *, job_type=None, system=None, limit_recent=10)`:
  - Queries `IntegrationEvent` where `integration_type == "controlled_dispatch"` for the tenant
  - Aggregates: `total_dispatches`, `successful_dispatches`, `failed_dispatches`, `skipped_dispatches`
  - `by_mode`: `{full_auto, manual, approval_required, unknown}` — counts per dispatch mode
  - `by_job_type`: `{job_type: count}` — from payload
  - `by_system`: `{system: count}` — from payload
  - ROI: `estimated_minutes_saved = successful * 5`; `estimated_hours_saved = round(minutes/60, 2)`
  - `recent`: last N events with `job_id, job_type, system, status, mode, external_id, message, created_at`
  - Optional filters: `job_type=` and `system=` reduce the result set in Python (post-query)
  - No schema change — reads existing `integration_events` rows

**`app/main.py`** — new endpoint
- `GET /dispatch/summary` — tenant-scoped; optional `job_type` / `system` / `limit` query params; returns `get_dispatch_summary()` dict directly

**`app/ui/index.html`** — Dashboard tab: Dispatchöversikt card
- 5 stat cards: Totalt skickade / Lyckade / Misslyckade / Överhoppade / Uppskattad tid sparad (minuter)
- 3 mode cards: Automatiska / Manuella / Via godkännande
- Recent table: Tid / Typ / System / Status / Läge / Ext-ID
- `loadDispatchSummary()` async function called from `loadDashboard()`; populates all elements; error displayed in `dispatchSummaryError` div

### Constraints
- No new DB table or column — reads existing `integration_events` rows
- ROI is deterministic (5 min fixed constant) — no AI/LLM calls
- `dispatch_mode` added to payload JSON only — backward compatible; old events without the field show `"unknown"` in the UI (payload.get fallback)

### Tests
28 new tests in `tests/test_dispatch_observability.py`:
- `TestEmptySummary` (4) — zero counts, mode keys present, empty job_type/system
- `TestSuccessAggregation` (4) — single success, minutes saved, failed not counted, mixed statuses
- `TestByMode` (6) — all four modes; fallback to unknown
- `TestByJobTypeAndSystem` (4) — counts, unknown fallback
- `TestOptionalFilters` (3) — job_type, system, both
- `TestLimitRecent` (3) — default 10, custom limit, fewer than limit
- `TestRecentShape` (2) — all fields present, missing fields fall back gracefully
- `TestEndpointShape` (2) — all top-level keys present, tenant isolation structural test

**1455/1455 total tests pass.**

## Completed slice (2026-04-26 — Time-Range Filters + Customer ROI Report)

Turns dispatch observability into customer-facing proof of value with selectable time windows and an executive summary card.

### What was added

**`app/workflows/dispatchers/observability.py`** — extended

| Symbol | Role |
|--------|------|
| `_VALID_RANGES` | `{"today", "7d", "30d", "all"}` |
| `_normalise_range(range_)` | Coerces unknown/None to `"30d"`; safe for all callers |
| `_range_bounds(range_)` | Returns `(from_dt, to_dt)` UTC datetimes for each preset |
| `_range_label(range_)` | Swedish human label for message strings |
| `_fetch_records(db, tenant_id, range_, *, job_type, system)` | Shared DB query with optional `created_at >= from_dt` filter |
| `get_dispatch_summary(…, range_=None, …)` | Extended with `range_` param; response now includes `range`, `from`, `to` metadata; backward-compatible |
| `get_dispatch_report(db, tenant_id, *, range_=None)` | New function; returns executive headline: `dispatches_completed`, `time_saved_hours`, `success_rate_percent`, `automation_share_percent`, `breakdown`, `systems`, `job_types`, `message` |

**automation_share definition** (documented in module docstring):
- `(approval_required + full_auto) / (total - skipped) * 100`
- Skipped events never reached an external system, so they are excluded from the denominator
- `success_rate = successful / (total - skipped) * 100` by the same logic
- Both return `0` when no actionable events exist (safe division)

**`app/main.py`** — endpoints updated

| Endpoint | Change |
|----------|--------|
| `GET /dispatch/summary` | Added `range` query param; passes to `get_dispatch_summary(range_=range)` |
| `GET /dispatch/report` | New endpoint; accepts `range` query param; returns `get_dispatch_report()` dict |

**`app/ui/index.html`** — Dashboard tab updates
- Range selector buttons (Idag / 7 dagar / 30 dagar / All tid) above Dispatchöversikt heading
- Active button highlighted via `btn-primary`; `_dsRange` JS variable tracks selection (default `30d`)
- `setDispatchRange(range)` — updates button state, reloads both `loadDispatchSummary()` and `loadDispatchReport()`
- `loadDispatchSummary()` now appends `?range=` to the fetch URL; shows range label next to heading
- `loadDispatchReport()` — new async function; populates ROI Rapport card
- ROI Rapport card: Slutförda dispatches / Sparad tid / Lyckandegrad / Automationsgrad + headline message

### Tests
38 new tests in `tests/test_dispatch_time_range.py`:
- `TestNormaliseRange` (7) — valid presets, None, invalid string, empty string
- `TestSummaryRangeFiltering` (6) — today/7d/30d/all/invalid/None range params
- `TestSummaryMetadata` (4) — range/from/to keys present, from=None for "all"
- `TestSummaryBackwardCompat` (2) — all original keys still present, by_mode shape unchanged
- `TestDispatchReport` (17) — headline values, success_rate, automation_share, zeros, only-skipped, breakdown/systems/job_types, message, range metadata, invalid range
- `TestTenantIsolation` (2) — summary and report are tenant-scoped

**1493/1493 total tests pass.**

## Completed slice (2026-04-26 — Customer Onboarding Wizard)

Makes first customer onboarding fast, visible, and repeatable from the existing UI.

### What was added

**`app/onboarding/` package** — new

| File | Role |
|------|------|
| `__init__.py` | Package marker |
| `readiness.py` | `get_onboarding_status()` + 8 individual step evaluators |

**Step evaluators** (all deterministic, no external API calls):

| Step key | Complete when |
|----------|--------------|
| `tenant_created` | Tenant row exists in `tenant_configs` |
| `gmail_ready` | `GOOGLE_MAIL_ACCESS_TOKEN` set OR Gmail scan succeeded in `workflow_scan.summary.gmail` |
| `monday_ready` | `MONDAY_API_KEY` set OR Monday scan succeeded in `workflow_scan.summary.monday` |
| `systems_scanned` | `workflow_scan.systems_scanned` contains `"gmail"` or `"monday"` |
| `routing_hints_saved` | At least one hint with non-empty `system` + `target.board_id` |
| `automation_policy_set` | `auto_actions` has at least one truthy value |
| `test_lead_created` | `JobRepository.count_jobs_for_tenant(…, job_type="lead") > 0` |
| `dispatch_verified` | `IntegrationEvent` exists with `integration_type="controlled_dispatch"` + `status="success"` |

**Overall status:**
- `not_started`: 0 steps complete
- `in_progress`: 1–7 steps complete
- `ready`: all 8 steps complete

**`app/main.py`** — two new endpoints

| Endpoint | Behaviour |
|----------|-----------|
| `GET /onboarding/status` | Returns full checklist; tenant-scoped; no external API calls |
| `POST /onboarding/test-lead` | Optional JSON body `{company_name, customer_name, email, message}`; creates lead job via `_run_verification_pipeline` (deterministic, no LLM, no external email); returns `{job_id, tenant_id, job_type, status, message}`; creates audit event |

**`app/ui/index.html`** — Onboarding tab extended (existing setup sections preserved)

- "Kunduppsättning" section added below existing Setup/Verify content
- Progress bar (0–100%) + step count + overall status label (Ej startad / Pågår / Redo för pilot)
- Checklist rows: ✅/⬜/⚠️ icon + label + message per step
- Action buttons: Uppdatera status / Skanna Gmail / Skanna Monday / Föreslå routing / Spara routing-hints
- "Skapa testlead" form: company_name, customer_name, email, message inputs + result card
- `loadWizardStatus()` fetches `GET /onboarding/status` and renders checklist
- `createTestLead()` POSTs to `POST /onboarding/test-lead` and reloads checklist
- Both `loadOnboarding()` and `loadWizardStatus()` called when Onboarding tab is opened

### Constraints respected
- No external API calls from readiness status endpoint
- No new integrations or adapters
- No React rewrite — existing single-file UI only
- Test lead uses deterministic pipeline (same as `POST /verify/{tenant_id}`)
- Existing Onboarding/Setup sections preserved unchanged

### Tests
49 new tests in `tests/test_onboarding.py`:
- `TestCheckTenantCreated` (2) — complete/incomplete
- `TestCheckGmailReady` (4) — env token, scanner summary, scanner top-level, nothing
- `TestCheckMondayReady` (3) — env key, scanner summary, nothing
- `TestCheckSystemsScanned` (6) — gmail, monday, both, empty, none, unknown only
- `TestCheckRoutingHintsSaved` (6) — valid hint, empty, missing board_id, missing system, None hint, no memory
- `TestCheckAutomationPolicy` (6) — configured, full_auto, False, None, empty, no key
- `TestCheckTestLead` (2) — complete, incomplete
- `TestCheckDispatchVerified` (2) — event exists, no event
- `TestGetOnboardingStatus` (9) — keys, 8 steps, all step keys, not_started, in_progress, ready, percent, tenant_id, field shapes
- `TestTenantIsolation` (2) — scoped, cross-tenant isolation
- `TestOnboardingTestLead` (6) — job_id, tenant_id, job_type, status, custom company, None request default

**1542/1542 total tests pass.**

## Completed slice (2026-04-26 — Slice 14: Integration Health Center)

### Problem solved
Operators had no way to see whether Gmail and Monday integrations were actually working without making external API calls or reading raw environment variables.

### What was built

**`app/health/integration_health.py`** — new module

`get_integration_health(db, tenant_id, *, app_settings)` returns per-system health from internal signals only. No external API calls. No secrets in response.

Per-system checks:

| Check key | Gmail | Monday |
|-----------|-------|--------|
| `config_present` | `GOOGLE_MAIL_ACCESS_TOKEN` set | `MONDAY_API_KEY` set |
| `scanner_ran` | `workflow_scan.summary.gmail.status == "success"` | `workflow_scan.summary.monday.status == "success"` |
| `inbox_sync` / `dispatch_success` | Latest `AuditEventRecord` with `action="gmail_inbox_sync"` | Latest `IntegrationEvent` with `integration_type="controlled_dispatch"` |

System statuses: `healthy | warning | error | not_configured`. Overall status: `error` if any error, `warning` if any warning/not_configured, else `healthy`.

**`app/main.py`** — `GET /integrations/health` (tenant-authenticated)

**`app/ui/index.html`** — Integrationshälsa card in Dashboard tab; `loadIntegrationHealth()` called on dashboard load.

### Tests
47 new tests in `tests/test_integration_health.py`.

**1589/1589 total tests pass.**

## Completed slice (2026-04-26 — Slice 15: Pilot Readiness Hardening)

### Problem solved
Operators had no single view to determine whether the platform was ready for a live pilot run. Individual signals existed (onboarding wizard, integration health, routing readiness) but were scattered across tabs.

### What was built

**`app/health/production_readiness.py`** — new module

`get_pilot_readiness(db, tenant_id, *, app_settings)` returns 11 deterministic checks aggregated from existing platform state. No external API calls. No secrets in response.

| Check key | Source | Pass / Warning / Fail |
|-----------|--------|----------------------|
| `auth_configured` | `TENANT_API_KEYS` env | pass if set, warning if empty |
| `tenant_exists` | `TenantConfigRepository.list_all` | pass if ≥1 tenant, fail if 0 |
| `onboarding_ready` | `get_onboarding_status` | pass=ready, warning=in_progress, fail=not_started |
| `integrations_health_not_error` | `get_integration_health` | pass=healthy, warning=warning, fail=error |
| `routing_ready_for_lead` | `resolve_routing_preview("lead")` | pass=ready, warning=missing/invalid |
| `dispatch_duplicate_protection` | idempotency_key column query | pass if accessible, fail if exception |
| `dispatch_observability` | integration_events count | pass if >0, warning if 0 |
| `scheduler_safe` | scheduler.run_mode + gmail env | warning if scheduled+no gmail, warning if paused |
| `required_env_present` | APP_NAME + integration envs | fail if no APP_NAME, warning if no integrations |
| `ui_available` | `_UI_PATH.exists()` | pass if file on disk, fail if missing |
| `test_lead_exists` | `JobRepository.count_jobs_for_tenant` | pass if >0, warning if 0 |

Overall status: `not_ready` if any fail, `almost_ready` if any warning, `ready` if all pass.

**`app/main.py`** — `GET /pilot/readiness` (tenant-authenticated)

**`app/ui/index.html`** — Pilotberedskap card in Dashboard tab (checklist table with pass/warning/fail icons + messages); `loadPilotReadiness()` called on dashboard load.

### Tests
49 new tests in `tests/test_production_readiness.py`.

**1638/1638 total tests pass.**

## Completed slice (2026-04-26 — Slice 16: Super Admin Panel v1)

### Problem solved
The platform had no way to get a cross-tenant view: "how are ALL customers doing?" The existing UI only answered "how is this selected tenant doing?"

### What was built

**`app/admin/super_admin.py`** — new module

`get_super_admin_overview(db, *, app_settings)` aggregates health for all DB tenants. One failing tenant does not abort the rest. No external API calls. No secrets in response.

Per-tenant shape:
```json
{
  "tenant_id": "...", "name": "...", "status": "healthy|warning|error|not_ready",
  "onboarding": {"status": "...", "percent": 0},
  "pilot_readiness": {"status": "...", "percent": 0},
  "integrations": {"overall_status": "...", "gmail": "...", "monday": "..."},
  "dispatch": {"total_30d": 0, "success_30d": 0, "failed_30d": 0, "hours_saved_30d": 0.0, "automation_share_percent_30d": 0},
  "latest_activity_at": null,
  "recent_error_count": 0
}
```

Top-level: `{total_tenants, healthy, warning, error, not_ready, total_hours_saved_30d, items}`.

Top-level status derivation per tenant: `error` if integration_health==error; `not_ready` if pilot==not_ready; `warning` if integration warning, onboarding not complete, or pilot almost_ready; else `healthy`.

**`app/main.py`** — `GET /admin/tenants/overview` (protected by existing API key auth)

**`app/ui/index.html`** — "Super Admin" tab added to top nav; summary cards (Totalt kunder / Friska / Varning / Fel / Ej redo / Sparade timmar 30d); tenant table (Kund, Tenant ID, Status, Onboarding %, Pilotberedskap %, Integrationshälsa, Dispatch 30d, Sparad tid, Fel, Senaste aktivitet, Åtgärd); "Öppna kund" button switches to Inställningar tab and loads that tenant's config.

### Auth note
`GET /admin/tenants/overview` currently uses the same per-tenant API key auth as other endpoints. This is sufficient for single-operator MVP use. Before exposing in a production multi-customer context, implement a dedicated `ADMIN_API_KEY` env var so individual tenant operators cannot view other tenants' data.

### Tests
44 new tests in `tests/test_super_admin.py`.

**1682/1682 total tests pass.**

## Completed slice (2026-04-26 — Slice 17: Admin Auth Hardening)

### Problem solved
`GET /admin/tenants/overview` returned cross-tenant data but was only protected by a per-tenant API key. Any tenant with a valid API key could read all other tenants' health data — not acceptable before production multi-customer use.

### What was built

**`app/core/settings.py`** — `ADMIN_API_KEY: str = ""` field added. Set via env var. Defaults to empty (fail-closed behaviour).

**`app/core/admin_auth.py`** — new module

`require_admin_api_key(x_admin_api_key)` FastAPI dependency:
- Reads `X-Admin-API-Key` header.
- Compares to `ADMIN_API_KEY` using `hmac.compare_digest` (constant-time).
- Missing header → 401.
- Wrong key → 401 (same code — no enumeration).
- `ADMIN_API_KEY` not configured → 401 (fail closed — admin endpoints disabled until configured).
- Configured value never appears in responses, logs, or error details.

**`app/main.py`** — `GET /admin/tenants/overview` dependency changed from `get_verified_tenant` to `require_admin_api_key`. Tenant X-API-Key no longer accepted on this endpoint.

**`env.example`** — `ADMIN_API_KEY` documented with usage note.

**`app/ui/index.html`** — Admin API-nyckel input added to Super Admin tab (password field, persisted to `localStorage` as `ui_admin_api_key`). `adminHeaders()` helper sends `X-Admin-API-Key` header. `loadAdminOverview()` gates on key presence and shows "Åtkomst nekad" on 401/403.

### Auth model going forward

| Layer | Header | Protects |
|-------|--------|---------|
| Tenant operator | `X-API-Key` | Per-tenant endpoints |
| Super admin | `X-Admin-API-Key` | Cross-tenant admin endpoints |

Future admin endpoints must use `Depends(require_admin_api_key)`.

### Remaining future work
- User accounts / RBAC (not in MVP scope).
- OAuth admin login (not in MVP scope).
- Per-IP rate limiting on admin endpoints (not in MVP scope).

### Tests
24 new tests in `tests/test_admin_auth.py`:
- `TestSettingsField` (3) — field exists, defaults empty, can be set
- `TestRequireAdminApiKey` (13) — passes correct key, 401 on missing/wrong/unconfigured, secret not in detail, whitespace handling, tenant key rejected, WWW-Authenticate header, reusable
- `TestAdminEndpointAuth` (8) — no key 401, wrong key 401, correct key passes, unconfigured fails closed, tenant key rejected, secret not exposed, dependency importable, tenant auth not broken

**1706/1706 total tests pass.**

## Completed slice (2026-04-26 — Slice 18: Fortnox Workflow Scanner)

### What was built
Read-only Fortnox scanner integrated into the existing `WorkflowScannerEngine` / `ADAPTER_REGISTRY` pattern.

### Files changed
- `app/integrations/fortnox/client.py` — added `params` arg to `_get()`; added read-only methods: `get_customers(limit)`, `get_articles(limit)`, `get_invoices(limit)`, `find_customer_by_email(email)`, `find_customer_by_name(name)`, `find_recent_invoices_by_customer(customer_number, limit)`, `find_invoice_by_document_number(document_number)`
- `app/workflows/scanners/fortnox_adapter.py` (new) — `_normalise_customer/article/invoice()`, `analyse_fortnox_data()` pure function, `FortnoxWorkflowScannerAdapter` with `system_key = "fortnox"`
- `app/workflows/scanners/engine.py` — imported + registered `FortnoxWorkflowScannerAdapter` under `"fortnox"` in `ADAPTER_REGISTRY`
- `app/main.py` — added `"fortnox"` slot to `_DEFAULT_MEMORY["system_map"]`
- `app/ui/index.html` — "Skanna Fortnox" button + summary card; `scanFortnox()` wrapper; `scanWorkflowSystem()` handles fortnox button disable/enable and detail message; `_renderScanStatus()` renders fortnox summary card
- `tests/test_fortnox_scanner.py` (new) — 42 tests

### Credential safety
- `FORTNOX_ACCESS_TOKEN` + `FORTNOX_CLIENT_SECRET` never appear in `ScanResult`, API responses, or error messages
- Missing credentials → failed `ScanResult` (no exception raised to caller)

### No-clobber guarantee
- Fortnox scan only writes to `settings.memory.system_map.fortnox` — gmail and monday slots are untouched
- Failed scan preserves all existing memory

### Tests
42 new tests in `tests/test_fortnox_scanner.py`:
- Normalisation helpers (16)
- `analyse_fortnox_data` pure function (7)
- Adapter missing config (5)
- Adapter successful scan (6)
- Engine registration + persistence (8)

**1748/1748 total tests pass.**

## Completed slice (2026-04-26 — Slice 19: Fortnox Customer + Invoice Actions)

### What was built
Three operator action endpoints that talk to Fortnox live via `FortnoxClient`. Read-mostly; one write (create_customer).

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/integrations/fortnox/customers/lookup` | Lookup by email then name; returns first match or null |
| POST | `/integrations/fortnox/customers/create` | Create customer; name required; email/org/phone optional |
| POST | `/integrations/fortnox/invoices/lookup` | By document_number → single invoice; by customer_number → list (limit≤50) |

All three:
- Return 503 when `FORTNOX_ACCESS_TOKEN` or `FORTNOX_CLIENT_SECRET` missing
- Return 422 on missing required fields
- Never leak credential values in error responses
- Require tenant auth (`X-API-Key`)

### Files changed
- `app/main.py` — `_get_fortnox_client_or_raise()` helper; three new route functions
- `app/ui/index.html` — "Fortnox Pilotverktyg" section in Kundminne tab; `fortnoxLookupCustomer()`, `fortnoxCreateCustomer()`, `fortnoxLookupInvoice()` JS functions
- `tests/test_fortnox_actions.py` (new) — 32 tests

### Tests
32 new tests in `tests/test_fortnox_actions.py`:
- `_get_fortnox_client_or_raise` (5)
- Customer lookup (9)
- Customer create (8)
- Invoice lookup (10)

**1780/1780 tests pass** (excluding 1 pre-existing env-dependent failure in `test_admin_auth` that fails when `ADMIN_API_KEY` is set in `.env`).

## Completed slice (2026-04-27 — Slice 20: UI Role Separation + Fix Tenant Open)

### Root cause of openTenant bug
`openTenant()` called `switchView('setup')` which synchronously triggered `loadSetup()`. `loadSetup()` reads `_activeTenantId` at that moment (still the admin's own tenant), loads the wrong tenant's config, then the `.then()` callback ran `switchTenant()` against the correct tenant — but only after `loadSetup()` had already rendered the wrong data. Race between switchView auto-load and the explicit tenant override.

### Fix
`openTenant(tenantId)` now pre-sets `_activeTenantId = tenantId` before calling `switchView('setup')`, so when `loadSetup()` runs it picks up the correct tenant ID. The dropdown is synced via `loadTenants()` after.

### Role separation
- `_uiMode`: `'admin'` | `'customer'`, stored in `localStorage` as `ui_role_mode`
- Admin mode: all tabs visible (purple-tinted admin-only tabs)
- Customer mode: only Dashboard + Ärenden visible; admin-only tabs hidden
- Role badge in header (purple for admin, teal for customer); click to toggle
- Switching to customer mode while on admin-only view auto-redirects to Dashboard
- `openTenant()` switches back to admin mode automatically
- Default view on boot: ops for admin, dash for customer

### Nav improvements
- Bottom-border underline indicator (3px) replaces border-right separator
- Admin-only tabs styled in purple to distinguish from customer tabs
- Hover states improved; tabs no longer have right-border dividers

### Files changed
- `app/ui/index.html` — role state, `_applyRoleMode()`, `toggleRole()`, `switchView()` refactored, `openTenant()` fixed, nav CSS updated, header role badge, init boot logic

### Tests
No backend changes. 1780/1780 tests pass (same as before).
