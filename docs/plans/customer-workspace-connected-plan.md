---
name: Connected Customer Workspace
overview: Koppla den färdiga kundarbetsytan till säker tenantisolerad produktionsdata genom kundsession och read-only workspace-API utan att aktivera kundwrites.
todos:
  - id: connected-a-current-truth
    content: Audita aktuell main efter avslutade parallella spår och lås integrationsgränser
    status: completed
  - id: connected-b-customer-auth
    content: Bygg serververifierad kundsession och tenantbunden autentisering
    status: completed
  - id: connected-c-workspace-api
    content: Implementera tenantisolerat read-only workspace-API
    status: in_progress
  - id: connected-d-tenant-security
    content: Verifera tenantisolering, cross-tenant denial och säkerhetsgränser
    status: pending
  - id: connected-e-frontend-connection
    content: Koppla befintlig kundfrontend från mockadapter till riktig read-only data
    status: pending
  - id: connected-f-production-readiness
    content: Produktionsverifiera connected read-only workspace och stäng spåret
    status: pending
isProject: true
---

# Connected Customer Workspace

## 1. Dokumentets auktoritet

Detta dokument styr utvecklingsspåret **Connected Customer Workspace** — uppföljning till den avslutade preview-planen ([`customer-workspace-plan.md`](customer-workspace-plan.md), todos A–H `completed`).

| Dokument | Roll |
|----------|------|
| [`docs/00-master-plan.md`](../00-master-plan.md) | Högsta auktoritet |
| [`docs/customer-workspace/product-contract.md`](../customer-workspace/product-contract.md) | Låst preview-produktkontrakt |
| [`docs/customer-workspace/api-contract.md`](../customer-workspace/api-contract.md) | Låst `/workspace/v1`-kontrakt |
| [`docs/customer-workspace/connected-current-truth.md`](../customer-workspace/connected-current-truth.md) | Verifierad audit för detta spår |
| Detta dokument | Implementationsordning och stop-gates |

Preview-planens tekniska innehåll är **read-only**. Endast todo-statusövergångar (`pending → in_progress → completed`) får ändras i denna plan under implementation.

**Relation till preview:** Preview under `/app` är mergead och verifierad (closure PARTIAL). Connected-spåret bygger ovanpå samma UI och samma `WorkspaceDataSource`-interface — utan att skriva om Todo C–G-vyer.

---

## 2. Mål och scope

### Mål

Koppla den färdiga kundarbetsytan till **säker, tenantisolerad, read-only produktionsdata** via:

1. Serverägd kundsession (HttpOnly cookie, revocation)
2. `GET /workspace/v1/*` read-only API
3. `ConnectedWorkspaceDataSource` i frontend

### In scope

- Customer-session-auth (`/auth/customer/*`)
- Read-only `/workspace/v1` backend (`app/customer_workspace/`)
- Tenantisolering och cross-tenant denial-tester
- Frontend-anslutning (mock kvar för preview/test)
- Produktionsverifiering av connected read-only-läge

### Out of scope (hela spåret)

- Approval resolution (approve/reject)
- Gmail send/reply
- Action dispatch / retry
- Scheduler writes
- Integrationswrites
- Decisioning, policy authorization, execution intent/outcome
- Live-eval qualification, testbot qualification
- `customer_workspace_writes = true` (förblir **false**)

---

## 3. Read-only-gräns (låst)

### 3.1 Business/workspace data — förbjudet

Genom **hela** Connected Customer Workspace-spåret (todos A–F):

| Kategori | Förbjudet |
|----------|-----------|
| Approvals | approve, reject, resolve |
| Gmail | send, reply, draft create |
| Actions | dispatch, retry, cancel |
| Jobs/cases | statusändring, retry, regenerate |
| Automation | policyändring, schedulerändring |
| Integrationer | OAuth connect, write-anrop |
| Kundkonto | `PUT /customer/account` från workspace-UI |

`GET /workspace/v1/*` ska **endast** läsa via adapters. Inga POST/PUT/PATCH/DELETE i `app/customer_workspace/`.

Feature flag (låst i hela spåret):

```typescript
customer_workspace_writes: false
```

### 3.2 Auth/session/provisioning-writes — tillåtet (endast connected-b)

Följande writes är **tillåtna**, men **endast** inom `connected-b-customer-auth` och **endast** för customer-workspace-identiteter:

| Tillåten write | Syfte |
|----------------|-------|
| Skapa/uppdatera `customer_workspace_users` | Credentials, display_name, status |
| Skapa `customer_workspace_sessions` | Login |
| Revoke session (`revoked_at`) | Logout, admin revoke, password change |
| Aktivera/inaktivera viewer-konto | Operator provisioning |
| Rate-limit / audit för login | Säkerhet |

**Hård gräns:** Dessa authwrites får **inte** ge någon väg till approval resolution, Gmail-write, dispatch, scheduler eller integrationswrites. De får **inte** exponera tenant-API-nycklar eller admin-session.

`PUT /customer/account` (befintlig tenant-API-nyckel-endpoint) ska **inte** användas från `/app` connected-läge.

### 3.3 Vad connected-c och senare får skriva

**Ingenting** utöver read-paths och test-fixtures. Session-revocation anropas endast via auth-modulen vid logout — inte från workspace-routes.

---

## 4. Implementationsordning

```text
connected-a  →  connected-b  →  connected-c  →  connected-d
                                    ↓
                              connected-e  →  connected-f
```

| Todo | Stop-gate |
|------|-----------|
| **connected-a** | Plan + connected-current-truth godkänd |
| **connected-b** | Session-tester gröna; logout/revocation verifierad; ingen `/workspace/v1` utan auth |
| **connected-c** | Alla 7 GET endpoints; adapter-tester; inga writes |
| **connected-d** | Cross-tenant 404; fail-closed; no-secrets scan |
| **connected-e** | UI oförändrat; mock kvar; connected smoke |
| **connected-f** | Produktionsverifiering; closure-dokument |

**connected-e blockeras** tills connected-c + connected-d passerar.  
**connected-f blockeras** tills connected-e passerar.

---

## 5. connected-a-current-truth

### Mål

Auditera `origin/main`, dokumentera stabila read-källor, identifiera auth-gap och lås integrationsgränser.

### Leverabler

- [`docs/customer-workspace/connected-current-truth.md`](../customer-workspace/connected-current-truth.md)
- Lokal rapport: `storage/status/customer-workspace-connected-current-truth.md` (ej committad)

### Stop-gate

Ingen implementation av connected-b får påbörjas förrän connected-a är `completed` och audit-SHA är dokumenterad.

---

## 6. connected-b-customer-auth

### 6.1 Login-kontrakt (låst)

**Första versionen:** `email + password` endast.

| Regel | Beslut |
|-------|--------|
| Identifierare | `email` (normaliserad: trim + lowercase) |
| Unicitet | **Globalt unik** bland aktiva identiteter (`status = 'active'`) |
| Tenant vid login | Härleds från användarposten — **aldrig** från klientinput |
| Lösenord | PBKDF2-HMAC-SHA256 (samma iterationer som admin: 260 000) |
| Roll | `customer_viewer` (enda rollen i v1) |

**Motivering:** Email-only login kräver global unicitet. `unique per tenant` + email-only skulle kräva att klienten anger tenant (förbjudet) eller ett separat organisationsidentifieringsfält. Inget etablerat repo-mönster för kundorganisationslogin utan tenant-input finns — admin använder username (env), tenant-API använder nyckel.

**Index (låst):**

```sql
CREATE UNIQUE INDEX ux_customer_workspace_users_active_email
  ON customer_workspace_users (lower(email))
  WHERE status = 'active';
```

Inaktiverade (`disabled`) konton blockerar inte återanvändning av email efter disable.

### 6.2 Sessionsmodell (låst beslut)

#### Varför inte admin-lik stateless cookie

Befintlig admin-session ([`app/core/admin_session.py`](../../app/core/admin_session.py)) är **stateless HMAC-signerad**:

- Cookie innehåller signerad payload (`sub`, `iat`, `exp`)
- `POST /auth/admin/logout` rensar **endast** browser-cookie
- Token förblir kryptografiskt giltig till `exp` — ingen server-side revocation
- Acceptabelt för enstaka env-konfigurerad admin; **otillräckligt** för multi-user customer workspace med disable/revocation-krav

#### Vald modell: server-side session records

**Minsta repo-kompatibla modell** som uppfyller revocation-kraven. Mönster hämtat från [`integration_invitations`](../../app/admin/tenant_lifecycle/invitation_models.py) (`token_hash`, `expires_at`, `revoked_at`).

| Komponent | Beslut |
|-----------|--------|
| Cookie-namn | `customer_session` (separat från `admin_session`) |
| Cookie-värde | Opaque random token (t.ex. 32 bytes, urlsafe base64) — **inte** JWT/HMAC-payload |
| Lagring | `customer_workspace_sessions` med `token_hash` (SHA-256), aldrig rå token i DB |
| Validering | DB lookup → kontrollera `revoked_at IS NULL`, `expires_at > now()`, user `active`, tenant aktiv |
| Expiration | `expires_at` i DB + `max_age` på cookie (default 8 h, konfigurerbar) |
| Logout | Sätt `revoked_at = now()` på sessionposten + rensa cookie |
| Disable user | Fail-closed vid nästa request (user lookup) |
| Disable tenant | Fail-closed via befintlig tenant-statuskontroll |
| Password change | Revoke alla aktiva sessioner för användaren |
| Cookie-attribut | HttpOnly; Secure i prod (`ENV` not in dev/local); SameSite=strict (samma som admin om ingen subdomain-split) |
| Same-origin | `require_same_origin` på login/logout (samma mönster som admin) |
| Rate limit | Login: 5/min per IP (samma som admin) |

**Tradeoffs:**

| Fördel | Nackdel |
|--------|---------|
| Verifierbar logout/revocation | DB-read per autentiserad request |
| Disable user/tenant omedelbart effektivt | Kräver migration + session cleanup-jobb (valfritt TTL) |
| Matchar befintlig `revoked_at`-konvention | Mer kod än ren stateless cookie |
| Ingen tenant i browser | Session-tabell måste indexeras på `token_hash` |

**Uttryckligen ej valt:** Stateless HMAC-cookie (admin-mönster), JWT med client-side claims, API-nyckel i browser, `X-Tenant-ID` från klient.

### 6.3 Endpoints (låsta)

```text
POST /auth/customer/login     # { email, password } → Set-Cookie: customer_session
POST /auth/customer/logout    # Revoke session + clear cookie
GET  /auth/customer/me        # { user_id, email, display_name, role, tenant_id, company_name }
```

Alla state-changing auth-routes: `require_same_origin`.

### 6.4 Datamodell (låst filscope)

**Tabell `customer_workspace_users`:**

| Kolumn | Typ | Notering |
|--------|-----|----------|
| `id` | VARCHAR(36) PK | UUID |
| `tenant_id` | VARCHAR(32) NOT NULL | Index; hämtas vid login |
| `email` | VARCHAR(256) NOT NULL | Normaliserad lowercase |
| `password_hash` | TEXT NOT NULL | PBKDF2 |
| `display_name` | VARCHAR(256) | |
| `role` | VARCHAR(32) | Default `customer_viewer` |
| `status` | VARCHAR(32) | `active` / `disabled` |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| `password_changed_at` | TIMESTAMPTZ | För session-invalidation |

**Tabell `customer_workspace_sessions`:**

| Kolumn | Typ | Notering |
|--------|-----|----------|
| `id` | VARCHAR(36) PK | |
| `user_id` | VARCHAR(36) FK | |
| `tenant_id` | VARCHAR(32) NOT NULL | Denormaliserat för snabb kontroll |
| `token_hash` | TEXT NOT NULL | UNIQUE |
| `expires_at` | TIMESTAMPTZ NOT NULL | |
| `revoked_at` | TIMESTAMPTZ | NULL = aktiv |
| `created_at` | TIMESTAMPTZ | |
| `last_seen_at` | TIMESTAMPTZ | Valfritt |

### 6.5 Filscope (connected-b)

```text
app/core/customer_session.py
app/core/customer_session_models.py
app/repositories/postgres/customer_workspace_user_models.py
app/repositories/postgres/customer_workspace_session_models.py
app/repositories/postgres/customer_workspace_user_repository.py
app/repositories/postgres/customer_workspace_session_repository.py
app/repositories/postgres/schema_migrations.py          # nya statements
app/admin/customer_workspace_users/routes.py            # operator provisioning (admin-only)
app/main.py                                             # auth routes endast
tests/test_customer_session_auth.py
tests/test_customer_workspace_user_provisioning.py
```

### 6.6 Provisioning (minimal v1)

Operator skapar viewer-konto via admin-only endpoint:

```text
POST /admin/tenants/{tenant_id}/workspace-users
```

Kräver `require_operator_role`. Returnerar **inte** lösenord i klartext efter skapande — operator sätter initialt lösenord via säker kanal eller one-time setup (implementationdetalj i connected-b).

### 6.7 Stop-gate

- Login/logout/me fungerar med DB-sessioner
- Revoked session → 401 på `/auth/customer/me` och `/workspace/v1/*`
- Disabled user → 401/403 fail-closed
- Disabled/inactive tenant → 403 fail-closed
- Ingen `/workspace/v1` utan giltig session
- Inga business-writes introducerade

---

## 7. connected-c-workspace-api

### 7.1 Endpoints (låsta, från api-contract)

```text
GET /workspace/v1/context
GET /workspace/v1/overview
GET /workspace/v1/work-items
GET /workspace/v1/work-items/{work_item_id}
GET /workspace/v1/approvals
GET /workspace/v1/activity
GET /workspace/v1/health
```

**Auth:** `Depends(get_customer_session_tenant)` — tenant **endast** från session.

**Metoder:** GET endast.

### 7.2 work_item_id (låst)

`work_item_id` = `job_id` som opaque string. Server-side lookup med obligatorisk `tenant_id`-filter från session. Cross-tenant → **404**.

### 7.3 Källrepository-matris

| Endpoint | Primär källa | Adapter |
|----------|--------------|---------|
| `/context` | `TenantConfigRepository`, `_get_customer_account` | Sanitera intern config |
| `/overview` | `_compute_summary`, approvals count, tenant triage | `adapters/overview.py` |
| `/work-items` | `JobRepository` via cases-logik | `adapters/work_items.py` |
| `/work-items/{id}` | `get_case`-data | Timeline utan rå processor_history |
| `/approvals` | `ApprovalRequestRepository.list_pending_for_tenant` | **Ej** `to_dict()` rakt av |
| `/activity` | `customer_activity` / `dashboard_activity` | + `customer_status` |
| `/health` | `customer_health` | Direct reuse |

**Needs-help:** Tenant-scopad `_build_tenant_triage` — **ej** `/admin/operations/needs-help` från frontend.

### 7.4 Förbjudna fält

Per [`api-contract.md`](../customer-workspace/api-contract.md) §6: `job_id`, `input_data`, `result`, `processor_history`, `request_payload`, `delivery_payload`, `next_on_approve`, `next_on_reject`, `execution_id`, `auto_actions`, LLM-råoutput, andra tenants `tenant_id`.

### 7.5 Filscope (connected-c)

```text
app/customer_workspace/
  __init__.py
  routes.py
  dependencies.py
  schemas.py
  status.py
  adapters/
    account.py
    overview.py
    work_items.py
    approvals.py
    activity.py
    health.py
app/main.py                    # include_router endast
tests/customer_workspace/
  test_context.py
  test_overview.py
  test_work_items.py
  test_approvals.py
  test_activity.py
  test_health.py
```

### 7.6 Routerregistrering (låst)

I [`app/main.py`](../../app/main.py), efter befintliga `include_router` (~L8585–8619), före static `/app` (~L9768):

```python
from app.customer_workspace.routes import router as customer_workspace_router
app.include_router(customer_workspace_router, prefix="/workspace/v1", tags=["customer-workspace"])
```

### 7.7 feature_flags i `/context` (connected-läge)

```json
{
  "customer_workspace_writes": false,
  "connected_api": true
}
```

`preview_mode` skickas **inte** från API i connected-läge (frontend sätter `workspace_mode: "connected"`).

### 7.8 Stop-gate

- Alla 7 endpoints returnerar kontraktsenliga responses
- Inga POST/PUT/PATCH/DELETE
- Tenant från session endast
- Adapter-tester gröna

---

## 8. connected-d-tenant-security

### 8.1 Obligatoriska tester

| Test | Förväntat |
|------|-----------|
| Customer A läser customer A | 200 |
| Customer A läser customer B work_item | 404 |
| Manipulerat work_item_id | 404 (ej 403) |
| Query params kan inte byta tenant | 404/ignoreras |
| Session utan tenant (korrupt data) | 401 fail-closed |
| Utgången session | 401 |
| Revoked session (efter logout) | 401 |
| Disabled user | 401/403 |
| Inactive tenant | 403 |
| Inga secrets i responses | PASS scan |
| Inga raw decision/execution payloads | PASS scan |

### 8.2 Filscope

```text
tests/customer_workspace/test_cross_tenant.py
tests/customer_workspace/test_session_fail_closed.py
tests/test_customer_workspace_no_secrets.py
```

### 8.3 Stop-gate

Alla säkerhetstester gröna i CI. Ingen connected-e förrän connected-d passerar.

---

## 9. connected-e-frontend-connection

### 9.1 Arkitektur (låst)

```text
befintligt UI (Todo C–G)
      ↓
WorkspaceDataSource (interface oförändrat)
      ↓
ConnectedWorkspaceDataSource (ny)
      ↓
GET /workspace/v1/*  (credentials: include)
      ↓
get_customer_session_tenant
```

**Ej tillåtet:** UI → `/jobs`, `/cases`, `/approvals/pending`, `/admin/*`.

### 9.2 Filscope

| Fil | Ändring |
|-----|---------|
| `frontend/src/customer/api/client.ts` | **Ny** — GET only, `credentials: "include"` |
| `frontend/src/customer/api/connectedDataSource.ts` | **Ny** |
| `frontend/src/customer/auth/CustomerAuthProvider.tsx` | Mock vs connected |
| `frontend/src/customer/types/workspace.ts` | `WorkspaceMode` + `"connected"` |
| `frontend/src/customer/auth/PreviewLoginPage.tsx` | Login-form connected |
| `frontend/src/customer/components/WorkspaceModeBadge.tsx` | Connected-etikett |
| `frontend/src/customer/shell.test.mjs` | Tillåt fetch till `/workspace/v1`, `/auth/customer` |
| `frontend/src/customer/api/mockDataSource.ts` | **Oförändrad** — preview/test |

### 9.3 Mock behålls

- `npm run test:customer` i preview-läge
- `VITE_CUSTOMER_MODE=preview` för lokal demo
- Inga API-nycklar i browser i något läge

### 9.4 Stop-gate

- 97 befintliga preview-tester fortsatt gröna
- Connected smoke: login → overview → work-items → logout
- `customer_workspace_writes` fortfarande false i UI

---

## 10. connected-f-production-readiness

### Mål

Produktionsverifiera connected read-only workspace och formellt stänga spåret.

### Leverabler

- `docs/customer-workspace/connected-release-notes.md`
- `docs/customer-workspace/connected-verification.md`
- Uppdatera `known-limitations.md` (connected vs preview)
- Lokal closure-rapport: `storage/status/customer-workspace-connected-closure.md`

### Closure-status

| Status | Krav |
|--------|------|
| **PASS** | Auth + API + tenant isolation verifierade i målmiljö; `/app` med riktig tenantdata |
| **PARTIAL** | Lokal/CI verifierad men ej produktionsdeploy |
| **BLOCKED** | Säkerhets- eller build-fel |

Writes förblir blockerade oavsett closure-status.

### Stop-gate

- Required CI grön
- Plan todos A–F `completed`
- Ärlig closure-status dokumenterad

---

## 11. Förbjudet filscope (hela spåret)

```text
app/workflows/**
app/decisioning/**
app/policies/**
app/evaluation/live/**          # läs endast för förståelse
POST /approvals/*/approve|reject
action dispatch, Gmail send
customer_workspace_writes = true
```

**Parallella spår — läs, rör inte:**

- R4/R5 digital coworker qualification
- Customer-card-domain (`app/domain/customer/`, `END_CUSTOMER_READ_API_ENABLED`)
- Testbot qualification

---

## 12. Teststrategi

### Backend

```text
tests/test_customer_session_auth.py
tests/customer_workspace/test_*.py
tests/test_customer_workspace_static.py     # regression
tests/test_tenant_isolation_http.py         # mönster
```

### Frontend

```text
npm run test:customer                       # preview + connected modes
frontend/src/customer/api/connectedDataSource.test.mjs
```

### CI

[`.github/workflows/release-gate.yml`](../../.github/workflows/release-gate.yml) — `frontend`, `tests`, `docker`. Inga nya workflows krävs.

---

## 13. Referensdokument

| Dokument | Syfte |
|----------|-------|
| [`connected-current-truth.md`](../customer-workspace/connected-current-truth.md) | Audit @ main SHA |
| [`product-contract.md`](../customer-workspace/product-contract.md) | Preview-produktkontrakt |
| [`api-contract.md`](../customer-workspace/api-contract.md) | API-shape |
| [`release-notes.md`](../customer-workspace/release-notes.md) | Preview release |
| [`known-limitations.md`](../customer-workspace/known-limitations.md) | Preview begränsningar |

---

*Plan skapad 2026-08-08. Bas-SHA: `3d2f7aa`. Preview closure: `afd97fa`.*
