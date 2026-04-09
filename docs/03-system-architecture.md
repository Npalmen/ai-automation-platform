# System Architecture

## Architecture summary
Systemet består av:
- FastAPI API-lager
- Workflow/orchestrator-lager
- Stateless processors
- PostgreSQL persistence
- Integrationslager med adapter/factory-pattern
- Audit + approval persistence
- Senare tunt operator/admin UI ovanpå API:t

## Core architecture principles
- Processors ska vara stateless
- Jobs ska vara stateful och bära historik
- Orchestratorn styr pipeline, skip logic och resume-paths
- Policy avgör auto/approval/manual review
- AI-output ska vara strukturerad, validerbar och sparbar
- Integrationer ska exekveras via gemensamt integrationslager

## Backend layers
- `app/core/`
- `app/domain/`
- `app/workflows/`
- `app/integrations/`
- `app/repositories/postgres/`
- `app/api/`
- `app/ai/` (om fortfarande aktiv i aktuell kodstruktur)

## Current workflow principle
Bas:
1. intake
2. classification

Exempel lead flow:
1. intake
2. classification
3. entity_extraction
4. lead
5. decisioning
6. policy
7. action_dispatch
8. human_handoff vid behov

## Approval flow principle
1. pipeline når policy
2. policy kräver approval
3. approval request skapas
4. jobbet pausas som `awaiting_approval`
5. approve/reject via API
6. approve återupptar post-approval path
7. reject skickar jobb till `manual_review`

## Persistence
Nuvarande persistens omfattar minst:
- jobs
- audit events
- approval requests
- action executions

## Frontend principle
Frontend ska vara tunt och konsumera API:t.
Ingen affärslogik ska dupliceras i UI-lagret.

## Deployment principle
- Lokal körning först
- Docker-stöd
- Env-driven config
- Tydlig väg mot staging/demo