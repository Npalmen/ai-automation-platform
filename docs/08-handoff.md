# Handoff

## Project
AI Automation Platform — multi-tenant backend-first plattform för AI-driven workflow automation.

## Current objective
Konsolidera dokumentationen och lås officiell MVP-riktning.
Nästa tekniska slice är att verifiera ett officiellt end-to-end backend-flöde:
lead intake → classification → entity extraction → decisioning → policy → approval/resume → Gmail action → audit visibility.

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
All core MVP slices are complete. Auth is enforced end-to-end. UI is stable, Swedish-localised, and polished. Tenants can be created via `POST /tenant` or the Inställningar tab. Active tenant is selected from a dropdown of real DB tenants — no free-text entry, no misleading fallback behaviour. Setup tab shows readiness status and a one-click verification test. 188/188 tests pass.

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

## How to use the Inställningar (Setup) tab
1. Open `http://localhost:8000/ui`
2. Click **Inställningar** in the top navigation
3. **Byt tenant:** enter a tenant ID in the switcher at the top and click "Ladda tenant" — config reloads for that tenant without a page refresh
4. **Skapa tenant:** fill in Tenant-ID + Namn in the creation form and click "Skapa tenant"
5. The **Konfigurationsstatus** panel shows readiness at a glance (job types, integrations, auto-actions)
6. Toggle job types, integrations, and auto-action settings
7. Click **Spara konfiguration** — persists to the `tenant_configs` DB table and reloads
8. Click **Kör verifieringstest** — submits a minimal `customer_inquiry` job and shows the result inline (no external credentials required)

## Remaining work
All original MVP backlog items are complete. The platform is in a stable, demonstrable state.

## Expected output from next implementation chat
- Pick one remaining work item above
- Continue from this repo state; README, all docs, and 88 tests are current
- Suggested next: DB-driven tenant config (removes last hardcoded config from code)