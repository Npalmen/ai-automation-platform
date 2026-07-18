# Kapitel 11 — Säkerhetsinventering

> **Status:** Slice 0 levererad · Implementation pågår  
> **Datum:** 2026-07-18  
> **Syfte:** Obligatorisk kartläggning före och under säkerhetshärdning inför Kapitel 12.

---

## 1. Trust boundaries

| Gräns | Komponenter | Kontroller | Kvarvarande risk |
|-------|-------------|------------|------------------|
| Browser ↔ backend | `/ops` React, `/ui` legacy | Session cookie, same-origin på writes | Legacy UI `localStorage` API-nyckel (F04) |
| Reverse proxy ↔ app | Caddy | TLS termination | Security headers i proxy (F10) |
| Admin ↔ tenant API | `/admin/*` vs tenant routes | Separata auth-dependencies | Legacy routes utan roll (F01) |
| Backend ↔ DB | PostgreSQL | `tenant_id` på tenant-tier repos | OAuth tokens plaintext (F05, accepted short-term) |
| Backend ↔ OAuth | Visma callback | Onboarding opaque state | Legacy `state=tenant_id` (F03) |
| Scheduler/cron | Intern | Admin key för manuella triggers | `GET run-all` mutation (F02) |

---

## 2. Authmodell

| Mekanism | Implementation | Styrka | Svaghet |
|----------|----------------|--------|---------|
| Session | `app/core/admin_session.py` | HttpOnly, SameSite=strict, Secure i prod | Stateless, ingen revocation |
| Admin API key | `app/core/admin_auth.py` | Constant-time, `ADMIN_API_KEYS` rotation | Bypassar roll på legacy routes |
| Tenant API key | `app/core/auth.py` | DB hash + prod fail-closed | Dev passthrough utan keys |
| OAuth | Onboarding + Visma | One-time state, HMAC | Legacy callback path |

**Rekommendation:** Enhetlig `require_operator_role` + `require_same_origin` på alla state-changing `/admin/*` routes.

---

## 3. Rollmatris

| Capability | read_only | operations | admin |
|------------|:---------:|:----------:|:-----:|
| Panel reads | ✓ | ✓ | ✓ |
| Safe operator actions | | ✓ | ✓ |
| Incidents / alert lifecycle (ej suppress) | | ✓ | ✓ |
| Alert suppress | | | ✓ |
| Onboarding activate / API key | | | ✓ |
| Recovery / support mutations | | ✓ | ✓ |
| Tenant rotate-key / status | | | ✓ |
| System status | | ✓ | ✓ |

Backend source of truth: `require_operator_role` i route dependencies. Frontend: `routePolicy.ts` (UX only).

---

## 4. Tenantisolering

**Verifierat:** `get_verified_tenant`, repo-scoped queries, `test_tenant_isolation_http.py`.

**Åtgärdat i K11:**
- `IntegrationRepository.get_by_idempotency_key` kräver `tenant_id`
- `get_verified_tenant` använder `ADMIN_API_KEYS`
- `tenant_middleware` sätter inte default `TENANT_1001`
- Cross-tenant admin-tester i `test_admin_cross_tenant_security.py`

**Designval:** Admin lookup by alert/incident/session ID är plattformsomfattande (operator scope).

---

## 5. Kritiska writes

Deklarativt register: `app/admin/security/critical_actions.py`.

Integrity test: `tests/test_admin_security_contracts.py`.

---

## 6. Audit

| Domän | Fail mode (före K11) | Efter K11 |
|-------|---------------------|-----------|
| Onboarding | Closed | Closed |
| Operator actions | Closed | Closed |
| Incidents | Transactional | Transactional |
| Alerts | Open (silent skip) | **Closed** |
| Recovery | Open (log+continue) | **Closed** |

---

## 7. Sessionssäkerhet

- Cookie: HttpOnly, SameSite=strict, Secure utanför dev
- Logout: `Secure` match på delete
- Ingen token i React `localStorage`
- Login rate limit: 5/min per IP (Slice 3)

---

## 8. Rate limiting

In-memory token bucket (`app/core/rate_limit.py`). Dokumenterad begränsning: ej distribuerad över instanser (F16 accepted).

| Endpoint | Policy |
|----------|--------|
| `POST /auth/admin/login` | 5/min per IP |
| `POST /admin/alert-evaluations/run` | 10/min per operator |
| `POST /admin/onboarding/*/activate` | 3/h per operator |
| Recovery/support writes | 20/h per operator |

---

## 9. Secrets

- Secret scan: `tests/test_security_secret_scan.py`
- F05 (OAuth plaintext): risk acceptance → DEC-028, K12 encryption

---

## 10. OAuth/integrationer

- Onboarding Visma: opaque state, one-time consume
- Legacy Visma `state=tenant_id`: **avstängd** i K11
- Gmail: platform credential (dokumenterad shared-credential risk)

---

## 11. Inputvalidering

Befintliga Pydantic-schemas på admin routes. Bounded pagination på list endpoints. Inga request-styrda imports.

---

## 12. Legacy

| Yta | K11-beslut |
|-----|------------|
| `app/ui/index.html` | Deprecation banner; mål K12 retirement |
| Legacy `/admin/*` | Role + origin guards |
| `GET /admin/alerts/run-all` | Ersatt av `POST` |
| Dormant `approval_routes.py` | Ej mounted (test verifierar) |

---

## 13. Fyndtabell

| ID | Severity | Status efter K11 |
|----|----------|------------------|
| F01 | Critical | **Fixed** — legacy writes role-guarded |
| F02 | High | **Fixed** — POST run-all |
| F03 | High | **Fixed** — legacy Visma callback blocked |
| F04 | High | **Mitigated** — deprecation banner |
| F05 | High | **Accepted** — DEC-028 |
| F06 | Medium | Documented |
| F07 | Medium | **Fixed** — recovery audit fail-closed |
| F08 | Medium | **Fixed** — alert audit fail-closed |
| F09 | Medium | **Fixed** — login rate limit |
| F10 | Medium | **Fixed** — security headers middleware |
| F11 | Medium | **Fixed** — tenant middleware |
| F12 | Medium | **Fixed** — routePolicy sync |
| F13 | Medium | **Fixed** — ADMIN_API_KEYS in get_verified_tenant |
| F14 | Low | Open (UI gap) |
| F15 | Accepted | Single operator account |
| F16 | Accepted | In-memory rate limiter |
