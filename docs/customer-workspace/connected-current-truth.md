# Connected Customer Workspace — Current Truth

> **Verifierad repositoryaudit för Connected Customer Workspace (todo connected-a).**
> Endast verifierade fakta och explicit markerade antaganden.
> Styrande dokument: [`customer-workspace-connected-plan.md`](../plans/customer-workspace-connected-plan.md).

---

## Auditmetadata

| Fält | Värde |
|------|-------|
| Auditdatum | 2026-08-08 |
| Branch | `feat/customer-workspace-connected` |
| Base SHA (`origin/main`) | `3d2f7aa` |
| Preview closure SHA | `afd97fa` (PR #68; workspace todos A–H `completed`) |
| Verifieringsmetod | `git fetch`, statisk kodinspektion, endpointinventering, grep, parallellspårs-jämförelse |
| Overall audit status | **PASS** — tillräcklig för connected-a; blockerare dokumenterade |

---

## 1. Preview-baseline (verifierat på main)

Preview-spåret är avslutat och mergeat. Följande är verifierat på `origin/main`:

| Faktum | Evidens |
|--------|---------|
| Customer SPA under `/app` | [`app/main.py`](../../app/main.py) L9768–9878 — `dist-customer` |
| Separat customer build | [`Dockerfile`](../../Dockerfile) — `npm run build:customer` |
| Customer frontend komplett | [`frontend/src/customer/**`](../../frontend/src/customer/) — 97 tester |
| Mock-only data | [`CustomerAuthProvider.tsx`](../../frontend/src/customer/auth/CustomerAuthProvider.tsx) — `mockDataSource`, `connected: false` |
| WorkspaceDataSource interface | [`frontend/src/customer/api/types.ts`](../../frontend/src/customer/api/types.ts) — 7 metoder |
| Inga nätverksanrop i preview | [`shell.test.mjs`](../../frontend/src/customer/shell.test.mjs) |
| Closure docs | `release-notes.md`, `known-limitations.md`, `verification.md` — closure PARTIAL |
| `customer_workspace_writes: false` | [`workspace.ts`](../../frontend/src/customer/types/workspace.ts) |

**Notering:** [`docs/customer-workspace/current-truth.md`](current-truth.md) (todo A, SHA `758502e`) är **föråldrad** för serving och frontend — den sade att `/app` saknas. Denna connected-audit ersätter den för connected-spåret.

---

## 2. Förändringar sedan preview-stängning (`afd97fa..3d2f7aa`)

```text
git log afd97fa..origin/main -- frontend/src/customer docs/customer-workspace app/main.py
```

**Resultat:** Inga ändringar i customer-workspace-filer i detta intervall.

Parallella spår som landat på main (relevanta för läsning, ej ändring):

| Spår | Commits (urval) | Kollision med connected |
|------|-----------------|-------------------------|
| R3/R4/R5 digital coworker | `#145`–`#184` | Ingen filkollision; läs ej write-paths |
| Customer-card-domain | `52f8a24`–`83609e3` | Separat domän (`end_customers`); ej workspace work-items |
| Testbot F | `#101`–`#102` | Ingen kollision |
| Production pilot P0 | `#108` | Ingen kollision |

Connected-spåret ska utgå från `3d2f7aa` utan att röra dessa spår.

---

## 3. Auth och session — nuläge

### 3.1 Befintliga mekanismer

| Mekanism | Modul | Tenant-källa | Browser-säker för `/app`? |
|----------|-------|--------------|---------------------------|
| Admin session | [`admin_session.py`](../../app/core/admin_session.py) | `X-Tenant-ID` header (operator väljer) | Nej — impersonation |
| Admin API key | [`admin_auth.py`](../../app/core/admin_auth.py) | `X-Tenant-ID` header | Nej |
| Tenant API key | [`auth.py`](../../app/core/auth.py) `get_verified_tenant` | Härledd från nyckel | **Förbjuden** i browser |
| Dev passthrough | `auth.py` L215–218 | `X-Tenant-ID` | Endast dev |

Admin-session är **stateless HMAC** (cookie = signerad payload). Logout rensar cookie men invaliderar **inte** token server-side. Detta uppfyller **inte** customer revocation-kraven.

### 3.2 Customer auth-gap

| Gap | Evidens |
|-----|---------|
| Inga `/auth/customer/*` routes | Grep i `app/` — 0 träffar |
| Inga `customer_session` symboler | Grep i `app/` — 0 träffar |
| Inga customer-credentials-tabeller | Grep `customer_workspace_user` — 0 träffar |
| Ingen OAuth för kund | Ej i repo |
| Legacy `/ui` API-nyckel i localStorage | [`app/ui/index.html`](../../app/ui/index.html) — **antipattern**, ej mål |

### 3.3 Befintliga kundnära endpoints (maskin-auth)

[`app/main.py`](../../app/main.py) L2295–2409:

| Endpoint | Auth | Write? |
|----------|------|--------|
| `GET /customer/account` | `get_verified_tenant` (API key) | Nej |
| `PUT /customer/account` | `get_verified_tenant` | **Ja** — ej för connected UI |
| `GET /customer/activity` | `get_verified_tenant` | Nej (saniterad) |
| `GET /customer/results` | `get_verified_tenant` | Nej |
| `GET /customer/health` | `get_verified_tenant` | Nej (saniterad) |

Dessa ska **inte** anropas från `/app` browser. Connected-läge använder `/workspace/v1` + session.

### 3.4 Låst login-beslut (connected-b)

| Regel | Värde |
|-------|-------|
| Login | `email + password` |
| Email-unicitet | **Globalt unik** bland `status = 'active'` |
| Tenant | Från `customer_workspace_users.tenant_id` — aldrig klientinput |
| Alternativ | Inget etablerat org-login-mönster i repo utan tenant-input |

### 3.5 Låst sessionsbeslut (connected-b)

| Krav | Admin (befintlig) | Customer (planerad) |
|------|-------------------|---------------------|
| HttpOnly cookie | Ja | Ja (`customer_session`) |
| Secure i prod | Ja | Ja |
| SameSite | strict | strict |
| Expiration | Token `exp` | DB `expires_at` + cookie `max_age` |
| Logout verkningsfull | **Nej** (stateless) | **Ja** (`revoked_at`) |
| Disable user | N/A (env user) | Fail-closed |
| DB per request | Nej | Ja (session lookup) |

**Modell:** Server-side `customer_workspace_sessions` med `token_hash`, `revoked_at`, `expires_at` — mönster från [`integration_invitations`](../../app/admin/tenant_lifecycle/invitation_models.py).

**Tradeoff:** Extra DB-read per request mot verifierbar revocation och disable. Stateless admin-cookie är medvetet **ej** vald.

---

## 4. Read-only-gräns (låst)

### Business/workspace writes — förbjudet (hela spåret)

Inga writes till jobs, approvals, Gmail, dispatch, scheduler, integrationer eller automation via connected-spåret.

`customer_workspace_writes` förblir `false`.

### Auth/provisioning writes — tillåtet (endast connected-b)

Tillåtna writes begränsade till:

- `customer_workspace_users` (CRUD för viewer-konton)
- `customer_workspace_sessions` (create vid login, revoke vid logout)
- Operator provisioning via admin-only routes

Dessa får **inte** öppna approval resolution, Gmail-write, dispatch eller integrationswrites.

`PUT /customer/account` ska inte användas från connected `/app`.

---

## 5. Workspace API — nuläge och källor

### 5.1 Implementation status

| Komponent | Status |
|-----------|--------|
| `app/customer_workspace/` | **Saknas** (0 filer) |
| `GET /workspace/v1/*` | **Ej implementerat** |
| API-kontrakt | Specificerat i [`api-contract.md`](api-contract.md) |

### 5.2 Stabila read-källor

| Workspace endpoint | Befintlig källa | Fil |
|--------------------|-----------------|-----|
| `/context` | Tenant account metadata | `TenantConfigRepository`, `_get_customer_account` i `main.py` |
| `/overview` | Dashboard summary + triage | `_compute_summary`, `_compute_roi`, `operations_triage` |
| `/work-items` | Cases/jobs | `list_cases` L3789+, `JobRepository` |
| `/work-items/{id}` | Case detail | `get_case` L3862+ |
| `/approvals` | Pending approvals | `ApprovalRequestRepository` |
| `/activity` | Customer activity | `customer_activity` L2331+ |
| `/health` | Customer health | `customer_health` L2383+ |
| Needs-help (i work-items) | Tenant triage | `_build_tenant_triage` i [`operations_triage.py`](../../app/admin/operations_triage.py) |

### 5.3 work_item_id

`work_item_id` = `job_id` (1:1 opaque string). Lookup med session `tenant_id`. Cross-tenant → 404.

### 5.4 Förbjudna fält (aldrig exponera)

`job_id`, `input_data`, `result`, `processor_history`, `request_payload`, `delivery_payload`, `next_on_approve`, `next_on_reject`, `execution_id`, `auto_actions`, LLM-råoutput, andra tenants `tenant_id`.

`ApprovalRequestRepository.to_dict()` får **inte** användas rakt av — innehåller interna payloads.

### 5.5 Gmail

Gmail read endast indirekt via job/activity-sammanfattningar. Inga Gmail-anrop i workspace-API. Eval-Gmail ([`app/evaluation/live/`](../../app/evaluation/live/)) är operator/eval-only.

---

## 6. Frontend — anslutningspunkt

| Komponent | Fil | Connected-ändring |
|-----------|-----|-------------------|
| Interface | `api/types.ts` | Oförändrat |
| Mock | `api/mockDataSource.ts` | Behålls |
| Auth | `auth/CustomerAuthProvider.tsx` | Välj mock vs connected |
| Ny client | `api/client.ts` | **Saknas** — skapas i connected-e |
| Ny datasource | `api/connectedDataSource.ts` | **Saknas** — skapas i connected-e |
| Vyer (C–G) | `features/**` | **Inga ändringar** planerade |

Arkitektur:

```text
UI → WorkspaceDataSource → ConnectedWorkspaceDataSource → /workspace/v1 → session → adapters
```

**Ej:** UI → `/jobs`, `/cases`, `/approvals/pending`.

---

## 7. Router och deploy

| Faktum | Evidens |
|--------|---------|
| `app/main.py` är registreringspunkt | Monolitisk; `include_router` för moduler |
| `/app` static serving | L9768+ |
| `/ops` static serving | L9767+ |
| Docker inkluderar customer build | `Dockerfile` L7, L32 |
| CI customer gates | `release-gate.yml` — `typecheck:customer`, `test:customer`, `build:customer` |

Ny router:

```python
app.include_router(customer_workspace_router, prefix="/workspace/v1")
```

Placering: efter befintliga routers (~L8585), före static handlers (~L9768).

---

## 8. Parallella domäner

### Customer-card-domain (separat)

| Aspekt | Detalj |
|--------|--------|
| Domän | Tenantens **slutkunder** (CRM-liknande) |
| API | `/end-customers` (feature-flag `END_CUSTOMER_READ_API_ENABLED=false`) |
| Service | `EndCustomerReadService` |
| Relation till workspace | **Ingen direkt** — workspace work-items kommer från `jobs`, inte end-customer aggregate |

Connected workspace ska **inte** blanda ihop tenant account (`/ops/customers`) med end-customer domain.

### Qualification flags (PENDING på main)

| Flagga | Status @ `3d2f7aa` |
|--------|----------------------|
| `PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED` | VALID (R5) |
| `PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED` | **PENDING** |
| `PROFILE_DRIVEN_TESTBOT_PASS` | **PENDING** |

Connected-spåret får inte röra live-eval eller testbot qualification.

---

## 9. Säkerhet — verifierat idag

| Kontroll | Preview | Connected (mål) |
|----------|---------|-----------------|
| API-nyckel i customer bundle | PASS (saknas) | Krävs |
| Admin cookie i customer bundle | PASS (saknas) | Krävs |
| Tenant API cross-tenant HTTP | PASS ([`test_tenant_isolation_http.py`](../../tests/test_tenant_isolation_http.py)) | Utöka för session |
| Customer session | N/A | Bygg i connected-b |
| Connected tenant isolation | NOT VERIFIED | connected-d |

---

## 10. Identifierade gaps (connected-spåret)

| ID | Gap | Todo |
|----|-----|------|
| G-1 | Ingen customer auth | connected-b |
| G-2 | Ingen server-side session med revocation | connected-b |
| G-3 | Inga customer credentials | connected-b |
| G-4 | Ingen `/workspace/v1` | connected-c |
| G-5 | Ingen `ConnectedWorkspaceDataSource` | connected-e |
| G-6 | Connected tenant isolation ej verifierad | connected-d |
| G-7 | Produktionsdeploy `/app` connected ej verifierad | connected-f |

---

## 11. Stop-gate connected-a

| Villkor | Status |
|---------|--------|
| Main auditerad @ `3d2f7aa` | PASS |
| Preview-baseline dokumenterad | PASS |
| Parallella spår identifierade | PASS |
| Auth-gap exakt | PASS |
| Sessionsbeslut dokumenterat med tradeoff | PASS |
| Read-only-gräns (business vs auth writes) låst | PASS |
| Login email globalt unik låst | PASS |
| Read-källor och förbjudna fält låsta | PASS |
| Filscope per todo låst i plan | PASS |

**connected-a kan markeras `completed` när denna fil och planen är mergeade.**

---

## 12. Referenser

| Dokument | SHA/kontext |
|----------|-------------|
| Preview closure | `afd97fa`, PR #66 + #68 |
| Preview verification | [`verification.md`](verification.md) |
| Preview limitations | [`known-limitations.md`](known-limitations.md) |
| API contract | [`api-contract.md`](api-contract.md) |
| Connected plan | [`customer-workspace-connected-plan.md`](../plans/customer-workspace-connected-plan.md) |

---

*Senast uppdaterad: 2026-08-08. Audit SHA: `3d2f7aa`.*
