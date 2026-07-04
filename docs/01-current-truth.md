# Current Truth

> **This file contains verified repository truth. It must not contain vision or plans.**
> If something is unverified, it is marked `Unverified`.
> The governing source for product direction is `docs/00-master-plan.md`.

---

## Last verified date

2026-07-04 (Governance Lock pass — documentation restructure only, no test run in this session)

## Verification method

Prior verification evidence sourced from archived docs (`docs/archive/legacy-05-current-state.md`, `docs/archive/legacy-08-handoff.md`, `docs/archive/legacy-14-go-live-validation-report.md`). Historical smoke test results preserved but not re-run in this session.

---

## Test status

| Claim | Status | Source |
|-------|--------|--------|
| Test suite runs with `py -3.10 -m pytest` | `Unverified` — command was known to pass but not re-run in this session | Archived current-state |
| Test count: 2457 (last confirmed figure in handoff) | `Unverified` — not re-run | Archived handoff 2026-05-18 |
| R1 release gate: `python -m scripts.run_release_gate_r1` | `Unverified` — last known passing, not re-run | Archived current-state |
| Smoke check: `python scripts/smoke_check.py --base-url <url> --expect-production` | `Unverified` — script exists, last known passing | Archived production guide |

> **Required action (Fas 1):** Run `py -3.10 -m pytest` and record actual count in this file.

---

## Production status

| Item | Status | Notes |
|------|--------|-------|
| Server deployment at `api.krowolf.se` | `Unverified` — was live at time of archived handoff (2026-05-21) | Check live |
| Local start via `uvicorn app.main:app --reload` | Known working | Documented in README |
| Docker Compose (Postgres only) | Known available | `docker-compose.yml` + `docker-compose.prod.yml` exist |
| `ENV=production` disables public docs and dev fallback | Implemented | Archived current-state |

---

## Existing integrations

| Integration | Read | Write | Auth | Status |
|-------------|------|-------|------|--------|
| Gmail (`google_mail`) | `list_messages`, `get_message` | `send_email` | OAuth2 + token refresh | Live-verified (2026-05-05) — `Unverified` if still current |
| Monday | `get_boards` (scanner) | `create_item`, `create_monday_item` | API key | Live-verified (2026-04-x) — `Unverified` if still current |
| Fortnox | customers, articles, invoices (read/preview) | invoice export (approval-gated) | Access token | Implemented; live status `Unverified` |
| Visma | OAuth callback exists | None confirmed | OAuth | Partial implementation; status `Unverified` |
| Slack | — | `notify_slack` | Webhook URL | Stub only |
| Microsoft Mail | — | — | — | Stub only, not activated |

---

## Existing UI views (single-file `app/ui/index.html`)

| View | Mode | Status |
|------|------|--------|
| Login screen (Admin / Kund tabs) | Both | Implemented |
| Dashboard — Operationscockpit | Admin | Implemented |
| Dashboard — Customer view | Customer | Implemented |
| Ärenden / Cases list + detail | Both | Implemented |
| Loggar / Ops (jobs + approvals) | Admin | Implemented |
| Inställningar / Setup | Admin | Implemented |
| Kontrollpanel / Control Panel | Admin | Implemented |
| Notifieringar | Admin | Implemented |
| Onboarding / Kunduppsättning | Admin + Customer | Implemented |
| Kundminne / Memory | Admin | Implemented |
| Redo för drift / Readiness | Admin | Implemented |
| Super Admin overview | Admin | Implemented |
| Supportkonsol | Admin | Implemented |
| Konto & Team | Customer | Implemented |
| Resultat / ROI | Customer | Implemented |
| Aktivitetslogg | Customer | Implemented |

---

## Existing admin/support functions

| Function | Endpoint | Status |
|----------|----------|--------|
| Super Admin tenant overview | `GET /admin/tenants/overview` | Implemented |
| Tenant provisioning | `POST /admin/tenants` | Implemented |
| Key rotation | `POST /admin/tenants/{id}/rotate-key` | Implemented |
| Recovery actions (retry/replay/reclassify) | `POST /admin/recovery/{job_id}/{action}` | Implemented |
| Support console (pause/resume automation, force inbox sync) | `GET|POST /admin/support/{tenant_id}/...` | Implemented |
| Production alerting engine (6 evaluators) | `GET|PUT /alerts/config`, `POST /alerts/run` | Implemented |
| Integration health | `GET /integrations/health` | Implemented |
| Pilot readiness (11 checks) | `GET /pilot/readiness` | Implemented |
| Scheduler trigger (admin) | `POST /scheduler/run-once` | Requires `X-Admin-API-Key` |
| Admin session auth (login/logout/me) | `/auth/admin/login|logout|me` | Implemented |

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

---

## Unverified claims

- Exact passing test count as of this session.
- Whether `api.krowolf.se` is currently reachable and healthy.
- Whether Gmail OAuth tokens are currently valid for any connected tenant.
- Whether Monday board connections are current.
- Whether Fortnox access tokens are current.
- Whether Visma OAuth flow is complete end-to-end.

---

## Required checks before first customer (Fas 1 Truth Audit)

- [ ] Run `py -3.10 -m pytest` and record actual pass count.
- [ ] Run `python -m scripts.run_release_gate_r1` and record result.
- [ ] Verify `GET /` returns `{"status":"ok"}` on target instance.
- [ ] Verify `GET /pilot/readiness` returns for at least one tenant.
- [ ] Verify `GET /integrations/health` reflects real Gmail and Monday state.
- [ ] Verify Gmail OAuth token is valid (or document that refresh is needed).
- [ ] Verify `GET /admin/tenants/overview` returns with `X-Admin-API-Key`.
- [ ] Confirm scheduler `run_mode` is set correctly for pilot tenant.
- [ ] Run smoke check: `python scripts/smoke_check.py --base-url <url> --expect-production`.
- [ ] Update this file with actual verified results.
