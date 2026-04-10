# AI Automation Platform

Backend-first, multi-tenant platform for AI-driven workflow automation.

Jobs are received, classified, processed through a pipeline, paused for human approval when required, and resumed to execute real integration actions. Everything is auditable.

---

## Current Status

All core MVP slices are complete and verified:

- FastAPI backend with PostgreSQL persistence
- Multi-tenant with per-tenant API key auth (`X-API-Key`)
- Workflow orchestrator with AI processors
- Approval flow (pause / resume)
- Action dispatch with controlled failure handling
- Audit logging
- Thin operator UI at `/ui`

See [docs/05-current-state.md](docs/05-current-state.md) for the full status.

---

## Repository Structure

```
app/          Core backend (API, workflows, integrations, UI)
docs/         Source of truth (scope, architecture, decisions, state)
tests/        Automated test suite (88 tests)
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
LLM_API_KEY=<your OpenAI key>
TENANT_API_KEYS={"TENANT_1001": "key-abc123"}
```

The LLM key is required for the AI classification and extraction processors.
`TENANT_API_KEYS` configures per-tenant API key auth (see [Authentication](#authentication) below).
All other keys (Gmail, Slack, etc.) are optional unless you are testing a specific integration.

### 3. Start PostgreSQL

**Option A — Docker (recommended):**

```bash
docker-compose up -d
```

This starts a Postgres 15 instance on port 5432 with user `postgres`, password `postgres`, database `ai_platform`.

**Option B — local Postgres:**

Create a database named `ai_platform` and set the matching `DATABASE_URL` in `.env`.

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

Or open the operator UI: **http://localhost:8000/ui**

---

## Running Tests

```bash
python -m pytest
```

Expected: 88 passed.

---

## Authentication

Protected endpoints require the `X-API-Key` header. Tenant identity is resolved from the key — the `X-Tenant-ID` header is **ignored** when auth is enabled.

Configure keys in `.env`:

```
TENANT_API_KEYS={"TENANT_1001": "key-abc123", "TENANT_2001": "key-def456"}
```

**Missing key** → `401 Unauthorized`
**Invalid key** → `403 Forbidden`

If `TENANT_API_KEYS` is empty or not set, auth is **disabled** and the `X-Tenant-ID` header is trusted directly. This is acceptable for local development only.

Unprotected endpoints (no key required): `GET /`, `GET /ui`, `GET /processors`

---

## Official Smoke Test — MVP Flow

This is the golden path for the lead flow with forced approval.
Run it after a clean local start with `TENANT_API_KEYS` configured.

All curl commands assume the server is running at `http://localhost:8000`
and `TENANT_API_KEYS={"TENANT_1001": "key-abc123"}` is set in `.env`.

### Step 1 — Create a job (lead, forced approval)

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
      "owner_email": "owner@example.com",
      "force_approval_test": true
    }
  }'
```

`force_approval_test: true` forces the policy processor to require approval regardless of AI confidence.

**Expected response:** a job object with `"status": "awaiting_approval"`.

Note the `job_id` from the response — you will need it in later steps.

### Step 2 — Confirm the approval request was created

```bash
curl -s http://localhost:8000/approvals/pending \
  -H "X-API-Key: key-abc123"
```

**Expected:** `{"items": [{...}], "total": 1}` containing one pending approval.

Note the `approval_id` from the response.

### Step 3 — Approve the job

```bash
curl -s -X POST http://localhost:8000/approvals/<approval_id>/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{"actor": "operator", "channel": "api"}'
```

Replace `<approval_id>` with the value from step 2.

**Expected response:** a job object with `"status": "completed"` (or `"failed"` if no Gmail credentials are configured — see Gmail note below).

### Step 4 — Inspect the job result

```bash
curl -s http://localhost:8000/jobs/<job_id> \
  -H "X-API-Key: key-abc123"
```

**Expected:** `"status": "completed"` or `"failed"`, with a populated `result` payload.

### Step 5 — Inspect executed actions

```bash
curl -s http://localhost:8000/jobs/<job_id>/actions \
  -H "X-API-Key: key-abc123"
```

**Expected:** `{"items": [{...}], "total": N}` — action records showing what was attempted.

### Step 6 — Verify the audit trail

```bash
curl -s http://localhost:8000/audit-events \
  -H "X-API-Key: key-abc123"
```

**Expected:** a list of audit events including `job_created`, `step_started`, `step_completed`, `workflow_completed` (or `workflow_failed`).

---

## Gmail Integration

If `GOOGLE_MAIL_ACCESS_TOKEN` is set in `.env`, the `send_email` action will make a real Gmail API call. Without it, the action falls back to a stub and is marked as a non-live execution.

Gmail access tokens are short-lived (1 hour). To use a real token:

1. Obtain an OAuth2 access token for the Gmail API
2. Set `GOOGLE_MAIL_ACCESS_TOKEN=<token>` in `.env`
3. Set `GOOGLE_MAIL_USER_ID=me`

If the token is expired, the action will fail and the job will be set to `FAILED` status. This is expected and handled — the error is persisted in `action_executions` and an audit event is emitted.

---

## Operator UI

Open `http://localhost:8000/ui` after starting the server.

> **Note:** The operator UI currently sends `X-Tenant-ID`, not `X-API-Key`. It works correctly when `TENANT_API_KEYS` is not configured (dev mode). Auth-aware UI support is a future improvement.

- Enter the tenant ID in the header field (default: `TENANT_1001`)
- **Jobs tab** — lists all jobs; click a row to open job detail
- **Job detail** — shows status, result, approvals, and actions for that job
- **Pending Approvals tab** — lists pending approvals with Approve/Reject buttons

See [docs/08-handoff.md](docs/08-handoff.md) for full UI usage instructions.

---

## API Reference

### Core

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/ui` | Operator UI |
| `POST` | `/jobs` | Create and process a job |
| `GET` | `/jobs` | List jobs for tenant |
| `GET` | `/jobs/{job_id}` | Get job detail |
| `GET` | `/jobs/{job_id}/actions` | Get actions for a job |
| `GET` | `/jobs/{job_id}/approvals` | Get approvals for a job |

### Approvals

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/approvals/pending` | List pending approvals |
| `POST` | `/approvals/{id}/approve` | Approve and resume job |
| `POST` | `/approvals/{id}/reject` | Reject job |

### Integrations & Audit

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/integrations` | List enabled integrations for tenant |
| `POST` | `/integrations/{type}/execute` | Execute an integration action directly |
| `GET` | `/audit-events` | List audit events for tenant |

All endpoints require the `X-Tenant-ID` header.

---

## Tenants

Tenant configuration is currently static in `app/core/config.py`.

| Tenant ID | Name | Enabled job types |
|-----------|------|-------------------|
| `TENANT_1001` | Default Tenant | lead, invoice, customer_inquiry |
| `TENANT_2001` | Sales Tenant | lead, customer_inquiry |
| `TENANT_3001` | Finance Tenant | invoice |

---

## Known Limitations

- No authentication — `X-Tenant-ID` is trusted without validation
- Tenant configuration is static in code, not database-driven
- Gmail access tokens expire and require manual refresh
- No pagination controls in the operator UI (backend supports it via query params)
- `docker-compose.yml` starts PostgreSQL only; the app itself must be run with `uvicorn`

---

## Documentation

| File | Description |
|------|-------------|
| [docs/02-mvp-scope.md](docs/02-mvp-scope.md) | MVP scope and success criteria |
| [docs/03-system-architecture.md](docs/03-system-architecture.md) | Architecture overview |
| [docs/05-current-state.md](docs/05-current-state.md) | Current implementation status |
| [docs/06-backlog.md](docs/06-backlog.md) | Completed and upcoming work |
| [docs/07-decisions.md](docs/07-decisions.md) | Architectural decisions log |
| [docs/08-handoff.md](docs/08-handoff.md) | Handoff notes and UI usage guide |
| [docs/10-test-strategy.md](docs/10-test-strategy.md) | Test strategy |
| [docs/11-release-checklist.md](docs/11-release-checklist.md) | Release checklist |
