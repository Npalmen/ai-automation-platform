# Test Strategy

## Goals
- Säkerställa att kärnflöden inte bryts
- Validera AI/workflow-logik efter varje slice
- Göra projektet tryggare att iterera med AI

## Test layers
- Unit tests för processors, policy och beslut
- API/integration tests för endpoints och DB
- End-to-end smoke test för officiellt MVP-flöde
- Senare manuell UI-verifiering

## MVP-critical flow
1. Create job
2. Run classification
3. Run entity extraction
4. Run decisioning/policy
5. Create approval request
6. Approve job
7. Resume pipeline
8. Execute Gmail send_email action
9. Confirm audit/events/actions state

## Minimum before merge
- Relevanta tester passerar
- Manuell smoke test utförd
- Docs uppdaterade