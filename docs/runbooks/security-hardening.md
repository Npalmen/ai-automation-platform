# Security hardening runbook (Kapitel 11)

> Operational guidance for security controls added in Kapitel 11.
> Inventory and findings: `docs/security/kapitel-11-inventory.md`.
> Architecture: `docs/05-architecture.md` (trust boundaries).

---

## Trust boundaries (summary)

| Tier | Auth | Scope |
|------|------|-------|
| Customer API | `X-API-Key` → tenant | Tenant-scoped jobs, approvals, customer surfaces |
| Operator session | HttpOnly `admin_session` cookie | `/ops` frontend + cookie-auth admin routes |
| Operator API key | `X-Admin-API-Key` | Scripts, legacy `/admin/*`, recovery/support when key used |
| Unauthenticated | None | `/health`, public health payloads only |

Critical writes require **role** (`read_only` | `operations` | `admin`) **and** `require_same_origin` on cookie-based mutations. API-key callers are exempt from Origin checks (documented for scripts).

---

## Operator lockout / 403 on writes

**Symptoms:** Operator sees forbidden (403) on POST/PATCH/DELETE in `/ops` or via API.

**Checks:**

1. Confirm role: `GET /auth/admin/me` — `read_only` cannot mutate.
2. Confirm Origin: browser requests must match `ALLOWED_ORIGINS` or same host as API.
3. Confirm session: cookie present; re-login if expired.

**Recovery:** Set `ADMIN_ROLE=admin` (or `operations` for non-admin writes), restart API, re-login.

---

## Login rate limiting (429)

**Behavior:** `POST /auth/admin/login` — max **5 attempts per IP per 60 seconds** (in-memory, per process).

**Symptoms:** `429` with `Retry-After` header; Swedish detail message.

**Operator action:** Wait for `Retry-After` seconds; avoid rapid scripted login loops.

**Multi-instance note:** Limit is **not** shared across replicas (F16 — accepted for MVP). For multi-instance deployments, prefer edge rate limiting (Caddy) or plan K12 distributed limiter.

---

## OAuth abuse (Visma)

**Legacy callback disabled:** Visma OAuth with `state=<raw tenant_id>` redirects to `/ops/customers?oauth=error&reason=legacy_oauth_disabled`.

**Supported path:** Onboarding wizard opaque state only (`/admin/onboarding/...`).

**If OAuth fails after upgrade:** Re-run connect from onboarding wizard; do not use legacy `/ui` Visma buttons.

---

## Audit fail-closed on critical writes

Recovery actions and operator-alert audit writes **raise 500** if audit persistence fails after the mutation. Do not retry blindly — check DB connectivity and `audit_events` table health before repeating destructive recovery.

---

## Security headers

App middleware sets (when not overridden by proxy):

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security` in production
- `Cache-Control: no-store` for `/ops`, `/auth/admin`, `/ui`

Production: mirror headers in `infra/Caddyfile.example` for defense in depth.

---

## Secret handling

- Never commit `.env`, API keys, or OAuth tokens.
- Run `python -m pytest tests/test_security_secret_scan.py` before release.
- OAuth tokens in DB are plaintext at rest (F05 — accepted; encryption deferred to K12).

---

## Incident response checklist

1. Rotate `ADMIN_API_KEY` / `ADMIN_API_KEYS` and tenant keys if leak suspected.
2. Invalidate sessions: rotate `SESSION_SECRET_KEY` and restart (forces re-login).
3. Review `audit_events` for operator actions and recovery/support mutations.
4. Check Visma/Google OAuth credential rows for unexpected tenants.
5. Re-run K11 regression bundle (see `docs/09-testing-and-release.md`).

---

## Verification commands

```bash
# K11 security regression bundle
python -m pytest tests/test_admin_security_contracts.py tests/test_admin_cross_tenant_security.py tests/test_security_secret_scan.py tests/test_recovery_actions.py tests/test_alerting.py tests/test_admin_alerts.py tests/test_admin_auth.py tests/test_admin_session.py tests/test_tenant_isolation_http.py -q

# Local E2E (server must be running)
python scripts/kapitel11_security_e2e_verify.py
```
