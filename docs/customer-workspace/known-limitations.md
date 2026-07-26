# Kundens arbetsyta — Kända begränsningar

> Gäller preview-release på `origin/main` efter closure (Todo H).
> Closure status: **PARTIAL**.

---

## Connected mode

**Status: BLOCKED**

| Skäl | Detalj |
|------|--------|
| Customer-session-auth | `/auth/customer/*` saknas |
| Serververifierad session | Ingen cookie-baserad kundinloggning |
| API-nyckel i browser | Får inte användas (legacy `/ui` är inte målarkitektur) |

Previewläget använder en hårdkodad mock-kontext i `CustomerAuthProvider` utan nätverksvalidering.

---

## Workspace API

**Status: Specificerat, inte implementerat**

API-kontraktet i `docs/customer-workspace/api-contract.md` definierar read-only endpoints under `/workspace/v1`:

| Endpoint | Status |
|----------|--------|
| `GET /workspace/v1/context` | Ej implementerat |
| `GET /workspace/v1/overview` | Ej implementerat |
| `GET /workspace/v1/work-items` | Ej implementerat |
| `GET /workspace/v1/work-items/{work_item_id}` | Ej implementerat |
| `GET /workspace/v1/approvals` | Ej implementerat |
| `GET /workspace/v1/activity` | Ej implementerat |
| `GET /workspace/v1/health` | Ej implementerat |

Frontend använder `WorkspaceDataSource` med enbart mock-implementation (`createMockDataSource`).

---

## Data

| Begränsning | Förklaring |
|-------------|------------|
| Mock/fixturedata | All visning bygger på deterministiska fixtures |
| Ingen live Gmail-data | Ingen koppling till inkorg eller utskick |
| Ingen live approvaldata | Approvals är read-only exempelposter |
| Ingen live needs-help-adapter | Needs-help kommer från samma mock-kö |
| Ingen live tenantkontext | Företagsnamn och kontakt är fiktiva |
| Ingen live integrationshälsa | Ingen ansluten status från backend |

`last_updated_at` på översikten är fixtureägd och ska inte tolkas som liveuppdatering.

---

## Writes

Följande finns **inte** i previewarbetsytan:

- Godkänn (`approve`) / avslå (`reject`)
- Skicka / svara på mejl
- Action retry
- Ändra status
- Uppdatera automation
- Integrationswrites

Feature flags är låsta:

```typescript
customer_workspace_writes: false
connected_api: false
preview_mode: true
```

Ingen URL-parameter, localStorage eller annan browserstate kan aktivera writes.

---

## Tenantisolering

| Aspekt | Status |
|--------|--------|
| API-nyckel i browser | **Verifierat saknas** i customer-frontend |
| Admin API-nyckel i browser | **Verifierat saknas** |
| Connected tenantisolering | **Ej verifierad** — kräver session + API |
| Cross-tenant denial | **NOT APPLICABLE** i preview — ingen live tenantdata |

Mockläget innehåller ingen ansluten tenantdata. Detta får **inte** beskrivas som tenantisolering PASS för connected mode.

---

## Deploy

| Aspekt | Status |
|--------|--------|
| Customer build (`npm run build:customer`) | Verifierad lokalt och i CI |
| Operator build (`npm run build`) | Verifierad lokalt och i CI |
| Static serving (`/app`, `/ops`) | Verifierad via pytest (29 tester) |
| Docker build | Verifierad i CI; ej körd lokalt (Docker saknas i closure-miljön) |
| Produktionsdeploy `/app` | **Ej verifierad** i denna closure |

---

## Browser och tillgänglighet

| Aspekt | Detalj |
|--------|--------|
| Viewports | 320–1920 px verifierade i Todo G (CSS/test-evidens) |
| Zoom | 100–200 % delvis verifierat (Todo G) |
| Automatiska tester | 97 customer-tester inkl. quality suite |
| Manuell browser | Representativ closure-smoke dokumenterad i verification.md |
| Skärmläsarcertifiering | **Ej utförd** — automatiska tester ersätter inte full WCAG-certifiering |

---

## Kända produktbegränsningar (avsiktliga)

Dessa är **inte buggar** utan medvetna previewgränser:

- Data uppdateras inte live; översikten visar fixture-timestamp
- Sökresultat kommer från mockadaptern, inte ett sökindex
- Tidslinjer i detaljvyn är exempeldata, inte rå processorhistorik
- Approvalsvyn kan visa väntande förslag men inte fatta beslut
- Ingen kundadministration, integration setup eller inställningsvy
- `/app/login` är informativ förhandsvisning, inte riktig inloggning

---

*Senast uppdaterad: 2026-07-27. Closure Todo H.*
