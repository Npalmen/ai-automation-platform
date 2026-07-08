# AI Automation Platform

## Read this first

Product direction, execution order and scope control are governed by:

- [`docs/00-master-plan.md`](docs/00-master-plan.md)

If README or any other document conflicts with `docs/00-master-plan.md`, the master plan wins.

README is for project overview and setup. It is not the strategic source of truth.

---

Backend-first, multi-tenant platform for AI-driven workflow automation.

Jobs are received, classified, processed through a pipeline, paused for human approval when required, and resumed to execute integration actions. Everything is auditable.

---

## Current Status

*Historical test counts and live-validation claims have been moved to [`docs/01-current-truth.md`](docs/01-current-truth.md). Run `py -3.10 -m pytest` to get the current verified count.*

Core capabilities (verified historically — see `docs/01-current-truth.md` for current state):

- FastAPI backend with PostgreSQL persistence
- Multi-tenant with per-tenant API key auth (`X-API-Key`)
- Workflow orchestrator with AI processors and deterministic fallbacks
- Approval flow (pause / resume) for high-risk actions
- Action dispatch with error handling and audit
- Gmail, Monday, and Fortnox integrations (see `docs/05-architecture.md` for status)
- Operator/customer UI at `/ui` (Swedish, role-aware)

---

## Repository Structure

```
app/          Core backend (API, workflows, integrations, UI)
docs/         Source of truth (scope, architecture, decisions, state)
tests/        Automated test suite
scripts/      Utility scripts (DB setup, connection check)
```

---

## Important API Contracts

All of the following are real behaviors observed during live testing — each one has caused a failure at least once.

### POST /jobs

- Requires **both** `X-API-Key` header and `tenant_id` in the request body — missing either returns an error
- `job_type` is a hint only; AI classification may override it — the actual type used is in the response
- `input_data` must be a nested object; top-level fields outside `input_data` are silently ignored by all processors

### POST /approvals/{id}/approve

- Requires a JSON body — minimal working body is `{}`
- Sending no body at all causes a parse error

### POST /integrations/{type}/execute

- Request body uses `"payload"`, not `"input"` — sending `"input"` silently produces an empty payload, and the adapter returns `400` with no indication that the wrong key was used
- For Monday: `board_id` is **not** a payload field — it is fixed at connection time from `MONDAY_BOARD_ID` in `.env`
- For Monday: `column_values` must be passed as a plain dict — the platform JSON-serializes it internally (monday's GraphQL API requires it as a JSON string; sending a pre-serialized string also works)

### Tenant configuration

- The DB `tenant_configs` table overrides the static config in `app/core/config.py` whenever a row exists for the tenant — if an integration appears enabled in the code but rejected at runtime, check the DB row
- `allowed_integrations` in the DB is stored as plain strings (e.g. `"monday"`); enum objects in static config are normalized on read — both formats work, but the DB is authoritative
- An integration must be in the tenant's `allowed_integrations` or the route returns `403` regardless of env var configuration

### Gmail OAuth

- All four env vars are required for automatic refresh: `GOOGLE_MAIL_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`
- Setting only some of them works until the access token expires (≈1 hour), then fails with `invalid_grant` (503)

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

## Quick Start (Actual Working Commands)

These exact commands have been verified against a live running instance.

### Gmail — send an email directly

Requires `GOOGLE_MAIL_ACCESS_TOKEN` (and optionally refresh credentials) in `.env`.

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

### Monday — create an item directly

Requires `MONDAY_API_KEY` and `MONDAY_BOARD_ID` in `.env`. The board is fixed from env — `board_id` is not a payload field.

```bash
curl -s -X POST http://localhost:8000/integrations/monday/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "action": "create_item",
    "payload": {
      "item_name": "New lead from AI Platform"
    }
  }'
```

With column values (pass as a dict — the platform serializes to JSON string internally):

```bash
curl -s -X POST http://localhost:8000/integrations/monday/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "action": "create_item",
    "payload": {
      "item_name": "Erik Lindqvist",
      "group_id": "topics",
      "column_values": {
        "text": "Erik Lindqvist",
        "email": {"email": "erik@example.com", "text": "erik@example.com"},
        "phone": {"phone": "0701234567", "countryShortName": "SE"},
        "status": {"label": "New"}
      }
    }
  }'
```

### Full pipeline — create a job

`tenant_id` in the body must match the tenant derived from `X-API-Key`. `job_type` is a hint — the classifier may override it.

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

### Approval flow — step by step

```bash
# Step 1 — list pending approvals, note the approval_id
curl -s http://localhost:8000/approvals/pending \
  -H "X-API-Key: key-abc123"

# Step 2 — approve; {} body is required (empty body causes a parse error)
curl -s -X POST http://localhost:8000/approvals/<approval_id>/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{}'
```

### Inspect job status and actions

```bash
# Job detail
curl -s http://localhost:8000/jobs/<job_id> \
  -H "X-API-Key: key-abc123"

# Actions executed for this job
curl -s http://localhost:8000/jobs/<job_id>/actions \
  -H "X-API-Key: key-abc123"

# Audit events
curl -s http://localhost:8000/audit-events \
  -H "X-API-Key: key-abc123"
```

---

## Running Tests

```bash
python -m pytest
```

Expected: 326 passed.

For a consolidated R1 release-candidate gate (regression + E2E pilot flow), run:

```bash
python -m scripts.run_release_gate_r1
```

Run one phase only:

```bash
python -m scripts.run_release_gate_r1 --phase regression
python -m scripts.run_release_gate_r1 --phase e2e
```

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

## Monday.com Integration Setup

```
MONDAY_API_KEY=<your_monday_api_token>
MONDAY_API_URL=https://api.monday.com/v2
MONDAY_BOARD_ID=<your_board_id_as_integer>
```

**Where to find these values:**
- API token: monday.com → Avatar → Developers → My Access Tokens → copy a personal token
- Board ID: visible in the board URL — `https://your-org.monday.com/boards/<board_id>`

**Supported actions:**

| Action | Required payload fields | Optional payload fields |
|--------|------------------------|------------------------|
| `create_item` | `item_name` | `group_id`, `column_values` |
| `create_update` | `item_id`, `body` | — |

**`board_id` is not a per-request field.** The board is fixed at connection time from `MONDAY_BOARD_ID`. To write to a different board, change the env var.

**`column_values`** is sent as a plain JSON dict in the request payload — the platform serializes it to a JSON string internally before sending to monday's GraphQL API (which requires `column_values` to be a JSON string, not an object). Pass a dict; do not pre-serialize it.

Common column value shapes by type:

```json
{
  "text":    "plain string value",
  "email":   {"email": "x@example.com", "text": "x@example.com"},
  "phone":   {"phone": "0701234567", "countryShortName": "SE"},
  "status":  {"label": "New"},
  "numbers": 42
}
```

Column IDs match the board's column configuration — inspect your board settings in monday.com to find the exact IDs.

**`group_id`** is the monday internal group identifier (not the display name). Find it via monday.com's board API or by inspecting the board URL when a group is selected.

**Common failures:**

| Error | Cause |
|-------|-------|
| `400 Missing monday api_key` | `MONDAY_API_KEY` not set |
| `400 Missing monday board_id` | `MONDAY_BOARD_ID=0` or unset |
| `400 Missing 'item_name'` | `item_name` absent from payload |
| `400 Unsupported monday action` | Wrong action string |
| `403 Forbidden` | `monday` not in tenant's `allowed_integrations` |
| `503` | monday GraphQL returned errors (invalid token, board not found, wrong column ID) |

**Add monday to a tenant's allowed integrations:**

```bash
curl -s -X PUT http://localhost:8000/tenant/config/TENANT_1001 \
  -H "Content-Type: application/json" \
  -d '{
    "enabled_job_types": ["lead", "customer_inquiry"],
    "allowed_integrations": ["google_mail", "monday"],
    "auto_actions": {}
  }'
```

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

## Known Sharp Edges

These are real behaviors that have caused failures during live testing.

1. **DB tenant config overrides static config** — if an integration appears enabled in `app/core/config.py` but the route returns `403`, the DB row for that tenant is overriding it. Check and update via `PUT /tenant/config/{tenant_id}`.

2. **Integration must be in `allowed_integrations` for the tenant** — both env vars and DB config must align. Setting `MONDAY_API_KEY` alone is not enough if `monday` is not in the tenant's allowed list.

3. **Enum vs string mismatch in tenant config** — the static config previously stored `IntegrationType.MONDAY` (enum objects); the DB stores plain strings (`"monday"`). The code normalizes both now, but if you see an integration silently blocked, inspect whether the DB row contains strings or enum reprs.

4. **Monday `column_values` must come from the platform serializer** — pass a plain dict in the request payload; do not pre-serialize to a JSON string. The platform calls `json.dumps()` before sending to monday's GraphQL API. Sending a raw Python dict directly to the monday API causes `Invalid type, expected a JSON string`.

5. **`board_id` is env-only for Monday** — there is no per-request board ID override. All `create_item` calls go to `MONDAY_BOARD_ID`. To target a different board, change the env var and restart.

6. **Windows terminal (GBK) misrenders UTF-8** — Swedish characters in the API response are correct UTF-8. The Windows GBK code page shows them as `?`. Run `chcp 65001` to switch the terminal to UTF-8 before running curl.

---

## Known Limitations

- No pagination controls in the operator UI (backend supports it via query params)
- `docker-compose.yml` starts PostgreSQL only — the app runs separately via `uvicorn`
- No DB migration tooling — schema changes require manual `create_all` or ALTER TABLE
- `app/api/routes/jobs.py` is dead code (not mounted) — does not affect runtime
- Action dispatch is live for Gmail and Monday; all other integrations (CRM, Slack, Fortnox, Visma) are stubbed or webhook-based
- Windows terminals using GBK code page (default) will misrender UTF-8 characters in curl output — run `chcp 65001` to switch to UTF-8

---

## Operations (Pilot)

Phase O: **CONDITIONAL GO** (2026-07-08). Before the first customer pilot run, complete:

| Document | Purpose |
|----------|---------|
| [docs/PILOT_READINESS_CHECKLIST.md](docs/PILOT_READINESS_CHECKLIST.md) | Full pre-pilot checklist (BLOCKER / REQUIRED / RECOMMENDED) |
| [docs/PHASE_O_CLOSURE_CHECKLIST.md](docs/PHASE_O_CLOSURE_CHECKLIST.md) | Phase O conditional items with exact curl commands |
| [docs/runbooks/](docs/runbooks/) | Operational runbooks (monitoring, approvals, failed jobs, OAuth, incidents, backup, onboarding) |

**Quick healthcheck** (one command covers app, DB, containers, disk, backups):
```bash
sudo APP_BASE_URL=https://api.krowolf.se \
  DOCKER_APP_CONTAINER=krowolf-app-1 DOCKER_DB_CONTAINER=krowolf-db-1 \
  DISK_CHECK_PATH=/opt/krowolf BACKUP_DIR=/opt/krowolf/backups \
  bash /opt/krowolf/scripts/check_production_health.sh
```

**Quick kill switch** (pause a tenant):
```bash
curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/pause-automation \
  -H "X-Admin-API-Key: ADMIN_API_KEY" -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"reason"}'
```

---

## Documentation

| File | Description |
|------|-------------|
| [docs/00-master-plan.md](docs/00-master-plan.md) | **Governing document — read first** |
| [docs/01-current-truth.md](docs/01-current-truth.md) | Verified system status |
| [docs/02-first-customer-plan.md](docs/02-first-customer-plan.md) | First customer go/no-go plan |
| [docs/03-product-roadmap.md](docs/03-product-roadmap.md) | Product roadmap |
| [docs/04-execution-rules.md](docs/04-execution-rules.md) | Rules for AI/execution agents |
| [docs/05-architecture.md](docs/05-architecture.md) | Technical architecture |
| [docs/06-backlog.md](docs/06-backlog.md) | Backlog (Now / Next / Later / Not Now) |
| [docs/07-decisions.md](docs/07-decisions.md) | Locked product decisions |
| [docs/08-runbook.md](docs/08-runbook.md) | Operations runbook |
| [docs/09-testing-and-release.md](docs/09-testing-and-release.md) | Test and release procedures |
| [docs/90-cursor-prompt-template.md](docs/90-cursor-prompt-template.md) | Execution prompt template |
| [docs/archive/](docs/archive/) | Historical documents |
| [docs/PILOT_READINESS_CHECKLIST.md](docs/PILOT_READINESS_CHECKLIST.md) | Pre-pilot readiness checklist |
| [docs/PHASE_O_CLOSURE_CHECKLIST.md](docs/PHASE_O_CLOSURE_CHECKLIST.md) | Phase O closure conditions |
| [docs/runbooks/](docs/runbooks/) | Operational runbooks |
