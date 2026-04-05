# System status

## Current platform state
The project is already a real platform foundation, not a prototype.

### Stack
- FastAPI
- PostgreSQL
- SQLAlchemy
- Pydantic

### Logical structure
```text
app/
  core/                  # config, tenant, audit
  domain/workflows/      # models + schemas
  workflows/             # job runner + processors
  integrations/          # adapters + factory + policies
  repositories/postgres/ # DB layer

#### SYSTEM STATUS - Update

###### Core Architecture

Stack:
- FastAPI
- PostgreSQL
- SQLAlchemy
- Pydantic

---

## Workflow Engine

### Files
- pipeline_runner.py
- job_runner.py
- processor_registry.py
- processors/*

---

## Pipeline Logic

```python
BASE_PIPELINE = [
    INTAKE,
    CLASSIFICATION
]

POST_CLASSIFICATION_PIPELINES = {
    INVOICE: [
        ENTITY_EXTRACTION,
        INVOICE,
        POLICY,
        HUMAN_HANDOFF
    ],
    LEAD: [
        ENTITY_EXTRACTION,
        LEAD,
        POLICY,
        HUMAN_HANDOFF
    ],
    CUSTOMER_INQUIRY: [
        ENTITY_EXTRACTION,
        CUSTOMER_INQUIRY,
        POLICY,
        HUMAN_HANDOFF
    ],
    UNKNOWN: [
        POLICY,
        HUMAN_HANDOFF
    ]
}

# System Status - Update

## Architecture

Systemet är byggt som:

- Event-driven pipeline
- Processor-based execution
- Integration dispatcher (async)

---

## Data Flow

1. Request → `/jobs`
2. Job skapas
3. Pipeline körs
4. Processor_history uppdateras
5. Dispatcher triggas
6. Integration events skapas
7. Retry worker hanterar leverans

---

## Guarantees

- Idempotency på integrationer
- Retry med exponential backoff
- Dead state efter max försök
- Audit logging på alla actions

---

## AI Status

- LLM integration finns
- Prompt system finns
- Classification AI aktiv

---

## Known Constraints

- Tokens lagras statiskt (ingen OAuth ännu)
- Ingen rate limiting ännu
- Ingen caching av AI responses

---

## System Health

✔ stabil startup  
✔ stabil DB  
✔ stabil pipeline  
✔ stabil integrations  

→ redo för nästa lager