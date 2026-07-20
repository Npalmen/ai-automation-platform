# Kapitel 2D — Deterministic Evaluation Harness

> **Status:** Implemented (local) — 2026-07-20  
> **Locked decision:** DEC-035  
> **Prerequisite:** DEC-034 (2C decision trace)

## Scope

Local deterministic evaluation through **real production entrypoints** (`run_pipeline`, `process_action_dispatch_job`, approval resolution). No live LLM, no external I/O, no `--with-llm` in 2D.

## Layout

| Path | Role |
|------|------|
| `app/evaluation/` | Schema, loader, runner, assertions, scoring, reporting, fixture AI, adapter fakes |
| `tests/evaluation/scenarios/` | Normative YAML scenarios (`schema_version: 2d.1`) |
| `tests/evaluation/baselines/` | Approved baseline snapshots (status/metrics only) |
| `scripts/run_eval_harness.py` | CLI |
| `scripts/generate_eval_scenarios.py` | Regenerate curated YAML from templates |

## Deterministic AI modes

| Mode | Use |
|------|-----|
| `fixture_ai` | Default — schema-valid fixtures per `prompt_name`, production `run_ai_step` parsers |
| `forced_fallback` | Explicit scenarios testing LLM failure / fail-closed only |

Runner fails on unexpected AI calls or unused fixtures. `pre_seed` only allowed with `contract_edge` or `legacy` tags.

## External execution

- **Does not patch away** `execute_action`
- Replaces **outermost** `get_integration_adapter` with `EvalFakeAdapter`
- Telemetry: `execution_function_calls`, `fake_adapter_calls`, `real_external_calls` (must be 0)

## Safety vs quality

1. **Safety gates** — veto (exit `1`)
2. **Per-metric quality gates** — exit `2` if any mandatory metric below threshold
3. **Diagnostic weighted score** — report only
4. **Baseline regression** — exit `21`

## CLI

```bash
python scripts/run_eval_harness.py --smoke
python scripts/run_eval_harness.py --baseline tests/evaluation/baselines/k2d-baseline-v1.json --fail-on-regression
```

## CI smoke scenarios

S01, S08, S10, S14, S15, S16, S17, S18

## PostgreSQL eval tier (2D.1)

**Status:** Verified (blocking sign-off complete) — 2026-07-21

Blocking verification before 2D.1 merge:

```powershell
# Idempotent eval database (local PostgreSQL)
python scripts/ensure_eval_pg_database.py

$env:ENV = "test"
$env:EVAL_HARNESS_PG_ALLOWED = "yes"
$env:EVAL_DATABASE_URL = "postgresql://<user>:<password>@localhost:5432/ai_platform_eval"
pytest -m pg_eval -q
```

Requirements enforced by `require_eval_pg_database_url()`:

- `ENV` must be exactly `test`
- `EVAL_HARNESS_PG_ALLOWED=yes`
- database name must be exactly `ai_platform_eval` (never `ai_platform`)
- host must be `localhost` or `127.0.0.1`

Migration verification (no `create_all` / `ensure_runtime_schema` as proof):

1. **Empty DB path:** `reset_public_schema` → `apply_pre_migration_baseline` (create_tables.py equivalent) → SQL files `009`…`015`
2. **Upgrade path:** same baseline → `009`…`014` → `015_decision_records.sql`

Tenant cleanup: explicit `purge_eval_tenant` + verification via **new engine** after `dispose()`.

**CI gap:** `.github/workflows/release-gate.yml` runs `python -m pytest` without `EVAL_*` env vars, so `pg_eval` is skipped in CI unless configured. Local Docker/PostgreSQL verification above is the authoritative 2D.1 sign-off gate until CI is extended.
