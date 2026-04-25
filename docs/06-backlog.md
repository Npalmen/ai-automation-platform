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

## Done (DB-driven tenant config — 2026-04-12)
- [x] `app/repositories/postgres/tenant_config_models.py` — `TenantConfigRecord` SQLAlchemy model (`tenant_configs` table)
- [x] `app/repositories/postgres/tenant_config_repository.py` — `TenantConfigRepository.get`, `upsert`, `to_dict`
- [x] `app/core/config.py` — `get_tenant_config(tenant_id, db=None)` reads from DB when `db` provided; falls back to `TENANT_CONFIGS` when no row or DB unavailable
- [x] `app/main.py` `/tenant` endpoint — passes `db` session to `get_tenant_config`; now returns DB row when present
- [x] `app/repositories/postgres/__init__.py` — `TenantConfigRecord` imported so `create_all` creates the table
- [x] `scripts/create_tables.py` — `tenant_config_models` import added
- [x] `tests/test_tenant_config.py` — 17 new tests; 105/105 pass
- [x] No change to policy logic, API contract, or existing test flows

## Done (integration event persistence — 2026-04-12)
- [x] `app/domain/integrations/models.py` — `IntegrationEvent` base changed from `base.Base` (orphaned) to `database.Base`; table now included in `create_all`
- [x] `app/repositories/postgres/__init__.py` — side-effect import of `app.domain.integrations.models` registers table with shared metadata
- [x] `scripts/create_tables.py` — `integration_models` import added
- [x] `app/main.py` `POST /integrations/{type}/execute` — synthetic dict replaced with real `IntegrationEvent` record persisted via `IntegrationRepository.create`; response built from saved record via `model_validate`
- [x] `tests/test_integration_event_persistence.py` — 11 new tests; 122/122 pass

## Done (Gmail OAuth token refresh — 2026-04-12)
- [x] `app/core/settings.py` — `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` settings added
- [x] `app/integrations/service.py` — refresh credentials included in `GOOGLE_MAIL` connection config
- [x] `app/integrations/google/mail_client.py` — `refresh_access_token()` function; `GoogleMailClient` accepts refresh credentials; on 401, refreshes token and retries once; 403 is not retried
- [x] `app/integrations/google/adapter.py` — refresh credentials threaded from `connection_config` to `GoogleMailClient`
- [x] `env.example` — `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` documented
- [x] `tests/test_gmail_oauth_refresh.py` — 19 new tests; 141/141 pass

## Done (sellable MVP intake flows — 2026-04-23)

### DEL 1: Customer inquiry flow
- [x] `_build_inquiry_default_actions(job)` — `create_monday_item` + `send_email` to support
- [x] `normalize_sender()`, `extract_phone()`, `classify_inquiry_priority()` shared helpers
- [x] HIGH/NORMAL priority surfaced in item name, email subject, column_values, body
- [x] `tests/test_inquiry_default_actions.py` — 76 tests

### DEL 2: Invoice flow
- [x] `_INVOICE_KEYWORDS` + `classify_email_type()` public function — invoice > lead > customer_inquiry
- [x] `_build_invoice_default_actions(job)` — `create_monday_item` + `create_internal_task`
- [x] `extract_invoice_amount`, `extract_invoice_number`, `extract_due_date`, `extract_invoice_data`
- [x] Extraction wired into invoice default actions (amount, invoice_number, due_date, supplier_name, raw_text)
- [x] `tests/test_invoice_default_actions.py` — 32 tests; `tests/test_invoice_extraction.py` — 47 tests

### Inbox type inference
- [x] `/gmail/process-inbox` infers `job_type` from message content via `classify_email_type`
- [x] Per-type tenant gate — skips with `"{type}_disabled"` if not enabled
- [x] Job created with inferred `JobType`; no hardcoded `actions` in `input_data`
- [x] `tests/test_gmail_tenant_config_gate.py` — rewritten (17 tests)

**702/702 tests pass. Sellable MVP complete.**

## Done (follow-up question engine — 2026-04-24)
- [x] `evaluate_information_completeness(job_type, input_data)` — deterministic completeness check for lead, customer_inquiry, invoice
- [x] `_build_lead_default_actions(job)` — new first-class builder (previously fell through to generic fallback)
- [x] `_build_follow_up_email(sender_email, questions)` — follow-up `send_email` using existing action type; no new integration
- [x] `_build_inquiry_default_actions` + `_build_invoice_default_actions` updated: completeness fields in column_values and task metadata
- [x] Explicit `input_data.actions` still overrides defaults (override behavior preserved)
- [x] `tests/test_followup_engine.py` — 23 tests; `tests/test_inquiry_default_actions.py` fix (1 test)
- [x] 725/725 tests pass

## Done (Customer Auto-Reply + Internal Handoff — 2026-04-25)
- [x] `send_customer_auto_reply` + `send_internal_handoff` injected for lead + inquiry fallback pipelines
- [x] Gated by `followups_enabled` + presence of customer email; skipped conditions produce `_skip` sentinel
- [x] `skipped_actions` / `skipped_count` in dispatch result payload
- [x] UI action label map: Kundsvar / Intern notifiering / Monday-objekt / Slack-notis / etc.
- [x] `tests/test_auto_reply_handoff.py` — 22 tests; 1022/1022 pass

## Done (Classification v2 / Better Inbox Taxonomy — 2026-04-25)
- [x] 9-type taxonomy: lead, customer_inquiry, invoice, partnership, supplier, newsletter, internal, spam, unknown
- [x] Priority order (deterministic): spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry
- [x] Visibility-only types (partnership/supplier/newsletter/internal/spam): only skipped sentinels — no customer emails
- [x] `AllowedJobType` extended in AI schema; 5 new `JobType` enum values
- [x] Swedish labels in UI `JOB_TYPE_LABELS` + `CASE_TYPE_LABELS`
- [x] `tests/test_classification_v2.py` — 52 new tests; 1074/1074 pass

## Done (Cases UX Upgrade — 2026-04-25)
- [x] `GET /cases`: q (ILIKE search on job_id + input_data), type, status, sort_by, sort_dir, limit, offset
- [x] Response includes: received_at, processed_at, customer_email, limit, offset
- [x] `received_at` stored in `input_data` during Gmail inbox ingestion (from Gmail Date header)
- [x] `GET /cases/{job_id}` includes received_at + processed_at
- [x] Ärenden tab UI: search/filter/sort/pagination controls; Swedish labels; received_at as primary timestamp
- [x] 33 new tests in test_cases.py; 1107/1107 pass

## Next (priority order)
- [ ] Monday Routing v2 — DEFERRED; per-job-type Monday board/group routing based on tenant config; deprioritized in favour of pipeline polish
- [ ] Dashboard polish — date-range filters, charts, auto-refresh interval
- [ ] Scheduler / cron trigger — external periodic call to `POST /scheduler/run-once`

## Future UI improvements (out of current scope)
- [ ] Audit log view — surface `GET /audit-events` in the UI
- [ ] Retries / re-run — trigger re-processing of failed jobs
- [ ] Notifications — surface action failures inline without manual refresh

## Known risks
- `app/api/routes/jobs.py` is dead code (not mounted in main.py) — remove or wire up
- No DB migration tooling yet (tables created via SQLAlchemy `create_all` on startup)
- Gmail token is short-lived; onboarding flow for OAuth refresh not built
- `create_internal_task` is stubbed — no persistence beyond the job result payload
