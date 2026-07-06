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

### Deferred — live verification phase (not next local step)

Full live verification plan: `docs/10-live-verification-plan.md` — not run yet, prepared only.

**Phase A — Pre-flight**
- [ ] Confirm full local test suite passes immediately before live session.
- [ ] Confirm R1 gate passes immediately before live session.

**Phase B — Production health**
- [ ] `GET https://api.krowolf.se/` → HTTP 200, `env: production`.
- [ ] `GET https://api.krowolf.se/health` → HTTP 200.
- [ ] Confirm `/docs` and `/openapi.json` return 404 in production.

**Phase C — Admin/auth**
- [ ] Admin endpoint without key → 401.
- [ ] Admin endpoint with wrong key → 401.
- [ ] Admin endpoint with correct key → 200.
- [ ] Tenant key rejected on admin endpoint.

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

## Now (pre-live blockers)

### Completed in Phase 2 prep

- [x] **First tenant setup path mapped and verified locally.** All endpoints (`POST /admin/tenants`, rotate-key, status, `GET /pilot/readiness`, `GET /integrations/health`, `GET /onboarding/status`, `POST /onboarding/test-lead`, `POST /verify/{tenant_id}`) verified via test suite.
- [x] **Pilot readiness verified** — 11 checks, all deterministic, no external API calls. `test_production_readiness.py` (169 tests) passes.
- [x] **Integration health verified** — reports `not_configured` safely without live tokens, no secrets in response. `test_integration_health.py` passes.
- [x] **Customer dashboard/status verified** — empty-state loads without crash. `test_customer_saas_surfaces.py` passes.
- [x] **`docs/08-runbook.md`** — added "First internal pilot tenant setup" section with concrete curl commands (Steps 1–11).
- [x] **`docs/02-first-customer-plan.md`** — added "Local pre-live setup checklist" (11 items).
- [x] **Flaky test fixed**: `test_sla_pass_already_run_today_skips` used `date.today()` (local TZ) vs UTC production code. Fixed to use `datetime.now(timezone.utc)`.

### Local blockers — none

No local blockers remain before live phase.

### Remaining local quality gaps

- [ ] Broaden deterministic extraction for Swedish addresses/property details beyond current keyword/entity coverage.
- [ ] Add more tenant-specific eval scenarios once the first pilot tenant's real service taxonomy and routing hints are known.
- [ ] Consider wiring deterministic support analysis output more directly into older AI-backed `customer_inquiry_processor` payloads if pilot feedback shows operator UI needs one consolidated payload.

### Pre-live blockers (require live environment)

- [ ] `ADMIN_API_KEY` must be set to strong random value in production.
- [ ] Gmail OAuth flow must be completed for pilot tenant (`GET /auth/gmail/start?tenant_id=...`).
- [ ] Monday `MONDAY_API_KEY` must be set and board connection verified.
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
