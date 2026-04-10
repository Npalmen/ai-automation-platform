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

## Official golden-path smoke test

Run after `uvicorn app.main:app --reload`:

1. `POST /jobs` with `force_approval_test: true` in `input_data` → expect `awaiting_approval`
2. `GET /approvals/pending` → note `approval_id`
3. `POST /approvals/<id>/approve` → expect `completed` or `failed` (if no Gmail credentials)
4. `GET /jobs/<job_id>/actions` → confirm action record exists
5. `GET /audit-events` → confirm `workflow_completed` or `workflow_failed` event

Full curl commands are in the README smoke test section.

## Minimum before merge
- Relevant tests pass (run `python -m pytest`)
- Manual smoke test executed following README golden path
- Docs updated (current-state, backlog, handoff)