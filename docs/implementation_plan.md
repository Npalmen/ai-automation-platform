# Implementation plan

## Purpose
This document explains what is already done, what is missing, and what should be built next.

The goal is to continue inside the existing workflow architecture.

Do not build a separate processor framework outside:
- `app/workflows/processors/`
- `app/workflows/pipeline_runner.py`
- `app/workflows/processor_registry.py`

---

## What is missing

### 1. Processor architecture
Still needed or still maturing:
- intake
- generalized entity extraction
- policy engine
- pipeline chaining
- domain routing

Status:
- started and partially implemented

---
### 2. Real integrations
Current state:
- mock integrations only

Needed:
- Visma / Fortnox invoice creation
- Gmail read/send
- webhook ingestion
- real external actions

Status:
- planned

---

### 3. AI layer
Current state:
- regex / heuristics

Needed later:
- LLM-based extraction
- AI classification
- summarization
- better reasoning for routing and handoff

Status:
- planned

---

### 4. Tenant config in DB
Current state:
- hardcoded tenant config

Needed:
- tenant table
- integration configs in DB
- policy configs in DB

Status:
- planned

---

### 5. Orchestration / pipeline
Current state:
- originally 1 job = 1 processor
- now pipeline work has started

Target:
```text
intake -> classification -> extraction -> policy -> domain processor

# Implementation Plan - update

## Phase 1 – Core (DONE)
- FastAPI
- DB
- Multi-tenant
- Job system

---

## Phase 2 – Pipeline (DONE)
- Processor system
- History-driven logic
- Business processors

---

## Phase 3 – Integrations (DONE)
- Dispatcher
- Retry worker
- Idempotency
- Manual retry
- Smoke tests
- Adapters

---

## Phase 4 – AI Layer (IN PROGRESS)

### Step 1 (DONE)
- LLM client
- Prompt loader
- Classification AI

### Step 2 (NEXT)
- Entity extraction AI
- Lead scoring AI
- Invoice validation AI

### Step 3
- Decision processor
- Dynamic routing

---

## Phase 5 – Intelligence Layer

- Auto decision making
- Confidence thresholds
- Hybrid human/AI system

---

## Phase 6 – Production

- OAuth
- Rate limiting
- Monitoring
- Alerting