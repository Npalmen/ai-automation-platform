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