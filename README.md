# AI Automation Platform

Multi-tenant AI automation backend för att ta emot ärenden, klassificera dem, extrahera data, fatta beslut, tillämpa policy och därefter antingen köra åtgärder automatiskt, skicka för approval eller lämna över till människa.

## Status

Projektet är förbi ren prototyp och har nu en fungerande backend-kärna med:

- FastAPI API
- PostgreSQL persistence
- SQLAlchemy repositories
- multi-tenant tenant-context via `X-Tenant-ID`
- orchestrator-baserad workflow pipeline
- AI-processorer med typed outputs
- audit events
- integration dispatcher
- approval flow med resume efter godkännande

## Vad plattformen gör

Plattformen tar in ett jobb via API och kör det genom en processor-pipeline:

1. Intake
2. Classification
3. Entity Extraction
4. Domänprocessor
5. Decisioning
6. Policy
7. Action Dispatch eller Approval / Human Handoff

Målet är att göra inkommande arbete maskinellt behandlingsbart utan att förlora kontroll, spårbarhet eller fallback till människa.

## Nuvarande pipeline-logik

### Bassteg

Alla workflows börjar med:

- `intake`
- `classification`

### Därefter per ärendetyp

#### Lead
- `entity_extraction`
- `lead`
- `decisioning`
- `policy`
- `action_dispatch`
- `human_handoff`

#### Customer inquiry
- `entity_extraction`
- `customer_inquiry`
- `decisioning`
- `policy`
- `action_dispatch`
- `human_handoff`

#### Invoice
- `entity_extraction`
- `invoice`
- `policy`
- `human_handoff`

#### Unknown
- `policy`
- `human_handoff`

## Kärnprinciper

- Alla processors är stateless
- Kommunikation mellan steg sker via `processor_history`
- AI-svar ska vara strukturerade och validerbara
- Failures ska degradera säkert
- Policy avgör om systemet får exekvera, kräver approval eller ska stanna för manuell hantering

## API-översikt

### Core
- `GET /`
- `GET /tenant`
- `GET /tenant/test`
- `GET /job-types`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs`

### Approvals
- `GET /approvals/{job_id}`
- `POST /approvals/{job_id}/approve`
- `POST /approvals/{job_id}/reject`

### Integrations
- `GET /integrations`
- `GET /integrations/available`
- `GET /integrations/{integration_type}/status`
- `POST /integrations/{integration_type}/action`
- `POST /integrations/{integration_type}/smoke-test`
- `GET /integrations/events`
- `GET /integrations/events/{event_id}`
- `POST /integrations/events/{event_id}/retry`
- `GET /integrations/events/all`

### Audit
- `GET /audit/events`
- `GET /audit/events/all`

## Mappstruktur

```text
app/
  ai/                     # LLM client, prompts, AI schemas/exceptions
  api/                    # API routes + dependencies
  core/                   # settings, logging, tenancy, config, audit service
  domain/                 # domain models, enums, schemas
  integrations/           # adapters, enums, factory, dispatcher
  repositories/postgres/  # persistence layer
  workflows/              # orchestrator, pipeline, processors, approval logic
tests/
docs/