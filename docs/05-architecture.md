# Architecture

> This document describes how the system is currently built. It is not a product vision document.
> Governed by `docs/00-master-plan.md`. Architecture changes require a decision in `docs/07-decisions.md`.

---

## System overview

FastAPI backend — multi-tenant, backend-first platform for AI-driven workflow automation.

Jobs are received, classified, processed through a pipeline, paused for human approval when required, and resumed to execute integration actions. Everything is auditable.

```
Gmail / API  →  POST /jobs  →  Pipeline  →  Policy  →  Approval Queue
                                                    ↘  Action Dispatch  →  Gmail / Monday / Fortnox
```

---

## Backend layers

| Layer | Path | Role |
|-------|------|------|
| API | `app/api/` | FastAPI routes, auth dependencies |
| Core | `app/core/` | Config, auth, admin session, settings |
| Domain | `app/domain/` | Jobs, approvals, actions, integrations (domain models) |
| Workflows | `app/workflows/` | Orchestrator, processors, dispatchers, scanners |
| Integrations | `app/integrations/` | Adapters (Gmail, Monday, Fortnox, Visma stubs) |
| AI | `app/ai/` | LLM classification/extraction schemas |
| Insights | `app/insights/` | Operational insights, SLA reminders, KPIs |
| Lead | `app/lead/` | Lead analyzer, scorer, offer draft, next action |
| Support | `app/support/` | Support analyzer, prioritizer, response draft |
| Onboarding | `app/onboarding/` | Readiness checks, wizard state |
| Admin | `app/admin/` | Recovery actions, support console |
| Alerts | `app/alerts/` | Production alerting engine |
| Finance | `app/finance/` (implied) | Invoice draft, Fortnox preview/export |
| Repositories | `app/repositories/postgres/` | SQLAlchemy models and DB access |
| UI | `app/ui/index.html` | Single-file operator/customer UI |

---

## Core architecture principles

- Processors are stateless.
- Jobs are stateful and carry history through the pipeline.
- The orchestrator controls pipeline, skip logic and resume paths.
- Policy decides auto / approval / manual review.
- AI output must be structured, validatable and persistable.
- Integrations execute via a shared integration layer (adapter/factory pattern).

---

## Pipeline

Standard lead pipeline:

```
intake → classification → entity_extraction → lead_analysis → decisioning → policy → action_dispatch → human_handoff
```

Customer inquiry pipeline:

```
intake → classification → entity_extraction → support_analysis → customer_inquiry → decisioning → policy → action_dispatch → human_handoff
```

Invoice pipeline:

```
intake → classification → entity_extraction → invoice → policy → human_handoff
```

Classification falls back to deterministic keyword rules when `LLM_API_KEY` is not set. Pipeline always completes.

---

## Approval flow

1. Pipeline reaches policy processor.
2. Policy requires approval (or `force_approval_test: true` in input).
3. Approval request created in DB (`approval_requests` table).
4. Job paused as `awaiting_approval`.
5. Operator approves or rejects via UI or API.
6. Approve → pipeline resumes at post-approval path, action executes.
7. Reject → job moves to `manual_review`.

---

## Multi-tenant

- Tenant identified via `X-API-Key` header (server-side resolved).
- `X-Tenant-ID` trusted only in dev mode (when `TENANT_API_KEYS` is empty).
- Tenant config stored in `tenant_configs` DB table; static fallback in `app/core/config.py`.
- Admin operations use `X-Admin-API-Key` + optional `X-Tenant-ID` for tenant-scoped admin access.
- DB-backed tenant API keys (hashed, `kw_` prefix) take precedence over env-var keys.
- Inactive tenant returns 403 at auth layer.

---

## Integration layer

All integrations use the pattern:

```
adapter.execute_action(action: str, payload: dict) → dict
```

Route: `POST /integrations/{type}/execute` accepts:

```json
{ "action": "<action_name>", "payload": { ... } }
```

### Google Mail — verified (historical)

| Action | Direction | Status |
|--------|-----------|--------|
| `send_email` | Write | Live-verified |
| `list_messages` | Read | Live-verified |
| `get_message` | Read | Live-verified |

OAuth: 401 → refresh → retry. All four env vars required for refresh.

Thread reply: supports `thread_id`, `In-Reply-To`, `References`.

### Monday — verified (historical)

| Action (direct) | Action (workflow) | Status |
|-----------------|-------------------|--------|
| `create_item` | `create_monday_item` | Live-verified |

`board_id` is env-only (`MONDAY_BOARD_ID`). `column_values` serialized internally.

### Fortnox

Read: customers, articles, invoices (up to 50 each).
Write: invoice export — approval-gated with idempotency key, dry-run preview available.
Credentials: `FORTNOX_ACCESS_TOKEN` + `FORTNOX_CLIENT_SECRET`.

### Visma

OAuth callback exists. Read/API test endpoint exists. Full write path not confirmed.

### Stubs

`notify_slack`, `notify_teams`, `create_internal_task` — stubs only.

---

## Action dispatch

`app/workflows/action_executor.py` — supported action types:

| Workflow action type | Adapter |
|---------------------|---------|
| `send_email` | GoogleMailAdapter |
| `send_customer_auto_reply` | GoogleMailAdapter |
| `send_internal_handoff` | GoogleMailAdapter |
| `create_monday_item` | MondayAdapter |
| `notify_slack` | Stub |
| `notify_teams` | Stub |
| `create_internal_task` | Stub (no persistence) |

The workflow does NOT auto-generate actions. Actions must be provided in `input_data.actions` or come from processor default-action builders.

---

## Controlled dispatch

`app/workflows/dispatchers/` — separate from pipeline action dispatch:

- `ControlledDispatchEngine` + `DISPATCH_REGISTRY` keyed by (system, job_type).
- `MondayLeadDispatchAdapter` — creates Monday item with idempotency guard.
- Policy: `resolve_dispatch_policy()` maps `auto_actions[job_type]` to `manual` / `approval_required` / `full_auto`.
- Duplicate guard via `idempotency_key` in `integration_events`.
- Auto-dispatch hook in `WorkflowOrchestrator._finalize_success`.

---

## Data stores

| Table | Purpose |
|-------|---------|
| `jobs` | Job records with status and result |
| `audit_events` | Audit trail for all pipeline events |
| `approval_requests` | Approval pause records (pipeline + dispatch + email) |
| `action_executions` | Executed action records |
| `integration_events` | Integration call records (dispatch, Fortnox export) |
| `tenant_configs` | DB-driven tenant configuration (overrides static config) |
| `tenant_api_keys` | Hashed DB-backed API keys per tenant |

---

## Risk boundaries

| Action type | Risk level | Policy |
|-------------|-----------|--------|
| Read from Gmail inbox | Low | Automatic |
| Classify / extract | Low | Automatic |
| Create case record | Low | Automatic |
| Send email to customer | High | Approval-gated by default |
| Create Monday item | Medium | Configurable per tenant |
| Fortnox invoice export | High | Approval-gated always |
| Fortnox dry-run preview | Low | Automatic |
| Delete anything | High | Not implemented / forbidden |
| Mass send | Forbidden now | Out of scope |

---

## Frontend principle

- Single-file `app/ui/index.html` served by FastAPI via `HTMLResponse`.
- No React, Vite, Tailwind, or build toolchain. (DEC-004)
- Dark/light mode via CSS tokens. No new design direction without decision.
- Admin mode shows all views; Customer mode shows safe subset.
- All business logic in backend; UI only consumes API.

---

## Deployment

- `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `docker-compose.yml` — Postgres only
- `docker-compose.prod.yml` — production stack
- `Dockerfile` — production container image
- `.github/workflows/release-gate.yml` — CI gate
- `scripts/run_release_gate_r1.py` — local release gate
- `scripts/smoke_check.py` — post-deploy smoke check
- `scripts/create_tables.py` — idempotent table creation
- `ENV=production` disables dev-mode fallback and public API docs

---

## Known dead code

- `app/api/routes/jobs.py` — not mounted in `main.py`, has SECURITY WARNING comment.
- `app/api/approval_routes.py` — not mounted, has SECURITY WARNING comment.
