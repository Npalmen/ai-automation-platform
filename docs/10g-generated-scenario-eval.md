# Kapitel 2G — Generated scenario evaluation

**Status:** Closure candidate — implementation complete  
**Generator version:** `2g-generator-v1`  
**Mutation version:** `2g-mutation-v1`  
**Canonicalization:** `semantic-json-v2`

## Scope

Hermetic, deterministic scenario evaluation built on the 20 locked gold scenarios from Kapitel 2E. Template-based generation and versioned mutations only — no Live Gmail, no Live LLM, no external writes.

## Batches

| Mode | Scenarios | Trigger |
|---|---:|---|
| PR | 60 | `pull_request` job `2g-pr-eval` |
| Main | 160 | `push` to `main` job `2g-main-eval` |

PR composition: 20 canonical + 20 security/policy + 20 representative mutations.  
Main composition: 20 canonical + 100 general mutations + 20 adversarial + 20 boundary.

## Reports

| File | Schema |
|---|---|
| `2g_generation_manifest.json` | `2g.generation-manifest.v1` |
| `2g_batch_report.json` | `2g.batch-report.v1` |
| `2g_failures.json` | `2g.failures.v1` |
| `2g_coverage_report.json` | `2g.coverage-report.v1` |
| `2g_final_report.json` | `2g.final-report.v1` |

## Release Gate

- `2g-pr-eval` — blocking on pull requests (60 scenarios)
- `2g-main-eval` — blocking on push to `main` (160 scenarios)
- `final-2g-evidence` — push to `main` only; packages official closure artifact

## Closure declaration

**Kapitel 2G — PASS och stängt**

This declaration becomes authoritative only when post-merge job `final-2g-evidence` succeeds on the same `main` SHA and produces `2g_final_report.json` with `overall_status=passed` inside artifact `2g-final-evidence-<main-sha>`.

No new Gmail or OpenAI runs are required for 2G closure. The locked 2F baseline remains `1d7073a433f901753449e57ec2ca2293ce56fbcf` (artifact run `30165696034`).

## Authoritative Live Eval references (read-only)

| Chapter | Workflow run |
|---|---|
| 2F.2 Gmail | `30050565974` |
| 2F.3 Live LLM | `30131333378` |
