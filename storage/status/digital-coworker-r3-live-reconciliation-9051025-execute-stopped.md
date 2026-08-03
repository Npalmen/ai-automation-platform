# R3 live canary execution — STOPPED (attempt 2, manual reconciliation required)

- generated_at: `2026-08-03T20:53:16Z`
- reconciled_at: `2026-08-03T21:15:00Z`
- runtime_sha: `9051025f67272c3cb68d61fd9780338cd872a6bc`
- campaign_id: `e7876c9b-22d3-4baf-95ed-0b11fc15806b`
- evaluation_run_id: `0a307286-41d7-4b98-8d8b-32b120618210`
- approval_artifact: `digital-coworker-r3-manual-send-approval-9051025.json`
- mode: `execute`
- overall_status: **FAIL**
- failure_stage: **delivery_observation**
- retry_performed: **false**

## Progress vs attempt 1

| Gate | Attempt 1 (`2c5f2d4`) | Attempt 2 (`9051025`) |
|------|----------------------|----------------------|
| `POST /admin/live-eval/runs` | HTTP 400 — `live_gmail + live_llm` | **HTTP 200 OK** |
| Registration contract | blocked | **passed** |
| Failure stage | `live_run_registration` | **`delivery_observation`** |

## PTB-DCQ-0000 side-effect classification

| Classification | Occurred | Notes |
|----------------|----------|-------|
| `inbound_trigger_sent` | **yes** | Sender→recipient synthetic trigger mail |
| `approved_reply_sent` | **no** | No frozen-body reply was sent |
| `draft_created` | **no** | No Gmail draft |

**This report does not count the trigger mail as a successful R3 approved reply.**

### Inbound trigger mail (verified post OAuth-fix)

| Field | Value |
|-------|-------|
| scenario_id | `PTB-DCQ-0000` |
| recipient_redacted | `ni…@sol-f.se` |
| sender_redacted | `qv…@gmail.com` |
| subject | `KROWOLF-EVAL/0a307286-41d7-4b98-8d8b-32b120618210/PTB-DCQ-0000/1 \| Offert solceller Uppsala` |
| sender_message_id_redacted | `19fc…0b09` |
| recipient_message_id_redacted | `19fc…2713` |
| sent_at | `2026-08-03T20:53:14Z` (Mon, 3 Aug 2026 13:53:14 -0700) |
| trigger_body_hash | `2ed7d1f0d03cbab262a9443ed9666938596d6a3076ac7c28a06e31cbb88d000a` |
| scenario_input_body_hash | `62a00ea8e88969d6d5491a0711aec27a2adaa59823456070e1b14c31af4be101` |
| in_recipient_inbox_after_oauth_fix | **yes** |

Trigger body hash is the synthetic inbound scenario text, **not** any of the eight approved frozen reply body hashes.

## Internal artifacts (attempt 2)

| Artifact | Created | Details |
|----------|---------|---------|
| live-eval run registration | **yes** | `0a307286-41d7-4b98-8d8b-32b120618210`, status=`registered` |
| run events | **no** | 0 events recorded |
| job | **no** | intake never completed |
| approval operation | **no** | pipeline never reached approval |
| execution intent | **no** | |
| reply operation | **no** | |
| Gmail reply send | **no** | `successful_sends=0` |
| Gmail draft | **no** | |
| registry external writes | **no** | sheets/monday/visma = 0 |

## Stop reason

1. `POST /admin/live-eval/runs` → **200 OK**
2. `send_scenario_email` → **inbound trigger sent** (sender OAuth OK)
3. `GET /admin/live-eval/runs/{id}/delivery` → **HTTP 500**
4. Root cause at time of attempt: recipient Gmail OAuth **401** on `list_labels` (`CREDENTIALS_MISSING`)
5. Runner mislabeled failure as `live_run_registration` (corrected in follow-up PR to `delivery_observation`)

Recipient OAuth verified live read-only **after operator token renewal** (2026-08-03): token refresh PASS, list_labels PASS, read query PASS.

## Execution counters (actual)

| Metric | Expected | Actual |
|--------|----------|--------|
| successful approved replies | 8 | **0** |
| inbound triggers sent | 0 | **1** (orphan — not counted as reply) |
| no_send_verified | 7 | **0** |
| failed_sends | 0 | **1** |
| unknown_outcomes | 0 | **0** |
| duplicates_blocked | 0 | **0** |
| Gmail drafts | 0 | **0** |

## Orphan trigger handling

- orphan_id: `orphaned_attempt_2`
- **Do not reuse** campaign_id `e7876c9b-…`, evaluation_run_id `0a307286-…`, or operation IDs from this attempt
- **Do not** auto-reply to the orphan trigger
- Excluded from next 8/8 approved-reply count
- Archive/delete only per existing eval cleanup policy (not performed in this reconciliation)

## Scenarios processed

| scenario_id | planned_gmail_send | status | notes |
|-------------|-------------------|--------|-------|
| PTB-DCQ-0000 | yes | **failed** | `delivery_observation` after orphan trigger |
| PTB-DCQ-0022 … PTB-SEM-0024 | — | **not started** | stop-on-first-error |

## Gate status

- R3_LIVE_CANARY: **PENDING** (STOPPED — not PASS)
- R4_LIVE_CAMPAIGN: **PENDING**
- R5_CLOSURE: **PENDING**
- PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED: **PENDING**
