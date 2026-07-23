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

`POST /jobs` strips any client-supplied `input_data.live_eval` before persistence. Only Gmail trusted intake + atomic root claim may attach `trusted=true` snapshots.

Registry binding (`validate_trusted_live_eval_context`) is required before fixture AI, live LLM routing, or write-policy dispatch: `job.tenant_id`, `config_hash`, `ai_mode`, fixture bundle, scenario/attempt, active status, and `expires_at` must match the authoritative `live_eval_runs` row.

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

### PostgreSQL integration_db (CI + local)

CI bootstraps schema once before `integration_db` tests:

```bash
ENV=test DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_platform \
  python -m scripts.ci.bootstrap_postgres_schema
ENV=test DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_platform \
  python -m pytest tests/evaluation/live -m integration_db --junitxml=live_eval_integration_db.junit.xml
```

The `integration_db` fixture verifies schema provisioning only; it does not run migrations.

CI gates (release-gate `live-eval-postgres` job):

1. `tests/evaluation/live -m integration_db` — exactly 5 tests (atomic root claim)
2. `test_postgres_migration_016_table_when_database_available` — 1 test
3. `tests/evaluation/live/test_telemetry_idempotency_pg.py -m integration_db` — 2 tests (session-safe telemetry)

### Journal

`storage/live_eval/runs/<id>/transitions.jsonl` (append-only) and `report.json` (atomic replace). Directory `0750`, files `0640`.

### Operator contract (Gmail filter)

`validate-config` verifies label `krowolf-live-eval` and intake query. Filter must apply the label — verified end-to-end in 2F.2.

#### Filter probe (before first real S01 run)

Verify the recipient filter without starting the testbot or Krowolf app:

1. Send a **manual** email from the dedicated sender account to the recipient account.
2. Use a subject **without** any `KROWOLF-EVAL` token (for example `Filter probe`).
3. Confirm the message receives exactly the label `krowolf-live-eval`.
4. Mark the message as **read**.
5. **Archive** the message (do not permanently delete by default).
6. Remove the `krowolf-live-eval` label from the archived probe.
7. Confirm no probe remains **unread** under the eval label.

The probe message is **not** part of testbot send telemetry. It must **never** contain a live-eval token. The first real S01 run may start only after the probe is fully cleared from the unread eval-label queue.

## 2F.2 scope (live Gmail transport)

2F.2 adds the first real Gmail transport path for scenario `S01_lead_laddbox_quality` (inbound-only, `awaiting_approval`, fixture AI).

### Architecture

- **Testbot process** (`scripts/run_live_eval.py`, `app/evaluation/live/runner.py`): sender credentials, journal, HTTP observer, cleanup.
- **Krowolf app**: recipient OAuth, duplicate-safe delivery observation, exact-message `process-delivery`, pipeline, telemetry.

### Gates

| Env var | Purpose |
|---------|---------|
| `EXTERNAL_SIDE_EFFECT_TESTS=yes` | Required for send, process-delivery, cleanup (both processes) |
| `LIVE_GMAIL_EVAL_ALLOWED=yes` | Gmail transport |
| `BUILD_GIT_SHA` | Runtime SHA match via `GET /admin/live-eval/runtime-readiness` |

### Admin routes (2F.2)

- `GET /admin/live-eval/runtime-readiness`
- `GET /admin/live-eval/runs/{id}` — redacted run summary
- `GET /admin/live-eval/runs/{id}/delivery` — duplicate-safe (max 2 candidates)
- `GET /admin/live-eval/runs/{id}/observation` — job + DecisionRecords (redacted)
- `POST /admin/live-eval/runs/{id}/process-delivery` — exact message intake
- `POST /admin/live-eval/runs/{id}/cleanup-recipient` — pre/post claim archive

### CLI

```bash
python scripts/run_live_eval.py run-scenario --scenario-id S01_lead_laddbox_quality --confirm-external
python scripts/run_live_eval.py cleanup-run --run-id <id> --confirm-external
python scripts/run_live_eval.py show-report --run-id <id>
```

### Live workflow

Manual `workflow_dispatch` only. Job `live_gmail_transport` uses ephemeral app (PostgreSQL + uvicorn) in GitHub environment `live-gmail-eval`.

### Sender credentials (testbot only)

- `LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN`
- `LIVE_EVAL_SENDER_GMAIL_CLIENT_ID`
- `LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET`

Never commit tokens. Report schema version: `2f.2`.

### Implementation status (2F.2 hardening)

**Merged to `main` @ `4d343f8` (PR #11, 2026-07-22).** Post-merge CI (Release Gate `29926558386`): hermetic 2F.2 tests 107 PASS (local); 2E smoke 10/10; `real_external_calls=0`; backend 4002 PASS; live-eval PG 5/5; telemetry PG 2/2; migration 016 PG 1/1; frontend PASS; Docker PASS. Gmail sends to date: **0**.

| Area | Status |
|------|--------|
| Code merged to `main` | Yes (`4d343f8`) |
| Hermetic unit/contract tests | Yes (107; no Gmail/LLM in CI hermetic job) |
| Security review (F-01–F-07) | Closed |
| Manual `live_gmail_transport` workflow | Built (`workflow_dispatch` only; not auto-run on merge) |
| Real Gmail send verified | **No** |
| Live Gmail E2E verified | **Pending operator verification** |
| Live LLM enabled | **No** |
| Operator secrets/config | **Required — not configured** |
| 2F.2 slice complete | **No** |
| 2F.3 started | **No** |

### Resume / no-resend

- `run_config.json` stores fingerprints (not raw addresses), `config_hash`, transport/ai modes, and `send_window_start`.
- `derive_resume_state()` drives phases: `pre_send`, `reconcile_only`, `post_send`, `post_delivery`, `post_intake`, `cleanup_only`.
- Registry vs journal mismatch → fail-closed `registry_journal_mismatch`.
- Terminal states (`passed`, `failed`, `send_outcome_unresolved`, etc.) are not resumable.

### Writer lock

- Atomic `.writer.lock` via `O_CREAT|O_EXCL` under `storage/live_eval/runs/<id>/`.
- Run storage must be **local and non-shared** between concurrent runners (no NFS/shared volume).
- Force unlock requires `--force-unlock`, `LIVE_EVAL_FORCE_UNLOCK=yes`, stale age, **same hostname**, and dead PID.
- Cross-host locks return `cross_host_lock_not_recoverable` (never force-unlocked).
- `lock_forced` transition recorded before re-acquire on same-host stale recovery.

### Send budget (locked for 2F.2)

- `max_scenarios_per_run = 1`
- `max_gmail_sends_per_run = 1`
- `max_gmail_replies_per_run = 0`
- Journal enforces no second send; `sending` without `sent` → reconcile only.

### Sent reconciliation

- Search `in:sent` only, max 2 candidates, full `get_message`, full token match (run/scenario/attempt), sender/recipient, window, optional RFC Message-ID.
- 0 → unresolved; 1 → resolved; >1 → correlation failure; never resend.

### Delivery hardening

- Exact Gmail label ID (list labels → resolve name → require ID in `label_ids`).
- `internal_date_ms=None` rejected.
- Run status gates on observation and process-delivery.

### Unexpected reply

- Observed after pipeline, before assertions.
- Full token + sender/recipient relation + window + metadata verification.
- Failure category `unexpected_external_write`; cleanup requires exact message ID.

### Server-side gates (`transport_mode=live_gmail`)

- Scenario `S01_lead_laddbox_quality`, `ai_mode=fixture_ai`, tenant allowlist, all live-eval mutation gates on process-delivery/cleanup.
- Idempotent process-delivery when run is `active` with matching `root_gmail_message_id`.

### OAuth seed

```bash
python scripts/seed_live_eval_gmail_oauth.py --tenant-id TENANT_LIVE_EVAL          # dry-run
python scripts/seed_live_eval_gmail_oauth.py --tenant-id TENANT_LIVE_EVAL --apply  # requires LIVE_EVAL_SEED_ALLOWED=yes
```

### CLI additions

```bash
python scripts/run_live_eval.py run-scenario --run-id-file "$RUNNER_TEMP/live_eval_run_id" ...
python scripts/run_live_eval.py resume-run --run-id <id> --force-unlock
python scripts/run_live_eval.py show-report --run-id <id>   # redacted JSON only
```

### Live workflow

Manual `workflow_dispatch` only on `main`. Workflow input `confirm_live_gmail` must be `READINESS_ONLY` or `RUN_S01`; default `DO_NOT_RUN` blocks the live job.

| Gate | Purpose |
|------|---------|
| `operator-gate` job | Requires `refs/heads/main` and `confirm_live_gmail` in `{READINESS_ONLY, RUN_S01}` (no environment secrets) |
| GitHub environment `live-gmail-eval` | Required reviewer, deployment branch policy **main only**, dedicated test credentials only |
| `BUILD_GIT_SHA` | Runtime SHA match via `GET /admin/live-eval/runtime-readiness` |

`live_gmail_transport` needs `foundation` + `operator-gate`, uses environment `live-gmail-eval`, `timeout-minutes: 45`, `concurrency.group: live-gmail-eval`.

**CI storage:** `STORAGE_PATH=${{ github.workspace }}/storage/ci-live-eval` so journals resolve to `storage/ci-live-eval/live_eval/runs/<id>/` and artifact upload uses the same resolved path via `resolved_run_directory()`.

**Failure observability:** every `run-scenario` exit emits a redacted JSON summary to stdout and `GITHUB_STEP_SUMMARY`, and attaches `failure_summary` to `report.json`. Missing `report.json` after run-ID creation fails the verify-artifacts step.

**Sender send-scope preflight (RUN_S01 only):** `verify_sender_send_scope()` checks send-capable Gmail scopes from OAuth refresh metadata only (`gmail.send`, `gmail.compose`, `gmail.modify`, `mail.google.com`) — no test-send, no tokeninfo. READINESS_ONLY read-only sender checks are unchanged.

**Send states:** `not_attempted`, `sending`, `confirmed`, `outcome_unknown`, `failed_before_send`. `outcome_unknown` is non-resumable.

**Cleanup:** without exact `recipient_gmail_message_id`, `cleanup-run` resolves the recipient ID from the run journal (`delivery_confirmed` transitions only). If the journal yields zero, multiple distinct, or sender IDs, cleanup returns `cleanup_state=not_safe_to_execute` with `gmail_mutations=0`. Exit semantics: when the primary scenario already failed, blocked cleanup returns exit `0` (non-masking); when the primary scenario passed, blocked cleanup returns `EXIT_CLEANUP` (6) so the run cannot be treated as fully successful without cleanup.

### 2F.2C recipient identity, pre-claim cleanup, structured safety (in progress)

**Root cause (RUN_S01 #8):** delivery observation validates recipient via message headers; intake trust validation used OAuth `user_id="me"` when `metadata_json.email` was missing. `"me"` is never a verified mailbox address.

**Canonical recipient identity:** `resolve_canonical_recipient_email()` prefers `metadata_json.email`, then syntactically valid `user_id`, else fail-closed (`recipient_identity_unverified`). OAuth seed stores the single allowlisted `LIVE_EVAL_RECIPIENT_EMAILS` entry in `metadata_json.email` (no duplicate secret).

**Structured safety rejection (HTTP 400):** `process-delivery` and `cleanup-recipient` return allowlisted payloads (`error_code=live_eval_safety`, `safety_reason`, `evaluation_run_id`, `scenario_id`, `attempt_id`, `tenant_id`, `failed_stage`, `http_status`, `retry_allowed`, `root_job_created`, `diagnostic_code`). Observer raises `LiveEvalSafetyRejectedError`; runner maps to `EXIT_CONFIG` (2), not `EXIT_TRANSPORT` (3).

**Pre-claim cleanup:** `cleanup-run` defaults to `--phase auto`. When `root_job_bound=false` and journal has exactly one `delivery_confirmed` recipient ID, cleanup uses `pre_claim` (archive only that message). `post_claim` requires trusted `root_gmail_message_id`.

**Summary provenance:** RUN_S01 `GITHUB_STEP_SUMMARY` includes `workflow_sha` from `BUILD_GIT_SHA` only (fixture markers like `abc123` are blocked). Foundation offline dry-run summary is labeled `offline/hermetic` and does not claim a workflow SHA.

### 2F.2B intake observability and journal cleanup

**Intake skip (HTTP 409):** `POST .../process-delivery` returns a structured, allowlisted payload (`error_code=intake_skipped`, `intake_skip_reason`, `evaluation_run_id`, `failed_stage`, `http_status`, `run_status`, `root_claimed`, `job_created`, `retry_allowed`, `diagnostic_code`). The testbot observer parses this before `raise_for_status()` and raises `LiveEvalIntakeSkippedError`; the runner maps intake skip to `EXIT_CONFIG` (2), not `EXIT_TRANSPORT` (3).

**Allowlisted `intake_skip_reason` values:** `missing_intake_cutoff`, `before_intake_cutoff`, `lead_disabled`, `customer_inquiry_disabled`, `invoice_disabled`, `duplicate`, `intake_skipped_unknown`.

**Eval tenant seed:** `scripts/seed_live_eval_tenant.py` sets `intake.intake_cutoff_at` to UTC seed time minus a 300s tolerance window (not a static historical date). Dry-run remains default; all ENV/tenant/database guards unchanged.

**Journal cleanup resolver:** `cleanup_only()` without `--recipient-message-id` loads `delivery_confirmed` transitions, deduplicates recipient IDs, requires exactly one unique ID, rejects sender ID matches, and verifies run/scenario/attempt/tenant metadata before exact cleanup.

#### Readiness-only (`READINESS_ONLY`)

Runs from `main` with protected environment `live-gmail-eval` and the same nine secrets as live S01. Verifies both Gmail accounts read-only:

- recipient via authenticated `POST /admin/live-eval/gmail-readiness`
- sender via `validate-config --sender-readiness --confirm-read-only`

Does **not** register a live-eval run, write a run-ID file, send Gmail, mutate Gmail, run cleanup, or invoke live LLM. Produces a redacted `readiness_report.json` artifact (`external_sends=0`, `gmail_mutations=0`).

```bash
python scripts/run_live_eval.py readiness-only \
  --tenant-id TENANT_LIVE_EVAL \
  --confirm-read-only \
  --report-file /path/to/readiness_report.json
```

#### Live S01 (`RUN_S01`)

Unchanged S01 flow: exact one send, journal, assertions, exact cleanup, redacted run artifact. Cleanup failures fail the job via a final gate step; artifacts still upload on failure. Scenario remains hardcoded to `S01_lead_laddbox_quality` only.

#### Operator sequence

1. Configure environment, nine secrets, and Gmail label/filter (including filter probe cleanup).
2. Dispatch workflow with `READINESS_ONLY` from `main`.
3. Verify readiness artifact: sender/recipient profile match, label present, `external_sends=0`, `gmail_mutations=0`.
4. Separately approve and dispatch `RUN_S01` for the first real S01 send.

### OAuth seed database guard (F-08)

`seed_live_eval_gmail_oauth.py` reuses the same substring-based production URL heuristic as `seed_live_eval_tenant.py`. No shared positive test-database fingerprint model exists in-repo yet; changing this is deferred as LOW to a separate seed-script hardening task. All other guards (`ENV=test`, `LIVE_EVAL_SEED_ALLOWED`, tenant allowlist, `is_test_tenant`) remain enforced.

Recipient Gmail OAuth rows may store `user_id="me"` in connection config as a Gmail API selector. **Intake trust validation** uses the canonical recipient email from OAuth `metadata_json.email` (seeded from `LIVE_EVAL_RECIPIENT_EMAILS`). Readiness still verifies the real recipient via `get_profile.email_address`.
