---
name: Semi-auto multi-action harness
overview: Fix semi-auto test harness contract mismatch from run 30215738563 by explicit operator_plan, deterministic target matching, and secondary approval assertions without product changes.
todos:
  - id: phase-a-inventory
    content: Write storage/status/semi-auto-multi-action-contract-30215738563.md (local, not committed)
    status: pending
  - id: phase-b-contract-schema
    content: Add operator_plan + secondary_approvals schema and semi_automatic_expected_outcomes parsing
    status: pending
  - id: phase-c-test-operator
    content: Refactor test_operator.py with deterministic target match and secondary assertions
    status: pending
  - id: phase-d-yaml
    content: Update TBSM01-TBSM08 YAML with operator_plan and corrected final_job_status
    status: pending
  - id: phase-e-runner-assertions
    content: Wire runner/assertions for target-scoped resolution checks
    status: pending
  - id: phase-f-readiness
    content: Add operator contract matrix and readiness gate
    status: pending
  - id: phase-g-tests
    content: Add/update harness contract tests
    status: pending
  - id: phase-h-pr
    content: PR, CI, squash-merge, post-merge Release Gate (no live rerun)
    status: pending
isProject: true
---

# Semi-auto multi-action harness fix

**Planstatus:** Godkänd exekveringsplan  
**Failed run:** `30215738563` @ `758502e` — 1/8 PASS  
**Root cause:** `harness_contract_mismatch` — multiple per-action approvals materialized; test operator required exactly one pending approval.

**Branch:** `fix/semi-auto-multi-action-approval-selection`

## Budget (live rerun — not authorized in this phase)

| Gate | Value |
|------|-------|
| Inbound sends | 8 |
| Authorized verified Gmail replies | 4 |
| Max replies per scenario | 1 |
| Unauthorized Gmail replies | 0 |
| Non-Gmail external writes | 0 |
| Sheets writes | 0 |
| Monday writes | 0 |
| Visma writes | 0 |

## Out of scope

Product approval materialization, dispatch, action authorization, Gmail adapter, write-policy, production routes.

## Operator contract

`operator_plan` is **authoritative** for semi-auto scenarios. Legacy `operator_action` remains **read-only** for backward compatibility in parsers; readiness **warns** when legacy field is used without `operator_plan`. TBSM01–TBSM08 use `operator_plan`.

## Target matching (deterministic)

Static identification keys: `tenant_id`, `job_id`, scenario correlation context, `action_type`, `delivery_type`.

- `action_operation_id` is read from the uniquely matched runtime approval and **locked** for duplicate/stale steps and assertions.
- **Forbidden:** list order, `created_at`, `approval_id` sort order.
- Zero matches → `target_approval_not_found`
- Multiple matches → `ambiguous_target_approval`

## Secondary approvals (TBSM01–TBSM07)

`send_internal_handoff` must:

- remain `pending` after operator phase
- have no resolution record, execution intent, or execution outcome
- not be touched by test operator

Assertions for resolution/intent/outcome/reply are scoped to target `action_operation_id`.

## Terminal job status

When secondary `send_internal_handoff` remains pending, product keeps job `awaiting_approval` ([`email_approval_resolution.py`](app/workflows/email_approval_resolution.py)). TBSM01–TBSM07 `final_job_status` = `awaiting_approval`.

## Mandatory stop

After green post-merge Release Gate:

```
OPERATOR ACTION REQUIRED — Auktorisera semi-auto rerun efter multi-action harness-fix
```

Todo D: `in_progress` · Todo E: `NO-GO`
