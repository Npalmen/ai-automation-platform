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
- Multi-tenant via `X-Tenant-ID`
- Job intake
- Classification processor
- Entity extraction processor
- Lead flow som officiellt MVP-flöde
- Policy / approval decision
- Approval persistence + approve/reject endpoints
- Action dispatch
- Audit events
- Gmail/Google Mail som första fungerande integration
- Tunt operator/admin UI i senare slice
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