# R3 live canary execution — STOPPED (attempt 5, manual reconciliation required)

- generated_at: `2026-08-04T18:15:00Z`
- runtime_sha: `8b9a046090f33083411240c016c553a5fb54554c`
- approval_artifact: `digital-coworker-r3-manual-send-approval-8b9a046.json`
- manifest_path: `storage/status/digital-coworker-r3-canary-manifest-8b9a046.json`
- manifest_hash: `dd87f9ce7676fb60b30e6a1651ae7db62aaafe04d7f2624ac80a5e1bcff16741`
- campaign_id: `d3550a0a-8beb-48a5-b433-78684ea00c3b`
- attempt_number: **5**
- mode: `execute`
- overall_status: **FAIL**
- failure_stage: **intake_observation**
- failure_substage: **tenant_intake_gate**
- failure_reason: **missing_intake_cutoff**
- retry_performed: **false**
- automatic_retry: **false**
- secrets_exposed: **false**

## Verified manifest (pre-execute)

| Field | Value |
|-------|-------|
| path | `storage/status/digital-coworker-r3-canary-manifest-8b9a046.json` |
| runner_sha | `8b9a046090f33083411240c016c553a5fb54554c` |
| manifest_hash | `dd87f9ce7676fb60b30e6a1651ae7db62aaafe04d7f2624ac80a5e1bcff16741` |
| send_budget | 8 |
| send scenarios | 8 |
| no-send scenarios | 7 |

## JIT gate (pre-execute)

- artifact: `storage/status/r3-attempt5-jit-gate-8b9a046.json`
- jit_pass: **true**
- orphan quarantine: attempts 2–4 not active, no root binding (attempt 4 registered only)

## Root cause

`POST …/process-delivery` returned intake skip `missing_intake_cutoff`.

`TENANT_LIVE_EVAL` has **no** `tenant_configs` row in Postgres. `evaluate_intake_gate` defaults `lifecycle_status=active` with empty intake settings → fail-closed `missing_intake_cutoff` before job creation.

JIT gate did not probe tenant intake cutoff configuration; pre-execute readiness passed on Gmail/credential/mutation paths only.

**Remediation before any retry:** run `scripts/seed_live_eval_tenant.py --tenant-id TENANT_LIVE_EVAL --apply` (requires `LIVE_EVAL_SEED_ALLOWED=yes`, `ENV=test`).

## Pipeline stage outcomes (attempt 5)

| Stage | Result |
|-------|--------|
| pre_execute_readiness | **PASS** |
| live_run_registration | **PASS** (run `b5bbe7ab-…`) |
| inbound_trigger_send | **PASS** (PTB-DCQ-0000) |
| delivery_observation | **PASS** (recipient message observed) |
| process_delivery / intake | **FAIL** (`missing_intake_cutoff`, substage `tenant_intake_gate`) |
| approved_reply_sent | **false** |
| draft_created | **false** |
| job_created | **false** |
| approval_created | **false** |
| execution_intent_created | **false** |
| reply_operation_created | **false** |

## PTB-DCQ-0000 side-effect classification (attempt 5)

| Classification | Occurred |
|----------------|----------|
| `inbound_trigger_sent` | **yes** (attempt 5 trigger — not counted as approved reply) |
| `approved_reply_sent` | **no** |
| `draft_created` | **no** |

| Field | Value |
|-------|-------|
| evaluation_run_id | `b5bbe7ab-7148-4366-8fba-bd92921481f4` |
| sender_message_id_redacted | `19fc…6263` |
| run status | `registered` |
| root_job_id | `null` |

**This trigger is not counted as an approved reply.**

## Execution counters (attempt 5 actual)

| Metric | Expected | Actual |
|--------|----------|--------|
| successful_sends | 8 | **0** |
| inbound triggers (attempt 5) | 0 | **1** (orphan — not counted as reply) |
| no_send_verified | 7 | **0** |
| failed_sends | 0 | **1** |
| unknown_outcomes | 0 | **0** |
| Gmail drafts | 0 | **0** |

## Orphan accounting (cumulative)

| Orphan | Attempt | evaluation_run_id | Status |
|--------|---------|-------------------|--------|
| `orphaned_attempt_2` | 2 | `0a307286-…` | Excluded from 8/8 |
| `orphaned_attempt_3` | 3 | `05839824-…` | Excluded from 8/8 |
| `orphaned_attempt_4` | 4 | `ccd9916f-…` | Excluded from 8/8 |
| `orphaned_attempt_5` | 5 | `b5bbe7ab-…` | Excluded from 8/8 (partial) |
| `orphaned_attempt_5` | 5 | `b5bbe7ab-…` | Excluded from 8/8 (partial) |

## Gate status

- R3_LIVE_CANARY: **PENDING** (STOPPED — not PASS)
- R4_LIVE_CAMPAIGN: **PENDING**
- R5_CLOSURE: **PENDING**
- PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED: **PENDING**

---

**R3 LIVE CANARY STOPPED — manuell reconciliation krävs innan nytt försök (attempt 6 kräver ny SHA-bunden approval, nytt campaign_id, nya evaluation_run_id, och tenant intake_cutoff seed)**
