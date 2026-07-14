# Backlog

> Governed by `docs/00-master-plan.md`.
> Backlog items must be compatible with the master plan. No side tracks without a decision in `docs/07-decisions.md`.
> Historical done-items live in `docs/archive/legacy-06-backlog.md`.

---

## Completed (Fas 1 + Fas 2 prep)

### Fas 1 — Current Truth Audit (2026-07-04)
- [x] Run `python -m pytest` — 2475 passed, 1 failed. Documented in `docs/01-current-truth.md`.
- [x] Run `python -m scripts.run_release_gate_r1` — PASSED (487 regression + 152 E2E).
- [x] Endpoint audit — all actual routes in `main.py` documented.
- [x] Integration audit — all integration modules inspected and documented.
- [x] UI audit — all views in `index.html` documented.
- [x] Automation risk and approval gate audit — documented.
- [x] Tenant/auth audit — documented.
- [x] **AUDIT-BUG-01** | FIXED 2026-07-04 | `httpx` added to `requirements.txt`.
- [x] **AUDIT-BUG-02** | FIXED 2026-07-04 | Policy gate now fail-closed for unknown tenant IDs.
- [x] Local tenant/auth/customer-data isolation hardening — 42 isolation tests pass.

### Fas 2 prep — First tenant setup path (2026-07-05)

- [x] **First tenant setup path mapped and verified locally.** All provisioning endpoints verified via test suite.
- [x] **Pilot readiness verified** — 11 checks, deterministic, no external API calls. `test_production_readiness.py` passes.
- [x] **Integration health verified** — `not_configured` safely without live tokens, no secrets in response.
- [x] **Customer dashboard/status verified** — empty-state loads without crash.
- [x] **`docs/08-runbook.md`** — added "First internal pilot tenant setup" section (Steps 1–11 with curl commands).
- [x] **`docs/02-first-customer-plan.md`** — added "Local pre-live setup checklist" (11 items).
- [x] **Flaky test fixed**: `test_sla_pass_already_run_today_skips` — timezone mismatch (`date.today()` vs UTC). Fixed.

### Fas 2 local hardening — Core Intelligence Quality Pass (2026-07-06)

- [x] **Core intelligence inventory completed locally** — classification, lead/support analyzers, invoice processing, policy, handoff, action dispatch, and customer reply drafting inspected.
- [x] **Deterministic Swedish eval suite added** — `tests/test_core_intelligence_quality.py` covers installation-company scenarios for classification, qualification, missing info, risk, approval/handoff, customer replies, low-risk routing, and high-risk do-not-touch behavior.
- [x] **Classification fallback improved** — empty/unclear and wrong-recipient input now becomes `unknown`; support/risk phrases beat broad lead keywords; Swedish spam/sales outreach is detected.
- [x] **Do-not-touch/risk logic added** — legal threats, reklamation, contract disputes, inkasso/betalningskrav, safety risk, sensitive personal data, data deletion, financial changes, and mass-send intent force manual review.
- [x] **Customer replies hardened** — sensitive lead/customer-inquiry replies are approval-gated non-binding acknowledgements and hand off to a responsible human.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2510 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Swedish Extraction & Qualification Quality Pass (2026-07-06)

- [x] **Extraction/qualification inventory completed** — `ai_processor_utils.py`, `lead/analyzer.py`, `lead/missing_info.py`, `support/analyzer.py`, `ai/schemas.py`, and `lead/models.py` mapped as controlling files.
- [x] **Swedish address extraction added** — `extract_swedish_location(text)` in `ai_processor_utils.py`: extracts street address, postal code (NNN NN), city (after postal code or preposition), property type (villa/brf/lantbruk/lägenhet/lokal), and fastighetsbeteckning. No LLM required.
- [x] **Org number extraction added** — `extract_org_number(subject, body)` matches Swedish format NNNNNN-NNNN.
- [x] **OCR / payment reference extraction added** — `extract_ocr_number(subject, body)` handles "OCR-nummer:", "betalningsref (OCR):", and similar Swedish bank giro label patterns.
- [x] **Invoice risk level detection added** — `detect_invoice_risk_level(subject, body)` returns "high_risk" (inkasso/kronofogden/kravbrev), "medium_risk" (betalningspåminnelse/förfallodatum passerat), or "normal". Inkasso/debt collection never enters low-risk automation.
- [x] **Lead missing-info address detection from text** — `_field_present("address")` now runs the new location extractor over raw text when entity dict has no address/city. Addresses inline in Swedish messages now satisfy the completeness check.
- [x] **Lead analyzer: expanded work-type keywords** — `electrical_work` now detects "felsökning", "nätanslutning", "jordfelsbrytaren löser", "säkringen löser". `solar_installation` now detects "växelriktare"/"inverter".
- [x] **Lead analyzer: lantbruk customer type** — "lantbruk", "gård", "jordbruk", "lantgård" map to `private` customer type.
- [x] **Support analyzer: electrical safety urgency** — "luktar bränt", "gnistor", "gnistrar" added to `_EMERGENCY_KEYWORDS` and `_URGENCY_KEYWORDS["critical"]`. Fires both `emergency` ticket type and `safety` category.
- [x] **Support analyzer: electrical fault issue keywords** — "jordfelsbrytaren löser", "säkringen löser", "växelriktaren", "inga solceller" added to `issue` ticket type keywords.
- [x] **Support analyzer: post-installation warranty detection** — "ni installerade", "installerade hos oss", "sedan ni installerade" added to `warranty` ticket type keywords.
- [x] **Support analyzer: frustrated escalation** — `requires_human` now includes `frustrated` in addition to `angry` sentiment (repeated-contact / recurring-fault cases escalate to human review).
- [x] **Swedish extraction eval suite added** — `tests/test_swedish_extraction_quality.py`, 61 deterministic tests covering all 8 focus areas.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2571 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Service Profiles & Qualification Schemas (2026-07-06)

- [x] **Service profile module created** — `app/service_profiles/` package: `models.py` (ServiceProfile frozen dataclass), `registry.py` (10 profiles), `qualification.py` (select, compute, build_message, tenant_seam), `__init__.py`.
- [x] **10 first service profiles defined** — generic_lead, generic_support, ev_charger_installation, solar_installation, battery_storage, electrical_fault, inverter_support, electrical_panel, invoice_generic, debt_collection_risk. Each has keywords, required_fields, optional_fields, risk_flags, routing defaults, and Swedish follow-up questions.
- [x] **Profile selection implemented** — `select_profile(job_type, lead_type, support_category, text, tenant_ctx)` routes deterministically through invoice → support → lead → fallback hierarchy.
- [x] **Service-specific missing fields** — `compute_profile_missing_info()` detects 20+ field types per profile, including profile-specific fields (safety_risk, desired_location, production_status, inverter_model_or_error_code, etc.).
- [x] **Service-specific Swedish follow-up questions** — `build_profile_question_message()` uses profile intro + question labels. `generate_question_message()` patched with optional `service_profile` param (backward-compatible).
- [x] **Risk profiles always manual_review** — debt_collection_risk has default_route, complete_action, and missing_info_action all = manual_review. Electrical safety risk_flags trigger high_risk_action = manual_review via `resolve_action()`.
- [x] **Tenant override seam** — `apply_tenant_overrides()` applies routing_hint overrides when tenant context is present; schema overrides applied in `compute_profile_missing_info`. Documented as future onboarding connection point.
- [x] **Service profiles eval suite added** — `tests/test_service_profiles_qualification.py`, 82 deterministic tests covering registry, selection, required fields, missing fields, follow-up questions, risk routing, and tenant override seam.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2653 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Local Final Spurt before Live (2026-07-06)

- [x] **Service profiles wired into lead pipeline** — `lead_analyzer_processor.py` calls `select_profile()` after `analyze_lead()`; passes `service_profile` to `generate_question_message()`; `service_profile_type` added to payload.
- [x] **Service profiles wired into support pipeline** — `support_analyzer_processor.py` calls `select_profile()` after `analyze_support()`; `service_profile_type` added to payload.
- [x] **Customer auto-reply quality (lead)** — `_build_lead_default_actions` reads `generated_question_message` from lead_analyzer payload and uses it for the customer auto-reply body; falls back to generic questions if not available.
- [x] **Customer auto-reply quality (inquiry)** — `_build_inquiry_default_actions` reads `support_generated_question_message` from support_analyzer payload and uses it for the customer auto-reply body; falls back to generic questions if not available.
- [x] **Risk/high-risk reply enforcement** — Sensitive cases (inkasso, legal threat, complaint, safety risk) use `_build_sensitive_customer_ack` with `_needs_approval=True`; no legal/financial commitment in reply body.
- [x] **Tenant routing hints verified** — `apply_tenant_overrides()` applied in `select_profile()` for both lead and support; `tenant_ctx.routing_hints[service_type]` overrides `default_route` without changing other fields.
- [x] **Tenant-specific required fields verified** — `compute_profile_missing_info()` checks `tenant_ctx.schema_for(service_type)` and applies tenant schema when present; `schema_source` correctly reflects override.
- [x] **Company name in replies** — `build_profile_question_message()` personalises intro with `company_name` when available from tenant context.
- [x] **Debt collection risk detection fixed** — Added "inkassokrav", "inkassobolag", "betalningsanmärkning" to `intelligence_safety._RISK_KEYWORDS["debt_collection"]`.
- [x] **Solar plural keyword fix** — Added "solceller", "solpaneler" to `lead/analyzer.py` solar_installation keywords so standard plural forms trigger correct profile selection.
- [x] **Service profile field presence: entity fallback** — `_profile_field_present` now handles `phone` and `email` via text regex + entity dict; generic entity-based fallback added for other entity fields.
- [x] **Test suites for pipeline wiring** — `tests/test_service_profile_pipeline.py` (25 tests) covering profile selection, lead_analyzer wiring, support_analyzer wiring, missing-info computation, and question generator integration.
- [x] **Test suites for customer reply quality** — `tests/test_customer_reply_quality.py` (22 tests) covering low-risk profile-aware replies, high-risk safe acknowledgements, non-binding language, signature, followup disable.
- [x] **Test suites for tenant routing hints** — `tests/test_tenant_routing_hints.py` (15 tests) covering routing override, required field override, company name, and tenant schema seam.
- [x] **Local golden path test suite** — `tests/test_local_golden_path.py` (20 tests) covering EV charger, solar, debt collection, electrical fault, and tenant routing golden paths end-to-end locally.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2735 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Local Cleanup/Consistency-Pass before Live Verification (2026-07-06)

- [x] **`docs/01-current-truth.md` test file count corrected** — repo structure table now shows "101 test files (see Test status above)" matching actual count and top-level test status.
- [x] **`docs/01-current-truth.md` customer-safe isolation wording updated** — now clearly distinguishes: customer-safe API responses (verified locally), tenant/admin/customer server-side isolation (verified locally), customer visual UI separation (partially verified code/static), live browser/session validation (deferred to live verification). Known-issues note updated accordingly.
- [x] **`profile_missing_fields` wired into lead pipeline** — `lead_analyzer_processor` now calls `compute_profile_missing_info(service_profile, ...)` and exposes `profile_missing_fields` and `profile_completeness_score` in payload. `generate_question_message` uses profile-specific missing fields for question content (fallback to generic if empty).
- [x] **Support question generator accepts `service_profile`** — `generate_support_question_message` now has optional `service_profile` parameter; uses `build_profile_question_message` for non-emergency/non-safety tickets; `support_analyzer_processor` passes `service_profile` to it.
- [x] **`_has_safety_risk` extended for `ticket_type=="safety"`** — ensures safety-typed tickets always get the safety disclaimer and bypass profile question generation, regardless of message content.
- [x] **Duplicate `_resolve_customer_reply_target` call removed** — redundant second call in `action_dispatch_processor._build_lead_default_actions` removed; behavior unchanged.
- [x] **9 new tests added to `test_service_profile_pipeline.py`** — covers `profile_missing_fields`/`profile_completeness_score` in lead payload, profile question content for EV charger, inverter support profile questions, emergency/safety bypass regression, and no-profile fallback.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2744 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Deferred — live verification phase

Full live verification plan: `docs/10-live-verification-plan.md` — production deploy completed 2026-07-07 on `/opt/krowolf` with live commit `87d9369`. Phase A-C, D, E, F, G, H, I, and J passed 2026-07-07. Phase K BLOCKED (Gmail invalid_grant). Full live verification not complete.

**Phase A — Pre-flight**
- [x] Confirm full local test suite passes immediately before live session — 2026-07-07 final pre-live UI simplification run: 2746 passed, 0 failed, 4 warnings.
- [x] Confirm R1 gate passes immediately before live session — 2026-07-07: 505 regression + 152 E2E passed.
- [x] Resolve unclear `app/ui/index.html` dirty state — previous fancy CSS/card-contrast styling replaced with minimal Internal Operator Console.
- [x] Deploy latest code before Phase A-C re-run — completed on `/opt/krowolf`; live commit `87d9369`; Docker Compose file `/opt/krowolf/docker-compose.prod.yml`; containers `krowolf-app-1`, `krowolf-db-1`, and `krowolf-caddy-1` running.
 - [x] Operator confirmation required before Phase D — DB backup taken (`pre-phase-d-20260707-190618.sql`); app/db/caddy containers running; admin key confirmed working; no real customer tenants modified.

**Phase B — Production health**
- [x] `GET https://api.krowolf.se/` → HTTP 200, `env: production`.
- [x] `GET https://api.krowolf.se/health` → HTTP 200, `env: production`.
- [x] Confirm `/docs` and `/openapi.json` return 404 in production.

**Phase C — Admin/auth**
- [x] Admin endpoint without key → 401.
- [x] Admin endpoint with wrong key → 401.
- [x] Admin endpoint with correct key → 200; existing tenants: `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1`.
- [x] Tenant key rejected on admin endpoint → 401 — verified in Phase D.

**Phase D — Tenant provisioning**
- [x] DB backup taken before Phase D — `pre-phase-d-20260707-190618.sql` (677 KB).
- [x] `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1` confirmed untouched.
- [x] `POST /admin/tenants` creates `T_LIVE_TEST_001` — HTTP 201, `status: active`.
- [x] `GET /admin/tenants` shows `T_LIVE_TEST_001` listed correctly.
- [x] `GET /tenant` with tenant key → HTTP 200.
- [x] `GET /pilot/readiness` → `almost_ready` (6 pass, 5 warnings, 0 failures — expected pre-integration).
- [x] `GET /integrations/health` → `warning`, no secrets in response.
- [x] Tenant key on `/admin/tenants` → HTTP 401 — isolation confirmed.
- [x] `GET /jobs` with `T_LIVE_TEST_001` key → empty list; no cross-tenant data.

**Phase E — Tenant/customer endpoint isolation and readiness**
- [x] All `/tenant`, `/customer/*`, `/jobs`, `/audit-events`, `/integration-events`, `/tenant/context`, `/tenant/memory`, `/integrations/health`, `/pilot/readiness` with tenant key → HTTP 200.
- [x] All above endpoints without key → HTTP 401.
- [x] Admin key on tenant endpoint (`/jobs`) → HTTP 403.
- [x] Tenant key on admin endpoint (`/admin/tenants`) → HTTP 401.
- [x] Wrong `X-Tenant-ID` header with correct key → HTTP 200 (correct: header ignored per auth design; tenant resolved from key).
- [x] No secrets, stack traces, or 500s in any response or logs.
- [x] No cross-tenant data (`T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1`) visible via `T_LIVE_TEST_001` key.
- [x] SQL logs show only `T_LIVE_TEST_001` queries; key values stored as SHA-256 hash only.

**Phase F — Safe synthetic intake/job flow**
- [x] `auto_actions: false` for all job types confirmed before first write.
- [x] `POST /jobs` with synthetic lead payload → HTTP 200; `job_id: bea23f74-...`; `tenant_id: T_LIVE_TEST_001`.
- [x] Pipeline ran to completion: `status: completed`, `requires_human_review: False`, `summary: "Ingen manuell överlämning behövs."`, 0 external actions dispatched.
- [x] `GET /jobs/:id` → HTTP 200; scoped to `T_LIVE_TEST_001`; no secrets.
- [x] Jobs list → only `T_LIVE_TEST_001` data; no cross-tenant entries.
- [x] Audit events → no external write events; no cross-tenant data.
- [x] Integration events → no external write events.
- [x] App logs → no Gmail/Monday/Fortnox/Visma writes; no 500s or stack traces.
- [x] `GET /jobs/:id` without key → HTTP 401.
- [x] Wrong `X-Tenant-ID` + correct key on specific job → HTTP 200 scoped to `T_LIVE_TEST_001` (header ignored per auth design).
- [x] Synthetic job `bea23f74-1dbe-4424-a8cb-60262da92f9b` retained under `T_LIVE_TEST_001` as Phase F evidence.

**Phase D — Tenant provisioning**
- [ ] `POST /admin/tenants` creates T_INTERN_PILOT, returns api_key (once).
- [ ] `GET /admin/tenants` shows T_INTERN_PILOT, no api_key in response.
- [ ] `GET /tenant` with tenant key returns `current_tenant: T_INTERN_PILOT`.
- [ ] Tenant key cannot reach `/admin/tenants`.
- [ ] `GET /pilot/readiness` shows expected not_ready/almost_ready state.

**Phase E — Customer endpoints**
- [ ] All `/customer/*`, `/integration-events`, `/tenant/context`, `/tenant/memory` require API key.
- [ ] No secrets in customer endpoint responses.

**Phase F — Integration health**
- [ ] `GET /integrations/health` returns safely without live tokens (not_configured).
- [ ] No token values in integration health response.


**Phase G — Approval queue / manual review**
- [x] Approval endpoints identified: `GET /approvals/pending`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject` — all tenant-scoped; reject safe (no external writes).
- [x] Synthetic `customer_inquiry` created with `force_approval_test: true` → HTTP 200; `job_id: 8b2d53d2-cc44-4d45-a11b-5a4a60654bb0`; `status: awaiting_approval`.
- [x] `GET /jobs/:id` → HTTP 200; `status: awaiting_approval`; `result.summary: "Approval dispatched via dashboard."`.
- [x] `GET /approvals/pending` → HTTP 200; `approval_id: f5d27fc3-071c-41f0-ba65-c9f052f591b3`; `next_on_approve: action_dispatch`; no cross-tenant data.
- [x] `/approvals/pending` without key → HTTP 401.
- [x] Wrong tenant header + T_LIVE_TEST_001 key → HTTP 200 scoped only to T_LIVE_TEST_001 (header ignored per auth design).
- [x] `POST /approvals/:id/reject` → HTTP 200; job status → `manual_review`; no external writes.
- [x] Approval removed from pending queue after reject; T_ELITGRUPPEN/TENANT_2001/T_TEST1 absent.
- [x] Audit events → no cross-tenant data; no external write events.
- [x] Integration events → no external write events.
- [x] App logs → no 500s, no stack traces, no external writes.
- [x] 24/24 checks passed; 0 failures; 0 warnings.
- [x] Phase F email_send approval (eml_adeaf87...) remains pending — non-blocking; consider rejecting via dashboard before pilot.

**Phase H — Integration health/OAuth readiness**
- [x] `GET /integrations/health` → 200; `overall_status: warning`; gmail configured but not OAuth-synced; no secrets; no cross-tenant.
- [x] `GET /integrations` → 200; Monday.com and Google Mail listed as enabled; no secrets.
- [x] `GET /setup/status` → 200; `readiness.score: 90, status: ready`; `google_mail: true, monday: true, fortnox: false, visma: false`.
- [x] `GET /pilot/readiness` → 200; `almost_ready`.
- [x] `GET /integrations/visma/status` → 200; `disconnected`; no tokens.
- [x] `GET /integrations/visma/oauth/url` → 503; not configured; safe.
- [x] `/oauth/start` and `/oauth/callback` — skipped (out of scope).
- [x] `GET /integration-events` → 200; no external write events; no cross-tenant.
- [x] `GET /audit-events` → 200; no cross-tenant; no secrets.
- [x] `GET /integrations/health` without key → 401.
- [x] Wrong `X-Tenant-ID` + correct key → 200 scoped to T_LIVE_TEST_001 only.
- [x] Phase F email_send approval (eml_adeaf87...) found and safely rejected (cleanup). No external write.
- [x] App logs clean — no 500s, no secrets, no external writes.
- [x] 42/42 checks passed; 0 failures; 1 warning (expected cleanup).

**Phase I — UI / read-only dashboard verification**
- [x] `GET https://app.krowolf.se/ui` → 200; "Internal Operator Console" confirmed in HTML; all operator sections present.
- [x] `GET https://api.krowolf.se/ui` → 200; same HTML.
- [x] Cache-bust request → 200; same content.
- [x] No-key: /tenant, /jobs, /approvals/pending → all 401.
- [x] Tenant read-only: /tenant, /customer/health, /customer/results, /customer/activity, /customer/account → all 200; T_LIVE_TEST_001 scoped; no secrets.
- [x] /pilot/readiness → 200; almost_ready.
- [x] /integrations/health → 200; overall_status: warning.
- [x] /jobs → 200; total=2 (Phase F+G synthetics only); no cross-tenant.
- [x] /approvals/pending → 200; 0 pending (clean after Phase H).
- [x] /audit-events → 200; T_LIVE_TEST_001 only.
- [x] /admin/tenants without key → 401; with admin key → 200; no api_key values in list.
- [x] Browser check: "Internal Operator Console" title confirmed; login form visible; no plaintext keys; minimal internal UI; no cached fancy SaaS dashboard. Screenshot taken 2026-07-07.
- [x] App logs clean — no 500s, no stack traces, no secrets.
- [x] 58 actual pass, 0 true fail; 3 script false-positives on HTML variable names (not actual values).

**Phase J — Gmail OAuth readiness/connection planning**
- [x] Gmail config: `GOOGLE_MAIL_ACCESS_TOKEN` (len=253), `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` — all SET. Env var names match `settings.py` exactly.
- [x] Token model: static env-var tokens — no browser OAuth consent URL flow. No consent route exists in app.
- [x] Sync routes identified but NOT called: `POST /gmail/process-inbox`, `POST /workflow-scan/gmail`, `POST /dashboard/inbox-sync`.
- [x] All Google OAuth URL/start/callback routes → 404 (not implemented — correct for static token model).
- [x] `GET /workflow-scan/status` → 200; `status: never_run` — inbox sync never executed.
- [x] `/integrations/health` → gmail.status: warning, configured: True (warning = not scanned yet).
- [x] `/setup/status` → `google_mail: True, email_connected: True, readiness.score: 90`.
- [x] `/pilot/readiness` → almost_ready; warnings: onboarding steps, routing hints, integration events.
- [x] No Gmail events in integration-events or audit-events.
- [x] Logs: no 500s, no tokens, no inbox sync, no Gmail writes.
- [x] 32/32 pass; 0 fail; 1 false-positive warn.
- [x] Phase K attempted 2026-07-07 — BLOCKED: Gmail invalid_grant (GOOGLE_OAUTH_REFRESH_TOKEN revoked/expired). Fix: regenerate OAuth tokens, update .env.production, restart app, rerun Phase K.

**Phase K — Gmail inbox sync (PASSED 2026-07-08)**
- [x] `POST /gmail/process-inbox` dry_run=true → HTTP 200; 0 new jobs (correct).
- [x] `POST /gmail/process-inbox` dry_run=false → HTTP 200; **8 real jobs created** from Gmail inbox.
- [x] `auto_actions: false` — no external dispatch triggered.
- [x] Token refresh working: new Google OAuth client `502012997563-gp9iku5erqff3u8tad923pk8mb7fsp8m` configured.
- [x] Container recreated with `docker compose up -d` (env vars require recreation, not just restart).
- [x] Phase K blocker removed. Phase O unblocked.

**Phase O — Final go/no-go pilot checklist (CONDITIONAL GO 2026-07-08)**
- [x] O1: Production health — `/` + `/health` → 200 production; `/docs` + `/openapi.json` → 404. All pass.
- [x] O2: Tenant readiness — T_LIVE_TEST_001 active; auto_actions=false; score=90; pilot/readiness=almost_ready (7p 4w 0f); no secrets.
- [x] O3: Gmail jobs — 10 total (2 synthetic + 8 Gmail); all ext_actions=0; all T_LIVE_TEST_001 scoped; no secrets.
- [x] O4: Pending approvals — 1 pending (eml_5d69..., action_dispatch, next_on_approve=email_send); not approved; cross-tenant absent.
- [x] O5: Events — 50 audit events (no external writes); 0 integration events; no secrets.
- [x] O6: Cross-tenant isolation — header ignored per design; T_ELITGRUPPEN data not exposed.
- [x] O7: Operator UI — app.krowolf.se/ui → 200; Operator Console confirmed; no secrets.
- [x] O8: Logs — no risky patterns in tail=1200; no 500s, tokens, writes.
- [x] O9: Cleanup review documented. All GO criteria met. CONDITIONAL GO issued.
- [x] 29/29 pass; 0 fail; 0 warn.
- [ ] **CONDITION**: Set support email `PUT /dashboard/control` for T_LIVE_TEST_001.
- [ ] **CONDITION**: Review pending approval `eml_5d69...` (email_send) — reject if not intentional.
- [ ] **CONDITION**: DB password rotation (maintenance window required).

**Phase N — Production hardening cleanup (PASSED 2026-07-07)**
- [x] N1: Hardening inventory confirmed — ENV=production, APP_NAME=Krowolf, all key env vars SET.
- [x] N2: SQL echo source identified — `echo=True` hardcoded in `database.py`.
- [x] N3: SQL echo fixed — `DB_ECHO: bool = False` added to `settings.py`; `database.py` now uses `echo=settings.DB_ECHO`; 2746 tests pass; committed as `01f5763`; Docker image rebuilt on server; `sql_echo_count_tail30=0` confirmed.
- [x] N4: Support email state inspected — empty `''`; set via `PUT /dashboard/control` (NOT env var); operator must confirm value before setting; suggested `support@krowolf.se` not yet applied.
- [x] N5: DB password hardening plan documented — password currently hardcoded in compose; safe rotation plan written in `docs/01-current-truth.md`; not executed (maintenance window required).
- [x] N6: Gmail token fix plan documented.
- [x] N7: Post-rebuild health: `/` + `/health` 200; `/docs`+`/openapi.json` 404; all tenant endpoints 200.
- [x] N8: Logs risk search: no risky patterns; SQL echo confirmed eliminated in production.
- [x] 2746 tests pass; commit `01f5763` live on server.
- [ ] Phase K remains BLOCKED.

**Phase M — Final pre-pilot cleanup/status consolidation (PASSED 2026-07-07)**
- [x] Server/container status: commit `87d9369`; app/db/caddy Up; no restart loop; no 500s.
- [x] Production health: `/` and `/health` → 200 `env: production`; `/docs` + `/openapi.json` → 404.
- [x] `/tenant` → 200; `T_LIVE_TEST_001` active; name: Live Test Tenant.
- [x] `/setup/status` → score 90, status ready; connections: google_mail✓ monday✓ fortnox✗ visma✗.
- [x] `/pilot/readiness` → `almost_ready`; 7 pass, 4 warn, 0 fail.
- [x] `/integrations/health` → `warning`; gmail+monday configured; fortnox not_configured.
- [x] `/jobs` → 2 synthetic jobs (Phase F+G evidence retained); no cross-tenant.
- [x] `/approvals/pending` → 0 (queue clean).
- [x] `/audit-events` + `/integration-events` → no external write events; no cross-tenant; no secrets.
- [x] Backups: pre-Phase-D backup + 16 daily automated backups; `.env.production`/compose/Caddyfile present.
- [x] Logs risk search (tail=1000): no risky patterns; no leaked tokens; no write events.
- [x] 8 known cleanup items confirmed documented.
- [x] 50/50 pass; 0 fail; 0 warn.
- [ ] Phase K remains BLOCKED — Gmail `invalid_grant` carried forward.

**Phase L — Monday readiness/no-write verification (PASSED 2026-07-07)**
- [x] `MONDAY_API_KEY` SET (len=227), `MONDAY_BOARD_ID` SET — Monday configured.
- [x] `/integrations/health` → `monday.status: warning, configured: True` — health check passes.
- [x] `/setup/status` → `connections.monday: True`, score 90 — Monday connection confirmed.
- [x] `/integrations/monday/status` → 404; `/integrations/monday/health` → 404 — controlled, no dedicated route (health bundled).
- [x] `POST /integrations/monday/execute` without key → 401 — write endpoint protected.
- [x] No Monday write events in integration-events or audit-events.
- [x] No 500s, no stack traces, no leaked tokens in logs.
- [x] Negative auth: 401 without key; cross-tenant scoping confirmed for T_LIVE_TEST_001.
- [x] Phase K Gmail blocker visible in logs (historical, expected).
- [x] 30 pass, 0 true fail, 2 false-positive script FAILs (explained).

**Phase G — Gmail OAuth and inbox sync**
- [ ] Gmail OAuth flow completed for pilot tenant.
- [ ] `GET /integrations/health` → `gmail.status: healthy`.
- [ ] Inbox sync creates case from test email.
- [ ] Outbound email requires approval (not auto-sent).

**Phase H — Monday/Fortnox/Visma safe checks**
- [ ] Monday integration health reflects correct state.
- [ ] Fortnox export confirmed approval-gated.
- [ ] Visma: not_configured (not required for first pilot).

**Phase I — Approval queue E2E**
- [ ] Test lead → awaiting_approval → approve → completed.
- [ ] Audit event created, tenant-scoped.

**Phase J — Customer UI**
- [ ] Customer dashboard loads after test jobs.
- [ ] No admin-only data in customer view.

**Phase K — Smoke check**
- [ ] `python scripts/smoke_check.py --base-url https://api.krowolf.se --expect-production` passes.

**Phase L — Go/no-go**
- [ ] All 16 gates in `docs/10-live-verification-plan.md` are green.
- [ ] Named support owner confirmed for pilot tenant.

---

### Sprint 3 — Google Sheets manual export (2026-07-14)

- [x] **Google Sheets adapter created** — `app/integrations/google/sheets_client.py`: real `GoogleSheetsClient` (Sheets v4 REST API, appends rows via USER_ENTERED) and `MockGoogleSheetsClient` (in-memory, for tests). Uses existing Google OAuth access token.
- [x] **Row mapper created** — `app/integrations/google/sheets_row_mapper.py`: `choose_tab()` for auto/explicit routing; `build_leads_row()` (12 cols), `build_support_row()` (12 cols), `build_logg_row()` (6 cols). Extracts sender, processor history fields, status, source.
- [x] **Manual export endpoint added** — `POST /integrations/google-sheets/export-job` in `app/main.py`. Body: `{"job_id": "...", "target": "auto"|"leads"|"support"|"logg"}`. Auth: X-API-Key (tenant).
- [x] **Tenant config support added** — `allowed_integrations` must include `"google_sheets"`. `settings.google_sheets.spreadsheet_id` must be set. Both fail-closed.
- [x] **Audit event created on export** — `create_audit_event` called with `category="integration"`, `action="google_sheets_export"`, `status`, and `details` (job_id, tab, spreadsheet_id, error).
- [x] **Integration event created on export** — `IntegrationEvent` row added with `integration_type="google_sheets"`, idempotency key, tab, spreadsheet_id, and status for observability.
- [x] **Safety gates verified** — (1) `google_sheets` not in `allowed_integrations` → `integration_not_allowed`; (2) `spreadsheet_id` empty/missing → `configuration_missing`; (3) wrong-tenant job → 404; (4) no access token → `configuration_missing`; (5) no auto-export from Gmail processing.
- [x] **Test suite added** — `tests/test_google_sheets_export.py`: 50 tests covering row mapper (choose_tab, build_leads_row, build_support_row, build_logg_row), MockGoogleSheetsClient, all endpoint safety gates, adapter called exactly once, audit event created, row_count in response, tenant-specific spreadsheet_id used, and no-auto-export pipeline checks.
- [x] **Full test suite verified** — `python -m pytest --tb=no -q` → 3140 passed, 0 failed, 4 warnings (2026-07-14). Sprint 1, 2, 2B tests all unaffected.

### Sprint 4 — AI Receptionist test-customer onboarding package (2026-07-15)

- [x] **Onboarding checklist created** — `docs/ai-receptionist-test-customer-onboarding.md`: purpose, prerequisites, step-by-step tenant setup, API key handling, Gmail label/query setup, Google Sheet setup, approval-first settings, safety checklist, what NOT to enable, rollback/stop procedure, reference commands.
- [x] **Test mail scenarios created** — `docs/ai-receptionist-test-mail-scenarios.md`: 8 core scenarios (EV charger, laddbox fault, battery add-on, solar issue, emergency, VVS, build/carpentry, complaint) with expected job_type, playbook, context, approval behavior, and sheet tab.
- [x] **MVP Gate created** — `docs/ai-receptionist-mvp-gate.md`: chapter-level verification checklist (Sections A–H) covering Gmail ingestion, playbook quality, safety routing, approval-first, Sheets export, tenant isolation, allowlist enforcement, and observability. Clear PASS/PASS WITH NOTES/BLOCKED/FAIL status. GO/NO-GO criteria defined.
- [x] **Friend test guide created** — `docs/ai-receptionist-friend-test-guide.md`: Swedish non-technical guide for test users explaining what Krowolf does, what to send, what to expect, feedback requested, and safety expectations.
- [x] **Helper script created** — `scripts/print_ai_receptionist_test_setup.py`: prints tenant settings, Gmail setup, Sheets column/tab structure, safety checklist, and scenario table. Read-only, no dependencies. Syntax verified.
- [x] **No code changed** — Sprint 4 is documentation only. No tests run (none required).
- [x] **Deferred confirmed** — UI, Visma writes, Outlook/SMS, auto-export, and Monday remain deferred per master plan.
- [x] **Next step defined** — Run `docs/ai-receptionist-mvp-gate.md` against live environment before first friend test.

## Now (pre-live blockers)

### Completed in Phase 2 prep

- [x] **First tenant setup path mapped and verified locally.** All endpoints (`POST /admin/tenants`, rotate-key, status, `GET /pilot/readiness`, `GET /integrations/health`, `GET /onboarding/status`, `POST /onboarding/test-lead`, `POST /verify/{tenant_id}`) verified via test suite.
- [x] **Pilot readiness verified** — 11 checks, all deterministic, no external API calls. `test_production_readiness.py` (169 tests) passes.
- [x] **Integration health verified** — reports `not_configured` safely without live tokens, no secrets in response. `test_integration_health.py` passes.
- [x] **Customer dashboard/status verified** — empty-state loads without crash. `test_customer_saas_surfaces.py` passes.
- [x] **`docs/08-runbook.md`** — added "First internal pilot tenant setup" section with concrete curl commands (Steps 1–11).
- [x] **`docs/02-first-customer-plan.md`** — added "Local pre-live setup checklist" (11 items).
- [x] **Flaky test fixed**: `test_sla_pass_already_run_today_skips` used `date.today()` (local TZ) vs UTC production code. Fixed to use `datetime.now(timezone.utc)`.

### Local blocker status

`GET /health` blocker is fixed locally and covered by tests.
`app/ui/index.html` is no longer an unknown fancy dirty state: it has been intentionally simplified into an Internal Operator Console with minimal black/white styling and included in the production deploy used for the passed Phase A-C checkpoint.
Production deploy and Phase A-C re-run completed on 2026-07-07. Live commit after Phase N hardening is `01f5763`. Phase D, E, F, G, H, I, J, K, L, M, N, and O PASSED. Phase O: **CONDITIONAL GO (2026-07-08)**. Next: prepare first controlled pilot run with real tenant. Conditions: set support email, review pending approval, rotate DB password.

### Remaining local quality gaps

- [ ] Broaden deterministic extraction for Swedish addresses/property details beyond current keyword/entity coverage.
- [ ] Add more tenant-specific eval scenarios once the first pilot tenant's real service taxonomy and routing hints are known.
- [ ] Consider wiring deterministic support analysis output more directly into older AI-backed `customer_inquiry_processor` payloads if pilot feedback shows operator UI needs one consolidated payload.
- [ ] Production `docker-compose` currently contains DB password directly. Rotate and move DB password to `.env.production` after live verification checkpoint.
- [x] SQLAlchemy SQL echo verbose in production — FIXED in Phase N. `DB_ECHO: bool = False` now default; `database.py` uses `echo=settings.DB_ECHO`. Committed `01f5763`, Docker image rebuilt, SQL echo eliminated in production.

### Pre-live blockers (require live environment)

- [ ] `ADMIN_API_KEY` must be set to strong random value in production.
- [ ] Correct admin-key success path must be verified with real `ADMIN_API_KEY` against a read-only admin endpoint such as `GET /admin/tenants`; do not print the key in reports.
- [ ] Operator must confirm `ENV=production`, non-empty `ADMIN_API_KEY`, `DATABASE_URL`, latest deployed code/container, Caddy/reverse proxy running, and DB backup completed before Phase D.
- [ ] Gmail OAuth flow must be completed for pilot tenant (`GET /auth/gmail/start?tenant_id=...`).
- [x] Monday `MONDAY_API_KEY` is SET (len=227) and `MONDAY_BOARD_ID` is SET — Phase L confirmed. Live item-creation not tested (intentional — no write in verification).
- [ ] DB backup must be run before first live onboarding.
- [ ] `python scripts/smoke_check.py --base-url <url> --expect-production` must pass.

---

## Next (Fas 2 — First Customer Pilot)

- [ ] Complete local pre-live setup checklist in `docs/02-first-customer-plan.md` against live server.
- [ ] Connect Gmail inbox to pilot tenant (live OAuth flow).
- [ ] Verify inbox sync reads real mail and creates cases.
- [ ] Verify customer-facing UI shows correct dashboard for pilot tenant.
- [ ] Verify approval-gated email flow works for pilot tenant.
- [ ] Complete go/no-go checklist in `docs/02-first-customer-plan.md`.

---

## Later (Fas 3–4)

- [ ] Stabilize daily operations routine (scheduler, alerts, failed job triage).
- [ ] Package standard onboarding steps for next customer.
- [ ] Improve UI where pilot feedback shows clear need.
- [ ] Define pricing and document in `docs/07-decisions.md`.
- [ ] Plan Outlook/Microsoft Mail intake.

---

## Explicitly Not Now

These items are forbidden before first customer unless `docs/00-master-plan.md` is explicitly updated:

- React or any other frontend framework.
- New frontend-stack.
- SSO or enterprise RBAC.
- Self-serve billing or subscription management.
- Full integration marketplace.
- Körjournal, resejournal, tidsstämpling.
- New large integrations not required for first customer.
- Free bookkeeping automation (Fortnox must remain read/preview/approval-gated).
- Generell chatbot without operational control.
- Any branschspecifik module not needed for first customer.

---

## Known risks (carried from archived backlog)

- `app/api/routes/jobs.py` is dead code (not mounted) — remove or wire up when safe.
- No DB migration tooling — schema changes via `create_all` + runtime safeguard.
- Gmail token is short-lived; onboarding OAuth refresh not self-service for customer.
- `create_internal_task` is stubbed — no persistence beyond job result payload.
