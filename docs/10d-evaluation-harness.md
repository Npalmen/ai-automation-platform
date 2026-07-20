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

Blocking verification before 2D.1 sign-off:

```bash
set EVAL_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_platform_eval
set EVAL_HARNESS_PG_ALLOWED=yes
set ENV=test
pytest -m pg_eval -q
```

Uses `ensure_runtime_schema()` (deployment migration path) and `migrations/015_decision_records.sql` for upgrade tests. Tenant cleanup is verified via explicit purge + new connection (not outer rollback).
