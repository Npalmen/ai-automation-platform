# Customer Workspace — Product Contract

> **Låst produktkontrakt för kundens arbetsyta.**
> Baserat på `docs/customer-workspace/current-truth.md` (audit SHA `758502e`).
> Gäller från todo B completion. Ändringar kräver explicit godkännande.

---

## 1. Syfte och målgrupp

### Syfte

Kundens arbetsyta är företagets dagliga read-only vy över den digitala medarbetaren. Den svarar på:

1. Vad har hänt?
2. Vad behöver jag besluta?
3. Vilka kunder väntar?
4. Vilka leads är viktigast?
5. Vad har systemet redan gjort?
6. Vad har misslyckats?
7. Vad behöver en människa ta över?

Grundprincip: **Systemet arbetar. Kunden leder.**

### Målgrupp

- Ägare och ledning i installations-/servicebolag (pilotkunder)
- Operativ kontaktperson som följer leads, kundfrågor och approvals
- **Inte** interna Krowolf-operatörer (de använder `/ops`)

---

## 2. Relation till andra ytor

| Yta | Route | Relation |
|-----|-------|----------|
| Operatörspanel | `/ops` | Separat produkt; får inte påverkas |
| Legacy UI | `/ui` | Historisk referens; ej målarkitektur |
| Kundens arbetsyta | `/app` | Detta kontrakt |

Kundfrontend får **inte** implementera decisioning, approval resolution, dispatch, Gmail-logik, policy authorization, schedulerlogik eller integrationswrite-logik.

---

## 3. Initial read-only boundary

### Tillåtet (read-only visning)

- Dagens viktigaste händelser och prioriterade arbetsobjekt
- Leads, kundfrågor, approvals (read-only), needs-help
- Utförda och väntande aktiviteter (när verifierad data finns)
- Status, historik, sökning, filtrering
- Loading, empty, partial error, full error
- Desktop, tablet, mobil

### Förbjudet initialt

| Action | UI-behandling |
|--------|---------------|
| approve / reject | Ej kopplad; disabled eller dold |
| dispatch | Ej kopplad |
| Gmail reply | Ej kopplad |
| action retry | Ej kopplad |
| schedulerändring | Ej kopplad |
| integrationswrite | Ej kopplad |
| automation mode write | Ej kopplad |
| policyändring | Ej kopplad |
| decision write | Ej kopplad |

Framtida write-ytor får endast visas som disabled state, preview, mockadapter eller avstängd feature flag.

---

## 4. Teknisk placering (låst)

| Beslut | Värde | Status |
|--------|-------|--------|
| Canonical route | `/app` | **LOCKED** |
| Vite base path | `/app/` | **LOCKED** |
| Build entry | `frontend/customer.html` | **LOCKED** |
| Vite config | `frontend/vite.customer.config.ts` | **LOCKED** |
| Build output | `frontend/dist-customer/` | **LOCKED** |
| Frontend namespace | `frontend/src/customer/**` | **LOCKED** |
| Shared components | `frontend/src/components/shared/**` (ny katalog vid behov) | **LOCKED** |
| Backend namespace | `app/customer_workspace/**` | **LOCKED** |
| API namespace | `GET /workspace/v1/*` | **LOCKED** |
| Test namespace | `tests/customer_workspace/**`, `tests/test_customer_workspace_*.py` | **LOCKED** |

### Servingstrategi

1. Customer SPA byggs med `npm run build:customer` (läggs till i todo C).
2. FastAPI serverar `/app`, `/app/{path}`, `/app/assets/*` från `frontend/dist-customer/` — samma mönster som `/ops`.
3. **Stop-gate:** Registrering i `app/main.py` kräver explicit godkännande (ej gjort i A/B).

---

## 5. Informationsarkitektur

### Routes (låst)

```text
/app                      → Översikt
/app/leads                → Leads
/app/support              → Kundfrågor
/app/approvals            → Godkännanden (read-only)
/app/needs-help           → Behöver hjälp
/app/activity             → Aktivitet
/app/search               → Global sökning
/app/work/:workItemId     → Arbetsobjektdetalj
/app/login                → Login (mock/preview eller framtida customer session)
/app/forbidden            → 403
```

### Huvudnavigation (synlig)

1. Översikt
2. Leads
3. Kundfrågor
4. Godkännanden
5. Behöver hjälp
6. Aktivitet

Sök (`/app/search`) nås via header-sökfält, inte primär nav-länk.

### Detaljroute

`/app/work/:workItemId` — gemensam detaljvy för leads, support, approvals och needs-help.

### Global sökning

- Route: `/app/search`
- Query-param: `q` (obligatorisk för resultat)
- Filter: `type`, `status`, `from`, `to` (allowlist, se api-contract)
- Backend: `GET /workspace/v1/work-items?q=...`

---

## 6. Roller

| Roll | Beskrivning | Tillgång |
|------|-------------|----------|
| `customer_viewer` | Read-only kundanvändare | Alla read-only vyer |
| `customer_admin` | Framtida; ej i initial scope | Samma som viewer initialt |

Initial implementation har en roll: **customer_viewer**. Rollen tilldelas via framtida customer-session; i mock/preview är rollen implicit.

Operatörsroller (`read_only`, `operations`, `admin`, `super_admin`) gäller **inte** i `/app`.

---

## 7. Authstrategi (låst beslut)

### Förbjuden klientlagring

Följande får **aldrig** lagras i:

- `localStorage`
- `sessionStorage`
- `IndexedDB`
- URL
- HTML
- JavaScript build constants
- Oskyddade cookies

Förbjudna hemligheter: tenant-API-nyckel, admin-API-nyckel, Gmail-token, OAuth refresh token, integrationshemligheter.

### Lägen

| Läge | Beskrivning | Initial status |
|------|-------------|----------------|
| `mock` | Hårdkodad/fixture-data i frontend | **Default för shell (todo C)** |
| `preview` | Frontend anropar mockadapter som speglar API-kontrakt | Tillgängligt parallellt |
| `connected` | Live API med serververifierad session | **BLOCKED** |

### Connected mode — BLOCKED

**Beslut:** Connected read-only-läge är **blockerat** tills customer-session-auth finns.

Skäl (verifierat i current-truth):
- Ingen `/auth/customer/*` implementation
- Enda befintliga tenant-auth är `X-API-Key` (får inte i browser)
- Legacy UI:s localStorage-mönster är explicit förbjudet

**Det är inte tillåtet** att rekommendera tenant-API-nyckel i webbläsaren.

### Tenantkälla (connected, framtida)

När customer-session finns:
- Tenant härleds **endast** från serververifierad session
- Frontend skickar inga `X-Tenant-ID` eller `X-API-Key` headers
- Cookie: HttpOnly, Secure, SameSite=Lax (minimikrav)

---

## 8. Statusvokabulär (låst)

Backend äger normalisering från interna statusar till `customer_status`.
Frontend presenterar **endast** `customer_status` och `customer_status_label` (svenska).

| `customer_status` | Svensk etikett |
|-------------------|----------------|
| `new` | Ny |
| `prioritized` | Prioriterad |
| `in_progress` | Pågår |
| `waiting_for_decision` | Väntar på beslut |
| `waiting_for_customer` | Väntar på kund |
| `prepared` | Förberedd |
| `scheduled` | Planerad |
| `completed` | Klar |
| `needs_help` | Behöver hjälp |
| `failed` | Misslyckades |
| `cancelled` | Avbruten |
| `unknown` | Okänd status |

### Fail-safe för okända statusar

- Backend mappar okända interna värden till `customer_status: "unknown"` och `customer_status_label: "Okänd status"`.
- Frontend får **inte** visa råa backend-enum (`awaiting_approval`, `processor_history`, etc.).
- Frontend får **inte** tolka decision/execution-kedjor.

---

## 9. Prioriteringsprincip

- Backend returnerar `priority_rank` (integer, lägre = högre prioritet) och `priority_label` (valfri svensk text).
- Frontend renderar backendens ordning; ingen egen risk- eller beslutsmotor.

---

## 10. UX-kontrakt

### Loading

- Skeleton eller spinner per sektion
- Global overlay endast vid initial shell-load

### Empty

- Tydlig svensk text: vad som saknas och varför det kan vara tomt
- Ingen teknisk jargon

### Partial error

- Sektioner som misslyckats visar inline fel med retry
- Övriga sektioner fortsätter rendera

### Full error

- Hela vyn ersätts med `ErrorState` och retry

### HTTP-fel

| Kod | Beteende |
|-----|----------|
| 401 | Redirect till `/app/login` |
| 403 | Redirect till `/app/forbidden` |
| 404 | Arbetsobjekt hittades inte (detaljvy) eller NotFound-sida |
| 5xx | Full error med retry |

### Stale data

- Visa `last_updated_at` i översikt
- Vid bakgrundsuppdatering: diskret indikator, ingen full sidladdning

### Responsivitet

| Viewport | Layout |
|----------|--------|
| Desktop ≥1024px | Sidebar + innehåll |
| Tablet 768–1023px | Kollapsbar sidebar |
| Mobil <768px | Bottom nav eller hamburger; inga horisontella tabeller utan kortlayout |

### Tillgänglighet (minimum)

- Tangentbordsnavigering i huvudnav
- Synliga fokusmarkörer
- `aria-label` på ikonknappar
- Status visas med text + färg (inte enbart färg)

---

## 11. Approvalkontrakt (read-only)

### Visningsbara fält

- `approval_id`, `title`, `summary`, `customer_status`, `requested_at`, `work_item_id`, `work_item_type`, `work_item_title`
- **Ej:** `request_payload`, `delivery_payload`, `next_on_approve`, `next_on_reject`, `job_id` (ersätts av `work_item_id`)

### Regler

- approve/reject **kopplas inte in**
- Framtida actions: disabled + feature flag `customer_workspace_writes=false`
- Approval resolution förblir huvudspårets ansvar (`app/workflows/*`)

---

## 12. Implementation paths per todo

| Todo | Tillåtna paths |
|------|----------------|
| C — shell | `frontend/src/customer/**`, `frontend/customer.html`, `frontend/vite.customer.config.ts`, `frontend/src/components/shared/**`, `frontend/src/lib/**`, `frontend/src/styles/**` |
| D — overview | + `frontend/src/customer/features/overview/**` |
| E — workflows | + `frontend/src/customer/features/leads/**`, `support/**`, `approvals/**`, `needs-help/**` |
| F — activity | + `frontend/src/customer/features/activity/**`, `search/**`, `work-detail/**` |
| G — quality | Samtliga customer paths + responsive/a11y fixes |
| H — closure | + `docs/customer-workspace/release-notes.md`, `known-limitations.md`, `verification.md` |

Backend (alla implementationstodos efter B-godkännande):
- `app/customer_workspace/**`
- `tests/customer_workspace/**`
- `tests/test_customer_workspace_*.py`
- `app/main.py` endast via explicit stop-gate-godkännande

---

## 13. Testgates per todo

### Gemensamma frontend-gates (varje todo som ändrar frontend)

```text
cd frontend
npm run tokens:generate
npm run typecheck
npm run lint
npm run test:contracts
npm run build
```

### Customer-specifika (från todo C)

```text
npm run typecheck:customer
npm run test:customer
npm run build:customer
```

### Backend (från workspace API-implementation)

```text
python -m pytest tests/customer_workspace/ tests/test_customer_workspace_*.py -q
python -m pytest tests/test_tenant_isolation_http.py -q -k workspace
```

### Säkerhetsgates (todo G)

- Ingen API-nyckel i frontend bundle (grep/CI)
- Inga write-anrop i network log (browser harness)
- Cross-tenant denial
- Operator regression: `npm run build` (operator) måste passera

---

## 14. Förbjudet scope (oförändrat från plan)

Får **inte** ändras utan separat godkännande:

```text
app/main.py                    (utom godkänd routerregistrering)
app/workflows/action_approval_resolution.py
app/workflows/approval_dispatcher.py
app/workflows/action_dispatch*
app/decisioning/*
app/policies/*
app/evaluation/live/*
testbot scenariofiler
approvalkontrakt
action authorization-kontrakt
execution intent/outcome-kontrakt
Gmail write-policy
migrationsfiler
databasschema
frontend produktionskod under src/ (operator)
Dockerfile, compose, Caddy, CI-workflows
```

---

## 15. Routerregistrering — approval gate

### `/app` serving (minsta ändring)

**Fil:** `app/main.py`  
**Symboler att lägga till:** `_customer_dist_root()`, `_customer_index_html()`, `_resolve_customer_asset()`, `customer_spa_root`, `customer_spa_fallback`, `customer_static_asset`  
**Mönster:** Kopiera `/ops`-handlers; peka på `frontend/dist-customer/`

### `/workspace/v1` API

**Fil:** `app/main.py`  
**Ändring:** `app.include_router(customer_workspace_router, prefix="/workspace/v1")`  
**Modul:** `app/customer_workspace/routes.py`  
**Regel:** Ingen registrering via import side effects

Båda kräver explicit godkännande innan implementation.

---

## 16. Kontraktsstatus

| Område | Status |
|--------|--------|
| Canonical route `/app` | **LOCKED** |
| Read-only boundary | **LOCKED** |
| Auth (connected blocked) | **LOCKED** |
| Statusvokabulär | **LOCKED** |
| Routes och navigation | **LOCKED** |
| Mock/preview first | **LOCKED** |
