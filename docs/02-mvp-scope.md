# MVP Scope

## MVP objective
Leverera en testbar och demonstrerbar teknisk MVP där en användare kan:

1. skapa ett jobb
2. låta systemet klassificera ärendet
3. extrahera nyckeldata
4. köra rätt processor/pipeline
5. tillämpa policy
6. pausa för approval när relevant
7. godkänna eller neka via API
8. exekvera minst en riktig integration action
9. se audit trail och tillhörande approvals/actions

## In scope
- FastAPI backend
- PostgreSQL persistence
- Multi-tenant with per-tenant API key auth (`X-API-Key`)
- Job intake
- Classification processor
- Entity extraction processor
- Lead flow som officiellt MVP-flöde
- Policy / approval decision
- Approval persistence + approve/reject endpoints
- Action dispatch
- Audit events
- Gmail/Google Mail som första fungerande integration
- Tunt operator/admin UI (`/ui`) — implementerat
- Testbar lokal körning
- Tydlig dokumentation

## Out of scope
- Full auth/roles-plattform
- Komplett tenant self-service
- Billing
- White-labeling
- Full analytics/dashboard suite
- Mobilapp
- Alla integrationsspår som finns i arkitekturen
- Komplett enterprise permission model

## MVP success criteria
- Projektet kan startas lokalt från clean environment
- Minst ett end-to-end workflow fungerar stabilt
- Approval och resume fungerar
- Gmail action kan demonstreras
- Audit events kan visas
- En ny chatt kan återuppta arbetet enbart från docs

## MVP status (as of 2026-04-20) — ALL CRITERIA MET

All success criteria above are confirmed met through live API testing.

### What the MVP is

An automation platform with three verified layers:

1. **Ingestion** — Gmail inbox can be read via `list_messages` + `get_message`. `POST /gmail/process-inbox` automates this into a single API call. Scheduled/webhook-triggered ingestion is the next step
2. **Decision engine** — full pipeline: intake → classification → entity extraction → decisioning → policy → action_dispatch. Runs deterministically without LLM when `input_data.actions` is provided explicitly
3. **Action dispatch** — real integrations: Gmail `send_email`, Monday `create_item`. Multi-action dispatch (both in one job) verified

### Key architectural fact

`input_data.actions` is the primary deterministic execution path. Providing explicit actions bypasses reliance on LLM output for routing. The workflow engine executes whatever is in that list.

### Email ingestion state

Manual trigger is proven: list_messages → get_message → map to /jobs → Monday item created. `POST /gmail/process-inbox` now automates this as a single API call — reads unread messages, creates jobs, returns results. It is implemented but not production-ready (no deduplication, no mark-as-read, no scheduler). A cron/webhook trigger is the next step.