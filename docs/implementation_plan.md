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

### 2. AI layer
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

### 3. Real integrations
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