# Current State

## Status summary
Projektet har passerat konceptstadiet och har en fungerande backend-kärna med riktig exekveringsförmåga.

## Confirmed implemented
- [x] FastAPI API
- [x] PostgreSQL persistence
- [x] SQLAlchemy repository layer
- [x] Multi-tenant tenant-context via `X-Tenant-ID`
- [x] Orchestrator-baserad workflow pipeline
- [x] AI-processorer med typed outputs
- [x] Approval flow med pause/resume
- [x] Action dispatch
- [x] Audit events
- [x] Approval persistence i DB
- [x] Action execution persistence i DB
- [x] Read-endpoints för approvals och actions
- [x] Live-testad Gmail / Google Mail integration för `send_email`

## Confirmed API surface
### Core
- [x] `GET /`
- [x] `GET /tenant`
- [x] `GET /jobs`
- [x] `GET /jobs/{job_id}`
- [x] `POST /jobs`

### Actions / approvals
- [x] `GET /jobs/{job_id}/actions`
- [x] `GET /jobs/{job_id}/approvals`
- [x] `GET /approvals/pending`
- [x] `POST /approvals/{approval_id}/approve`
- [x] `POST /approvals/{approval_id}/reject`

### Integrations
- [x] `GET /integrations`
- [x] `POST /integrations/{integration_type}/execute`

### Audit
- [x] `GET /audit-events`

## Partially implemented / needs hardening
- [ ] Operator/admin UI
- [ ] DB-driven tenant config
- [ ] Auth / API keys / roller
- [ ] Bättre testtäckning
- [ ] Riktig integration event persistence för direkta integrationstest-endpoints
- [ ] Kundonboarding för Gmail, Visma, Monday och Slack

## Known risks
- Dokumentationen är idag splittrad över flera filer
- Huvudplan riskerar att drifta mellan chattar om docs inte konsolideras
- Frontend saknas eller är inte officiellt etablerad som MVP-del
- Vissa integrationsspår finns i arkitekturen men ska inte tolkas som produktionklara