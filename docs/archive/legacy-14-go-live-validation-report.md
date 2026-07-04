> Archived document. Historical reference only. Current governing source is docs/00-master-plan.md.

# Go-Live Validation Report

**Date:** 2026-05-17
**Validator:** Production QA pass (automated + manual code review)
**Test count at sign-off:** 2273 passed, 0 failed
**Verdict:** ✅ CLEARED FOR CONTROLLED PILOT LAUNCH

---

## Launch Blockers

### Confirmed and Fixed

| ID | Area | Finding | Fix |
|----|------|---------|-----|
| B-01 | Security | Misleading docstring on `POST /verify/{tenant_id}` said "No auth required" while the endpoint actually requires `X-Admin-API-Key`. Could cause operators to expose it publicly assuming it is safe. | Fixed docstring to "Requires X-Admin-API-Key header." |
| B-02 | Security | Dormant `app/api/approval_routes.py` used `X-Tenant-ID` (client-controlled) instead of `get_verified_tenant` — any caller could impersonate any tenant if the router were accidentally mounted. | Added SECURITY WARNING header comment; fixed broken imports in both dormant modules so they are at least importable. |
| B-03 | Security | Dormant `app/api/routes/jobs.py` accepted `tenant_id` from request body with no auth. | Same fix as B-02. |
| B-04 | Runbook | `runbook-scheduler.md` referenced `POST /scheduler/trigger` (does not exist) and `POST /scheduler/digest` (does not exist). Support staff would hit 404 during incidents. | Corrected to `POST /scheduler/run-once` with `X-Admin-API-Key`. Removed non-existent `/scheduler/digest`. |
| B-05 | Runbook | `runbook-oauth.md` referenced `GET /dashboard/integration-health` and `GET /dashboard/pilot-readiness` (neither endpoint exists). | Corrected to `GET /integrations/health` and `GET /pilot/readiness`. |
| B-06 | Deployment | `scripts/smoke_check.py` only validated health and production docs hiding. Authenticated tenant surfaces (integration health, scheduler status, pilot readiness) were never validated post-deploy. | Added `--tenant-api-key` flag with three authenticated smoke checks. |
| B-07 | Deployment | Release gate (`run_release_gate_r1.py`) did not include any tenant isolation or security tests. A regression in auth could go undetected at the gate. | Added `test_tenant_isolation_http.py`, `test_auth.py`, and `test_admin_operations_triage.py` to the regression phase. |

---

## High Priority Issues

### Confirmed and Fixed

| ID | Area | Finding | Fix |
|----|------|---------|-----|
| H-01 | Integration | Monday client had no tests for HTTP-level 429 (rate limit), 403 (permission), and 503 failures. These propagate as `HTTPError` from `raise_for_status()` but this was not validated. | Added 7 tests: `TestMondayClientHttpErrors` covering 429, 403, 503, bad board ID, missing column, and adapter propagation. |
| H-02 | Gmail | OAuth revocation during scheduled inbox sync raised `HTTPException(503)` inside the scheduler, which catches `Exception`. The graceful degradation path was not explicitly tested. | Added 2 tests: `test_oauth_revocation_503_degrades_gracefully` and `test_oauth_revocation_does_not_mask_error`. |
| H-03 | Security | No HTTP-level tests verified that Tenant A's key cannot read Tenant B's jobs, or that cross-tenant approval access returns 404. All auth tests were unit-level only. | Added 24 HTTP-level isolation tests in `test_tenant_isolation_http.py`. |

---

## Medium Issues

### Not Fixed (Acceptable for MVP)

| ID | Area | Finding | Decision |
|----|------|---------|---------|
| M-01 | Integration | Integration health signals are internal (based on audit events). Live OAuth revocation or Monday credential failure is not visible until the next sync/dispatch attempt writes a failed event. | **Acceptable for MVP.** Documented in plan. Operators can see errors at next scheduler run. |
| M-02 | Onboarding | `dispatch_verified` readiness step only checks for `controlled_dispatch` integration events. A Fortnox-only tenant or a tenant where Monday items go through the pipeline action would have a false-negative here. | **Acceptable for MVP.** The controlled dispatch path IS the product's quality signal. Pipeline-only Monday is the legacy path. |
| M-03 | Deployment | Docker compose uses a single uvicorn worker. No auto-scaling or worker count config. | **Acceptable for MVP.** Documented in known limitations. |
| M-04 | Launch checklist | `scripts/smoke_check.py` validates endpoints but cannot validate DB data correctness (e.g., ROI metrics accuracy against real records). | **Acceptable for MVP.** ROI accuracy is covered by `test_dashboard_roi.py`. |

---

## Nice-to-Have

| ID | Area | Finding |
|----|------|---------|
| N-01 | Runbook | `runbook-oauth.md` mentions Microsoft OAuth as future capability. The comment is accurate but does not include a timeline or status update. |
| N-02 | Smoke check | The `--tenant-api-key` smoke check could also validate `/onboarding/status` to confirm the end-to-end onboarding readiness endpoint is reachable. |
| N-03 | Release gate | The E2E phase does not include `test_gmail_oauth_refresh.py` or `test_gmail_scheduler_mode.py`. These could be added for full E2E confidence. |

---

## Fixes Made Per Slice

### Slice A: Security hygiene and HTTP isolation tests
- `app/main.py`: Fixed misleading "No auth required" docstring on `POST /verify/{tenant_id}`.
- `app/api/approval_routes.py`: Added SECURITY WARNING comment explaining why this module must not be mounted.
- `app/api/routes/jobs.py`: Added SECURITY WARNING comment; fixed broken imports (`create_job`→`JobRepository.create_job`, `update_job`→`JobRepository.update_job`, `JobResponse` import path).
- `tests/test_tenant_isolation_http.py`: New file — 24 HTTP-level tenant isolation tests covering missing key (401), wrong key (403), forged X-Tenant-ID, admin-key-as-tenant-key, cross-tenant job/approval 404, inactive tenant 403, dormant routes not mounted, and admin endpoint auth.

### Slice B: Onboarding and runbook accuracy
- `docs/runbook-scheduler.md`: Fixed all endpoint references (`/scheduler/trigger` → `/scheduler/run-once`, removed non-existent `/scheduler/digest`, added `X-Admin-API-Key` requirement, fixed status check URL).
- `docs/runbook-oauth.md`: Fixed `GET /dashboard/integration-health` → `GET /integrations/health` and `GET /dashboard/pilot-readiness` → `GET /pilot/readiness` in two places.
- `scripts/smoke_check.py`: Added `--tenant-api-key` flag with integration health, scheduler status, and pilot readiness checks. Added admin needs-help check to admin flow.
- `docs/13-5-customer-launch-checklist.md`: Updated technical release gate to include the tenant surface smoke checks.

### Slice C: Gmail OAuth revocation
- `tests/test_scheduler.py`: Added `test_oauth_revocation_503_degrades_gracefully` and `test_oauth_revocation_does_not_mask_error`.

### Slice D: Monday HTTP failure coverage
- `tests/test_monday_client.py`: Added `TestMondayClientHttpErrors` with 7 tests covering 429, 403, 503, bad board ID, missing column, and adapter propagation.

### Slice E: Approval and dashboard
- No fixes needed. All 98 tests pass. Tenant isolation for approvals and dashboard queries confirmed.

### Slice F: Deployment and release gate
- `scripts/run_release_gate_r1.py`: Added `test_tenant_isolation_http.py`, `test_auth.py`, and `test_admin_operations_triage.py` to the regression phase.

---

## Remaining Manual Launch Gates

These cannot be automated and require production secrets or external systems:

1. **Gmail OAuth token configured.** `GOOGLE_MAIL_ACCESS_TOKEN` and `GOOGLE_OAUTH_REFRESH_TOKEN` set in production `.env`.
2. **Monday API key configured.** `MONDAY_API_KEY` set in production `.env`.
3. **Admin API key configured.** `ADMIN_API_KEY` set in production `.env` and stored securely.
4. **Tenant API keys provisioned.** At least one tenant provisioned via `POST /admin/tenants` with a DB-backed key.
5. **Backup cron wired.** External `pg_dump` cron configured; first backup confirmed successful.
6. **Restore rehearsal.** A restore from backup must be rehearsed before pilot (see `docs/12-production-guide.md`).
7. **Pilot readiness at green.** `GET /pilot/readiness` returns `overall_status: ready` for each pilot tenant (or documented yellow warnings).
8. **Needs-help queue clear.** `GET /admin/operations/needs-help` shows 0 critical rows before go-live.
9. **Named support owner.** A person is responsible for monitoring and triaging the needs-help queue during pilot.

---

## Test Count Summary

| Test file | Tests |
|-----------|-------|
| `test_tenant_isolation_http.py` | 24 (new) |
| `test_monday_client.py` | +7 (total 22) |
| `test_scheduler.py` | +2 (total 44) |
| All other test files | unchanged |
| **Total** | **2273 passed** |

---

## Verdict

The platform has no confirmed launch blockers that remain unfixed. The seven blockers found during this pass have all been resolved. The 2273-test suite passes cleanly. The release gate now includes security isolation tests. Runbooks reference correct endpoints. The smoke check validates authenticated tenant surfaces.

**Krowolf is cleared for controlled pilot launch to 5 customers**, subject to the 9 manual production gates listed above.
