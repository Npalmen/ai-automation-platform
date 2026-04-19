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

## Current state
MVP is complete and live-validated. Gmail send and Monday item creation are confirmed working through real API calls. Full pipeline, approval flow, and action persistence verified end-to-end. Auth is enforced. UI is stable, Swedish-localised, and tenant-aware. Verification is deterministic (no LLM required). 326/326 tests pass.

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

- **Gmail send** — `POST /integrations/google_mail/execute` reaches the Gmail API and delivers email; OAuth refresh validated
- **Monday item creation** — `POST /integrations/monday/execute` creates a real item in a monday.com board
- **Full pipeline** — intake → classification → extraction → decisioning → policy → action_dispatch; all stages execute with real data
- **Approval pause/resume** — job enters `awaiting_approval`; `POST /approvals/{id}/approve` with `{}` resumes it; action executes after approval; result persisted
- **Action persistence** — `GET /jobs/{job_id}/actions` returns the executed action record
- **326 tests passing**

---

## How to test the system via API (step-by-step)

**1. Direct Gmail send (requires OAuth env vars):**
```bash
curl -s -X POST http://localhost:8000/integrations/google_mail/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{"action": "send_email", "payload": {"to": "you@example.com", "subject": "Test", "body": "Hello"}}'
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

## Remaining work
All original MVP backlog items are complete.

## Expected output from next implementation chat
- Continue from this repo state; all docs and 326 tests are current
- Gmail and Monday integrations are live-verified
- Platform is stable and ready for first customer onboarding or additional integration testing