# Backlog

## Done (schema and table bootstrap hardening — 2026-04-09)
- [x] `JobListResponse` redefined as `{items, total}` to match main.py return shape
- [x] `main.py` Base import changed from `base.Base` (empty) to `database.Base` (all models) — all tables now created on startup

## Done (read endpoint hardening — 2026-04-09)
- [x] Root-cause all 500s on read endpoints: six missing repository alias methods
- [x] Add `JobRepository.list_jobs` / `count_jobs`
- [x] Add `AuditRepository.list_events` / `count_events`
- [x] Add `IntegrationRepository.list_events` / `count_events` (static)
- [x] Add `tests/test_repository_aliases.py` (10 tests); 46/46 pass

## Done (MVP flow slice — 2026-04-09)
- [x] Trace official lead flow end-to-end
- [x] Patch: remove asyncio.run() wrapping synchronous run_pipeline (main.py)
- [x] Patch: fix send_email to use IntegrationType.GOOGLE_MAIL not missing EMAIL
- [x] Patch: is_integration_configured now recognises token-based integrations
- [x] Fix: remove duplicate assertion block in test_invoice_duplicate_detection
- [x] Add tests/test_mvp_flow.py (23 tests, 36/36 total pass)
- [x] Update docs/05-current-state.md and docs/08-handoff.md

## Done (action error handling hardening — 2026-04-09)
- [x] `action_dispatch_processor`: result `status="failed"` when any action fails; audit event emitted with error detail
- [x] `orchestrator._finalize_success`: routes to `FAILED` (not `MANUAL_REVIEW`) when `failed_count > 0` in action_dispatch payload
- [x] `get_db`: added `except: db.rollback(); raise` for defensive session handling
- [x] `tests/test_action_failure.py` (11 tests); 68/68 pass

## Done (thin operator/admin UI — 2026-04-10)
- [x] `app/ui/index.html` — single-file UI, no build toolchain
- [x] `GET /ui` route in `app/main.py` — serves HTML directly via FastAPI
- [x] Jobs list, job detail (approvals + actions), pending approvals tab
- [x] Approve/Reject buttons call existing endpoints; UI refreshes after decision
- [x] `X-Tenant-ID` sent on every request via editable tenant field
- [x] 74/74 tests pass; no backend business logic changed (DEC-003)

## Done (operability and docs hardening — 2026-04-10)
- [x] `requirements.txt` created with all pinned runtime + test dependencies
- [x] `docker-compose.yml` written — Postgres 15, port 5432, correct DB name
- [x] `env.example` created — full template with all env vars documented
- [x] `scripts/create_tables.py` fixed — imports all four model modules; all tables confirmed via output
- [x] README fully rewritten — setup, DB verification, full curl smoke test, Gmail notes, API table, limitations
- [x] `force_approval_test` flag documented as the official golden-path trigger
- [x] 74/74 tests pass; no code logic changed

## Done (auth / API key enforcement — 2026-04-11)
- [x] `app/core/auth.py` — `get_verified_tenant` dependency; key map loaded from `TENANT_API_KEYS` env var
- [x] All protected endpoints use `Depends(get_verified_tenant)`; `X-Tenant-ID` no longer trusted directly
- [x] Auth disabled (empty `TENANT_API_KEYS`) → dev mode with warning; auth enabled → 401/403 on bad keys
- [x] `tests/test_auth.py` (14 tests); 88/88 pass
- [x] `env.example`, README, and docs updated

## Done (UI auth alignment — 2026-04-11)
- [x] `app/ui/index.html` — API key input replaces tenant ID input
- [x] All fetch calls send `X-API-Key`; key persisted to `localStorage`
- [x] Warning banner when no key set; auto-load skipped on fresh open without key
- [x] 88/88 tests pass; no backend changes

## Next (priority order)
- [ ] **DB-driven tenant config** — move hardcoded tenant config from code to `tenant_config` DB table
- [ ] **Integration event persistence** — persist results from `/integrations/{type}/execute` to `integration_events` table
- [ ] **Gmail OAuth refresh** — build token refresh flow so Gmail integration stays live

## Future UI improvements (out of current scope)
- [ ] Authentication — API key or session-based, gating the `/ui` route
- [ ] Filtering and search — filter jobs by status, type, date range
- [ ] Pagination controls — currently UI fetches first 100; add next/prev
- [ ] Audit log view — surface `GET /audit-events` in the UI
- [ ] Retries / re-run — trigger re-processing of failed jobs
- [ ] Notifications — surface action failures inline without manual refresh
- [ ] Improved UX — replace inline HTML/CSS with a proper component approach if scope grows

## Known risks
- `app/api/routes/jobs.py` is dead code (not mounted in main.py) — remove or wire up
- No DB migration tooling yet (tables created via SQLAlchemy `create_all` on startup)
- Gmail token is short-lived; onboarding flow for OAuth refresh not built
