# Current Truth

> **This file contains verified repository truth. It must not contain vision or plans.**
> If something is unverified, it is marked `Unverified`.
> The governing source for product direction is `docs/00-master-plan.md`.

---

## Last verified date

2026-07-21 (Slice A integration selection — canonical on `main` commit `7c511ee`; pilot RC `krowolf-app:rc-7c511eeb0719`; tenant `T_NIKLAS_DEMO_001`; Gmail soak not resumed.)

2026-07-21 (Slice B partial — branch `feature/integration-selection-slice-b`: backend kernel + Niklas gate PASS; onboarding `IntegrationsStepPanel` tri-state per integration with category groups; `selections` draft/PATCH; selection-aware `evaluate_integrations_step`; registry API exposes `category` / `alternatives_group` / `support_status`. Deploy + merge pending.)

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
| Integration selection Slice A (tenant health gating) | `Verified — local + pilot` | Canonical keys (`google_mail` + legacy `gmail` alias at ingest); `selection_resolver` derives `not_selected` / `selected_optional` / `selected_required` / `migration_review_required` from credentials + `allowed_integrations` (no migration 015). Unselected integrations → `not_applicable` tenant health; no triage/alert/customer-detail warning. Platform capabilities (e.g. Fortnox) separated from tenant warnings. Alert suppression reason: `integration_not_selected_after_selection_model_migration`. **Canonical `main` `7c511ee`** (cherry-pick from `a99c33c`); pilot RC `krowolf-app:rc-7c511eeb0719`. Tests: parity + health + tenant_directory + super_admin — 144 passed (2026-07-21). Post-deploy: Fortnox `not_selected`/warning absent; Gmail test-read PASS; Visma unchanged; scheduler paused; jobs=0; approvals=0. |
| Test suite runs | `Verified` | 3265 passed, 0 failed (run 2026-07-16; includes Visma write-safety + R1 release gate) |
| Test count: 3265 tests | `Verified` | Run 2026-07-16 after Visma Chapter 3 regression |
| Internal demo rehearsal | `Verified — production` | Read-only walkthrough 2026-07-16 on `T_NIKLAS_DEMO_001`; no Visma writes; see `docs/PILOT_TRANSITION.md` Part A |
| Pilot transition pack | `Verified (docs)` | Scope, onboarding, operations, metrics, commercial draft in `docs/PILOT_TRANSITION.md` |
| Visma write safety | `Verified` | `test_visma_write_safety.py` + `test_visma_oauth.py` + `test_migrate_visma_oauth_credential.py` — 64 passed (2026-07-16) |
| Gmail manual-review handoff | `Verified (local)` | `app/workflows/manual_review_handoff.py` — UNREAD + `krowolf-manual-review` label on `manual_review`; queue at `/manual-review/jobs`; resolve via `POST .../resolve`; daily report `unresolved_manual_review`. 15 tests pass. Production backfill: `POST .../reconcile-gmail` on existing demo jobs. |
| Tenant Google Mail OAuth (operator panel) | `Verified (local + pilot)` | Signed single-use state (`integration_oauth_states`, 15 min TTL); admin connect; callback DB routing fix (`oauth_state_resolver`); tenant credential in `oauth_credentials`; auto refresh via `oauth_token_resolver`; legacy `/oauth/start` returns 410. **Pilot `T_NIKLAS_DEMO_001` live connect verified 2026-07-19** (`credential_source=tenant_oauth`, test-read + refresh + dry-run PASS). 7-day soak started (`docs/niklas-gmail-soak-log.md`). Stored Google grant may include legacy `gmail.send` + `spreadsheets` — Krowolf uses only `readonly` + `modify` during soak. |
| Internal handoff post-approval state | `Verified (local)` | `app/workflows/email_approval_resolution.py` — after final `email_send` approval resolves, job clears stale `awaiting_approval`/pending counts, records action execution, sets `completed` with `customer_case_open=true` for successful `send_internal_handoff`. 12 tests in `tests/test_internal_handoff_completion.py`. |
| Dashboard `ready_cases` | `Verified (local)` | Uses `ApprovalRequestRepository.count_pending_for_tenant` (same source as `/approvals/pending`), not `jobs.status=awaiting_approval`. |
| Daily summary `internal_handoffs_sent` | `Verified (local)` | Counts distinct successful `send_internal_handoff` action executions in report window; Swedish line when > 0. |
| Approval via Gmail reply | `Unverified — deferred` | `approval_command_parser.py` parses GODKÄNN/STOPPA/ÄNDRA; not wired to Gmail intake; no approval-request email with embedded reference sent today. |
| Sprint 4: AI Receptionist test-customer onboarding package | `Added 2026-07-15` | `docs/ai-receptionist-test-customer-onboarding.md`, `docs/ai-receptionist-test-mail-scenarios.md`, `docs/ai-receptionist-mvp-gate.md`, `docs/ai-receptionist-friend-test-guide.md`, `scripts/print_ai_receptionist_test_setup.py` |
| Sprint 3: Google Sheets manual export endpoint | `Verified — ADDED 2026-07-14` | `POST /integrations/google-sheets/export-job`; gated by `allowed_integrations` + `spreadsheet_id`; fail-closed; audit+integration events; append-only Leads/Support tabs |
| Sprint 3: Google Sheets Sammanfattning | `Verified (local + production config)` | Replace-range current-state summary tab; Support free-text limitation may still apply for some fields |
| Sprint 3: Google Sheets adapter + mock | `Verified — ADDED 2026-07-14` | `GoogleSheetsClient` (real, Sheets v4 REST) and `MockGoogleSheetsClient` (in-memory, for tests) in `app/integrations/google/sheets_client.py` |
| Sprint 3: Row mapper (Leads/Support/Logg) | `Verified — ADDED 2026-07-14` | `app/integrations/google/sheets_row_mapper.py`; Leads=12 cols, Support=12 cols, Logg=6 cols; extracts sender, processor history, status, source |
| Sprint 3: No auto-export from Gmail pipeline | `Verified — CONFIRMED 2026-07-14` | gmail_adapter, lead_analyzer_processor, action_dispatch_processor, support_analyzer_processor contain no `google_sheets`/`append_row` references |
| Sprint 1: nested tenant settings persist via deep-merge | `Verified — FIXED 2026-07-12` | `TenantConfigRepository.update_settings` uses `copy.deepcopy` + `flag_modified`; `tests/test_tenant_settings_persistence.py` |
| Sprint 1: email `auto_actions=semi` requires approval | `Verified — FIXED 2026-07-12` | `_email_needs_approval` fail-closed; only `True`/`auto`/`full_auto` bypass; `tests/test_email_approval.py` |
| Sprint 1: integration dispatch checks `allowed_integrations` | `Verified — FIXED 2026-07-12` | `action_executor.execute_action` skips with `integration_not_allowed`; `tests/test_integration_action_gating.py` |
| Sprint 1: jobs expose pending approval state | `Verified — FIXED 2026-07-12` | Orchestrator + `JobResponse` fields `has_pending_approvals` / `pending_approvals_count`; `tests/test_job_pending_approval_visibility.py` |
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
| Tenant routing hints override service profile route | `Verified` | `apply_tenant_overrides()` reads merged hints: `internal_routing_hints` first, then legacy string values in `routing_hints`; dict dispatch values ignored for profile routing. |
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

### Sprint 5 — Phase 1 value layer (2026-07-15)

| Item | Status | Notes |
|------|--------|-------|
| `OfferDraft` enriched with contact + approval fields | `Verified` | `app/lead/models.py` + `app/lead/offer_draft.py`. Adds `customer_name`, `customer_email`, `customer_phone`, `address`, `missing_fields`, `human_approval_required=True` |
| `_infer_lead_status` corrected | `Verified` | `lead_analyzer_processor.py`. `ask_questions` → `waiting_for_customer`; `create_offer_draft` → `quote_draft_prepared` |
| `LeadStatus` extended | `Verified` | `app/lead/models.py`. Added `quote_draft_prepared` literal |
| Invoice routing classifier | `Verified` | `app/invoice/routing.py`. Deterministic keyword detection for `debt_collection_review`, `payment_reminder_review`, `manual_review_required`, `forward_to_accounting`, `ignore_not_invoice` |
| `invoice_processor` wired to routing | `Verified` | `invoice_routing`, `risk_signals`, `routing_reason` added to processor payload |
| Derived status helper | `Verified` | `app/workflows/derived_status.py`. Pure `derive_job_status(job)` reads processor history; returns one of 7 derived statuses |
| Daily report generator | `Verified` | `app/reporting/daily_report.py`. `generate_daily_report(db, tenant_id, since_hours=24)` returns counts + top_priorities + rendered Swedish text |
| `GET /reports/daily-summary` endpoint | `Verified` | Tenant-scoped, `since_hours` param, uses `generate_daily_report` |
| Approval command parser | `Verified` | `app/workflows/approval_command_parser.py`. `parse_approval_command(body)`. Supports GODKÄNN/APPROVE, STOPPA/REJECT, ÄNDRA/CHANGE. Fail-closed |
| 25 Sprint 5 unit tests | `Verified` | `tests/test_sprint5_phase1_value.py` — 25 passed, 0 failed |

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
| Server deployment at `api.krowolf.se` | `Verified — Phase A-C PASS` | 2026-07-07 production deploy completed on `/opt/krowolf`, live commit `87d9369`, using `/opt/krowolf/docker-compose.prod.yml`; app/db/caddy containers running. Phase D and full live verification not run. |
| Local start via `uvicorn app.main:app --reload` | `Verified (code)` | Startup sequence present in `app/main.py` |
| Docker Compose (Postgres only) | `Verified (code)` | `docker-compose.yml` + `docker-compose.prod.yml` + `Dockerfile` all present |
| `ENV=production` disables public docs and dev fallback | `Verified (code)` | `_is_production_env()` and `_openapi_urls_for()` in `main.py` |
| `.env` file present | `Verified` | `.env` exists in repo root |

### Controlled live verification Phase A-C (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| Phase A — Pre-flight | `Verified — PASS` | Production deploy completed from `/opt/krowolf`; live commit `87d9369`; Docker Compose file `/opt/krowolf/docker-compose.prod.yml`; containers `krowolf-app-1`, `krowolf-db-1`, and `krowolf-caddy-1` running. |
| Full local test suite | `Verified — PASS` | `python -m pytest --tb=no -q` — 2744 passed, 0 failed, 4 warnings. |
| R1 release gate | `Verified — PASS` | `python -m scripts.run_release_gate_r1` — 505 regression + 152 E2E passed. |
| Live root health | `Verified — PASS` | `GET https://api.krowolf.se/` returned HTTP 200 and `{"status":"ok","app_name":"Krowolf","env":"production"}`. |
| Live `/health` route | `Verified — PASS` | `GET https://api.krowolf.se/health` returned HTTP 200 and `{"status":"ok","app_name":"Krowolf","env":"production"}` after production deploy. |
| Production docs disabled | `Verified — PASS` | `GET /docs` and `GET /openapi.json` both returned HTTP 404. |
| Admin endpoint without key | `Verified — PASS` | `GET /admin/tenants` returned HTTP 401. |
| Admin endpoint with wrong key | `Verified — PASS` | `GET /admin/tenants` with `X-Admin-API-Key: wrong-key` returned HTTP 401. |
| Admin endpoint with correct key | `Verified — PASS` | `GET /admin/tenants` with correct `X-Admin-API-Key` returned HTTP 200 and existing tenants `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1`. |
| Tenant key against admin endpoint | `Deferred` | No tenant key exists yet; deferred to Phase D/E. |
| Server/deploy env inspection | `Partially verified` | Server path, compose file, live commit, and running app/db/caddy containers confirmed. Secret values were not recorded. |
| Live verification overall | `Not completed` | Phase A-C, D, E, F, G, H, I, and J passed. Phase K BLOCKED (Gmail invalid_grant). Full live verification not complete. |

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
| `/health` returned HTTP 404 on production | `Fixed and verified live` | Added unauthenticated `GET /health` with public payload only: `status`, `app_name`, `env`; production now returns HTTP 200 after deploy. |
| `/health` tests | `Verified — PASS` | `tests/test_root_routing.py` now verifies HTTP 200, public fields, and no secret-like keys. |
| Production docs disablement regression | `Verified — PASS` | Existing docs disablement tests still pass. |
| Dirty `app/ui/index.html` | `Resolved intentionally — deployed` | Previous fancy CSS/card-contrast dirty state was replaced with minimal Internal Operator Console styling, included in live commit `87d9369`, and deployed with the Phase A-C checkpoint. Existing functional HTML/JS operator flows were preserved; static structure check passed. |
| Correct admin-key success path | `Verified — PASS` | Read-only `GET /admin/tenants` with correct key returned HTTP 200. Key was not recorded. |
| Operator confirmations | `Verified — Phase D complete` | Live commit `87d9369`, compose path, running app/db/caddy containers confirmed. DB backup (`pre-phase-d-20260707-190618.sql`, 677 KB) taken before Phase D. Phase D tenant provisioning passed. |

### Phase D — Tenant provisioning (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| DB backup taken before Phase D | `Verified — PASS` | `backups/pre-phase-d-20260707-190618.sql` (677 KB). Automated daily backups also present through `ai_platform_2026-07-07-0200.sql.gz`. |
| Admin access pre-Phase D | `Verified — PASS` | `GET /admin/tenants` with admin key returned HTTP 200. |
| Existing tenants untouched | `Verified — PASS` | `T_ELITGRUPPEN` (active), `TENANT_2001` (active), `T_TEST1` (active) — none modified. |
| `T_LIVE_TEST_001` pre-existing check | `Verified` | Tenant did not exist before Phase D. |
| Create `T_LIVE_TEST_001` | `Verified — PASS` | `POST /admin/tenants` returned HTTP 201. `tenant_id: T_LIVE_TEST_001`, `name: Live Test Tenant`, `slug: live-test-001`, `status: active`. API key shown once (masked, length 35) and not recorded. |
| `T_LIVE_TEST_001` appears in admin list | `Verified — PASS` | `GET /admin/tenants` after creation listed `T_LIVE_TEST_001` correctly. |
| Key rotation | `Verified — PASS` | `POST /admin/tenants/T_LIVE_TEST_001/rotate-key` returned HTTP 200; fresh key obtained (length 35). Used for tenant verification and cleared immediately after. |
| `GET /tenant` with tenant key | `Verified — PASS` | HTTP 200; endpoint accessible with `T_LIVE_TEST_001` key. |
| `GET /pilot/readiness` with tenant key | `Verified — PASS` | `overall_status: almost_ready`; 6 passed, 5 warnings, 0 failures — expected for new tenant without integrations. |
| `GET /integrations/health` with tenant key | `Verified — PASS` | `overall_status: warning`; no secrets in response body. |
| Tenant key rejected on admin endpoint | `Verified — PASS` | `GET /admin/tenants` with `T_LIVE_TEST_001` tenant key returned HTTP 401 — isolation confirmed. |
| T_ELITGRUPPEN data not visible to T_LIVE_TEST_001 | `Verified — PASS` | `GET /jobs` with `T_LIVE_TEST_001` key returned empty list; no cross-tenant data. |
| Secrets handled | `Verified` | Admin key never recorded. Tenant key used in-memory on server only; cleared with `unset` after each check. Temp scripts removed from server. |
| Phase D overall | `Verified — PASS` | All D-checks passed 2026-07-07. |

### Phase E — Tenant/customer endpoint isolation and readiness (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| Preconditions | `Verified` | Phase A-D confirmed passed; `T_LIVE_TEST_001` confirmed active; key rotated fresh for Phase E. |
| E1 `/tenant` with key | `Verified — PASS` | HTTP 200; no secrets in body; no cross-tenant data. |
| E1b `/tenant` without key | `Verified — PASS` | HTTP 401. |
| E2a `/customer/health` with key | `Verified — PASS` | HTTP 200; no secrets; no cross-tenant data. |
| E2b `/customer/health` without key | `Verified — PASS` | HTTP 401. |
| E2c `/customer/results` with key | `Verified — PASS` | HTTP 200; no secrets; no cross-tenant data. |
| E2d `/customer/activity` with key | `Verified — PASS` | HTTP 200; no secrets; no cross-tenant data. |
| E2e `/customer/account` with key | `Verified — PASS` | HTTP 200; no secrets; no cross-tenant data. |
| E3 `/pilot/readiness` with key | `Verified — PASS` | HTTP 200; `almost_ready`; no secrets. |
| E4a `/integrations/health` with key | `Verified — PASS` | HTTP 200; `overall_status: warning`; no secrets in body. |
| E4b `/integrations/health` without key | `Verified — PASS` | HTTP 401. |
| E5a `/jobs` with key | `Verified — PASS` | HTTP 200; empty list; no cross-tenant data. |
| E5b `/jobs` without key | `Verified — PASS` | HTTP 401. |
| E6a `/audit-events` with key | `Verified — PASS` | HTTP 200; no cross-tenant data. |
| E6b `/audit-events` without key | `Verified — PASS` | HTTP 401. |
| E6c `/integration-events` with key | `Verified — PASS` | HTTP 200; no cross-tenant data. |
| E6d `/integration-events` without key | `Verified — PASS` | HTTP 401. |
| E7a `/tenant/context` with key | `Verified — PASS` | HTTP 200; no secrets; no cross-tenant data. |
| E7b `/tenant/context` without key | `Verified — PASS` | HTTP 401. |
| E7c `/tenant/memory` with key | `Verified — PASS` | HTTP 200; no secrets; no cross-tenant data. |
| E7d `/tenant/memory` without key | `Verified — PASS` | HTTP 401. |
| E8a `X-Tenant-ID: T_ELITGRUPPEN` with `T_LIVE_TEST_001` key | `Verified — PASS (design)` | HTTP 200. Correct behavior: `X-Tenant-ID` header is ignored when `TENANT_API_KEYS` is configured; tenant resolves from key only. Response was scoped to `T_LIVE_TEST_001`, not `T_ELITGRUPPEN`. |
| E8b Admin key on `/jobs` | `Verified — PASS` | HTTP 403; admin key correctly rejected as tenant key. |
| E8c Tenant key on `/admin/tenants` | `Verified — PASS` | HTTP 401; tenant key correctly rejected on admin endpoint. |
| Logs review | `Verified — PASS` | No 500s, no stack traces, no leaked secrets, no cross-tenant SQL queries. SQL echo verbose (logged clean hashed key values only — non-blocking cleanup item). |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory on server only; cleared with `unset`; temp script removed. |
| Phase E overall | `Verified — PASS` | All E-checks passed 2026-07-07. |

### Phase F — Safe synthetic intake/job flow (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| F1: Tenant safety config | `Verified — PASS` | `T_LIVE_TEST_001` active; `auto_actions: {lead: false, customer_inquiry: false, invoice: false}`; no integrations configured for external writes. |
| F2: Create synthetic lead job | `Verified — PASS` | `POST /jobs` returned HTTP 200; `job_id: bea23f74-1dbe-4424-a8cb-60262da92f9b`; `tenant_id: T_LIVE_TEST_001`; `job_type: lead`; no secrets in response. |
| F2: Pipeline completion | `Verified — PASS` | Job ran through full pipeline in-process; `status: completed`; `result.status: completed`; `result.summary: "Ingen manuell överlämning behövs."`; `requires_human_review: False`; 0 external actions dispatched. |
| F3: GET /jobs/:id | `Verified — PASS` | HTTP 200; `tenant_id: T_LIVE_TEST_001`; `job_type: lead`; `status: completed`; no secrets; no cross-tenant data. |
| F4: Jobs list isolation | `Verified — PASS` | HTTP 200; synthetic job listed; `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1` absent. |
| F5: Audit events | `Verified — PASS` | HTTP 200; no cross-tenant data; no external write audit events (no gmail send / monday write / fortnox export / visma write). |
| F5b: Integration events | `Verified — PASS` | HTTP 200; no external write events. |
| F6: No external writes | `Verified — PASS` | App logs reviewed: no Gmail send, no Monday write, no Fortnox/Visma events; no 500s or stack traces. |
| F7: GET /jobs/:id without key | `Verified — PASS` | HTTP 401. |
| F7b: Wrong tenant header on specific job | `Verified — PASS (design)` | HTTP 200 with `tenant_id: T_LIVE_TEST_001` — job correctly scoped to T_LIVE_TEST_001; `X-Tenant-ID` header ignored per auth design. |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory on server; cleared with `unset`; temp scripts removed. |
| Synthetic job left as evidence | `Intentional` | Synthetic job `bea23f74-1dbe-4424-a8cb-60262da92f9b` retained under `T_LIVE_TEST_001` as Phase F evidence. No delete action taken. |
| Phase F overall | `Verified — PASS` | 20/20 checks passed; 0 failures; 0 warnings. |

---


### Phase G — Approval queue / manual review (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| G1: Approval endpoints identified | `Verified — PASS` | `GET /approvals/pending`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`, `GET /jobs/{id}/approvals` — all tenant-scoped via `get_verified_tenant`; reject body `{actor?,channel?,note?}`; reject never sends email or dispatches externally. |
| G2: Create synthetic approval-trigger job | `Verified — PASS` | `POST /jobs` with `force_approval_test: true` + `job_type: customer_inquiry` → HTTP 200; `job_id: 8b2d53d2-cc44-4d45-a11b-5a4a60654bb0`; `status: awaiting_approval`; `tenant_id: T_LIVE_TEST_001`; no secrets in response. |
| G3: GET /jobs/:id | `Verified — PASS` | HTTP 200; `status: awaiting_approval`; `result.summary: "Approval dispatched via dashboard."`; scoped to T_LIVE_TEST_001; no secrets; no cross-tenant data. |
| G4: GET /approvals/pending | `Verified — PASS` | HTTP 200; 2 pending for T_LIVE_TEST_001; `approval_id: f5d27fc3-071c-41f0-ba65-c9f052f591b3`; `next_on_approve: action_dispatch`; no cross-tenant; no secrets. |
| G5a: /approvals/pending without key | `Verified — PASS` | HTTP 401. |
| G5b: X-Tenant-ID: T_ELITGRUPPEN + T_LIVE_TEST_001 key | `Verified — PASS (design)` | HTTP 200 scoped to T_LIVE_TEST_001 only; no T_ELITGRUPPEN data; header ignored per auth design. |
| G6: POST /approvals/:id/reject | `Verified — PASS` | HTTP 200; job status -> `manual_review`; no email/monday/fortnox markers; no external write executed. |
| G7: Approval no longer pending after reject | `Verified — PASS` | `f5d27fc3-...` removed from pending queue; other tenants absent. |
| G8a: /audit-events | `Verified — PASS` | HTTP 200; no cross-tenant data; no external write events. |
| G8b: /integration-events | `Verified — PASS` | HTTP 200; no external write events. |
| G9: App logs | `Verified — PASS` | `POST /approvals/.../reject 200 OK` confirmed; no 500s; no stack traces; no external writes. |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory on server; cleared with unset; temp scripts removed. |
| Cleanup note | `Non-blocking` | Phase F email_send approval (eml_adeaf87...) remains pending — consider rejecting via dashboard before pilot. |
| Phase G overall | `Verified — PASS` | 24/24 checks passed; 0 failures; 0 warnings. |

### Phase H — Integration health/OAuth readiness (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| H1: GET /integrations/health | `Verified — PASS` | HTTP 200; `overall_status: warning`; `gmail.status: warning` (configured, not yet OAuth-synced); no tokens/secrets; no cross-tenant data. Warning is a safe, controlled state for a new tenant. |
| H2a: GET /integrations | `Verified — PASS` | HTTP 200; 2 enabled integrations (Monday.com, Google Mail); no secrets; no cross-tenant. |
| H2b: GET /setup/status | `Verified — PASS` | HTTP 200; `readiness.score: 90, status: ready`; `google_mail: true, monday: true, fortnox: false, visma: false`; `missing: ["Support email not configured"]`; no secrets. |
| H2c: GET /pilot/readiness | `Verified — PASS` | HTTP 200; `almost_ready`; no secrets. |
| H3a: GET /integrations/visma/status | `Verified — PASS` | HTTP 200; `status: disconnected, connected: false`; no tokens. |
| H3b: GET /integrations/visma/oauth/url | `Verified — PASS` | HTTP 503; `"Visma OAuth is not configured"`; VISMA_CLIENT_ID not set; safe not-configured response. |
| H3-skip: oauth/start, oauth/callback | `Skipped — Out of scope` | Redirect/token-exchange endpoints not tested per plan. |
| H4: GET /integration-events | `Verified — PASS` | HTTP 200; no gmail/monday/fortnox write events; no cross-tenant. |
| H5: GET /audit-events | `Verified — PASS` | HTTP 200; T_LIVE_TEST_001 data only; no secrets. |
| H6a: /integrations/health without key | `Verified — PASS` | HTTP 401. |
| H6b: X-Tenant-ID: T_ELITGRUPPEN + T_LIVE_TEST_001 key | `Verified — PASS (design)` | HTTP 200 scoped to T_LIVE_TEST_001 only; T_ELITGRUPPEN integration state not exposed. |
| H7: Pending approvals cleanup | `Verified — PASS + Cleanup` | Phase F email_send approval (eml_adeaf87..., job bea23f74...) found and safely rejected (HTTP 200); no external write; no cross-tenant. |
| H8: App logs | `Verified — PASS` | All requests logged cleanly; no 500s; no stack traces; no secrets; 401 for no-key; 503 for unconfigured Visma. |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory only; cleared with unset; temp scripts removed. |
| Phase H overall | `Verified — PASS` | 42 pass, 0 fail, 1 warn (expected cleanup). |

**Integration state summary (T_LIVE_TEST_001, 2026-07-07):**
- Gmail: `warning` — env credentials present (`google_mail: true`), OAuth not yet connected, no scanner run.
- Monday: enabled (`monday: true`), connection state not separately checked.
- Visma: `disconnected` — VISMA_CLIENT_ID not set; safely returns 503 on oauth/url.
- Fortnox: `false` — not configured.

### Phase I — UI / read-only dashboard verification (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| I1a: app.krowolf.se/ui | `Verified — PASS` | HTTP 200; 460 KB HTML; "Internal Operator Console" markers present; no actual secret values embedded. |
| I1b: api.krowolf.se/ui | `Verified — PASS` | HTTP 200; same HTML served via API host. |
| I1c: Cache-bust request | `Verified — PASS` | HTTP 200; same operator console content. |
| I2: Static HTML content | `Verified — PASS` | All sections present: Internal Operator Console, Tenants, Readiness, Integrations, Jobs, Approvals, Activity, Setup. No cross-tenant data. No actual secret values (script false-positives on JS variable names and CSS selectors explained separately). |
| I3: No-key auth states | `Verified — PASS` | /tenant, /jobs, /approvals/pending without key → all 401. |
| I4: Customer read-only endpoints | `Verified — PASS` | /tenant, /customer/health, /customer/results, /customer/activity, /customer/account — all 200; T_LIVE_TEST_001 scoped; no secrets; no cross-tenant. |
| I5a: /pilot/readiness | `Verified — PASS` | 200; almost_ready. |
| I5b: /integrations/health | `Verified — PASS` | 200; overall_status: warning (expected). |
| I5c: /jobs | `Verified — PASS` | 200; total=2 (Phase F + G synthetic); no cross-tenant. |
| I5d: /approvals/pending | `Verified — PASS` | 200; 0 pending (queue clean after Phase H cleanup). |
| I5e: /audit-events | `Verified — PASS` | 200; T_LIVE_TEST_001 only; no secrets. |
| I6a: /admin/tenants without key | `Verified — PASS` | HTTP 401. |
| I6b: /admin/tenants with admin key | `Verified — PASS` | 200; tenants: T_ELITGRUPPEN, TENANT_2001, T_LIVE_TEST_001, T_TEST1; no api_key values in list; no secrets. |
| I7: Browser UI check | `Verified — PASS` | Browser confirmed: "Internal Operator Console" title; Admin/Kund login tabs; username/password form; no plaintext API keys visible; no old polished SaaS dashboard; minimal internal operator UI. Screenshot captured 2026-07-07. |
| I8: App logs | `Verified — PASS` | All endpoints logged correctly; no 500s; no stack traces; no secrets; 401 for no-key. |
| Script false-positives | `Non-blocking` | 3 script FAILs were false positives: HTML `input[type="password"]` CSS selector, JS variable names (`access_token`, `admin_api_key`), and config status text ("FORTNOX_ACCESS_TOKEN är konfigurerade") — all variable NAMES, not actual VALUES. Verified via grep extraction and browser inspection. |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory only; cleared with unset; temp scripts removed. |
| Phase I overall | `Verified — PASS` | 58 actual pass, 0 true fail, 0 warn; 3 script false-positives explained. |

### Phase J — Gmail OAuth readiness/connection planning (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| J1: Gmail config inspection | `Verified — PASS` | All required env vars SET and masked: `GOOGLE_MAIL_ACCESS_TOKEN (len=253)`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID` (visible, safe), `GOOGLE_OAUTH_CLIENT_SECRET` (masked), `GOOGLE_MAIL_API_URL`, `GOOGLE_MAIL_USER_ID=me`. Env var names match `app/core/settings.py` exactly. No secrets printed. |
| J2: Route/code inspection | `Verified — PASS` | Gmail uses static token model — no OAuth consent URL route exists. Sync routes identified (NOT called): `POST /gmail/process-inbox`, `POST /workflow-scan/gmail`, `POST /dashboard/inbox-sync`. Token refresh is internal only. |
| J3: /integrations/health | `Verified — PASS` | 200; `gmail.status: warning, configured: True`; `monday: warning, configured: True`; `fortnox: not_configured`; no secrets. Warning expected — scanner not yet run. |
| J4a: /setup/status | `Verified — PASS` | 200; `google_mail: True, email_connected: True`; `readiness.score: 90, status: ready`; `missing: ["Support email not configured"]`; no secrets. |
| J4b: /pilot/readiness | `Verified — PASS` | 200; `almost_ready`; warnings: onboarding 4/8 steps, no routing hints, no integration events. Expected pre-scan state. |
| J5: OAuth auth-url routes | `Verified — PASS` | All Google OAuth URL routes → 404 (not implemented). Correct: Gmail uses static token model, no consent redirect needed. |
| J6: Gmail callback route | `Verified — PASS` | No Gmail OAuth callback route (404). No token exchange. No real code sent. |
| J7: Inbox sync status | `Verified — PASS` | Sync routes documented and NOT called. `GET /workflow-scan/status` → 200; `status: never_run, last_scan_at: null`. No inbox data read. |
| J8a: /integration-events | `Verified — PASS` | 200; no gmail_send/inbox_sync events; no secrets; T_LIVE_TEST_001 only. |
| J8b: /audit-events | `Verified — PASS` | 200; no secrets; no cross-tenant. |
| J9: App logs | `Verified — PASS` | No 500s; no stack traces; no OAuth tokens; 404s for non-existent OAuth routes; no inbox sync. 1 false-positive WARN (grep matched function name). |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory only; cleared with unset; temp scripts removed. |
| Phase J overall | `Verified — PASS` | 32 pass, 0 fail, 1 warn (false positive). |

**Gmail OAuth state summary (2026-07-07):**
- Token model: Static env-var tokens — no browser consent flow needed.
- `GOOGLE_MAIL_ACCESS_TOKEN`: SET (len=253) — valid token present.
- `GOOGLE_OAUTH_REFRESH_TOKEN`: SET — auto-refresh enabled.
- `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`: both SET.
- Scanner: `never_run` — inbox sync not yet executed.
- Inbox sync is blocked until explicit Phase K approval.

### Phase K — Gmail inbox sync (2026-07-08) — PASSED

| Check | Status | Detail |
|-------|--------|--------|
| Preconditions | `Verified — PASS` | `auto_actions: {lead: False, customer_inquiry: False, invoice: False}`; safe to proceed. |
| K1: dry_run=true | `Verified — PASS` | HTTP 200; `dry_run: True`; 0 new jobs created (correct); no side effects. |
| K2: dry_run=false (real sync) | `Verified — PASS` | HTTP 200; `dry_run: False`; **8 new jobs created** from Gmail inbox; `jobs_before=2 → jobs_after=10`. |
| K3: Jobs after sync | `Verified — PASS` | 10 total jobs (2 synthetic + 8 from Gmail); no cross-tenant; no secrets. |
| K4: App logs | `Verified — PASS` | `POST /gmail/process-inbox HTTP/1.1 200 OK` (×2); no errors; no leaked tokens. |
| K5: auto_actions safe | `Verified — PASS` | `auto_actions: {lead: False, customer_inquiry: False, invoice: False}` — no automatic external dispatch triggered. |

**Resolution (2026-07-08):**
- New Google OAuth client created: `502012997563-gp9iku5erqff3u8tad923pk8mb7fsp8m`
- New `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_MAIL_ACCESS_TOKEN` updated in `.env.production`
- Container recreated with `docker compose up -d` (not just restart — required to pick up new env vars)
- Token refresh verified against Google API before container restart: `PASS, new_access_token=SET (len=253), expires_in=3599`
- Phase K now **PASSED**; blocker removed

**Important lesson:** `docker compose restart` does NOT re-read `.env.production` — must use `docker compose up -d` to recreate container with updated env vars.

**Previous attempt (2026-07-07) — BLOCKED:**
- First attempt: HTTP 503; `invalid_grant` — old refresh token revoked/expired.
- Second attempt: tokens replaced but with wrong OAuth client_id (old client); `unauthorized_client`.
- Third attempt: new client_id + secret set correctly; container recreated; Phase K PASSED.

### Phase L — Monday readiness/no-write verification (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| L1: Monday config inspection | `Verified — PASS` | `MONDAY_API_KEY` SET (len=227), `MONDAY_BOARD_ID` SET (len=11), `MONDAY_API_URL` SET. `MONDAY_WORKSPACE_ID` not present (not required). No token value printed. |
| L2: Monday routes identified | `Verified — PASS` | Write routes identified and NOT called: `POST /integrations/{type}/execute`. Read-only routes tested: `/integrations`, `/integrations/health`, `/setup/status`, `/pilot/readiness`, `/workflow-scan/status`. No `/integrations/monday/status` route exists (correct). |
| L3: /integrations/health | `Verified — PASS` | HTTP 200; `overall_status: warning`; `monday.status: warning, configured: True`; no tokens/secrets; no cross-tenant data. Warning: expected state — Monday API key set but no dispatch event logged yet. |
| L4a: /setup/status | `Verified — PASS` | HTTP 200; `connections.monday: True`; `readiness.score: 90, status: ready`; `missing: ["Support email not configured"]`; no secrets. |
| L4b: /pilot/readiness | `Verified — PASS` | HTTP 200; `overall_status: almost_ready`; script FAIL was false positive — grep matched `"TENANT_API_KEYS konfigurerat."` string, not an actual key value. |
| L5: Monday-specific status endpoints | `Verified — PASS` | `/integrations/monday/status` → 404; `/integrations/monday/health` → 404. Correct — no Monday-specific status route exists; health is bundled in `/integrations/health`. |
| L6: Execute endpoint protection | `Verified — PASS` | `POST /integrations/monday/execute` without key → 401. No real Monday payload sent. Write routes protected. |
| L7a: /integration-events | `Verified — PASS` | HTTP 200; no monday_create/update/delete events; no secrets; T_LIVE_TEST_001 only. |
| L7b: /audit-events | `Verified — PASS` | HTTP 200; script FAIL was false positive — grep matched `action: "api_key_rotated"`, not a leaked credential. No Monday write events. No secrets. |
| L8a: Negative auth — no key | `Verified — PASS` | `/integrations/health` without key → 401. |
| L8b: Cross-tenant isolation | `Verified — PASS (design)` | `X-Tenant-ID: T_ELITGRUPPEN` + `T_LIVE_TEST_001` key → 200 scoped to T_LIVE_TEST_001 only. Header ignored per auth design; T_ELITGRUPPEN state not exposed. |
| L9: App logs | `Verified — PASS` | No 500s; no stack traces; no Monday write events; no leaked tokens. 2 expected Phase K WARNs (`POST /gmail/process-inbox 503`) visible as historical blocker. |
| False positives | `Non-blocking` | 2 script FAILs were false positives: L4b matched `"TENANT_API_KEYS konfigurerat."` in pilot/readiness text; L7b matched `action: "api_key_rotated"` in audit-events. Both confirmed benign by direct response inspection. |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory only; cleared with unset; temp scripts removed from server and local. |
| Phase L overall | `Verified — PASS` | 30 pass, 2 false-positive script fails (explained), 0 true failures, 0 warnings. |

**Monday config summary (2026-07-07):**
- `MONDAY_API_KEY`: SET (len=227) — API key present.
- `MONDAY_BOARD_ID`: SET (len=11) — board target configured.
- `MONDAY_API_URL`: `https://api.monday.com/v2` — standard endpoint.
- `MONDAY_WORKSPACE_ID`: not present — not required for item creation.
- Monday uses API-key auth (no OAuth consent flow).
- Monday `adapter.py` creates items via GraphQL — gated by `auto_actions` and `MONDAY_API_KEY`.
- No Monday writes executed. `auto_actions` remain `false` for all types.

**Carried blockers:**
- Phase K: `GOOGLE_OAUTH_REFRESH_TOKEN` invalid/revoked — requires new Gmail OAuth tokens before inbox sync can run.

### Phase M — Final pre-pilot cleanup/status consolidation (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| M1: Server/container status | `Verified — PASS` | Commit `87d9369` confirmed; `krowolf-app-1` (Up 2 hours), `krowolf-db-1` (Up 2 months), `krowolf-caddy-1` (Up 2 months); no restart loop; no 500s or stack traces in last 120 log lines. |
| M2: Production health | `Verified — PASS` | `/` → 200 `env: production`; `/health` → 200 `env: production`; `/docs` → 404; `/openapi.json` → 404. All expected. |
| M3a: /tenant | `Verified — PASS` | 200; `name: Live Test Tenant`; no cross-tenant data. |
| M3b: /setup/status | `Verified — PASS` | 200; `connections: {google_mail: True, monday: True, fortnox: False, visma: False}`; `readiness.score: 90, status: ready`; `missing: ["Support email not configured"]`; no secrets. |
| M3c: /pilot/readiness | `Verified — PASS` | 200; `overall_status: almost_ready`; 7 pass, 4 warn, 0 fail. Warnings expected (onboarding 4/8, no routing hints, no dispatch events, integration health warnings). |
| M3d: /integrations/health | `Verified — PASS` | 200; `overall_status: warning`; `gmail: warning, configured=True`; `monday: warning, configured=True`; `fortnox: not_configured`; no secrets; no cross-tenant data. |
| M4a: /jobs | `Verified — PASS` | 200; `job_count=2` (Phase F+G synthetic evidence retained); no cross-tenant data; no secrets. |
| M4b: /approvals/pending | `Verified — PASS` | 200; `pending_count=0` — queue clean. |
| M5a: /audit-events | `Verified — PASS` | 200; no external write events; no gmail_send/monday_write/fortnox/visma events; no secrets; T_LIVE_TEST_001 only. |
| M5b: /integration-events | `Verified — PASS` | 200; no external write events; no cross-tenant data; no secrets. |
| M6: Backups/operational files | `Verified — PASS` | Pre-Phase-D backup `pre-phase-d-20260707-190618.sql` (677 KB) present. 16 daily automated backups (`ai_platform_2026-06-22-0200.sql.gz` → `ai_platform_2026-07-07-0200.sql.gz`). `.env.production`, `docker-compose.prod.yml`, `infra/Caddyfile` all present. |
| M7: Cleanup list confirmed | `Verified — PASS` | All 8 known cleanup items documented in docs (see below). |
| M8: Logs risk search | `Verified — PASS` | No risky patterns in last 1000 log lines. No Traceback, 500 Internal, leaked tokens, Gmail send, Monday write, Fortnox, or Visma events. Phase K `invalid_grant` entries not present in tail-1000 (belong to earlier log window). |
| Stop conditions | `None triggered` | No unexpected 500s, no cross-tenant data, no external write events, no server instability, no missing backups. |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory only; cleared with unset; temp scripts removed. |
| Phase M overall | `Verified — PASS` | 50 pass, 0 fail, 0 warn. |

**Known cleanup items (carried to Phase N):**
1. Phase K Gmail `invalid_grant` — `GOOGLE_OAUTH_REFRESH_TOKEN` revoked/expired; must refresh before Phase O.
2. DB password in `docker-compose.prod.yml` — needs rotation and move to `.env.production`.
3. SQLAlchemy SQL echo verbose in production logs — review and reduce.
4. Support email not configured — in `setup/status` missing list.
5. `/pilot/readiness` `almost_ready` — expected warnings: onboarding 4/8 steps, no routing hints saved, no integration events logged.
6. `GOOGLE_CALENDAR_ACCESS_TOKEN` empty — calendar not in scope.
7. Phase F email_send approval cleaned in Phase H — no action needed.
8. `MONDAY_WORKSPACE_ID` not in `.env.production` — not required for item creation; document as known gap.

**Pre-pilot blocker summary:**
- All blocking issues resolved. Phase K PASSED (Gmail tokens fixed). Phase O PASSED (CONDITIONAL GO).
- Backup scripts added (2026-07-08): `scripts/backup_postgres.sh`, `scripts/restore_postgres_rehearsal.sh`, `scripts/check_backup_freshness.sh`. Offsite upload requires `OFFSITE_BACKUP_COMMAND` configuration on server (not yet configured — **BLOCKER before first real customer pilot**; local-only backups are not sufficient).

**Full live verification status:**
- Phases A–O: **PASSED** (Phase O: CONDITIONAL GO, 2026-07-08)
- Phase K: **PASSED** (Gmail `invalid_grant` resolved)
- Phase O: **CONDITIONAL GO** — all GO criteria met; conditions below.

**Phase O CONDITIONAL GO conditions (must be satisfied before first real pilot run):**
1. Set `support_email` for T_LIVE_TEST_001: `PUT /dashboard/control {"support_email": "support@krowolf.se"}`
2. Review pending approval `eml_5d69...` (action_dispatch, next_on_approve=email_send) — do NOT approve without explicit operator decision; reject if not intentional.
3. Rotate DB password when maintenance window available (plan in docs).
4. Monday live item-creation: verify before enabling `auto_actions.lead=true` for any real tenant.

### Phase N — Production hardening cleanup (2026-07-07)

| Check | Status | Detail |
|-------|--------|--------|
| N1: Hardening inventory | `Verified — PASS` | Commit `87d9369` on server (pre-rebuild); app/db/caddy all Up; `ENV=production`; `APP_NAME=Krowolf`; all key env vars SET (DATABASE_URL, ADMIN_API_KEY, GOOGLE tokens, MONDAY_API_KEY); `SUPPORT_EMAIL` absent from env (correct — stored in DB per-tenant). |
| N2: SQL echo source | `Verified` | `app/repositories/postgres/database.py` had `echo=True` hardcoded. `session.py` correctly had no echo. Identified as the source of verbose SQL logging in production. |
| N3: SQL echo fix — code | `Fixed — PASS` | Changed `echo=True` → `echo=settings.DB_ECHO` in `database.py`; added `DB_ECHO: bool = False` to `settings.py`. 2746 tests pass, 0 failures. Committed as `01f5763`. |
| N3: SQL echo fix — deploy | `Deployed — PASS` | Git pull on server: `87d9369..01f5763`. Docker image rebuilt (`COPY app` layer only — pip layer cached, fast rebuild). Container recreated and started. `sql_echo_count_tail30=0` — SQL echo eliminated in production. |
| N3: Post-rebuild health | `Verified — PASS` | `/` → 200; `/health` → 200 `env: production`; `/docs` → 404; `/openapi.json` → 404; `/tenant` → 200; `/approvals/pending` → 200; `/integrations/health` → 200. All endpoints healthy post-rebuild. |
| N4: Support email | `Documented — PARTIAL` | `support_email` is stored in DB per-tenant settings, NOT in `.env.production`. Set via `PUT /dashboard/control` with `{"support_email": "..."}`. Current value: `''` (empty). Operator must confirm and set email address before pilot. Suggested value: `support@krowolf.se` — not set without explicit confirmation. |
| N5: DB password hardening | `Planned — PARTIAL` | `POSTGRES_PASSWORD` hardcoded directly in `docker-compose.prod.yml` (line 19, not using `${POSTGRES_PASSWORD}` interpolation). `DATABASE_URL` in `.env.production` embeds password inline. Rotation plan documented below. Not executed — requires maintenance window. |
| N6: Gmail token blocker plan | `Documented` | Refresh token invalid/revoked. Required fix documented. Not executed here. |
| N7: Post-hardening health | `Verified — PASS` | All endpoints healthy after Docker image rebuild (see N3 above). |
| N8: Logs risk search | `Verified — PASS` | No risky patterns (no Traceback, 500, leaked tokens, Gmail send, Monday write). SQL echo eliminated. |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory only; cleared with unset; all temp scripts removed from server and local. |
| Phase N overall | `Verified — PASS` | Hardening complete: SQL echo fixed and deployed. Support email and DB password rotation require operator action. |

**DB password rotation plan (safe maintenance task — NOT executed in Phase N):**
1. Take fresh DB backup: `sudo docker exec krowolf-db-1 pg_dump -U postgres ai_platform > /opt/krowolf/backups/pre-rotation-$(date +%Y%m%d-%H%M%S).sql`
2. Generate strong new password (e.g. `openssl rand -base64 32`)
3. Add `POSTGRES_PASSWORD=<new>` to `.env.production`
4. Edit `docker-compose.prod.yml`: change `POSTGRES_PASSWORD: <hardcoded>` to `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`
5. Update `DATABASE_URL` in `.env.production` to use new password
6. Alter Postgres user: `sudo docker exec krowolf-db-1 psql -U postgres -c "ALTER USER postgres WITH PASSWORD '<new>';"`
7. Rebuild image: `sudo docker compose -f docker-compose.prod.yml up -d`
8. Verify `/health` and a DB-backed endpoint return 200
9. Keep old password secured until rollback window passes

**Support email configuration (operator action required):**
- Endpoint: `PUT /dashboard/control` (requires `X-API-Key` for `T_LIVE_TEST_001`)
- Payload: `{"support_email": "support@krowolf.se", "automation": {...}, "scheduler": {...}}`
- Confirm email address with operator before setting

**Gmail token blocker (Phase K — required before Phase O):**
1. Re-run Google OAuth consent flow for the Gmail account
2. Update `GOOGLE_MAIL_ACCESS_TOKEN` and `GOOGLE_OAUTH_REFRESH_TOKEN` in `.env.production`
3. Rebuild app: `sudo docker compose -f docker-compose.prod.yml build app && sudo docker compose -f docker-compose.prod.yml up -d app`
4. Rerun Phase K: `POST /gmail/process-inbox`

**Production commit after Phase N:**
- `87d9369` → `01f5763` (fix: make SQLAlchemy engine echo env-controlled, default off)
- Docker image rebuilt and deployed. Live commit: `01f5763`.

### Phase O — Final go/no-go pilot checklist (2026-07-08) — CONDITIONAL GO

| Check | Status | Detail |
|-------|--------|--------|
| O1: Production health | `Verified — PASS` | `/` → 200 `env: production`; `/health` → 200 `env: production`; `/docs` → 404; `/openapi.json` → 404. All expected. |
| O2: Tenant status/readiness | `Verified — PASS` | `T_LIVE_TEST_001` active; `auto_actions: {lead: false, customer_inquiry: false, invoice: false}`; `setup/status` score=90 status=ready; `pilot/readiness` overall=almost_ready (7p 4w 0f); `integrations/health` overall=warning (gmail+monday configured, fortnox not_configured); no secrets. |
| O3: Gmail jobs verification | `Verified — PASS` | **10 total jobs** (2 synthetic evidence + 8 from Gmail inbox). Job types: 4×unknown, 2×invoice, 2×lead, 1×customer_inquiry. All ext_actions=0. All status=manual_review or completed. All scoped to T_LIVE_TEST_001. No secrets. No cross-tenant. |
| O4: Pending approvals | `Verified — PASS` | **1 pending approval** — `eml_5d69...`, type=action_dispatch, state=pending, `next_on_approve=email_send`. Not approved. Operator must review before approving (would trigger email send). No cross-tenant. |
| O5: Events | `Verified — PASS` | 50 audit events (api_key_rotated×1, step_completed×22, step_started×22, workflow_completed×5); 0 integration events. No gmail_send, no Monday write, no Fortnox/Visma events. No secrets. |
| O6: Cross-tenant isolation | `Verified — PASS` | T_ELITGRUPPEN key + T_LIVE_TEST_001 header → 200 scoped to T_LIVE_TEST_001 only. Header ignored per auth design. No T_ELITGRUPPEN data exposed. |
| O7: Operator UI | `Verified — PASS` | `app.krowolf.se/ui` → 200; "Operator Console" present in HTML; 460 KB. No secret values embedded. |
| O8: Logs risk search | `Verified — PASS` | No risky patterns in last 1200 log lines. No Traceback, 500 Internal, leaked tokens, Gmail send, Monday write, Fortnox, Visma. Clean HTTP log (all 200/404/401 as expected). |
| O9: Cleanup review | `Verified` | FIXED: SQL echo; FIXED: Gmail token. PARTIAL: support email (not set), DB password (plan exists). NOTED: Monday write (not live-tested), Fortnox/Visma (not required). |
| Secrets handling | `Verified` | Admin key and tenant key used in-memory only; cleared with unset; temp script removed. |
| Phase O overall | `CONDITIONAL GO` | **29 pass, 0 fail, 0 warn**. All GO criteria met. Conditions documented. |

**Phase O job breakdown (masked, T_LIVE_TEST_001):**

| # | job_id (prefix) | type | status | rhr | ext_actions | summary |
|---|----------------|------|--------|-----|-------------|---------|
| 1 | 9e99fd23 | unknown | manual_review | True | 0 | Manuell överlämning skapad |
| 2 | 83d6634b | unknown | manual_review | True | 0 | Manuell överlämning skapad |
| 3 | ac664d21 | unknown | manual_review | True | 0 | Manuell överlämning skapad |
| 4 | 0152e4e1 | lead | completed | False | 0 | Ingen manuell överlämning behövs |
| 5 | 7ba97e0a | invoice | manual_review | True | 0 | Manuell överlämning skapad |
| 6 | 223cc7d9 | invoice | manual_review | True | 0 | Manuell överlämning skapad |
| 7 | 0c755f40 | unknown | manual_review | True | 0 | Manuell överlämning skapad |
| 8 | bb928d46 | unknown | manual_review | True | 0 | Manuell överlämning skapad |
| 9 | 8b2d53d2 | customer_inquiry | manual_review | True | 0 | Approval rejected (Phase G synthetic) |
| 10 | bea23f74 | lead | completed | False | 0 | Ingen manuell överlämning behövs (Phase F synthetic) |

Notes: Jobs 9 and 10 are the 2 Phase F/G synthetic evidence jobs. Jobs 1–8 are the 8 Gmail-inbox jobs from Phase K. All 0 external actions. No PII or email content recorded.

**CONDITIONAL GO rationale:**
- All GO criteria: ✅ Production healthy, ✅ Gmail sync working, ✅ Isolation confirmed, ✅ No external writes, ✅ Operator can inspect jobs, ✅ Approvals functional, ✅ Logs clean.
- No NO-GO criteria triggered.
- Conditions: support email, pending approval review, DB password rotation.

## Operator panel initiative — governance and deploy status (Kapitel 0B, 2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| New operator panel frontend stack (React/TS/Vite/shadcn/Tailwind/React Router/TanStack) | `Locked (decision)` | `docs/07-decisions.md` DEC-024. Supersedes DEC-015 **only** for Krowolf's internal operator panel; DEC-015 remains locked for the customer portal and all other frontend work. |
| `docs/00-master-plan.md` / `docs/05-architecture.md` frontend restrictions | `Verified — updated` | Both now reference the DEC-024 exception instead of stating an unqualified prohibition. |
| `app/ui/index.html` legacy status | `Verified (unchanged)` | Frozen legacy per DEC-024; no code changed in Kapitel 0B; remains the only served UI until the new panel exists. |
| `infra/Caddyfile` (real production reverse-proxy config) | `Not verified` | Never committed to this repo (`git log` shows no history for `infra/` or `Caddyfile`). Referenced only by path in `docker-compose.prod.yml`. Not retrieved in Kapitel 0B — no SSH credentials/host access available in this session; prior sessions already documented SSH auth failure against the production host (see "Post-push deploy / Phase A-C re-run attempt" above). |
| `infra/Caddyfile.example` | `Added — explicitly NOT verified production truth` | Hand-written target config inferred from `docker-compose.prod.yml` + this file's `app.krowolf.se`/`api.krowolf.se` live-verification entries above. See `infra/README.md`. Must be reconciled with the real file before any production deploy of the new panel. |
| Deploy readiness for new panel | `Tracked` | Full matrix in `docs/07-decisions.md` under "DEC-024 — Deploy readiness matrix". Kapitel-1A-blocking items are all satisfied by Kapitel 0B; production-deploy-blocking items (real Caddy verification, build integration, etc.) are explicitly not required before Kapitel 1A. |

### Kapitel 1A — Frontend foundation (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| `frontend/` React/TS/Vite project | `Verified (local)` | `npm run typecheck`, `npm run lint`, `npm run build` pass locally. Tailwind v3 + shadcn/ui baseline (`button`, `badge`). Router `basename: /ops`; routes `/`, `/foundation`, `*`. |
| FastAPI `/ops` serving | `Verified (tests)` | Additive routes in `app/main.py`: `GET /ops`, `GET /ops/{path}` → SPA `index.html` (503 if build missing); `GET /ops/assets/{path}` → `FileResponse` with path-traversal guard (404 if missing). No `StaticFiles` mount. |
| Backend tests | `Verified (local)` | `tests/test_operator_panel_static.py` — 12 tests pass (SPA fallback, assets, 503, traversal block, regression on `/health`, `/ui`, `/`, `/jobs`). |
| CI frontend job | `Verified (written)` | `.github/workflows/release-gate.yml` — new `frontend` job (Node 22: typecheck, lint, build); `docker` job depends on `[tests, frontend]`. |
| Docker multi-stage build | `Written — not verified locally` | `Dockerfile` adds `node:22-slim` frontend-build stage; `.dockerignore` excludes `frontend/node_modules` and `frontend/dist`. Docker CLI not available in this environment; image build verification deferred to CI. |
| Legacy UI `app/ui/index.html` | `Verified (unchanged)` | Not modified; `/ui` and host-gated `/` still serve legacy HTML. |
| `infra/Caddyfile` production truth | `Not verified` | Unchanged from Kapitel 0B. `/ops` path route chosen to avoid Caddy dependency for initial integration. |

### Kapitel 1B — Design contracts and visual reference (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| JSON design contracts | `Verified (local)` | `frontend/design/krowolf-ui-profile.json`, `component-contracts.json`, `page-contracts.json`. Profile v1.0.0, locale sv-SE, direction nordic_operations. |
| Token pipeline | `Verified (local)` | `npm run tokens:generate` → `src/styles/tokens.generated.css`; `tailwind.config.js` reads profile via `createRequire`. |
| Contract tests | `Verified (local)` | `npm run test:contracts` — profile tokens, breakpoints ascending, implemented-component set, page contracts. |
| Operator components (10) | `Verified (local)` | PageHeader, StatusBadge, SeverityBadge, MetricCard, HealthIndicator, EmptyState, ErrorState, LoadingState, ActionDialog, CriticalActionDialog in `frontend/src/components/operator/`. Variant types derived from JSON; `satisfies Record<...>` enforcement. |
| Design reference route | `Verified (local)` | `/ops/design-reference` — static demo data only, no API calls. Responsive queue (desktop table / mobile cards). |
| Backend SPA test | `Verified (local)` | `test_ops_design_reference_serves_spa_fallback` in `tests/test_operator_panel_static.py`. No `app/main.py` changes. |
| Cursor rule | `Verified (written)` | `.cursor/rules/frontend-ui.mdc` |
| CI | `Verified (written)` | `npm run test:contracts` added to frontend job in `release-gate.yml`. |
| Manual responsive browser verification | `Still outstanding` | Documented checklist in `frontend/README.md` not yet executed in this environment. |
| Kapitel 1A Docker verification | `Still outstanding` | Unchanged by this chapter. |

### Kapitel 2 — Global operativ översikt (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| Overview endpoint | `Verified (tests)` | `GET /admin/operations/overview` — global, read-only, `require_admin_api_key`. Returns typed `OperationsOverviewResponse`. |
| Counter definitions | `Verified (tests)` | `active_tenants`, `jobs_last_24h` (24h), `pending_approvals`/`open_manual_reviews` (point-in-time), `failed_jobs`/`stuck_jobs` (48h), `integration_errors` (24h). Each counter includes `window_hours`. |
| Stuck jobs rule | `Verified (tests)` | `pending`/`processing` only, `updated_at < 48h`. Excludes approval wait states. |
| Aggregation failure | `Verified (tests)` | Mandatory SQL error → 503, no partial counters. Safe logging without connection strings. |
| Priority list | `Verified (tests)` | Reuses triage signals via `collect_all_triage_rows`; overview-specific sort (severity → external → oldest → stable ID). Stable IDs: `job:`, `approval:`, or `hash:`. |
| Integration status | `Verified (tests)` | Gmail from health check; Visma/Google Sheets from event log (`unknown` when no events). |
| Platform status | `Verified (tests)` | Explicit priority: critical → failed → warning → healthy → unknown. |
| Triage refactor | `Verified (tests)` | `collect_all_triage_rows()` shared; `get_admin_needs_help` behavior unchanged. |
| Frontend OverviewPage | `Verified (local)` | `/ops` index; read-only; no client-side re-sort; `ErrorState` on 503; `window_hours` drives metric captions. |
| Backend tests | `Verified (local)` | 29 tests in `test_admin_operations_overview.py`. Performance smoke: 50 mock tenants < 2s. |
| Frontend gates | `Verified (local)` | typecheck, contracts, lint, build pass. |
| Inherited N+1 | `Documented` | One `collect_all_triage_rows` call per overview request; not rebuilt in this chapter. |
| Manual responsive browser verification | `Still outstanding` | Not executed in this environment. |
| Kapitel 1A Docker verification | `Still outstanding` | Unchanged. |
| Kapitel 1B browser verification | `Still outstanding` | Unchanged. |

### Kapitel 3 — Kundlista och kunddetalj (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| Tenant list endpoint | `Verified (tests)` | Extended `GET /admin/tenants` — search/filter/sort/pagination; enriched items with `tenant_status`, `health`, `package:null`, `operator_owner:null`, `enabled_modules`, `jobs_last_30d`, `integrations_summary`, batched counts. |
| Tenant detail endpoint | `Verified (tests)` | `GET /admin/tenants/{tenant_id}/overview` — single read-only aggregation; 404 when missing. |
| Tenant status vs health | `Verified (tests)` | `tenant_status` (`active`/`inactive`/`unknown`) separate from operational `health`. `paused` only when `automation.demo_mode` or `scheduler.run_mode=paused`. |
| Last activity | `Verified (tests)` | `last_activity_at` = max of latest job, approval, integration event, audit event (batched `GROUP BY`). |
| Integration sources | `Verified (tests)` | List: Gmail from triage; Visma/Sheets from OAuth + event log (`unknown` when no signal). Detail: gmail/monday/fortnox from `get_integration_health`; visma/sheets separate. |
| List totals | `Verified (tests)` | Bounded lists paired with separate true totals (`manual_review.total`, `jobs.total`, `audit.total`, etc.). |
| Settings allowlist | `Verified (tests)` | No wholesale `settings` serialization; only `to_dict` fields + pause-signal keys via `_get_automation`/`_get_scheduler`. |
| Frontend customers feature | `Verified (local)` | `/ops/customers` list + `/ops/customers/:tenantId` detail; `DataTable`, `FilterBar`, `TenantIdentifier`, `AuditTimeline`. |
| Backend tests | `Verified (local)` | `tests/test_admin_tenant_directory.py` (25 tests). Performance smoke: 50 mock tenants < 2s for list. |
| Frontend gates | `Verified (local)` | typecheck, contracts, lint, build pass. |
| Inherited N+1 (list) | `Documented` | `collect_all_triage_rows` per list request; approvals/activity/jobs counts batched. |
| Manual responsive browser verification | `Still outstanding` | Not executed in this environment. |

### Kapitel 4 — Gemensam felkö och Behöver hjälp (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| Shared triage normalization | `Verified (tests)` | `dedupe_and_normalize_signals` + latest-per-source integration events in `collect_all_triage_rows`; consumed by overview, tenant directory, needs-help queue, and legacy `get_admin_needs_help`. |
| New signal types | `Verified (tests)` | `reconciliation_required` (current-state, not safe to retry); `tenant_config` (active non-demo tenants with empty job types + integrations). |
| Retry/impact rules | `Verified (tests)` | Per-signal `retryable`/`external_impact` enum (`yes`/`no`/`unknown`/`not_applicable`); no `area.startswith("integration")` default. |
| Runbook allowlist | `Verified (tests)` | Registry IDs + Swedish labels only in API; no filesystem paths exposed. |
| Needs-help queue endpoint | `Verified (tests)` | `GET /admin/operations/needs-help` — typed `NeedsHelpQueueResponse`; panel severities (`critical`/`failed`/`warning`/`information`); filtered pre-pagination summary; search/category/source_type/minimum_age_hours filters. |
| Needs-help detail endpoint | `Verified (tests)` | `GET /admin/operations/needs-help/{item_id}` — optional `tenant_id` for scoped lookup; global scan fallback documented as scaling limitation. |
| Legacy compatibility | `Verified (tests)` | `get_admin_needs_help()` unchanged for existing consumers/tests; route now uses `list_needs_help_queue`. |
| Frontend needs-help feature | `Verified (local)` | `/ops/needs-help` queue + `/ops/needs-help/:itemId` detail; summary metrics, filters, DataTable, customer navigation. |
| Backend tests | `Verified (local)` | Extended `test_admin_operations_triage.py`, `test_admin_operations_overview.py`; new `test_admin_operations_needs_help.py`. |
| Frontend gates | `Verified (local)` | typecheck, contracts, build pass. |
| Manual responsive browser verification | `Still outstanding` | Not executed in this environment. |

### Kapitel 7 — Användning, kostnad och kapacitet (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| Usage endpoints | `Verified (tests)` | `GET /admin/usage/overview`, `GET /admin/usage/tenants`; days 7/30/90; read-only. |
| Period semantics | `Verified (tests)` | Half-open UTC `[start, end)`; comparison contiguous with zero gap/overlap. |
| Batched aggregation | `Verified (tests)` | Period metrics via fixed `GROUP BY tenant_id` queries; not O(tenants) for period data. |
| `automation_rate` | `not_measured` | Documented gap: `audit_events` has no indexed `job_id` for operator_action linkage. |
| `manual_reviews_created` | `not_measured` | `gmail_manual_review_handoffs` counts Gmail audit rows only (`gmail_handoff_applied`). |
| Terminal job counts | `Proxy` | `jobs_completed`/`jobs_failed` use `updated_at` with `timestamp_basis: updated_at_proxy`. |
| AI usage/cost | `Honest gaps` | `ai_usage.status=not_measured`; `ai_cost.status=unknown`; no fabricated amounts. |
| Capacity | `baseline_missing` | `peak_jobs_per_hour` via Python hour-bucketing (dialect-neutral). |
| `attention_status` | `Documented exception` | Inherits `collect_all_triage_rows()` O(tenants) cost (pre-existing pattern). |
| Auth | `Verified (tests)` | Single `require_operator_role(_USAGE_READ_ROLES)`; tenant API key rejected. |
| Frontend usage | `Verified (local)` | `src/features/usage/` — no charts; data-quality section; no dead AI-cost filters. |
| Backend tests | `Verified (local)` | `tests/test_admin_usage.py`; incidents/needs-help regressions pass. |
| Frontend gates | `Verified (local)` | typecheck, lint, build pass. |
| Manual responsive browser verification | `Still outstanding` | Not executed in this environment. |
| Not built | `Documented` | Billing, subscriptions, time-series charts, per-tenant usage detail page, AI instrumentation. |

### Kapitel 9 — Standardiserad kundonboarding (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| **Kapitel 9 overall** | `PASS` | Slice 1 + 2A + 2B PASS (Fas B 2026-07-17). |
| **Slice 2B** | `PASS` | Fas B + Gmail readiness fix (2026-07-18): Monday tenant-bound E2E, Visma preflight, browser integrations UI, Gmail truth API + `POST …/readiness` 200 (typed checks, no 500 on `locally_verified`/`externally_verified` source_class). |
| **Slice 1** | `Verified — PASS` | Writable steps 1–3, readiness, activate/cancel; registry SoT + activation-plan binding; tests `tests/test_admin_onboarding.py` + `tests/test_admin_onboarding_registries.py`. |
| **Slice 2A** | `Verified — PASS` | Writable service profile, routing, data start; `GET/PATCH …/service-profile`, `…/routing`, `…/data-start`; materialization to `memory.lead_config`, `memory.internal_routing_hints`, `intake.*`; `tests/test_admin_onboarding_slice2a.py` (13 pass). |
| Registry source of truth | `Verified (tests)` | `app/admin/onboarding/registries.py`; `GET /admin/onboarding/registries`; frontend loads capabilities/presets from API only. |
| Registry versioning | `Verified (tests)` | `registry_schema_version` (API shape) vs `registry_revision` (business fingerprint); both exposed on registries + activation-plan. |
| Runtime evaluation | `Verified (tests)` | `runtime_evaluation.py`; capability lifecycle (`configured_not_running` for followups + paused scheduler); `requires_api_key` derived from `required_runtime`. |
| Activation plan binding | `Verified (tests)` | `GET …/activation-plan` returns `plan_hash`; `POST …/activate` requires matching hash → `409 stale_activation_plan` on drift. |
| Registry integrity | `Verified (startup)` | `validate_registry_integrity()` fail-closed in `app/main.py` on_startup. |
| Migration | `Verified (code)` | `migrations/009_onboarding_sessions.sql` + `schema_migrations.ensure_runtime_schema()`; partial unique index `ux_onboarding_sessions_open_per_tenant`. |
| ORM / repository | `Verified (tests)` | `app/admin/onboarding/` — sessions, step states, drafts; explicit startup import. |
| Tenant ID | `Verified (tests)` | Collision-resistant `T_{bucket}_{suffix}`; slug separate; not `T_{SLUG}`. |
| Create session | `Verified (tests)` | `POST /admin/onboarding` — inactive tenant + session; **no API key** on create. |
| Writable steps | `Verified (tests)` | `PATCH …/identity`, `…/modules`, `…/automation`, `…/service-profile`, `…/routing`, `…/data-start`, `…/integrations`, `…/external-routing` with optimistic `version` + audit. |
| Integrations step | `Verified (tests)` | Config-only drafts; `POST …/integrations/{key}/verify` only path to `verified`; Gmail capped at `configured_not_running`; Visma OAuth via opaque state. |
| Settings materialization (2B) | `Verified (tests)` | Activate writes `settings.schema_version: 3`, `intake.gmail.label_query`, `integrations.external_routing_targets`, legacy `memory.routing_hints` mirror, verification refs. |
| Runtime routing read | `Verified (tests)` | Dispatch + auto-dispatch + `/tenant/routing-preview` read `settings.integrations.external_routing_targets` first; `memory.routing_hints` dict fallback only; invalid canonical → manual_review (no legacy fallback). |
| Customer detail config | `Verified (code)` | `GET /admin/tenants/{id}/overview` includes `onboarding_config` read-only summary. |
| Readiness | `Verified (tests)` | Source classification includes `locally_verified`/`externally_verified`; Gmail checks (`platform_credential`, `label_query`, `tenant_mailbox_access`, `live_intake`, `capability_operational`); legacy/invalid integrations draft fail-closed; global health ≠ tenant verified. |
| Activation | `Verified (tests)` | Admin-only; transactional; `plan_hash` + `acknowledged_warning_ids` + `readiness_check_version`; scheduler fail-closed (`paused`). |
| API key | `Verified (code)` | Separate `POST …/api-key` (admin); only when selected capabilities require `api_access` runtime (derived from registry). |
| Frontend legacy values | `Verified (code)` | Unknown saved capability/preset keys shown read-only; PATCH blocked until operator replaces invalid config. |
| Legacy `POST /admin/tenants` | `Deprecated for UI` | Scripts only; operator panel uses `/admin/onboarding` exclusively. |
| Frontend onboarding | `Verified (local)` | `src/features/onboarding/`; `/ops/customers/new`, `/ops/customers/:tenantId/onboarding`; Ny kund on customer list. |
| Onboarding audit (2B) | `Verified (tests)` | Allowlisted domain events in `audit_events.py`; fail-closed on mutation; no tokens in details; `tests/test_onboarding_audit_events.py`. |
| Frontend slice 2B | `Verified (tests)` | `IntegrationsStepPanel` — Visma connect/unlink, unrequest, routing reset/preview, Gmail classification; `slice2bWizard.test.mjs` in `npm run test:onboarding`. |
| Manual responsive browser verification | `Verified (Fas B 2026-07-17)` | Integrations wizard localhost:5173; Visma authorization_required, Gmail classification, routing reset/preview; overflow pass 320×568–1440×900 + 200%; 0 credential fields. |
| Not built (slice 2B) | `Documented` | External OAuth revoke; Fortnox wizard; Gmail live intake verification (ops runbook only). |

### Onboarding 2.0 — pilot deploy & sign-off (2026-07-20)

| Item | Status | Notes |
|------|--------|-------|
| **Canonical commit** | `Verified — PASS` | `f077aa5dda23d692499210bbc621240a6b8977f2` on `origin/main`; server worktree aligned. |
| **RC image** | `Verified — PASS` | `krowolf-app:rc-f077aa5dda23`; digest `sha256:8f05924d6138a8728726915a48b853f75a8a4edd5b41a0d0a4eb94d3ddaa6932`; annotated tag `rc-f077aa5dda23`. |
| **Migrations 012–014** | `Verified — PASS` | Lifecycle columns, `integration_invitations`, `tenant_activation_snapshots`; idempotent on app restart. |
| **Tenant whitelist** | `Verified — PASS` | Post-cleanup: exactly `T_NIKLAS_DEMO_001` (`lifecycle_status=active`, `config_version=3`). Removed test tenants `T_5E4E4A_48B840`, `T_5E529D_D12F78`, `T_5E7400_4F081E` via `TenantDeletionService` (super_admin). |
| **super_admin live** | `Verified — PASS` | `SUPER_ADMIN_OPERATOR_IDS=operator-admin`; dry-run row counts; `confirm_tenant_id` + reason enforced; Niklas blocked (`not_test_tenant`); audit `tenant.deleted` per removal. |
| **read_only live** | `Verified — PASS` | Temporary `ADMIN_ROLE=read_only` with super_admin list cleared; PATCH/archive/delete/invitation/lifecycle → 403; registries read 200. Role restored to `admin` after smoke. |
| **Runtime gates** | `Verified — PASS` | `/health=200`; scheduler `paused`; jobs=0; approvals=0; tenant alerts=0; `credential_source=tenant_oauth`; Gmail test-read PASS; no live scan; `external_side_effects=0`. |
| **Gmail soak** | `Not resumed` | Whitelist + baseline green (`ready_for_soak_day_1=true`); operator must explicitly resume soak — see `docs/niklas-gmail-soak-log.md`. |
| **Architecture** | `Documented` | `docs/onboarding-2.0-architecture.md`; migrations `012`–`014`. |

### Kapitel 8 — System-, backup- och deploystatus (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| System status endpoint | `Verified (tests)` | `GET /admin/system/status`; read-only; `require_operator_role(_USAGE_READ_ROLES)`. |
| Runtime / resilience / deploy readiness | `Verified (tests)` | Three domain statuses; deploy gaps do not auto-fail runtime. |
| Metadata readers | `Verified (tests)` | Typed `MetadataReadOutcome`; no paths/exceptions in API. |
| Backup metadata | `Verified (scripts/tests)` | `scripts/backup_postgres.sh` writes `BACKUP_STATUS_FILE`; `archive_integrity_verified` (gunzip -t). |
| Restore metadata | `Verified (scripts/tests)` | `scripts/restore_postgres_rehearsal.sh` writes `RESTORE_STATUS_FILE`; verification enums. |
| Build metadata | `Verified (tests)` | `scripts/write_build_metadata.py` + Dockerfile build args; CI docker job passes quoted args. |
| Metadata write failures | `Documented limitation` | API shows stale/missing only; script log is sole source for write failures. |
| Shared status paths | `Documented` | Host `/opt/krowolf/storage/status/…` ↔ container `/app/storage/status/…` via bind mount. |
| `build_time` vs deploy | `Verified (tests)` | `deployment.last_deploy.deployed_at` unknown; never aliased to build time. |
| Caddy / release gate | `Honest gaps` | Routing: not verified in VCS; release gate: no runtime artifact. |
| Pilot readiness | `Out of scope` | Not called from system status endpoint. |
| Scheduler helper fix | `Verified (tests)` | `_derive_scheduler_signal` reads nested `scheduler.run_mode` + legacy fallback. |
| Frontend system | `Verified (local)` | `src/features/systemStatus/`; `/ops/system`; operations+admin roles. |
| Backend tests | `Verified (local)` | `tests/test_admin_system_status.py`, `tests/test_system_status_sources.py`, script tests. |
| Frontend gates | `Verified (local)` | typecheck, contracts, build pass. |
| Manual responsive browser verification | `Still outstanding` | Not executed in this environment. |
| Not built | `Documented` | Deploy buttons, backup/restore triggers, shell/SSH, deploy history DB, CI gate artifact in runtime. |

### Mellankapitel 8B — Responsivitet och testmiljösanering (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| **Mellankapitel 8B overall** | `Verified — PASS` | Responsivitet + testmiljösanering verifierade 2026-07-17. |
| `useListLayout` | `Verified (code)` | Content-width tiers: full ≥1200px, compact 768–1199px, cards &lt;768px; conservative initial `compact`. |
| DataTable layout modes | `Verified (code)` | `compactRow` → `compactColumns` → card fallback; needs-help + usage + customers + incidents wired. |
| FilterBar | `Verified (code)` | Column wrap on narrow widths; min field width; reset on needs-help/usage. |
| Manual responsive verification | `Verified — PASS` | 4 vyer (`/ops/needs-help`, `/ops/usage`, `/ops/customers`, `/ops/incidents`) × 10 breakpoint/zoom-lägen (320–1440 px + 125/150/200 %). Korrekt full/compact/cards-växling; ingen global overflow; ingen teckenvis textbrytning; datum/badges och filter intakta; inga layoutblinkningar. |
| Reset CLI | `Verified (tests)` | `python -m scripts.reset_test_environment` — inventory, purge-tenants, prune-stale-data, seed-baseline. |
| Execute guards | `Verified (tests)` | Positive ENV + DATABASE_URL fingerprint allowlist; `RESET_TEST_ENVIRONMENT_ALLOWED=yes`; `--confirm LOCAL_TEST_RESET`. |
| Purge scope | `Verified (tests)` | Explicit `--tenant-id` or `local-standard` allowlist only; unknown tenants never auto-deleted. |
| Incident purge policy | `Verified (tests)` | Unlink tenant links; shared incidents preserved; orphan timeline/incident deleted last. |
| Test environment purge | `Verified (local)` | Execute-purge: `TENANT_1001`, `TENANT_2001`, `T_KROWOLF_E2E_TEST` (1619 rader). Legacy-tenants och deras gamla signaler borta. |
| Baseline seed | `Verified (local)` | `T_LOCAL_OPS_BASELINE` skapad via `seed-baseline --execute` (config + 2 jobs + 1 pending approval). |
| Demo tenant preserved | `Verified (local)` | `T_NIKLAS_DEMO_001` oförändrad (743 rader kvar efter purge). |
| `TENANT_2002` orphan | `Known — documented` | 1 completed job utan `tenant_config`; medvetet ej purgat i 8B-körningen; hanteras separat. |
| Runbooks | `Verified (docs)` | `docs/runbooks/test-data-dependency-map.md`, `local-test-environment-reset.md`. |

### Kapitel 10 — Operator alerts (2026-07-18)

| Item | Status | Notes |
|------|--------|-------|
| **Kapitel 10 overall** | `Verified — PASS` | Slice 1 + Slice 2 + Slice 3 E2E/browser verified 2026-07-18. |
| Migration 011 | `Verified (E2E)` | `operator_alerts`, `alert_evaluation_runs`, `operator_digests`, `notification_deliveries`. |
| Alert registry | `Verified (E2E)` | 16 types loaded at startup. |
| Evaluation engine | `Verified (E2E)` | Dedup, advisory lock, dry_run, evaluator error isolation, auto-resolve. |
| Lifecycle | `Verified (E2E)` | open → redetected → acknowledged → snoozed → resolved → reopened (after grace). |
| Operator digest | `Verified (E2E)` | Deterministic ordering; `in_app_only` when `OPERATOR_ALERT_RECIPIENT` unset. |
| Frontend alertcenter | `Verified (E2E)` | `/ops/alerts`, `/ops/alerts/:id`, `/ops/digests`, header `AlertIndicator`. |
| Responsive browser | `Verified (E2E)` | 320–1440 px + 125/150/200 % zoom; 320 px header overflow fixed in AppShell. |
| Tenant isolation | `Verified (E2E)` | Cross-tenant filter blocked; suppress admin-only (tests + route policy). |
| Secrets | `Verified (E2E)` | No tokens/credentials in audit, digest, API responses, or frontend DOM. |
| Backend tests | `Verified (local)` | `tests/test_admin_alerts.py` (17); + triage/needs-help/incidents/system/auth/session/tenant isolation (216 total in regression bundle). |
| Frontend gates | `Verified (local)` | typecheck, build, `test:onboarding` (10) pass. |
| E2E scripts | `Verified (local)` | `scripts/kapitel10_e2e_verify.py` (26 checks), `scripts/kapitel10_reopen_verify.py`. |
| Not built in UI | `Documented` | Snooze/suppress actions API-only (no detail-page controls yet). |
| Activity anomaly evaluator | `Preview only` | Slice 3 non-blocking per plan. |

### Kapitel 11 — Security hardening (2026-07-18)

| Item | Status | Notes |
|------|--------|-------|
| **Kapitel 11 overall** | `Verified — PASS` | Slice 0–3 complete; backend regression 236 passed; Slice 3 E2E script 40 PASS (2026-07-18). |
| Browser role matrix | `Verified (E2E script)` | `read_only`/`operations`/`admin` via server-side `ADMIN_ROLE` + session cookie (not frontend headers). |
| Origin/auth matrix | `Verified (E2E script)` | Evil origin blocked; API-key-without-origin allowed for scripts; F06 missing Origin accepted on cookie writes. |
| Session cookies | `Verified (E2E script)` | HttpOnly + SameSite=strict; logout → 401; React `/ops` has empty localStorage/sessionStorage. |
| Legacy UI | `Verified (browser)` | Deprecation + read-only banner at `/ui`; writes blocked client-side; admin key not persisted in localStorage; `GET /admin/alerts/run-all` → 404; Visma legacy callback → redirect `legacy_oauth_disabled`. |
| Proxy/headers | `Verified (partial)` | App middleware: nosniff, DENY, Referrer-Policy, Permissions-Policy, no-store on `/ops` paths. `infra/Caddyfile.example` adds HSTS for production; local `dev_https_proxy` forwards only (no edge headers). CSP not set (open finding, low). |
| Rate limiting | `Verified (E2E script)` | Login 5/min per IP; Retry-After; isolated keys; `reset_rate_limits_for_tests` test-only. |
| Responsive (login) | `Verified (browser)` | 320×568 — no horizontal overflow on `/ops/login`. |
| Slice 3 E2E script | `Verified (local)` | `scripts/kapitel11_slice3_e2e_verify.py` → `kapitel11_slice3_e2e_report.json`. |
| Inventory | `Verified (docs)` | `docs/security/kapitel-11-inventory.md` — trust boundaries, F01–F16. |
| Critical-action registry | `Verified (tests)` | `app/admin/security/critical_actions.py`; `tests/test_admin_security_contracts.py`. |
| Legacy write guards | `Verified (tests)` | Recovery, support, rotate-key, demo-seed, onboarding activate — role + same-origin. |
| `read_only` mutations | `Verified (tests)` | 403 on all critical writes including legacy routes. |
| `GET /admin/alerts/run-all` | `Verified (tests)` | Removed; `POST` with `operations`+ role + rate limit. |
| Audit fail-closed | `Verified (tests)` | `recovery_actions.py`, `alerts/audit_events.py` — no silent skip on mutations. |
| Tenant middleware | `Verified (tests)` | No default `TENANT_1001` when header absent. |
| Idempotency tenant scope | `Verified (tests)` | `get_by_idempotency_key(..., tenant_id=...)`. |
| `get_verified_tenant` admin keys | `Verified (tests)` | `ADMIN_API_KEYS` supported. |
| Visma legacy OAuth | `Verified (tests)` | `state=tenant_id` callback blocked; onboarding opaque state only. |
| Rate limits | `Verified (tests)` | Login + recovery/support/run-all; in-memory per process (F16 accepted). |
| Security headers | `Verified (tests)` | App middleware + `infra/Caddyfile.example`. |
| Secret scan | `Verified (tests)` | `tests/test_security_secret_scan.py`. |
| Cross-tenant admin | `Verified (tests)` | `tests/test_admin_cross_tenant_security.py`. |
| Frontend route policy | `Verified (local)` | Onboarding + digests ops/admin guards; legacy `/ui` deprecation banner. |
| Backend regression bundle | `Verified (local)` | Security contracts, cross-tenant, secret scan, auth, session, alerts, recovery, tenant isolation. |
| E2E script | `Verified (local)` | `scripts/kapitel11_security_e2e_verify.py` (headers + guarded routes). |
| Accepted limitations | `Documented` | F05 OAuth plaintext at rest, F14 suppress UI gap, F15 single operator, F16 in-memory rate limit — DEC-028. |

### Kapitel 12 — Release verification (2026-07-18)

| Item | Status | Notes |
|------|--------|-------|
| **Slice 1 overall** | `Verified — PARTIAL` | `scripts/kapitel12_slice1_verify.py` → `kapitel12_slice1_report.json`: 61 PASS, 0 FAIL, 4 PARTIAL (2026-07-18). |
| **Slice 2 overall** | `Verified — PASS` | Pilot `api.krowolf.se` 2026-07-18: offsite S3 backup+restore from `ai_platform_2026-07-18-202653`; restore-app verify `:8001` PASS (`k12_restore_app_verify.py`); canonical cron via `krowolf-backup-canonical.sh`; scheduler paused; external side effects 0. |
| RB-01 offsite backup | `Verified — PASS` | Live S3 upload+fetch+checksum; restore to `ai_platform_restore_test`; report `storage/status/k12_slice2_del3_resume_report.json`. |
| Profil A/B prestanda | `Verified (pilot RC)` | `k12_rc_perf.py` PASS: overview p95 ≤96 ms, error rate 0%, DB connections 3. |
| Offsite upload helper | `Verified (tests)` | `offsite_backup_upload.py` + `offsite_backup_s3.py` (S3-compatible); deployed to pilot `/opt/krowolf/scripts/`. |
| Backup metadata v2 | `Verified (tests)` | `write_operation_status.py` — `checksum_sha256`, `local_status`, `offsite_status`, `offsite_verified`. |
| Backup alert evaluators | `Verified (tests)` | `summarize_backup_status_for_signals()` fixes stale/failed backup alerts (was broken MetadataReadResult `.get`). |
| Safe local retention | `Verified (code)` | `backup_postgres.sh` skips prune without `.offsite_verified` when offsite configured. |
| Golden paths A–I | `Verified (pytest)` | A 41, B 21, C 25, D 106, E 108, F 50, G 18, H 36, I 67 tests passed via slice script. |
| Roles/auth matrix | `Verified (E2E script)` | `read_only` blocked on approve/reject/recovery/rotate; `operations`+ on writes; session + same-origin on operator routes. |
| Tenant A/B isolation | `Verified (tests)` | `tests/test_tenant_isolation_http.py` 42 passed; alerts filter + recovery wrong-context checks in slice script. |
| RB-04 approval-first React | `Verified (local)` | `approval.approve` in operator action registry + `POST …/approve`; React `approveTenantApproval` + needs-help/customer detail wiring. |
| RB-02 legacy hardening | `Verified (local)` | `/ui` read-only (`LEGACY_UI_READ_ONLY`); `adminApiFetch` blocks non-GET; no `localStorage.setItem(LS_ADMIN_KEY)`; purge on login/logout. |
| RB-03 recovery UI | `Accepted (RB-03)` | API/runbook only; no React recovery console required for CONDITIONAL GO. |
| Pilot deploy/rollback | `Verified — PASS` | Reproducible RC `56b18882a9aa`; rollback to `rc-865b87165eda` 19 s; forward 14 s; 8/8 endpoints PASS. |
| Restore verify tables | `Verified (fix)` | `restore_postgres_rehearsal.sh` uses `tenant_configs`, `approval_requests`, etc. |
| Legacy parity gaps | `Documented` | Recovery console, jobs browser, dedicated manual-review queue remain partial (API/overview/needs-help acceptable per releasebeslut). |
| Frontend gates | `Verified (local)` | typecheck, contracts, onboarding tests pass in slice script. |
| Prestanda Profil A/B | `Verified (pilot RC)` | `scripts/k12_rc_perf.py` on live RC; strict 404/schema fail. |
| Release inventory | `Verified (docs)` | `docs/kapitel-12-release-inventory.md` — Fas 1 plan godkänd 2026-07-18. |
| **Slice 3 overall** | `Verified — PASS` | Autentiserad browsermatris **PASS** alla tre roller (2026-07-19 pilot); aggregat `/opt/krowolf/storage/status/kapitel12_browser_report.json`; operations Del 7 + admin suppress/rotation PASS; `credentials_exposed=false`; `external_side_effects=0`. |
| Release decision K12 | `GO` | Browseraggregat PASS; backend **3589/0**; security **240/0**; frontend gates PASS; pilot `ADMIN_ROLE=admin`; scheduler pausad. |
| Browser matrix | `Verified (pilot CDP)` | read_only + operations (+ Del 7) + admin PASS; 7 viewports × 3 zoom; `/ops` primära sidor inkl. foundation/design-reference; rapport per roll under `storage/status/k12_browser_*_report.json`. |
| Browser safe boundaries | `Documented (pilot)` | Suppress **API PASS / UI not_mounted**; recovery/replay/reclassify/re-extract/resend/gmail **not_executed_safe_boundary**; controlled_dispatch approve **not_executed_safe_boundary** — permissions verifierade via security bundle + Del 7. |
| Legacy retirement | `Beslut B` | `docs/kapitel-12-slice3-legacy-parity.md` — read-only fallback; full 410 deferred post-pilot. |
| Security gate K12 | `Verified — PASS` | **240 passed**, 0 failed (2026-07-19 slutgate). |
| Full regression K12 | `Verified — PASS` | **3589 passed, 0 failed**, 4 warnings, ~22 s (2026-07-19); scheduler digest-test fix (`send_hour=0`); frontend typecheck/contracts/onboarding/build PASS; bundle ~552 KB JS. |

### Kapitel 6 — Incidenthantering (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| Incident models | `Verified (tests)` | `app/admin/incident_models.py` — four FK-free tables; explicit startup import before `create_all()`. |
| Schema registration test | `Verified (tests)` | SQLite `create_all` proves all four incident tables register. |
| Status transitions | `Verified (tests)` | Backend-enforced `ALLOWED_TRANSITIONS`; same-status → 409; `closed` terminal. |
| Concurrency | `Verified (tests)` | Atomic `UPDATE … WHERE version = :expected_version` + rowcount check. |
| Audit atomicity | `Verified (tests)` | `_add_audit_event_no_commit` + single `db.commit()` per write (not `AuditRepository.create_event`). |
| Signal identity | `Verified (tests)` | Exact `(tenant_id, signal_id)` match; frozen snapshot at link time. |
| Owner | `Verified (tests)` | Assign-self only; no owner in create/update request models. |
| Orphan policy | `Verified (tests)` | Soft-unlink; `tenant_name_snapshot`; no hard deletes. |
| Routes | `Verified (tests)` | Full CRUD-ish surface under `/admin/incidents`; `require_operator_role` + `require_same_origin` on writes. |
| Needs-help linking | `Verified (tests)` | `recommended_incident_action`, `linked_incidents.open/closed` on detail. |
| Frontend incidents | `Verified (local)` | `src/features/incidents/` — list, detail, create dialog, timeline, actions. |
| Security scan | `Verified (local)` | No secrets headers, no `dangerouslySetInnerHTML` in incidents feature. |
| Backend tests | `Verified (local)` | `tests/test_admin_incidents.py`; needs-help/operator-actions/tenant-directory/overview regressions pass. |
| Frontend gates | `Verified (local)` | typecheck, contracts, lint, build pass. |
| Manual responsive browser verification | `Still outstanding` | Not executed in this environment. |
| Not built | `Documented` | Auto-incident generation, notifications, attachments, SLA, bulk actions. |

### Kapitel 5 — Säkra operatörsåtgärder (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| Action registry | `Verified (tests)` | Six safe writes: `tenant.pause_automation`, `tenant.resume_automation`, `tenant.scheduler.pause`, `tenant.scheduler.resume`, `approval.reject`, `approval.approve` (`controlled_dispatch`, `email_send` only). No generic action engine. |
| Blocked actions | `Documented` | `job.manual_review.resolve` (Gmail side-effect risk), reclassify/re-extract/replay/critical writes — `Kräver manuell hantering`. |
| Role enforcement | `Verified (tests)` | `require_operator_role(allowed_roles)` dependency factory; server-derived `OperatorIdentity`; `read_only` → 403 on writes. |
| Request/response | `Verified (tests)` | `OperatorActionRequest` (`reason`, `confirmation: true`, optional `idempotency_key`); `OperatorActionResponse` with `completed`/`no_change`/etc. |
| Idempotency | `Verified (tests)` | State-based primary gate (pause/resume/scheduler no-op → `no_change`; approval state conflict → 409). `idempotency_key` audit-only; concurrent duplicate requests documented limitation. |
| Audit | `Verified (tests)` | `category=operator_action`; allowlisted `details` (operator, reason, safety_class, before/after state). Fail-closed 500 if audit write fails after state change. |
| Routes | `Verified (tests)` | Explicit POST routes under `/admin/tenants/{tenant_id}/…`; `require_same_origin` (Kapitel 1C). No `X-Tenant-ID` header from frontend. |
| `available_actions` | `Verified (tests)` | Backend-generated on needs-help detail + tenant overview; state-invalid omitted; `read_only` gets `allowed=false` + `blocked_reason`. |
| Frontend operatorActions | `Verified (local)` | `src/features/operatorActions/` — explicit API per action, mutations `retry: false`, `OperatorActionsSection` on customer detail + needs-help detail. |
| Security scan | `Verified (local)` | No `X-Admin-API-Key`, `localStorage`, dynamic execute URLs in `frontend/src` or `dist`. |
| Backend tests | `Verified (local)` | `tests/test_admin_operator_actions.py`; needs-help/tenant-directory regressions pass. |
| Frontend gates | `Verified (local)` | typecheck, contracts, lint, build pass. |
| Manual responsive browser verification | `Still outstanding` | Not executed in this environment. |

### Kapitel 1C — Operations shell and authentication (2026-07-17)

| Item | Status | Notes |
|------|--------|-------|
| Backend session extensions | `Verified (tests)` | Reuses `/auth/admin/login`, `/auth/admin/logout`, `/auth/admin/me`. Adds typed `operator` + `environment` on `/me` and login (session mode). `ADMIN_ROLE` fail-closed validator in `Settings`. `ALLOWED_ORIGINS` + `require_same_origin()` on login/logout POST. |
| Operator roles | `Verified (tests)` | `read_only`, `operations`, `admin` via `ADMIN_ROLE`. Invalid config fails startup; runtime defense never grants `admin` on invalid role. |
| Frontend auth feature | `Verified (local)` | `src/features/auth/` — AuthProvider, RequireAuth, RequireRole, LoginPage, forbidden/unauthorized pages. TanStack Query session state. |
| AppShell | `Verified (local)` | `AppShell.tsx` — sidebar (desktop), drawer (mobile), topbar, environment badge from `/auth/admin/me`, operator profile, logout. |
| Protected routes | `Verified (local)` | Live pages: overview, needs-help, customers, incidents, usage, system. `/ops/foundation` and `/ops/design-reference` require `admin`. |
| Route policy | `Verified (typed)` | `src/routes/routePolicy.ts` documents role requirements per path. |
| Security scan | `Verified (local)` | No `X-Admin-API-Key`, `localStorage`, `sessionStorage`, or `VITE_` secrets in `frontend/src` or `frontend/dist`. |
| Backend tests | `Verified (local)` | Extended `tests/test_admin_session.py` (role, environment, origin, secrets). `tests/test_operator_panel_static.py` smoke tests for new `/ops/*` paths. Auth/tenant regressions pass. |
| Frontend gates | `Verified (local)` | `tokens:generate`, `test:contracts`, `typecheck`, `lint`, `build` pass. |
| Real operational data | `Not built` | Placeholder pages only. |
| Tenant context | `Not built` | Reserved in AppShell layout only. |
| Manual responsive browser verification | `Still outstanding` | Login/AppShell checklist documented; not executed in this environment. |
| Kapitel 1A Docker verification | `Still outstanding` | Unchanged. |
| Kapitel 1B browser verification | `Still outstanding` | Unchanged. |

---

## Repo structure (verified)

| Path | Contents |
|------|----------|
| `app/` | Main application package |
| `frontend/` | Operator panel React/TS/Vite app (Kapitel 1A–9); `frontend/design/` JSON contracts; `frontend/src/features/auth/` + `overview/` + `customers/` + `needsHelp/` + `operatorActions/` + `onboarding/`; built to `frontend/dist`, served at `/ops` |
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
| `/integrations/google-sheets/export-job` | POST | Important — Sprint 3; manual job-to-Sheets export; fail-closed |

### Dashboard and Cases

| Endpoint group | Status |
|----------------|--------|
| `/dashboard/summary`, `/roi`, `/leads`, `/support`, `/activity`, `/kpis`, `/cockpit`, `/control`, `/sla-breaches`, `/operational-insights` | `Verified (code)` |
| `/cases`, `/cases/{id}`, `/cases/{id}/operations`, `/cases/{id}/followup`, `/cases/{id}/closeout`, `/cases/{id}/finance/export-status` | `Verified (code)` |
| `/cases/{id}/automation-wow` | `Verified (code)` |

### Admin

| Endpoint group | Status |
|----------------|--------|
| `/admin/onboarding` (+ session sub-routes, `/registries`, `/activation-plan`) | `Verified (tests)` — Kapitel 9 slice 1 |
| `/admin/tenants`, `/admin/tenants/overview`, `/admin/tenants/{id}/rotate-key`, `/admin/tenants/{id}/status` | `Verified (code)` — legacy script path; UI uses `/admin/onboarding` |
| `/admin/tenants/{id}/demo/seed` | `Verified (code)` |
| `/admin/recovery/{id}/retry|replay-dispatch|reclassify|re-extract|resend-approval|reprocess-gmail` | `Verified (code)` |
| `/admin/support/{id}/state|pause-automation|resume-automation|force-inbox-sync|disable-scheduler|enable-scheduler|ack-needs-help|clear-acknowledged` | `Verified (code)` |
| `/admin/usage/analytics`, `/admin/audit-events`, `/admin/operations/needs-help` | `Verified (code)` |
| `/admin/alerts` (summary, list, detail, acknowledge, snooze, resolve, suppress, registry) | `Verified (E2E)` — Kapitel 10 |
| `/admin/alert-evaluations` (run, status) | `Verified (E2E)` — Kapitel 10 |
| `/admin/operator-digests` (list, detail, generate, send) | `Verified (E2E)` — Kapitel 10 |
| `/admin/alerts/run-all` | `Verified (code)` — legacy tenant email + platform evaluation bridge |

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
| Current connection valid | `Partially verified — Phase L` | `MONDAY_API_KEY` SET (len=227), `MONDAY_BOARD_ID` SET; `/integrations/health` → `monday.status: warning, configured: True`. Live write not tested. |
| Production-ready | `Partially verified` | Code complete; API key present; live item-creation not tested (no write allowed in verification). |
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
| Code exists | `Verified` | `app/integrations/visma/oauth_service.py`, `oauth_routes.py`, `client.py`, `adapter.py`, `mappers.py`, `token_resolver.py` |
| OAuth exists | `Verified (code)` | Full authorize → exchange → refresh flow in `oauth_service.py`; `/callback` route and `/integrations/visma/oauth/callback` mounted |
| OAuth connected (demo tenant) | `Verified — production` | `T_NIKLAS_DEMO_001` sandbox/test account; `POST /integrations/visma/test-read` → `api_readable=true` (2026-07-16) |
| Read support | `Verified — production` | Company settings, fiscal years, terms of payment, articles, customers, customer invoices (read-only probes) |
| Write support | `Verified — production (approval-gated)` | `POST /finance/invoices/{job_id}/visma/export` → `approval_required`; approve once → `exported`; idempotent `already_exported` on repeat |
| Write safety | `Verified` | Tenant OAuth only (`token_resolver`); Visma auto-dispatch disabled; idempotency key per tenant+job; `reconciliation_required` on uncertain network |
| Export payload | `Verified` | PascalCase fields; `TermsOfPaymentId`, `FiscalYearId`, `ArticleId` on rows resolved from tenant API; synthetic customer lookup before create |
| Approval-gated | `Verified — production` | `next_on_approve=finance_visma_export`; no write before approval |
| Idempotency | `Verified — production` | Repeat export → `already_exported`; one success integration event per job |
| Auto-dispatch | `Verified — disabled` | Visma legacy dispatcher events marked dead; no automatic Visma writes |
| Generic execute route | `Verified — blocked` | `POST /integrations/visma/execute` write actions blocked |
| Uncertain network | `Verified (code)` | Export timeout/network → `reconciliation_required`; no blind retry |
| Quotations | `Not implemented` | No Visma quote export |
| Supplier invoices | `Not implemented` | No supplier invoice import |
| Tested | `Verified` | `test_visma_oauth.py`, `test_visma_write_safety.py` (23 tests) |
| Production-ready | `Partially verified` | One successful sandbox export on demo tenant; stale v1–v5 approvals rejected 2026-07-16; 5 failed integration events remain historical only |
| Sandbox artifacts | `Documented` | 2 sandbox customers + 2 Krowolf invoices in Visma test company (1 approval-gated v6 + 1 diagnostic from pre-fix validation); retained — no safe API delete path |
| First-customer relevance | Medium — optional pilot path after explicit rollout policy |

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
| Decision contract (2B) | `Verified — ADDED 2026-07-20` | `policy_authorization` internal truth; legacy `auto_execute`/`send_for_approval` in decisioning fail-closed; dispatch-boundary action authorization; per-action approvals; `tests/test_decision_contract.py`, `test_action_authorization.py`, `test_action_dispatch_authorization_boundary.py` |
| Decision trace (2C) | `Verified — ADDED 2026-07-20` | Append-only `decision_records`; `action_operation_id`; two-phase external write; `DECISION_RECORD_ENFORCE_WRITES`; `tests/test_decision_trace_2c.py` |
| Evaluation harness (2D) | `Verified — ADDED 2026-07-20` | `app/evaluation/`; 10 YAML scenarios + S18; smoke via `tests/evaluation/`; CLI `scripts/run_eval_harness.py`; DEC-035 |
| Approval-resume decision trace (2D.1) | `Verified` | PostgreSQL-tier sign-off 2026-07-21: `ai_platform_eval` @ PostgreSQL 18.3; baseline + SQL migrations 009→015; 014→015 upgrade; identity + unique indexes; concurrent CAS (1 winner / 1 idempotent loser); tenant purge via new engine; readiness pass/fail; S18 smoke; 7/7 `pg_eval`; full suite 3716 passed; `real_external_calls=0` |
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
- ~~**Gmail OAuth token validity unverified.**~~ **RESOLVED 2026-07-08.** New OAuth client `502012997563-gp9iku5erqff3u8tad923pk8mb7fsp8m` configured; token refresh confirmed working; inbox sync returned HTTP 200 with 8 real jobs.

### Important

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
- Production `docker-compose` currently contains DB password directly. Rotate and move DB password to `.env.production` after live verification checkpoint.
- SQLAlchemy/DB query logging appears verbose in production logs. Review and disable/minimize production SQL echo if not needed.

---

## Unverified claims

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
- [x] Verify `GET /health` returns `{"status":"ok"}` on target instance after deploying the local blocker fix. — **Done 2026-07-07.** HTTP 200, `app_name: Krowolf`, `env: production`.
- [ ] Verify `GET /pilot/readiness` returns passing state for pilot tenant.
- [ ] Verify `GET /integrations/health` reflects real Gmail and Monday state.
- [ ] Verify Gmail OAuth token is valid (or document that refresh is needed).
- [ ] Verify `GET /admin/tenants/overview` returns with `X-Admin-API-Key`.
- [ ] Confirm scheduler `run_mode` is set correctly for pilot tenant.
- [ ] Verify customer API key cannot access admin-level data endpoints.
- [ ] Run smoke check: `python scripts/smoke_check.py --base-url <url> --expect-production`.
