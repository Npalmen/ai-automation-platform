# Implementation Plan

## Completed

### Phase 1
- core workflow engine
- processor registry
- tenant-aware job gating
- integration layer
- retry dispatcher
- audit layer

### Phase 2
- AI Core
  - LLM client
  - prompt registry
  - response schemas
  - safe fail handling
- AI Classification Processor
- AI Entity Extraction Processor
- AI Lead Scoring Processor
- AI Decisioning Processor
- dynamic lead routing
- persistence after each processor step
- audit events for workflow execution

## Current State
Production-capable internal lead pipeline is in place.

## Next Phase

### Phase 3A — Customer Inquiry AI
Goals:
- AI classification already routes inquiry traffic
- replace or enhance inquiry analysis with AI
- structured output for support/sales/billing inquiries
- decisioning to queue or response drafting

### Phase 3B — Invoice AI
Goals:
- AI extraction for invoice data
- AI validation support
- approval/hold/manual review decisioning
- tighter policy logic for finance flow

### Phase 3C — Action Dispatch
Goals:
- use decisioning output to trigger integrations
- create CRM lead automatically
- create support ticket automatically
- log integration dispatch results into audit trail

### Phase 3D — Test Expansion
Goals:
- full pipeline tests
- DB persistence tests
- tenant policy tests
- integration dispatch tests