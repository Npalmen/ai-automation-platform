# R3 live canary result (Gate R3)

Redacted formal record of the qualifying R3 frozen live canary. Local operator artifacts under `storage/status/` remain uncommitted.

## Gate status

| Gate | Status |
|------|--------|
| `R3_LIVE_CANARY` | **PASS** |
| `R4_LIVE_CAMPAIGN` | PENDING |
| `R5_CLOSURE` | PENDING |
| `PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED` | PENDING |

## Qualifying run

| Field | Value |
|------|--------|
| Qualifying SHA | `5e9b1839d9a4ac5ac6aef1795d88a2eff5f06517` |
| Campaign ID | `54f2f10b-4f09-4ae4-9950-39bd2efb1214` |
| Attempt | 8 |
| Tenant | `TENANT_LIVE_EVAL` |
| Campaign type | `coworker_r3_frozen_live_canary` |
| Execution mode | `r3_frozen_approved_body` |
| Reply provider | `live_eval_recipient_env` / `google_mail` |
| Tenant Gmail fallback | false |
| Stub fallback | false |
| Manifest path | `storage/status/digital-coworker-r3-canary-manifest-5e9b183.json` |
| Manifest hash | `dd87f9ce7676fb60b30e6a1651ae7db62aaafe04d7f2624ac80a5e1bcff16741` |

## Counts

| Metric | Result |
|--------|--------|
| Approved replies | 8/8 |
| No-send verified | 7/7 |
| Failures | 0 |
| Unknown outcomes | 0 |
| Duplicates | 0 |
| New Gmail drafts | 0 |
| Canonical body hashes | 8/8 MATCH |

## Exclusion

Attempts 1–7 are historical stopped/orphaned runs. Attempt 7 produced seven real Gmail replies that are permanent external side effects but are **excluded** from this PASS count and from any R4 reuse.

## Policy notes

- Automatic Gmail remains **false**.
- Production activation remains **false**.
- The R3-only `PTB-DCQ-0088` hold→pending materialization override must **not** be generalized into R4 or production policy.

## Next gate

R4 is a separate live coworker-quality campaign (`coworker_r4_live_quality_campaign` / `r4_reviewed_live_candidate`) and requires its own SHA-bound manifest, candidate package, human review, preflight, and dry-run before any manual execute approval.
