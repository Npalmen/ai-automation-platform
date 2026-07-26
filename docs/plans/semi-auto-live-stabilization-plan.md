---
name: Semi-auto live stabilization
overview: Stabilisera semi-auto-kampanjens approvalmaterialisering, scenarioisolering, negativa kontroller och Gmail-verifiering efter run 30219704813 utan ny live-rerun
todos:
  - id: stabilize-a-side-effect-truth
    content: Fastställ faktisk Gmail- och approvalpåverkan från run 30219704813
    status: completed
  - id: stabilize-b-materialization-contract
    content: Anpassa scenario- och readinesskontrakt till testtenantens faktiska materialiserade actions
    status: completed
  - id: stabilize-c-scenario-isolation
    content: Gör Gmail-intake, job detection och approvalval strikt run- och scenarioisolerade
    status: completed
  - id: stabilize-d-negative-controls
    content: Separera negative-control assertions från operator- och target-action assertions
    status: completed
  - id: stabilize-e-recipient-verification
    content: Gör Gmail reply-verifiering provider- och mottagarbaserad med outcome-unknown fail-closed
    status: completed
  - id: stabilize-f-reporting-readiness
    content: Förbättra readiness, kampanjräknare, kontraktsmatris och evidensrapportering
    status: completed
  - id: stabilize-g-regression-delivery
    content: Kör regressionssviter, PR, CI, merge och post-merge Release Gate
    status: in_progress
  - id: stabilize-h-rerun-gate
    content: Slutgranska stabiliseringen och stoppa för nytt operatörsgodkännande
    status: pending
isProject: true
---

# Semi-auto live stabilization

**Failed run:** `30219704813` @ `d54c82c` — 0/8 PASS  
**Branch:** `fix/semi-auto-live-stabilization`  
**Prior fix:** PR #60 multi-action operator contract

## Root causes (run 30219704813)

| Scenario | Failure | Category |
|----------|---------|----------|
| TBSM01–05 | `secondary approval 'send_internal_handoff' not found` | Harness — tenant lacks `internal_notification_email` |
| TBSM06 | `intake_skipped_unknown` | Harness/environment — intake skip reason not allowlisted or classification gate |
| TBSM07 | `target_approval_not_found` | Harness — stale step cannot match terminal rejected approval |
| TBSM08 | `missing target_action_operation_id` | Harness — negative control runs target-scoped assertions |

**Adapter attempts (TBSM01–03):** `provider_accepted_not_recipient_verified` — 3 adapter sends, 0 recipient-verified replies.

## Budget (live rerun — not authorized in this phase)

| Gate | Value |
|------|-------|
| Inbound sends | 8 |
| Authorized verified Gmail replies | 4 |
| Max replies per scenario | 1 |
| Unauthorized Gmail replies | 0 |
| Non-Gmail external writes | 0 |

## Materialization contract (live-eval tenant)

`TENANT_LIVE_EVAL` seed has no `internal_notification_email`. Product skips `send_internal_handoff` with `no_internal_recipient` (`action_dispatch_processor.py`).

Semi-auto-core contract:

- `send_customer_auto_reply` → `materialized_pending` (target)
- `send_internal_handoff` → `not_materialized` (`tenant_internal_notification_disabled`)

Multi-action with actual internal handoff → separate campaign family later.

## Implementation scope

Harness only unless audit proves isolated product bug:

- `tenant_materialization.py` — tenant-aware action expectations
- TBSM YAML — `not_materialized` secondary, `negative_control` on TBSM08
- `test_operator.py` — terminal-state target match for stale/duplicate steps
- `runner.py` — skip target-scoped assertions for negative control
- `reply_metrics.py` — independent provider/recipient counters
- `campaign/runner.py` — observed `approval_status`, `campaign_run_id`
- Readiness materialization matrix
- Regression tests

## Out of scope

- Live Gmail rerun
- Changing test tenant to force internal handoff
- General decisioning / approval schema / migrations

## Stop gate

After green post-merge Release Gate:

```
OPERATOR ACTION REQUIRED — Auktorisera stabiliserad semi-auto rerun
```

`testbot-d-semi-automatic-campaign` remains `in_progress`.  
`testbot-e-automatic-campaign` remains `NO-GO`.
