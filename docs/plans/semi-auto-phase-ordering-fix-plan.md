---
name: Semi-auto phase ordering fix
overview: Korrigera canary-harnessens pre- och post-operator-faser så att transient awaiting_approval inte krävs efter att operator action redan observerats, utan att dölja approval bypass eller saknad Gmail-exekvering
todos:
  - id: phase-order-a-timeline
    content: Bygg exakt event- och funktionsordning för TBSM01 och TBSM04 i run 30308440030
    status: completed
  - id: phase-order-b-reproduction
    content: Reproducera terminal-status-before-job-detected i hermetisk och PostgreSQL-baserad campaign runner
    status: completed
  - id: phase-order-c-contract
    content: Definiera separata pre-operator, operator och post-operator observationskontrakt
    status: completed
  - id: phase-order-d-implementation
    content: Implementera phase-aware polling och monotona operator markers utan att acceptera approval bypass
    status: completed
  - id: phase-order-e-assertions
    content: Korrigera scenarioassertions för TBSM01 och TBSM04 med runtimebaserad fasprovenance
    status: completed
  - id: phase-order-f-regression
    content: Kör tester, PR, CI, merge och post-merge Release Gate
    status: in_progress
  - id: phase-order-g-canary
    content: Kör exakt en ny TBSM01 och TBSM04 canary
    status: pending
  - id: phase-order-h-stop
    content: Rapportera canary och stoppa före full kampanj
    status: pending
isProject: true
---

# Semi-auto phase ordering fix

## Context

Canary `30308440030` @ `d9001232` (PR #86 merged) fails at `poll_pipeline_observation → unexpected_terminal_status` in `job_detected` before the test operator runs. R3 (`pending_approval_count = 0` after target resolution) holds.

## Goal

Separate pre-operator, operator, and post-operator observation contracts with monotonic phase provenance. Detect `approval_bypass_or_phase_order_violation` when terminal/resolution appears before recorded operator execution.

## Non-goals

- No product approval bypass
- No weakening of PR #84/#85/#86
- No full TBSM01–TBSM08 campaign

## Implementation scope

- `app/evaluation/live/semi_auto_phase.py` — phase contracts and polling
- `app/evaluation/live/runner.py` — phase orchestration
- `app/evaluation/live/campaign/runner.py` — provenance on scenario results
- `app/evaluation/live/campaign/semi_automatic_expected_outcomes.py` — post-operator terminal statuses
- `tests/evaluation/live/test_semi_auto_phase_ordering.py` — regression tests
