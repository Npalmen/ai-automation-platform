# AI Automation Platform

Backend-first, multi-tenant platform for AI-driven workflow automation.

Jobs are received, classified, processed through a pipeline, paused for human approval when required, and resumed to execute integration actions. Everything is auditable.

---

## Verified Capabilities

The following has been validated through live API testing (2026-04-14):

- **Live Gmail sending works** — `POST /integrations/google_mail/execute` reaches the Gmail API and sends real email using access + refresh token flow
- **Full pipeline verified end-to-end** — intake → classification → entity extraction → decisioning → policy → approval pause → resume → action dispatch
- **Approval flow works** — job enters `awaiting_approval`, `POST /approvals/{id}/approve` with `{}` resumes execution, actions execute after approval
- **Action execution is persisted** — queryable via `GET /jobs/{job_id}/actions`
- **300 tests passing**

---

## Current Status

MVP is complete and stabilized:

- FastAPI backend with PostgreSQL persistence
- Multi-tenant with per-tenant API key auth (`X-API-Key`)
- Workflow orchestrator with AI processors and deterministic fallbacks
- Approval flow (pause / resume)
- Action dispatch with error handling and audit
- Operator UI at `/ui` (Swedish, tenant-aware)
- 300 tests passing

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

## API Contracts (Important)

These are observed behaviors from live testing — not assumptions.

### POST /jobs

- Requires `X-API-Key` header **and** `tenant_id` in the request body
- `job_type` in the request is a hint, not authoritative — the system may override it via AI classification
- `input_data` must be a nested object; top-level fields outside `input_data` are ignored by processors

### POST /approvals/{id}/approve

- Requires a JSON body — minimal working body is `{}`
- Without a body the request fails with a parse error

### POST /integrations/{type}/execute

- Request body uses `"payload"`, not `"input"`
- Sending `"input"` instead silently produces an empty payload and returns `400`

### Authentication

All protected endpoints require `X-API-Key`. Tenant identity is resolved from the key — `X-Tenant-ID` is ignored when auth is enabled.

| Condition | Response |
|-----------|----------|
| Missing key | `401 Unauthorized` |
| Invalid key | `403 Forbidden` |

If `TENANT_API_KEYS` is empty or unset, auth is **disabled** and `X-Tenant-ID` is trusted directly. Acceptable for local development only.

Unprotected endpoints (no key required): `GET /`, `GET /ui`, `GET /tenants`, `GET /tenant/config/{id}`, `PUT /tenant/config/{id}`, `POST /tenant`, `POST /verify/{id}`

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

## Quick Start (Tested)

These are the exact commands verified against a running instance.

### Direct Gmail send

```bash
curl -s -X POST http://localhost:8000/integrations/google_mail/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "action": "send_email",
    "payload": {
      "to": "recipient@example.com",
      "subject": "Test from AI Platform",
      "body": "This is a live test."
    }
  }'
```

> Note: the field is `"payload"`, not `"input"`.

### Create a job

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "tenant_id": "TENANT_1001",
    "job_type": "lead",
    "input_data": {
      "subject": "Intresserad av era tjänster",
      "message_text": "Hej, vi söker en lösning för att automatisera vår kundhantering.",
      "sender_name": "Erik Lindqvist",
      "sender_email": "erik@lindqvist.se",
      "sender_phone": "070-1234567"
    }
  }'
```

> `tenant_id` in the body must match the tenant derived from `X-API-Key`. `job_type` may be overridden by the classifier.

### Approve a pending job

```bash
# 1. Find the approval ID
curl -s http://localhost:8000/approvals/pending \
  -H "X-API-Key: key-abc123"

# 2. Approve it — body {} is required
curl -s -X POST http://localhost:8000/approvals/<approval_id>/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{}'
```

> `{}` is required. An empty body causes a parse error.

### Inspect a job and its actions

```bash
curl -s http://localhost:8000/jobs/<job_id> \
  -H "X-API-Key: key-abc123"

curl -s http://localhost:8000/jobs/<job_id>/actions \
  -H "X-API-Key: key-abc123"
```

---

## Running Tests

```bash
python -m pytest
```

Expected: 300 passed.

---

## Gmail Integration (Working Setup)

Verified working configuration. All four env vars are required for automatic token refresh.

```
GOOGLE_MAIL_ACCESS_TOKEN=<your_access_token>
GOOGLE_MAIL_USER_ID=me
GOOGLE_OAUTH_REFRESH_TOKEN=<your_refresh_token>
GOOGLE_OAUTH_CLIENT_ID=<your_client_id>
GOOGLE_OAUTH_CLIENT_SECRET=<your_client_secret>
```

**How token refresh works:**

On a `401` from the Gmail API, the platform calls `https://oauth2.googleapis.com/token` with the refresh credentials and retries the request once. If refresh fails, the action raises `RuntimeError` which the route converts to `503`.

**Access token only (short-lived):**

```
GOOGLE_MAIL_ACCESS_TOKEN=<token>
GOOGLE_MAIL_USER_ID=me
```

Token expires in ~1 hour. Expired tokens cause the action to fail (`503`) if no refresh credentials are configured.

**Common failure: `invalid_grant`**

This means the refresh token is expired, revoked, or was issued for a different client ID/secret. Signs:
- `503` response with `invalid_grant` in the detail
- Startup log warning: `Incomplete OAuth refresh credentials: N of 3 fields set`

Fix: re-authorize the OAuth application and obtain a new refresh token. All three of `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, and `GOOGLE_OAUTH_CLIENT_SECRET` must be set together — setting only some of them will fail.

**Note on terminal encoding:**

The API response is UTF-8 encoded. On Windows terminals using GBK/CP936 code page, Swedish characters (ä, å, ö) may render as `?` in curl output. The data is correct — the display is wrong. Run `chcp 65001` in your terminal to switch to UTF-8 before running curl.

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
| `job_type` | Yes | Hint only — may be overridden by AI classification |
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
  -d '{}'
```

> The `{}` body is required. The endpoint will fail without it.

**Expected:** job object with `"status": "completed"` (or `"failed"` if no Gmail credentials are configured).

### Step 4 — Inspect the job

```bash
curl -s http://localhost:8000/jobs/<job_id> -H "X-API-Key: key-abc123"
curl -s http://localhost:8000/jobs/<job_id>/actions -H "X-API-Key: key-abc123"
curl -s http://localhost:8000/audit-events -H "X-API-Key: key-abc123"
```

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
| `POST` | `/approvals/{id}/approve` | Required | Approve and resume — body `{}` required |
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
| `POST` | `/integrations/{type}/execute` | Required | Execute integration action directly |
| `GET` | `/audit-events` | Required | Audit events for tenant |

#### `POST /integrations/{type}/execute` — request body

```json
{
  "action": "send_email",
  "payload": {
    "to": "recipient@example.com",
    "subject": "Test",
    "body": "Message body."
  }
}
```

> **Note:** The field is `payload`, not `input`. Sending `input` instead will silently produce an empty payload and return a `400` error from the adapter.

**Google Mail (`google_mail`) — `send_email` required fields:**

| Field | Required | Notes |
|-------|----------|-------|
| `to` | Yes | Recipient email address |
| `subject` | Yes | Email subject |
| `body` | Yes | Plain text body |
| `html_body` | No | HTML body (optional) |
| `cc` | No | CC address |
| `bcc` | No | BCC address |

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
- Windows terminals using GBK code page (default) will misrender UTF-8 characters in curl output — run `chcp 65001` to switch to UTF-8

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
