# Kapitel 2C — Decision Trace Foundation

> **Status:** Implemented (local) — 2026-07-20  
> **Locked decision:** DEC-034  
> **Prerequisite:** DEC-033 (2B decision contract)

## Scope

Append-only `decision_records` table and runtime instrumentation. Evaluation Harness is **Kapitel 2D** (separate).

## Core concepts

### `action_operation_id`
- UUID created on first `action_authorization` for a logical external operation
- Independent of `pipeline_run_id`, HMAC key, and fingerprints
- Propagated through approval metadata, execution intent, and outcome
- Reused on approval resume, retry, and recovery

### `action_fingerprint`
- Optional HMAC diagnostic (`DECISION_RECORD_HMAC_KEY` + `fingerprint_key_version`)
- NULL when key unset — never used as idempotency identity
- Payload change changes fingerprint; same `action_operation_id` must not accept conflicting fingerprint

### `PipelineRunContext`
- Explicit parameter via `DecisionTraceSession` (no thread-local)
- Fields: `pipeline_run_id`, `parent_pipeline_run_id`, `source`, `tenant_config_version`, `code_version`, `started_at`

### External write (not exactly-once)
1. Persist `action_authorization`
2. Persist `execution_intent` (`pending`)
3. Call adapter
4. Persist `execution_outcome`

Per-action approval resume (2D.1): steps 2–4 run in the **approval-resume pipeline run** after operator approval. Steps 2 (`execution_intent`) and approval CAS are committed atomically **before** the adapter call. `action_approval_resolution` is recorded between `pipeline_run_started` and `execution_intent`. `parent_pipeline_run_id` links to the original `action_authorization` run.

If adapter may have succeeded but outcome persist fails → `outcome_unknown`, block automatic adapter retry, `reconciliation_required`.

## Migration

- `migrations/015_decision_records.sql`
- Registered in `schema_migrations.py` (`_DECISION_RECORD_MIGRATION_STATEMENTS`)
- Deploy order: migration → application code
- `tenant_id` / `job_id`: unbounded `VARCHAR` (matches `jobs`, `approval_requests`)

## Settings

| Setting | Default | Notes |
|---------|---------|-------|
| `DECISION_RECORD_ENFORCE_WRITES` | `true` | Invalid → `true`; forbidden `false` in `ENV=production` |
| `DECISION_RECORD_HMAC_KEY` | empty | Optional fingerprints only |
| `APP_CODE_VERSION` | `dev-local` | Pinned on each run |

Startup calls `verify_decision_trace_readiness()` when enforce is active.

## `processor_history`

Reset semantics on retry/reclassify **unchanged**. Full history lives in `decision_records`.

## Files

- `app/workflows/pipeline_run_context.py`
- `app/workflows/decision_record.py`
- `app/workflows/decision_record_service.py`
- `app/workflows/action_fingerprint.py`
- `app/workflows/external_write_trace.py`
- `app/workflows/decision_trace_readiness.py`
- `app/repositories/postgres/decision_record_*.py`

## Tests

`tests/test_decision_trace_2c.py`
