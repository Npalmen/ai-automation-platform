# AI Automation Platform

Multi-tenant AI automation backend för att ta emot inkommande arbete, förstå det, fatta kontrollerade beslut och därefter:

- köra åtgärder automatiskt
- pausa för approval
- lämna över till människa

Plattformen är byggd för att bli en osynlig AI-operatör för små bolag, växande bolag och enterprise use cases.

---

## Syfte

Systemet automatiserar och orkestrerar arbetsflöden för exempelvis:

- leads
- fakturor
- kundärenden
- interna processer
- notifieringar och uppföljningar

Målet är inte “fri AI”, utan kontrollerad AI i en deterministisk workflow-motor där:

- processors är stateless
- jobs är stateful
- orchestratorn styr flödet
- AI används för strukturerade beslut, inte för att styra systemflödet direkt

---

## Nuvarande status

Projektet är förbi ren prototyp och har nu en fungerande backend-kärna med:

- FastAPI API
- PostgreSQL persistence
- SQLAlchemy repository layer
- multi-tenant tenant-context via `X-Tenant-ID`
- orchestrator-baserad workflow pipeline
- AI-processorer med typed outputs
- approval flow med pause/resume
- action dispatch
- audit events
- approval persistence i DB
- action execution persistence i DB
- read-endpoints för approvals och actions
- live-testad Gmail integration via Google Mail provider

Detta är nu en teknisk MVP med riktig exekveringsförmåga, inte bara en konceptuell arkitektur.

---

## Arkitektur i korthet

### Kärnregler

- Alla processors är stateless
- Jobbet bär historik via `processor_history`
- Orchestratorn styr pipeline, skip logic och resume-logik
- Policy avgör om systemet får autoexekvera, kräver approval eller måste stanna för manuell hantering
- AI-output ska vara strukturerad, validerbar och sparbar

### Workflow-princip

Bassteg:

1. `intake`
2. `classification`

Därefter dynamisk pipeline beroende på ärendetyp.

### Exempel: lead flow

1. `intake`
2. `classification`
3. `entity_extraction`
4. `lead`
5. `decisioning`
6. `policy`
7. `action_dispatch`
8. `human_handoff` vid behov

### Approval flow

1. pipeline når policy
2. policy kräver approval
3. approval request skapas
4. jobbet pausas som `awaiting_approval`
5. approve/reject via API
6. approve återupptar post-approval path
7. reject skickar till `manual_review`

---

## Vad som fungerar nu

### Core
- FastAPI backend
- settings, logging och tenant middleware
- PostgreSQL + repositories
- job persistence

### AI pipeline
- intake
- classification
- entity extraction
- lead processor
- invoice processor
- decisioning
- policy

### Workflow engine
- dynamisk pipeline
- skip logic
- audit logging
- error handling
- approval resume

### Integrations
- Google Mail / Gmail provider fungerar live för `send_email`
- Slack finns som integrationsspår
- Monday, Visma, Google och Microsoft ligger i integrationsarkitekturen

### Persistence
- jobs
- audit events
- approval requests
- action executions

### Read/API surface
- job list
- job detail
- pending approvals
- job approvals
- job actions
- approve / reject

---

## Vad som saknas för säljbar produkt

Nästa stora fokus är inte mer kärnarkitektur, utan produktisering:

1. minimal operator/admin UI
2. input connectors
3. DB-driven tenant config
4. auth / API keys / roller
5. bättre testtäckning
6. riktig integration event persistence för direkta integrationstest-endpoints
7. onboardingflöde för kundkoppling av Gmail, Visma, Monday och Slack

---

## API-översikt

### Core
- `GET /`
- `GET /tenant`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs`

### Actions / approvals
- `GET /jobs/{job_id}/actions`
- `GET /jobs/{job_id}/approvals`
- `GET /approvals/pending`
- `POST /approvals/{approval_id}/approve`
- `POST /approvals/{approval_id}/reject`

### Integrations
- `GET /integrations`
- `POST /integrations/{integration_type}/execute`

### Audit
- `GET /audit-events`

---

## Mappstruktur

```text
app/
  ai/
  api/
  core/
  domain/
  integrations/
  repositories/postgres/
  workflows/
docs/
tests/