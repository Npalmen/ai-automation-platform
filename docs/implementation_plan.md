# Implementation Plan

## Completed Phases

## Phase 1 – Platform Foundation
Färdigställt:

- FastAPI application
- tenant-aware request handling
- workflow/job model
- repository structure
- integration layer foundation
- audit foundation

## Phase 2 – AI Workflow Core
Färdigställt:

- AI client
- prompt registry
- typed response schemas
- fallback-safe AI utilities
- classification processor
- entity extraction processor
- lead processor
- decisioning processor
- policy handling
- human handoff logic

## Phase 3 – Orchestration and Control
Färdigställt:

- `WorkflowOrchestrator`
- base pipeline + routed pipelines
- action dispatch in workflow path
- approval request generation
- approval resolution with resume-after-approve
- audit step lifecycle
- job list/detail API
- audit event API
- integration event API + retry

---

## Current Phase

## Phase 4 – Operational MVP Hardening

Det här är den riktiga fasen nu. Fokus bör inte vara mer basal omstrukturering utan hårdning av systemet för verklig användning.

### Goals
- stabilisera lead flow för verklig execution
- stärka inquiry flow
- stärka invoice flow
- göra action dispatch användbar i kundnära scenarier
- skapa minimal operationsyta

---

## Next Workstreams

## Workstream A – Lead Automation Completion
Mål:

- koppla decisioning till verklig CRM-action
- säkra idempotency i dispatch
- förbättra routing-regler
- exponera tydligare operationsstatus i API/UI

## Workstream B – Customer Inquiry Upgrade
Mål:

- bättre structured intent extraction
- tydlig support/sales/billing triage
- response draft eller ticket creation
- säkra fallback rules

## Workstream C – Invoice Upgrade
Mål:

- AI-stödd invoice extraction
- validation rules
- approval/hold policies
- bättre ekonomiflödeslogik

## Workstream D – Admin / Ops Layer
Mål:

- job list UI
- approval queue UI
- manual review queue
- audit / event visibility
- retry controls

## Workstream E – Productization
Mål:

- tenant config till DB
- auth + roles
- deployment standard
- environment handling
- onboarding path för första kunder

## Workstream F – Quality
Mål:

- pipeline tests
- repository tests
- tenant isolation tests
- approval lifecycle tests
- dispatch tests

---

## Delivery Logic

Rekommenderad ordning:

1. Lead dispatch till riktig integration
2. Approval/manual review UI
3. Inquiry upgrade
4. Invoice upgrade
5. Auth/RBAC
6. Full product packaging

---

## Exit Criteria for “First Sellable Version”

Versionen kan kallas första säljbara när följande är uppfyllt:

- minst ett verkligt affärsflöde är live
- approval och manual review kan hanteras utan kod
- audit och jobbspårning räcker för support
- tenant-gränser är tydliga
- deployment är repeterbar
- testtäckningen räcker för trygg ändringstakt