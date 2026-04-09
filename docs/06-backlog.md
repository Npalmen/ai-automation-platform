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

## Next (priority order)
- [ ] **Smoke test with real DB** — run full lead flow with `force_approval_test=true`, approve via API, verify Gmail `send_email` actually fires (requires `.env` with Google credentials)
- [ ] **Operator/admin UI** — thin read-only dashboard: job list, approval queue, audit log (DEC-003)
- [ ] **Auth / API keys** — per-tenant API key validation on all endpoints
- [ ] **DB-driven tenant config** — move hardcoded tenant config from env to `tenant_config` DB table
- [ ] **Integration event persistence** — persist results from `/integrations/{type}/execute` to `integration_events` table

## Known risks
- `app/api/routes/jobs.py` is dead code (not mounted in main.py) — remove or wire up
- No DB migration tooling yet (tables created via SQLAlchemy `create_all` on startup)
- Gmail token is short-lived; onboarding flow for OAuth refresh not built
