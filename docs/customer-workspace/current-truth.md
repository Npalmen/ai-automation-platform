# Customer Workspace — Current Truth

> **Verifierad repositoryaudit för utvecklingsspåret kundens arbetsyta.**
> Innehåller endast verifierade fakta och explicit markerade antaganden.
> Styrande dokument: `docs/00-master-plan.md` > `docs/01-current-truth.md` > `docs/04-execution-rules.md`.

---

## Auditmetadata

| Fält | Värde |
|------|-------|
| Auditdatum | 2026-07-26 |
| Branch | `feat/customer-workspace` |
| Worktree | `c:\ai_automation_platform-customer-workspace` |
| Base SHA (`origin/main`) | `758502ed1b451929bdb4bd39c9b02aaf760c5aeb` |
| Verifieringsmetod | Statisk kodinspektion, testfilgranskning, endpointinventering i `app/main.py`, frontend/router/package-granskning, CI-workflow-granskning |
| Overall audit status | **PASS** (tillräcklig för todo A; blockerare dokumenterade för connected mode) |

---

## Governing documents — konfliktlösning

Vid konflikt gäller:

1. `docs/00-master-plan.md` — högsta auktoritet
2. `docs/07-decisions.md` — låsta beslut
3. `docs/04-execution-rules.md`
4. `docs/01-current-truth.md`

Master plan anger att customer UI behöver inte vara full self-service men ska kunna visa enkel status/wow-statistik. Kundens arbetsyta är ett separat spår och får inte förväxlas med `/ops`.

---

## Verifierade fakta

### Frontend — operatörspanel (inte kundarbetsyta)

| Faktum | Evidens |
|--------|---------|
| Befintlig React-app är operatörspanelen | `frontend/package.json` name: `krowolf-operator-panel`; router basename `/ops` i `frontend/src/routes/router.tsx:155` |
| Vite base path | `/ops/` — `frontend/vite.config.ts:6` |
| Auth är admin-session | `frontend/src/features/auth/api.ts` anropar `/auth/admin/login`, `/auth/admin/logout`, `/auth/admin/me` |
| API-klient använder cookies | `frontend/src/api/client.ts:26` — `credentials: "include"` |
| Ingen localStorage/sessionStorage i React-frontend | Grep i `frontend/src/` — 0 träffar för `localStorage`, `sessionStorage`, `X-API-Key`, `apiKey` |
| Operatörsroller | `read_only`, `operations`, `admin`, `super_admin` — `frontend/src/features/auth/types.ts` |
| Operator AppShell och nav | `frontend/src/components/operator/AppShell.tsx`, `navConfig.ts` |
| Needs-help är operator/admin-only | `frontend/src/features/needsHelp/api.ts` → `GET /admin/operations/needs-help` |
| Separat customer entry finns inte | Ingen `frontend/customer.html`, `vite.customer.config.ts` eller `frontend/src/customer/` |
| Designkontrakt finns | `frontend/design/krowolf-ui-profile.json`, `component-contracts.json`, `page-contracts.json` |
| Frontend CI-gates | `.github/workflows/release-gate.yml` job `frontend`: `npm ci`, `typecheck`, `lint`, `test:contracts`, `build` |

### Legacy UI (`app/ui/index.html`)

| Faktum | Evidens |
|--------|---------|
| Monolitisk HTML/JS operator + customer-läge | Customer tabs: results, activity, customerSettings, account (`app/ui/index.html` ~609–624) |
| Tenant API-nyckel lagras i localStorage | `localStorage.setItem(LS_KEY, key)` vid customer login (~3077–3078) |
| Customer mode validerar nyckel mot `GET /tenant` | `fetch` med `X-API-Key` (~3072) |
| Admin mode använder admin API-nyckel/session | `LS_SESSION`, `LS_ROLE_KEY` (~3055–3108) |
| Kundvyer: results, activity, account | Anropar `/customer/results`, `/customer/activity`, `/customer/account` |
| Inte design-/arkitekturmall för nytt spår | Säkerhetsantipattern (API-nyckel i localStorage); ska inte återanvändas för connected mode |

### Backend auth

| Faktum | Evidens |
|--------|---------|
| Primär tenant-auth | `get_verified_tenant` i `app/core/auth.py` |
| Resolution order | Admin session cookie + `X-Tenant-ID` → `X-Admin-API-Key` + `X-Tenant-ID` → `X-API-Key` → dev passthrough |
| Customer-session-auth saknas | Inga `/auth/customer/*` routes; inga `customer_session` symboler |
| Admin auth routes | `POST /auth/admin/login`, `POST /auth/admin/logout`, `GET /auth/admin/me` — `app/main.py:311–414` |
| Tenant härleds från API-nyckel för kundendpoints | Alla `/customer/*` använder `Depends(get_verified_tenant)` |
| Hostbaserad tenantidentitet saknas | Ingen host→tenant mapping i auth |
| Customer endpoints kräver API-nyckel | Verifierat i `docs/01-current-truth.md` och `tests/test_tenant_isolation_http.py` |

### Static serving och deploy

| Faktum | Evidens |
|--------|---------|
| `/ops` serveras från `frontend/dist/` | `app/main.py:9713–9732` — `_ops_index_html()` |
| `/ops/assets/*` | `app/main.py:9705–9710` |
| `/ui` serverar legacy HTML | `app/main.py:282–284` |
| `/app` serveras inte | Ingen route handler för `/app` i `app/main.py` |
| Docker bygger en frontend | `Dockerfile` — `node:22-slim` → `COPY --from=frontend-build /frontend/dist ./frontend/dist` |
| Caddy proxar till app:8000 | `infra/Caddyfile.example` — `@ops path /ops*` med `Cache-Control no-store` |
| Andra frontendbuild kräver | Ny dist-katalog, nya routes i `app/main.py`, ev. Dockerfile/Caddy-ändringar (stop-gates, ej ändrade nu) |

### Backend namespace

| Faktum | Evidens |
|--------|---------|
| `app/customer_workspace/` saknas | Glob — 0 filer |
| `GET /workspace/v1/*` saknas | Grep i `app/` — inga workspace HTTP routes |
| `/cases` finns tenant-scoped | `app/main.py:3729+` — filter, sort, pagination, search |
| Needs-help är admin-global | `GET /admin/operations/needs-help` — `app/main.py:9074+`; tenant-filter via query param för operator |

---

## Antaganden (ej kodverifierade i denna audit)

| Antagande | Motivering |
|-----------|------------|
| Produktions-Caddyfile matchar `infra/Caddyfile.example` strukturellt | Example markerad som inferred; live config ej hämtad |
| `origin/main` vid merge inte divergerar signifikant | Rebase görs före PR |
| Parallella branches (`feature/kapitel-2f*`, `fix/*`) påverkar inte customer-workspace docs-scope | Inga `feat/customer-workspace` konflikter hittades |

---

## Frontendkartläggning

### Applikationstyp

**Operator** — React SPA under `/ops` med admin cookie-auth och operatörsroller.

### Routing

```text
/ops/login
/ops/                    → OverviewPage
/ops/needs-help          → operator triage (admin API)
/ops/customers/*         → tenant management, onboarding, settings
/ops/incidents, /ops/alerts, /ops/digests, /ops/usage, /ops/system
```

### Återanvändbara komponenter (shared-kandidater)

| Komponent | Fil | Bedömning |
|-----------|-----|-----------|
| `EmptyState` | `frontend/src/components/operator/EmptyState.tsx` | **Återanvänd** — generisk |
| `ErrorState` | `frontend/src/components/operator/ErrorState.tsx` | **Återanvänd** |
| `LoadingState` | `frontend/src/components/operator/LoadingState.tsx` | **Återanvänd** |
| `PageHeader` | `frontend/src/components/operator/PageHeader.tsx` | **Återanvänd** med copy-anpassning |
| `StatusBadge` | `frontend/src/components/operator/StatusBadge.tsx` | **Adapter krävs** — operatorvarianter; kundstatus ska komma från backend |
| `MetricCard` | `frontend/src/components/operator/MetricCard.tsx` | **Återanvänd** |
| `FilterBar` | `frontend/src/components/operator/FilterBar.tsx` | **Återanvänd** |
| `DataTable` | `frontend/src/components/operator/DataTable.tsx` | **Delvis** — mobil kräver kortlayout enligt designregler |
| `HealthIndicator` | `frontend/src/components/operator/HealthIndicator.tsx` | **Återanvänd** för integration health |
| Design tokens | `frontend/design/krowolf-ui-profile.json` | **Återanvänd** |
| `cn()` utility | `frontend/src/lib/utils.ts` | **Återanvänd** |

### Operatorbundna (får inte flyttas rakt av)

| Komponent/feature | Anledning |
|-------------------|-----------|
| `AppShell`, `navConfig` | Operatörsnavigation, roller, miljöbadge |
| `TenantIdentifier` | Multi-tenant operator context |
| `CriticalActionDialog`, `ActionDialog` | Operator actions |
| `AuditTimeline` | Intern audit |
| `features/auth/*` | Admin session |
| `features/customers/*`, `onboarding/*`, `customerSettings/*` | Operator tenant management |
| `features/needsHelp/*` | Admin API, cross-tenant |
| `features/incidents/*`, `alerts/*`, `operatorActions/*` | Operator only |

### Separat entry — lämplighet

**PASS** — samma `frontend/package.json` kan få:
- `frontend/customer.html`
- `frontend/vite.customer.config.ts` (base `/app/`, outDir `dist-customer`)
- `frontend/src/customer/main.tsx`

Operatorbuild påverkas inte om paths är isolerade och inga befintliga filer ändras.

---

## Backendkartläggning

### Befintliga kundendpoints (`/customer/*`)

Alla använder `GET`/`PUT` med `get_verified_tenant`. Endast GET är in scope för read-only workspace.

| Endpoint | Kundvänlig | Stabilitet | Rekommendation |
|----------|------------|------------|----------------|
| `GET /customer/account` | Ja | Testad (`test_customer_saas_surfaces.py`) | **Direct reuse** (via adapter i `/workspace/v1/context`) |
| `GET /customer/activity` | Ja | Testad | **Direct reuse** (via `/workspace/v1/activity`) |
| `GET /customer/results` | Ja | Testad | **Direct reuse** (via `/workspace/v1/overview`) |
| `GET /customer/health` | Ja | Testad | **Direct reuse** (via `/workspace/v1/health`) |
| `PUT /customer/account` | N/A | Write | **Out of scope** initialt |

### Dashboard-endpoints

| Endpoint | Kundvänlig | Tester | Rekommendation |
|----------|------------|--------|----------------|
| `GET /dashboard/summary` | Nej (`ready_cases`) | `test_dashboard.py` | **Internal only** |
| `GET /dashboard/roi` | Delvis (assumptions) | `test_dashboard_roi.py` | **Adapter required** — använd `/customer/results` istället |
| `GET /dashboard/leads` | Nej | `test_lead_layer_v2.py` | **Internal only** |
| `GET /dashboard/support` | Nej | `test_support_layer_v1.py` | **Internal only** |
| `GET /dashboard/activity` | Nej (`job_id`) | `test_dashboard.py` | **Adapter required** — `/customer/activity` finns |
| `GET /dashboard/kpis` | Nej | Engine only | **Internal only** |
| `GET /dashboard/operational-insights` | Nej | Engine only | **Internal only** |
| `GET /dashboard/sla-breaches` | Nej (PII) | Engine only | **Internal only** |
| `GET /dashboard/cockpit` | Nej | **Inga HTTP-tester** | **Internal only / unstable** |

### Job/approval-endpoints

| Endpoint | Kundvänlig | Tester | Rekommendation |
|----------|------------|--------|----------------|
| `GET /jobs` | Nej (raw payloads) | `test_tenant_isolation_http.py` | **Unstable/block** för kund |
| `GET /jobs/{id}` | Nej | Cross-tenant test | **Unstable/block** |
| `GET /jobs/{id}/actions` | Nej | Inga | **Internal only** |
| `GET /jobs/{id}/approvals` | Nej | Inga | **Internal only** |
| `GET /approvals/pending` | Nej (dispatch payloads) | Auth only | **Internal only** — read-only kundvy kräver adapter |

### Cases-endpoints (alternativ källa)

| Endpoint | Kundvänlig | Kommentar |
|----------|------------|-----------|
| `GET /cases` | Delvis | Exponerar `job_id`, rå `status`, `sla_status`; har filter/sort/pagination |
| `GET /cases/{job_id}` | Nej | `processor_history`, actions, integration payloads |

**Rekommendation:** Cases ska inte konsumeras direkt av kundfrontend. Adapter i `app/customer_workspace/` ska mappa till `work_item`-kontrakt med serverägd `customer_status`.

### Tenant-endpoints

| Endpoint | Rekommendation |
|----------|----------------|
| `GET /tenant` | **Adapter required** — döljer `auto_actions`, `allowed_integrations` |
| `GET /tenant/context` | **Adapter required** — döljer `demo_mode`, intern onboarding |

---

## Endpointmatris (fullständig)

| Path | Metod | Symbol | Auth | Tenant-källa | Pagination | Filter/sort | Kundvänlig | Testad | Stabilitet | Rekommendation |
|------|-------|--------|------|--------------|------------|-------------|------------|--------|------------|----------------|
| `/tenant` | GET | `tenant_info` | `get_verified_tenant` | API key | — | — | Delvis | Ja (shape) | Stabil | Adapter |
| `/tenant/context` | GET | `tenant_context_current` | `get_verified_tenant` | API key | — | — | Delvis | Auth only | Stabil | Adapter |
| `/customer/account` | GET | `get_customer_account` | `get_verified_tenant` | API key | — | — | Ja | Ja | Stabil | Direct reuse |
| `/customer/activity` | GET | `customer_activity` | `get_verified_tenant` | API key | limit/offset | — | Ja | Ja | Stabil | Direct reuse |
| `/customer/results` | GET | `customer_results` | `get_verified_tenant` | API key | — | — | Ja | Ja | Stabil | Direct reuse |
| `/customer/health` | GET | `customer_health` | `get_verified_tenant` | API key | — | — | Ja | Ja | Stabil | Direct reuse |
| `/dashboard/summary` | GET | `dashboard_summary` | `get_verified_tenant` | API key | — | — | Nej | Ja | Stabil | Internal only |
| `/dashboard/roi` | GET | `dashboard_roi` | `get_verified_tenant` | API key | — | — | Delvis | Ja | Stabil | Adapter |
| `/dashboard/leads` | GET | `dashboard_leads` | `get_verified_tenant` | API key | — | — | Nej | Ja | Stabil | Internal only |
| `/dashboard/support` | GET | `dashboard_support` | `get_verified_tenant` | API key | — | — | Nej | Ja | Stabil | Internal only |
| `/dashboard/activity` | GET | `dashboard_activity` | `get_verified_tenant` | API key | limit/offset | — | Nej | Ja | Stabil | Adapter |
| `/dashboard/kpis` | GET | `dashboard_kpis` | `get_verified_tenant` | API key | — | — | Nej | Nej (HTTP) | Stabil | Internal only |
| `/dashboard/operational-insights` | GET | `dashboard_operational_insights` | `get_verified_tenant` | API key | limit | severity sort | Nej | Nej (HTTP) | Stabil | Internal only |
| `/dashboard/sla-breaches` | GET | `dashboard_sla_breaches` | `get_verified_tenant` | API key | — | — | Nej | Nej (HTTP) | Stabil | Internal only |
| `/dashboard/cockpit` | GET | `dashboard_cockpit` | `get_verified_tenant` | API key | — | — | Nej | Nej | **Unstable** | Internal only |
| `/approvals/pending` | GET | `list_pending_approvals` | `get_verified_tenant` | API key | limit/offset | — | Nej | Auth only | Stabil | Internal only |
| `/jobs` | GET | `list_jobs` | `get_verified_tenant` | API key | limit/offset | — | Nej | Ja | Stabil | Block |
| `/jobs/{id}` | GET | `get_job` | `get_verified_tenant` | API key | — | — | Nej | Ja | Stabil | Block |
| `/jobs/{id}/actions` | GET | `get_job_actions` | `get_verified_tenant` | API key | — | — | Nej | Nej | Stabil | Internal only |
| `/jobs/{id}/approvals` | GET | `get_job_approvals` | `get_verified_tenant` | API key | — | — | Nej | Nej | Stabil | Internal only |

---

## Authmatris

| Auth-typ | Finns | Klientlagring tillåten | Kundworkspace |
|----------|-------|------------------------|---------------|
| Tenant API key (`X-API-Key`) | Ja | **Förbjudet** i browser | Endast server-side eller mock |
| Admin API key | Ja | **Förbjudet** | Ej tillämpligt |
| Admin session cookie (`/auth/admin/*`) | Ja | HttpOnly cookie (OK för operator) | **Ej tillämpligt** — operator only |
| Customer session | **Nej** | — | **BLOCKER** för connected production |
| Host-based tenant | Nej | — | — |
| OAuth refresh i browser | Nej i React SPA | **Förbjudet** | — |

### Connected mode — blockerare

**BLOCKED** tills serververifierat customer-session-kontrakt finns.

Legacy UI lagrar tenant API-nyckel i `localStorage` — detta får **inte** upprepas i ny kundfrontend.

Minsta framtida backendändring (stop-gate, ej implementerad):
- Ny modul `app/customer_workspace/auth.py` med session/cookie-baserad kundauth
- Routes `POST /auth/customer/login`, `POST /auth/customer/logout`, `GET /auth/customer/me`
- Registrering i `app/main.py` (explicit approval gate)

---

## Serving/deploymatris

| Path | Byggs av | Serveras av | Status för `/app` |
|------|----------|-------------|-------------------|
| `/ops` | `npm run build` → `frontend/dist/` | `ops_spa_root`, `ops_spa_fallback` | Mönster att kopiera |
| `/ui` | Ingen build (statisk HTML) | `operator_ui` | Legacy, ej mål |
| `/app` | **Saknas** | **Saknas** | Kräver ny build + `app/main.py` routes |

### Filer som måste ändras för `/app` (stop-gates)

| Fil | Ändring | Status |
|-----|---------|--------|
| `frontend/vite.customer.config.ts` | Ny build, base `/app/` | Ej ändrad |
| `frontend/customer.html` | Ny entry | Ej ändrad |
| `app/main.py` | `_customer_index_html()`, `/app`, `/app/{path}`, `/app/assets/*` | **Approval gate** |
| `Dockerfile` | Ev. andra dist-kopia | **Approval gate** |
| `infra/Caddyfile` (prod) | Ev. `@app path /app*` cache headers | **Approval gate** |

`/workspace/v1` API kräver separat stop-gate: routerregistrering i `app/main.py` via `app/customer_workspace/routes.py`.

---

## Testmatris

### Befintliga frontend-gates

```text
npm run tokens:generate
npm run typecheck
npm run lint
npm run test:contracts
npm run build
```

Kör i CI: `.github/workflows/release-gate.yml` job `frontend`.

Customer-specifika scripts saknas (`typecheck:customer`, `build:customer`).

### Befintliga backend-tester relevanta för kundworkspace

| Testfil | Täcker |
|---------|--------|
| `tests/test_customer_saas_surfaces.py` | `/customer/*` shape och sanitering |
| `tests/test_dashboard.py` | `/dashboard/summary`, `/dashboard/activity` |
| `tests/test_dashboard_roi.py` | `/dashboard/roi` |
| `tests/test_tenant_isolation_http.py` | Auth, cross-tenant, `/customer/*` 401 |
| `tests/test_admin_session.py` | `/auth/admin/*` |
| `tests/test_operator_panel_static.py` | `/ops` static serving |
| `tests/test_setup_ui_endpoints.py` | `GET /tenant` shape |
| `tests/test_lead_layer_v2.py` | `/dashboard/leads` |
| `tests/test_support_layer_v1.py` | `/dashboard/support` |
| `tests/test_operational_insights.py` | Engine only (ej HTTP för kpis/cockpit) |

### Saknade tester (framtida workspace-gates)

- HTTP-tester för `GET /workspace/v1/*`
- Customer frontend contract tests
- No-secret-storage browser test
- No-write network verification
- Customer status normalization tests
- Cross-tenant workspace denial
- Responsive matrix (browser harness)

### CI

| Workflow | Innehåll |
|----------|----------|
| `release-gate.yml` | Full pytest, frontend gates, docker build |
| `live-eval.yml` | Live eval (ej relevant för docs) |
| `live-llm-eval.yml` | LLM eval |

Docs-only PR:er valideras via diff-scope; full CI körs vid merge till main.

---

## Återanvändbara delar

1. **Backend:** `/customer/account`, `/customer/activity`, `/customer/results`, `/customer/health` som datakällor bakom adapter.
2. **Backend:** `/cases` som intern källa för work-items (adapter krävs för statusmapping och fältfiltrering).
3. **Frontend:** Design tokens, loading/empty/error states, MetricCard, FilterBar, PageHeader.
4. **Frontend:** Separat Vite entry i samma package (verifierat lämpligt).
5. **Tester:** `test_customer_saas_surfaces.py` som mönster för sanitering.

---

## Förbjudna eller instabila delar

| Område | Anledning |
|--------|-----------|
| `GET /jobs`, `GET /jobs/{id}` | Rå pipeline-data |
| `GET /approvals/pending` | Dispatch/email payloads |
| `/admin/operations/needs-help` | Admin-only, cross-tenant |
| Legacy UI localStorage auth | Säkerhetsrisk |
| `app/decisioning/*`, `app/policies/*`, dispatch, Gmail write | Förbjudet scope |
| `GET /dashboard/cockpit` | Inga HTTP-tester |
| Frontend approve/reject/dispatch | Utanför read-only boundary |

---

## Konfliktrisker

| Risk | Bedömning |
|------|-----------|
| Parallellt spår ändrar `app/main.py` | Hög — routerregistrering kräver koordinering |
| Parallellt spår ändrar `frontend/package.json` | Medel — customer scripts |
| Befintlig `feat/customer-workspace` branch | **Ingen konflikt** — branch skapad ny från `origin/main` |
| Lokala ändringar i main worktree | `storage/status/*` modifierade — ej staged; påverkar inte customer worktree |
| Approval/action kontrakt under aktiv utveckling | Stop-gate om workspace behöver ändra dem |

---

## Rekommenderad arkitektur

```text
frontend/customer.html
frontend/vite.customer.config.ts
frontend/dist-customer/
frontend/src/customer/
  main.tsx
  app/
  routes/
  api/
  auth/
  components/
  features/
  layouts/
  types/

app/customer_workspace/
  __init__.py
  routes.py          # GET /workspace/v1/*
  adapters/          # Mappar intern data → kundkontrakt
  status.py          # customer_status normalisering
  schemas.py

tests/customer_workspace/
tests/test_customer_workspace_*.py
```

- **Canonical route:** `/app`
- **API namespace:** `GET /workspace/v1/*` (read-only)
- **Serving:** Spegla `/ops`-mönstret i `app/main.py`
- **Första läge:** mock/preview (auth blockerar connected)

---

## Öppna blockerare

| ID | Blockerare | Påverkan | Lösning |
|----|------------|----------|---------|
| B-1 | Ingen customer-session-auth | Connected production mode | Implementera `/auth/customer/*` (framtida, egen stop-gate) |
| B-2 | `/workspace/v1` saknas | Ingen sammanhållen kund-API | `app/customer_workspace/routes.py` + `app/main.py` registrering |
| B-3 | `/app` serveras inte | Ingen deploybar kund-SPA | `app/main.py` + customer build |
| B-4 | Needs-help saknar tenant-API | Kundvy tom utan adapter | Adapter filtrerar triage per tenant |
| B-5 | Approvals saknar kundsäker read-API | Read-only approvalvy kräver adapter | `GET /workspace/v1/approvals` |

---

## Beslut som måste låsas i todo B

1. Canonical route `/app` — **låses i product-contract** (ingen teknisk blockerare)
2. Connected vs mock/preview — **låses BLOCKED för connected**
3. Statusvokabulär och svenska etiketter — **låses i product-contract**
4. `GET /workspace/v1/*` kontrakt — **låses i api-contract**
5. Roller för kundworkspace — **låses i product-contract**
6. Routerregistrering i `app/main.py` — **dokumenteras som approval gate**
