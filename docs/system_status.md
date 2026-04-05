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