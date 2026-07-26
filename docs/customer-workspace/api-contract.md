# Customer Workspace — API Contract

> **Read-only API-kontrakt under `GET /workspace/v1`.**
> Inga POST, PUT, PATCH eller DELETE i initial scope.
> Baserat på `docs/customer-workspace/current-truth.md`.

---

## 1. Översikt

| Egenskap | Värde |
|----------|-------|
| Base path | `/workspace/v1` |
| Metoder | **GET endast** |
| Auth (connected) | Customer session cookie (framtida) |
| Auth (initial dev) | Mock adapter i frontend |
| Tenant source | Serververifierad session → `tenant_id` |
| Content-Type | `application/json` |
| Stabilitet | **Ny** — kräver `app/customer_workspace/` implementation |

### Response envelope (gemensam)

Alla list-endpoints returnerar:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0,
  "partial_errors": []
}
```

`partial_errors` är en array av `{ "section": string, "code": string, "message": string }` när en del av aggregerad data inte kunde hämtas. HTTP-status förblir `200` om minst en sektion lyckades.

Enkelobjekt-endpoints returnerar objektet direkt (ingen wrapper).

### Felkoder

| HTTP | `detail` / body | Betydelse |
|------|-----------------|-----------|
| 401 | `Not authenticated` | Saknad/ogiltig session |
| 403 | `Forbidden` | Tenant inaktiv eller roll saknas |
| 404 | `Not found` | Resurs saknas eller annan tenant |
| 422 | Validation error | Ogiltiga query params |
| 500 | `Internal server error` | Oväntat fel |
| 503 | `Service unavailable` | Beroende otillgängligt |

Cross-tenant access ska returnera **404** (inte 403) för att undvika enumeration.

---

## 2. Statuskontrakt

### Fält på alla arbetsrelaterade objekt

```typescript
type CustomerStatus =
  | "new"
  | "prioritized"
  | "in_progress"
  | "waiting_for_decision"
  | "waiting_for_customer"
  | "prepared"
  | "scheduled"
  | "completed"
  | "needs_help"
  | "failed"
  | "cancelled"
  | "unknown"

interface CustomerStatusFields {
  customer_status: CustomerStatus
  customer_status_label: string  // Svenska, serverägd
}
```

### Normalisering (backend-ägd)

Implementeras i `app/customer_workspace/status.py`.

| Intern status (exempel) | `customer_status` |
|-------------------------|-------------------|
| `pending`, `received` | `new` |
| `prioritized`, `hot` | `prioritized` |
| `processing`, `running` | `in_progress` |
| `awaiting_approval` | `waiting_for_decision` |
| `waiting_customer`, `awaiting_info` | `waiting_for_customer` |
| `draft_ready`, `prepared` | `prepared` |
| `scheduled` | `scheduled` |
| `completed`, `done` | `completed` |
| `needs_help`, `manual_review` | `needs_help` |
| `failed`, `error` | `failed` |
| `cancelled`, `rejected` | `cancelled` |
| Okänt | `unknown` |

Frontend får **inte** duplicera denna mapping.

---

## 3. Endpoints

### 3.1 `GET /workspace/v1/context`

Bootstrap för shell.

| Egenskap | Värde |
|----------|-------|
| Auth | Customer session (framtida) |
| Tenant | Session |
| Källrepositories | `get_customer_account`, `_build_tenant_context_payload` (saniterad) |

**Query parameters:** inga

**Response:**

```json
{
  "tenant_id": "TENANT_1001",
  "company_name": "Acme AB",
  "contact_name": "Anna Svensson",
  "contact_email": "anna@acme.se",
  "support_email": "support@acme.se",
  "language": "sv",
  "region": "SE",
  "workspace_mode": "connected",
  "feature_flags": {
    "customer_workspace_writes": false,
    "connected_api": false
  }
}
```

**Förbjudna fält:** `auto_actions`, `allowed_integrations`, `demo_mode`, intern onboarding-procent

**Återanvändning:** Adapter över `GET /customer/account` + saniterad tenant context

**Stabilitet:** Ny; beroende av `app/customer_workspace/`

---

### 3.2 `GET /workspace/v1/overview`

Daglig översikt och prioriterad arbetslista.

| Egenskap | Värde |
|----------|-------|
| Auth | Customer session |
| Tenant | Session |
| Källrepositories | `customer_results`, `customer_activity`, cases query, approvals adapter, needs-help adapter |

**Query parameters:** inga

**Response:**

```json
{
  "last_updated_at": "2026-07-26T18:00:00+02:00",
  "summary": {
    "cases_handled_today": 12,
    "waiting_for_decision": 3,
    "waiting_for_customer": 2,
    "needs_help": 1,
    "failed_today": 0,
    "estimated_hours_saved": 1.5,
    "estimated_value_sek": 750
  },
  "priority_work_items": [
    {
      "work_item_id": "wi_abc123",
      "type": "lead",
      "title": "Offertförfrågan solceller",
      "customer_name": "Erik Johansson",
      "customer_status": "waiting_for_decision",
      "customer_status_label": "Väntar på beslut",
      "priority_rank": 1,
      "priority_label": "Hög prioritet",
      "updated_at": "2026-07-26T17:30:00+02:00"
    }
  ],
  "partial_errors": []
}
```

**Pagination:** Nej (top N=20 priority items server-side)

**Sortering:** `priority_rank ASC`, sedan `updated_at DESC` (serverägd)

**Förbjudna fält:** `job_id`, `approval_id`, processor payloads

**Återanvändning:** Adapter — kombinerar `/customer/results`, cases, approvals, needs-help

---

### 3.3 `GET /workspace/v1/work-items`

Lista arbetsköer (leads, support, needs-help, mixed).

| Egenskap | Värde |
|----------|-------|
| Auth | Customer session |
| Tenant | Session |
| Källrepositories | `list_cases` (adapter), needs-help adapter |

**Query parameters:**

| Param | Typ | Default | Beskrivning |
|-------|-----|---------|-------------|
| `type` | `lead` \| `support` \| `needs_help` \| `all` | `all` | Arbetsobjektstyp |
| `status` | `CustomerStatus` | — | Filter på normaliserad status |
| `q` | string | — | Sök i titel, kundnamn, e-post |
| `from` | ISO date | — | Skapad från |
| `to` | ISO date | — | Skapad till |
| `sort` | `updated_at` \| `priority_rank` \| `created_at` | `priority_rank` | Sorteringsfält |
| `order` | `asc` \| `desc` | `asc` för priority, `desc` för datum | Riktning |
| `limit` | int 1–100 | 50 | Sidstorlek |
| `offset` | int ≥0 | 0 | Offset |

**Response item:**

```json
{
  "work_item_id": "wi_abc123",
  "type": "lead",
  "title": "Offertförfrågan",
  "customer_name": "Erik Johansson",
  "customer_email": "erik@example.com",
  "customer_status": "prioritized",
  "customer_status_label": "Prioriterad",
  "priority_rank": 2,
  "priority_label": null,
  "summary": "Kort kundvänlig sammanfattning",
  "created_at": "2026-07-25T10:00:00+02:00",
  "updated_at": "2026-07-26T09:00:00+02:00"
}
```

**Förbjudna fält:** `job_id`, `input_data`, `result`, `sla_status` (rå), `processor_history`

**Återanvändning:** Adapter över `GET /cases` + needs-help triage

**Stabilitet:** Beroende av cases-kontrakt (stabil men kräver adapter)

---

### 3.4 `GET /workspace/v1/work-items/{work_item_id}`

Detaljvy för ett arbetsobjekt.

| Egenskap | Värde |
|----------|-------|
| Auth | Customer session |
| Tenant | Session |
| Källrepositories | `get_case` (adapter), action summary (saniterad) |

**Path:** `work_item_id` — opaque string; internt mappat till `job_id` server-side (aldrig exponerat till klient som primärnyckel i listor utöver work_item_id)

**Response:**

```json
{
  "work_item_id": "wi_abc123",
  "type": "support",
  "title": "Fråga om installation",
  "customer_name": "Maria Lind",
  "customer_email": "maria@example.com",
  "customer_status": "waiting_for_customer",
  "customer_status_label": "Väntar på kund",
  "priority_rank": 5,
  "summary": "Kunden har fått en fråga om mått",
  "created_at": "2026-07-20T08:00:00+02:00",
  "updated_at": "2026-07-26T11:00:00+02:00",
  "timeline": [
    {
      "at": "2026-07-20T08:00:00+02:00",
      "kind": "received",
      "label": "Ärende mottaget",
      "detail": null
    },
    {
      "at": "2026-07-20T08:05:00+02:00",
      "kind": "system_action",
      "label": "Systemet analyserade ärendet",
      "detail": null
    }
  ],
  "waiting_for": "Svar från kund om mått",
  "human_takeover_required": false
}
```

**Förbjudna fält:** `processor_history`, `request_payload`, `result_payload`, `execution_id`, `external_id`, LLM-råoutput

**404:** Okänd `work_item_id` eller annan tenant

**Återanvändning:** Adapter över `GET /cases/{job_id}` — **inte** direkt konsumtion

---

### 3.5 `GET /workspace/v1/approvals`

Read-only lista över väntande godkännanden.

| Egenskap | Värde |
|----------|-------|
| Auth | Customer session |
| Tenant | Session |
| Källrepositories | `list_pending_approvals` (saniterad) |

**Query parameters:**

| Param | Typ | Default |
|-------|-----|---------|
| `limit` | int 1–100 | 50 |
| `offset` | int ≥0 | 0 |
| `status` | `pending` \| `all` | `pending` |

**Response item:**

```json
{
  "approval_id": "apr_xyz",
  "work_item_id": "wi_abc123",
  "work_item_type": "lead",
  "work_item_title": "Offert solceller",
  "title": "Godkänn utskick",
  "summary": "Systemet vill skicka offertutkast",
  "customer_status": "waiting_for_decision",
  "customer_status_label": "Väntar på beslut",
  "requested_at": "2026-07-26T16:00:00+02:00"
}
```

**Förbjudna fält:** `request_payload`, `delivery_payload`, `next_on_approve`, `next_on_reject`, `job_id`, `channel`, `requested_by`

**Återanvändning:** Adapter över `GET /approvals/pending`

**Regel:** Inga approve/reject endpoints i detta namespace

---

### 3.6 `GET /workspace/v1/activity`

Aktivitetshistorik.

| Egenskap | Värde |
|----------|-------|
| Auth | Customer session |
| Tenant | Session |
| Källrepositories | `customer_activity` |

**Query parameters:**

| Param | Typ | Default |
|-------|-----|---------|
| `limit` | int 1–100 | 25 |
| `offset` | int ≥0 | 0 |
| `type` | `lead` \| `support` \| `invoice` \| `all` | `all` |

**Response item:**

```json
{
  "at": "2026-07-26T14:00:00+02:00",
  "type": "lead",
  "customer_status": "completed",
  "customer_status_label": "Klar",
  "priority": "normal",
  "label": "Lead hanterat"
}
```

**Återanvändning:** **Direct reuse** via tunn wrapper över `GET /customer/activity` (lägg till `customer_status` fält i adapter)

**Stabilitet:** Hög — befintliga tester i `test_customer_saas_surfaces.py`

---

### 3.7 `GET /workspace/v1/health`

Integration och systemhälsa.

| Egenskap | Värde |
|----------|-------|
| Auth | Customer session |
| Tenant | Session |
| Källrepositories | `customer_health` |

**Query parameters:** inga

**Response:**

```json
{
  "overall_status": "healthy",
  "message": "Alla kopplingar fungerar",
  "systems": {
    "google_mail": { "status": "healthy", "label": "E-post" },
    "fortnox": { "status": "not_configured", "label": "Fortnox" }
  }
}
```

**Återanvändning:** **Direct reuse** över `GET /customer/health`

**Stabilitet:** Hög

---

## 4. Sökendpoint

Global sökning använder `GET /workspace/v1/work-items` med `q` satt. Ingen separat search-endpoint.

`/app/search` → frontend route som anropar work-items med query params.

---

## 5. Källrepository-matris

| Workspace endpoint | Befintlig källa | Återanvändning |
|--------------------|-----------------|----------------|
| `/context` | `/customer/account`, `/tenant/context` | Adapter (sanitera) |
| `/overview` | `/customer/results`, cases, approvals, needs-help | Adapter |
| `/work-items` | `/cases`, needs-help triage | Adapter |
| `/work-items/{id}` | `/cases/{job_id}` | Adapter |
| `/approvals` | `/approvals/pending` | Adapter (sanitera) |
| `/activity` | `/customer/activity` | Direct reuse (+ statusfält) |
| `/health` | `/customer/health` | Direct reuse |

---

## 6. Förbjudna fält (globalt)

Får aldrig returneras i workspace-responses:

- `job_id` (ersätts av `work_item_id`)
- `input_data`, `result` (rå)
- `processor_history`
- `request_payload`, `delivery_payload`, `result_payload`
- `next_on_approve`, `next_on_reject`
- `execution_id`, `external_id`, `provider`
- `auto_actions`, `allowed_integrations`
- LLM-råoutput, stack traces
- Andra tenants `tenant_id`

---

## 7. Implementation och routerregistrering

### Ny modul

```text
app/customer_workspace/
  __init__.py
  routes.py       # APIRouter med alla GET handlers
  schemas.py      # Pydantic response models
  status.py       # customer_status mapping
  adapters/
    account.py
    work_items.py
    approvals.py
    overview.py
    activity.py
    health.py
```

### Registrering (approval gate)

**Fil:** `app/main.py`  
**Rad:** Efter befintliga router includes, före static handlers  
**Kod (föreslagen):**

```python
from app.customer_workspace.routes import router as customer_workspace_router
app.include_router(customer_workspace_router, prefix="/workspace/v1", tags=["customer-workspace"])
```

**Auth dependency:** Ny `get_customer_session_tenant` (framtida); under utveckling kan endast testas med `X-API-Key` i integrationstester — **inte** i browser.

### Tester (krävs vid implementation)

```text
tests/customer_workspace/test_context.py
tests/customer_workspace/test_work_items.py
tests/customer_workspace/test_approvals_read_only.py
tests/customer_workspace/test_status_mapping.py
tests/test_customer_workspace_tenant_isolation.py
```

---

## 8. Write-förbud (verifiering)

Initialt kontrakt innehåller **inga** POST, PUT, PATCH, DELETE.

Docs-gate: grep på `api-contract.md` och `routes.py` vid implementation ska bekräfta GET-only.

---

## 9. Kontraktsstatus

| Endpoint | Spec klar | Implementation |
|----------|-----------|----------------|
| `GET /workspace/v1/context` | Ja | Ej implementerad |
| `GET /workspace/v1/overview` | Ja | Ej implementerad |
| `GET /workspace/v1/work-items` | Ja | Ej implementerad |
| `GET /workspace/v1/work-items/{id}` | Ja | Ej implementerad |
| `GET /workspace/v1/approvals` | Ja | Ej implementerad |
| `GET /workspace/v1/activity` | Ja | Ej implementerad |
| `GET /workspace/v1/health` | Ja | Ej implementerad |

**Overall API contract status:** **LOCKED** (spec); **BLOCKED** (connected runtime tills auth + router finns)
