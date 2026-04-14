# AI Automation Platform

Backend-first, multi-tenant platform for AI-driven workflow automation.

Jobs are received, classified, processed through a pipeline, paused for human approval when required, and resumed to execute integration actions. Everything is auditable.

---

## Current Status

MVP is complete and stabilized:

- FastAPI backend with PostgreSQL persistence
- Multi-tenant with per-tenant API key auth (`X-API-Key`)
- Workflow orchestrator with AI processors and deterministic fallbacks
- Approval flow (pause / resume)
- Action dispatch with error handling and audit
- Operator UI at `/ui` (Swedish, tenant-aware)
- 263 tests passing

See [docs/05-current-state.md](docs/05-current-state.md) for the full status.

---

## Repository Structure

```
app/          Core backend (API, workflows, integrations, UI)
docs/         Source of truth (scope, architecture, decisions, state)
tests/        Automated test suite
scripts/      Utility scripts (DB setup, connection check)
```

---

## Local Setup

### Requirements

- Python 3.10+
- PostgreSQL 14+ (local install or Docker)

### 1. Clone and install dependencies

```bash
git clone https://github.com/Npalmen/ai-automation-platform
cd ai-automation-platform
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp env.example .env
```

Edit `.env` and set at minimum:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_platform
TENANT_API_KEYS={"TENANT_1001": "key-abc123"}
```

`LLM_API_KEY` is only required if you want live AI classification and extraction. Without it, processors fall back to deterministic defaults — the pipeline still runs.

All other keys (Gmail, Slack, etc.) are optional unless testing a specific integration.

### 3. Start PostgreSQL

**Option A — Docker (recommended):**

```bash
docker-compose up -d
```

Starts Postgres 15 on port 5432 with user `postgres`, password `postgres`, database `ai_platform`.

**Option B — local Postgres:**

Create a database named `ai_platform` and set `DATABASE_URL` in `.env`.

### 4. Verify the database connection

```bash
python -m scripts.test_db_connection
# Expected: DB OK: 1
```

### 5. Start the backend

```bash
uvicorn app.main:app --reload
```

Tables are created automatically on first startup.

### 6. Verify the server

```bash
curl http://localhost:8000/
# Expected: {"status":"ok","app_name":"AI Automation Platform","env":"dev"}
```

Open the operator UI: **http://localhost:8000/ui**

---

## Running Tests

```bash
python -m pytest
```

Expected: 263 passed.

---

## Authentication

Protected endpoints require the `X-API-Key` header. Tenant identity is resolved from the key — `X-Tenant-ID` is **ignored** when auth is enabled.

Configure keys in `.env`:

```
TENANT_API_KEYS={"TENANT_1001": "key-abc123", "TENANT_2001": "key-def456"}
```

| Condition | Response |
|-----------|----------|
| Missing key | `401 Unauthorized` |
| Invalid key | `403 Forbidden` |

If `TENANT_API_KEYS` is empty or unset, auth is **disabled** and `X-Tenant-ID` is trusted directly. Acceptable for local development only.

Unprotected endpoints (no key required): `GET /`, `GET /ui`, `GET /tenants`, `GET /tenant/config/{id}`, `PUT /tenant/config/{id}`, `POST /tenant`, `POST /verify/{id}`

---

## Calling `/jobs` — Correct Format

> **WARNING:** `input_data` must be a nested object. Fields like `subject` and `message_text` at the top level of the request are ignored — they must be inside `input_data`.

### Required request shape

```json
{
  "tenant_id": "TENANT_2001",
  "job_type": "customer_inquiry",
  "input_data": {
    "subject": "Fråga om offert",
    "message_text": "Hej, jag vill installera solceller. Kan ni skicka offert?",
    "sender_name": "Testkund",
    "sender_email": "test@example.com",
    "sender_phone": "0701234567"
  }
}
```

### Field notes

| Field | Required | Notes |
|-------|----------|-------|
| `tenant_id` | Yes | Must match the tenant derived from `X-API-Key` |
| `job_type` | Yes | Must be enabled for the tenant |
| `input_data` | Yes | Dict passed through the pipeline |
| `input_data.subject` | Recommended | Used by classification and entity extraction |
| `input_data.message_text` | Recommended | Main content for AI processors |
| `input_data.sender_name` | Recommended | Flat format supported |
| `input_data.sender_email` | Recommended | Flat format supported |
| `input_data.sender_phone` | Optional | Flat format supported |

**Sender field formats — both are supported:**

```json
// Flat (recommended for API callers)
"input_data": {
  "sender_name": "Erik Lindqvist",
  "sender_email": "erik@example.com",
  "sender_phone": "070-1234567"
}

// Nested dict (also accepted)
"input_data": {
  "sender": {
    "name": "Erik Lindqvist",
    "email": "erik@example.com",
    "phone": "070-1234567"
  }
}
```

Nested dict takes precedence when both are present.

### Supported `job_type` values

| Value | Pipeline |
|-------|---------|
| `lead` | intake → classification → entity_extraction → lead → decisioning → policy → action_dispatch → human_handoff |
| `customer_inquiry` | intake → classification → entity_extraction → customer_inquiry → decisioning → policy → action_dispatch → human_handoff |
| `invoice` | intake → classification → entity_extraction → invoice → policy → human_handoff |

Only types enabled for the tenant are accepted. A request with a non-enabled type returns `403`.

### Typical responses

| `status` | Meaning |
|----------|---------|
| `completed` | Pipeline ran fully; actions executed (or stubbed) |
| `awaiting_approval` | Policy required human approval; pipeline paused |
| `manual_review` | Policy routed to manual review (low confidence or validation issue) |
| `failed` | An action dispatch step failed; error persisted to audit and `action_executions` |

### Example: create a lead job

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "tenant_id": "TENANT_1001",
    "job_type": "lead",
    "input_data": {
      "subject": "Intresserad av era tjänster",
      "message_text": "Hej, vi söker en lösning för att automatisera vår kundhantering. Kan ni kontakta oss?",
      "sender_name": "Erik Lindqvist",
      "sender_email": "erik@lindqvist.se",
      "sender_phone": "070-1234567"
    }
  }'
```

---

## Official Smoke Test — Approval Flow

This is the end-to-end golden path. Run after a clean local start with `TENANT_API_KEYS` configured.

### Step 1 — Create a job with forced approval

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "tenant_id": "TENANT_1001",
    "job_type": "lead",
    "input_data": {
      "subject": "New lead from website",
      "message_text": "Hi, I am interested in your services.",
      "sender_name": "Test Lead",
      "sender_email": "lead@example.com",
      "force_approval_test": true
    }
  }'
```

`force_approval_test: true` forces the policy processor to require approval regardless of AI confidence.

**Expected:** job object with `"status": "awaiting_approval"`. Note the `job_id`.

### Step 2 — Check the pending approval

```bash
curl -s http://localhost:8000/approvals/pending \
  -H "X-API-Key: key-abc123"
```

**Expected:** `{"items": [{...}], "total": 1}`. Note the `approval_id`.

### Step 3 — Approve the job

```bash
curl -s -X POST http://localhost:8000/approvals/<approval_id>/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{"actor": "operator", "channel": "api"}'
```

**Expected:** job object with `"status": "completed"` (or `"failed"` if no Gmail credentials are configured).

### Step 4 — Inspect the job

```bash
curl -s http://localhost:8000/jobs/<job_id> -H "X-API-Key: key-abc123"
curl -s http://localhost:8000/jobs/<job_id>/actions -H "X-API-Key: key-abc123"
curl -s http://localhost:8000/audit-events -H "X-API-Key: key-abc123"
```

---

## Gmail Integration

If `GOOGLE_MAIL_ACCESS_TOKEN` is set, `send_email` actions make a real Gmail API call. Without it the action falls back to a stub.

**Option A — access token only (short-lived):**

```
GOOGLE_MAIL_ACCESS_TOKEN=<token>
GOOGLE_MAIL_USER_ID=me
```

Token expires in ~1 hour. Expired tokens cause the action to fail (job → `FAILED`).

**Option B — with automatic token refresh (recommended):**

```
GOOGLE_MAIL_ACCESS_TOKEN=<token>
GOOGLE_OAUTH_REFRESH_TOKEN=<refresh_token>
GOOGLE_OAUTH_CLIENT_ID=<client_id>
GOOGLE_OAUTH_CLIENT_SECRET=<client_secret>
```

On a 401, the platform refreshes the token and retries once. If refresh fails, the action fails cleanly.

---

## Operator UI

Open `http://localhost:8000/ui`.

- **API key** — enter in the header field; persisted to `localStorage`
- **Inställningar tab** — create/switch tenants, configure job types and integrations, set automation levels, run verification test
- **Operationer tab** — view jobs, job detail (result, approvals, actions), approve/reject pending approvals

The verification test (`POST /verify/{tenant_id}`) runs a deterministic pipeline — no LLM or external credentials required.

---

## API Reference

### Jobs

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/jobs` | Required | Create and process a job |
| `GET` | `/jobs` | Required | List jobs for tenant |
| `GET` | `/jobs/{job_id}` | Required | Get job detail |
| `GET` | `/jobs/{job_id}/actions` | Required | Actions for a job |
| `GET` | `/jobs/{job_id}/approvals` | Required | Approvals for a job |

### Approvals

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/approvals/pending` | Required | List pending approvals |
| `POST` | `/approvals/{id}/approve` | Required | Approve and resume |
| `POST` | `/approvals/{id}/reject` | Required | Reject |

### Tenants (unauthenticated — operator bootstrap)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/tenants` | List all tenants |
| `POST` | `/tenant` | Create a tenant |
| `GET` | `/tenant/config/{id}` | Get tenant config |
| `PUT` | `/tenant/config/{id}` | Save tenant config |
| `POST` | `/verify/{id}` | Run deterministic verification job |

### Integrations & Audit

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/integrations` | Required | List enabled integrations |
| `POST` | `/integrations/{type}/execute` | Required | Execute integration action |
| `GET` | `/audit-events` | Required | Audit events for tenant |

---

## Tenants

Tenant configuration is DB-driven. The `tenant_configs` table is the source of truth; `app/core/config.py` (`TENANT_CONFIGS`) is a fallback when no DB row exists.

Default static fallback tenants (used when no DB row exists for a tenant):

| Tenant ID | Enabled job types |
|-----------|-------------------|
| `TENANT_1001` | lead, invoice, customer_inquiry |
| `TENANT_2001` | lead, customer_inquiry |
| `TENANT_3001` | invoice |

To use a tenant with the API, it must be configured in `TENANT_API_KEYS` and have a DB row (or static fallback).

---

## Known Limitations

- No pagination controls in the operator UI (backend supports it via query params)
- `docker-compose.yml` starts PostgreSQL only — the app runs separately via `uvicorn`
- No DB migration tooling — schema changes require manual `create_all` or ALTER TABLE
- `app/api/routes/jobs.py` is dead code (not mounted) — does not affect runtime
- Action dispatch is stubbed for most integrations; only Gmail has a live implementation

---

## Documentation

| File | Description |
|------|-------------|
| [docs/02-mvp-scope.md](docs/02-mvp-scope.md) | MVP scope and success criteria |
| [docs/03-system-architecture.md](docs/03-system-architecture.md) | Architecture overview |
| [docs/05-current-state.md](docs/05-current-state.md) | Current implementation status |
| [docs/06-backlog.md](docs/06-backlog.md) | Completed and upcoming work |
| [docs/07-decisions.md](docs/07-decisions.md) | Architectural decisions log |
| [docs/08-handoff.md](docs/08-handoff.md) | Handoff notes and session history |
| [docs/10-test-strategy.md](docs/10-test-strategy.md) | Test strategy |
| [docs/11-release-checklist.md](docs/11-release-checklist.md) | Release checklist |
