# Kapitel 2F — Live Gmail + Live LLM E2E Testbot

## 2F.1 scope (foundation)

2F.1 implements the process-independent live-eval foundation without sending Gmail, reading testbot replies, or making live LLM calls.

### Authoritative registry

`live_eval_runs` is the authoritative run registry (not `audit_events`). Migration: `migrations/017_live_eval_runs.sql`.

| Field | Purpose |
|-------|---------|
| `evaluation_run_id` | Primary key |
| `tenant_id`, `scenario_id`, `attempt_id` | Run identity |
| `transport_mode`, `ai_mode` | Registered modes |
| `fixture_bundle_id` | Server-resolved allowlisted bundle |
| `expected_sender`, `expected_recipient` | Allowlisted addresses |
| `status` | `registered` → `active` → terminal |
| `expires_at`, `config_hash` | TTL and integrity |

`audit_events` records lifecycle events only: registered, activated, completed, aborted, expired, safety_rejected.

Migration `018_live_eval_external_events.sql` adds persistent telemetry with composite FK `(tenant_id, evaluation_run_id)` → `live_eval_runs`.

### Trusted context chain

1. Parse `evaluation_run_id` + `scenario_id` + `attempt_id` from subject (`KROWOLF-EVAL/{id}/{scenario}/{attempt}`).
2. Lookup `live_eval_runs` and verify tenant, TTL, sender, recipient, label query, status.
3. Build `TrustedLiveEvalSnapshot` and store on `job.input_data.live_eval`.
4. Thread continuation reuses the **immutable** root `live_eval` snapshot unchanged. Current `gmail_message_id` / `gmail_thread_id` live in `source` metadata only.
5. Missing subject token on continuation is allowed when the root job is trusted; a present but mismatched token is safety-rejected.
6. Root job claim is atomic (`registered` → `active` + `root_gmail_message_id` / `root_job_id` / `activated_at`); job creation and claim share one DB transaction in Gmail intake.

Mail must not determine `ai_mode`, fixture bundle, tenant, or write policy.

### Admin API

- `POST /admin/live-eval/runs` — register run (`X-Admin-API-Key`)
- `POST /admin/live-eval/runs/{id}/status` — complete/abort (requires `tenant_id`)
- `POST /admin/live-eval/gmail-readiness` — read-only Gmail profile/label/tenant/allowlist/intake verification (`LIVE_GMAIL_EVAL_ALLOWED`); uses `get_profile` + `list_labels` only

### Safety gates

| Env var | Purpose |
|---------|---------|
| `LIVE_EVAL_ALLOWED=yes` + `ENV=test` | Master gate |
| `LIVE_GMAIL_EVAL_ALLOWED=yes` | Gmail transport (2F.2+) |
| `LIVE_LLM_EVAL_ALLOWED=yes` | Live LLM mode |
| `LIVE_EVAL_SEED_ALLOWED=yes` | Seed script `--apply` |

### Write policy

Only allowed external app write in 2F: `send_customer_auto_reply` to registered allowlisted testbot address when run is active and Gmail write is enabled for the eval tenant. All other integrations are blocked with auditable `app_external_write_blocked` telemetry.

### Telemetry

Persistent `live_eval_external_events` with:

- `operation_key` — logical operation identity (idempotent success boundary)
- `event_key` — single attempt/outcome (`failed→succeeded` allowed; max one `succeeded` per `operation_key`)
- Success recorded only after adapter success; retries after success skip external calls

ContextVar is in-process optimization only; hooks resolve from `job.input_data.live_eval`, pipeline metadata, registry, and DB.

### CLI

```bash
python scripts/run_live_eval.py validate-config          # offline, zero network
python scripts/run_live_eval.py dry-run
python scripts/run_live_eval.py --gmail-readiness --confirm-read-only   # via admin API only
python scripts/seed_live_eval_tenant.py --tenant-id TENANT_LIVE_EVAL   # dry-run
```

### Pytest markers

Excluded from release gate and ordinary suites:

```
not monday_live and not live_gmail_eval and not live_llm_eval and not live_e2e_eval
```

### Journal

`storage/live_eval/runs/<id>/transitions.jsonl` (append-only) and `report.json` (atomic replace). Directory `0750`, files `0640`.

### Operator contract (Gmail filter)

`validate-config` verifies label `krowolf-live-eval` and intake query. Filter must apply the label — verified end-to-end in 2F.2.
