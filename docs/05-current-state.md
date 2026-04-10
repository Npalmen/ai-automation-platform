# Current State

## Status summary
Projektet har passerat konceptstadiet och har en fungerande backend-kärna med riktig exekveringsförmåga.

## Confirmed implemented
- [x] FastAPI API
- [x] PostgreSQL persistence
- [x] SQLAlchemy repository layer
- [x] Multi-tenant tenant-context via `X-Tenant-ID`
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
- [x] All fetches send `X-Tenant-ID` from an editable tenant input field
- [x] Approve/Reject POSTs to existing endpoints; UI refreshes after decision
- [x] No React, no Vite, no separate frontend toolchain — pure HTML/CSS/JS inline
- [x] 74/74 tests still pass

**UI limitations (by design — out of MVP scope):**
- No authentication — tenant ID is entered manually and not validated
- No pagination controls — UI fetches first 100 jobs/approvals; backend supports pagination
- No filtering or search
- No audit log view in the UI (data exists in API at `GET /audit-events`)
- No job creation form
- No retries or advanced action controls
- No auto-refresh — operator triggers all loads manually

## Partially implemented / needs hardening
- [ ] DB-driven tenant config
- [ ] Auth / API keys / roller
- [ ] Riktig integration event persistence för direkta integrationstest-endpoints
- [ ] Kundonboarding för Gmail, Visma, Monday och Slack
- [ ] End-to-end integration test with real DB

## Known risks
- Dokumentationen är idag splittrad över flera filer
- Huvudplan riskerar att drifta mellan chattar om docs inte konsolideras
- Frontend saknas eller är inte officiellt etablerad som MVP-del
- Vissa integrationsspår finns i arkitekturen men ska inte tolkas som produktionklara