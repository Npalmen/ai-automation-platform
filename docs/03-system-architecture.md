# System Architecture

## Architecture summary
Systemet består av:
- FastAPI API-lager
- Workflow/orchestrator-lager
- Stateless processors
- PostgreSQL persistence
- Integrationslager med adapter/factory-pattern
- Audit + approval persistence
- Tunt operator/admin UI ovanpå API:t (`GET /ui`)

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

## Integration layer

Integrations are action-based. All integrations use the pattern:

```
adapter.execute_action(action: str, payload: dict) → dict
```

The integration route (`POST /integrations/{type}/execute`) accepts:
```json
{ "action": "<action_name>", "payload": { ... } }
```

### Google Mail — verified read + write

| Action | Direction | Status |
|---|---|---|
| `send_email` | Write | ✅ LIVE VERIFIED |
| `list_messages` | Read | ✅ LIVE VERIFIED |
| `get_message` | Read | ✅ LIVE VERIFIED |

All three actions share a 401→token refresh→retry path.

### Monday — verified

| Action (direct) | Action (workflow) | Status |
|---|---|---|
| `create_item` | `create_monday_item` | ✅ LIVE VERIFIED |

The workflow action type `create_monday_item` maps to the adapter's `create_item` action.

### Action dispatch — workflow integration

The workflow engine dispatches actions through `app/workflows/action_executor.py`. Supported action types in the workflow:

- `send_email` → `GoogleMailAdapter`
- `create_monday_item` → `MondayAdapter`
- `notify_slack` → stub
- `notify_teams` → stub
- `create_internal_task` → stub

**The workflow does NOT auto-generate actions.** Actions must be provided explicitly in `input_data.actions` or derived by a future rule engine. Without explicit actions, action_dispatch runs but executes nothing.

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