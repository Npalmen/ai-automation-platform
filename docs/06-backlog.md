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
