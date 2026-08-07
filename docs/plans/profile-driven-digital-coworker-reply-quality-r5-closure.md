---
title: Profile-Driven Digital Coworker Reply Quality — R5 Closure
slug: profile-driven-digital-coworker-reply-quality-r5-closure
status: approved
created: 2026-08-08
parent_plan: docs/plans/profile-driven-digital-coworker-reply-quality-plan.md
trigger: R4_LIVE_CAMPAIGN_PASS
qualification_target: PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED
candidate_runtime_sha: b7fd95e075c16feee93a116a6062e402c1fee3df
executor_runtime_sha: 4ad74d4ac19011d5edfb8ea160112f649052422d
r4_pass_campaign_id: b4dcd6a8-9bda-4ce4-8b63-4e7a54176605
qualifying_source_sha: 4ad74d4ac19011d5edfb8ea160112f649052422d
qualifying_source_workflow_run: "31220948265"
automatic_gmail_activation: false
production_activation: false
external_writes_allowed: false
todos:
  A: pending
  B: pending
  C: pending
  D: pending
  E: pending
---

# Objective

Close the profile-driven digital coworker reply-quality chapter (Todo J) by registering `PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED = VALID` from frozen R1–R4 evidence. R5 is **write-free**: no Gmail, LLM, candidate regeneration, or production activation.

## Verified R4 baseline (Attempt 12 only)

| Binding | Value |
|---------|-------|
| Campaign UUID | `b4dcd6a8-9bda-4ce4-8b63-4e7a54176605` |
| Candidate runtime SHA | `b7fd95e075c16feee93a116a6062e402c1fee3df` |
| Executor runtime SHA | `4ad74d4ac19011d5edfb8ea160112f649052422d` |
| Manifest semantic hash | `bdebc3ce422aee302fdafad748e3e9b93a3deda8effe5deb90b49853e09144f5` |
| Candidate package hash | `6e6c37aaa57df1464fbc367701c0cfbfaf500f697ffae5cec3a50d2dda116254` |
| Human review SHA256 | `7dced592907fb6fcbb89e632f1e37246cd120ace2a453e0aaa198397f5f0b57b` |

Evidence:

- `storage/status/digital-coworker-r4-attempt12-pass-record-4ad74d4.json`
- `storage/status/digital-coworker-r4-live-execution-4ad74d4.json`
- `storage/status/digital-coworker-r4-reconciliation-4ad74d4.json`

Attempts 1–11 are permanently quarantined and excluded from R4 PASS.

## Canonical qualification provenance (locked)

Registry entry `PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED` binds to the **runtime that qualified R4 Attempt 12**, not the closure PR merge SHA:

```yaml
status: VALID
source_sha: 4ad74d4ac19011d5edfb8ea160112f649052422d
source_workflow_run: "31220948265"
```

Release Gate run `31220948265` (verified: name=Release Gate, conclusion=success, head_sha=`4ad74d4…`) is the qualifying CI evidence for executor `4ad74d4`.

The closure PR's own merge SHA and post-merge Release Gate / Regression Main runs are **R5 closure/postmerge evidence only** — they do not replace registry provenance.

## Canonical architecture (reuse only)

| Concern | Path |
|---------|------|
| Qualification registry | `app/evaluation/regression/qualification_registry.yaml` |
| Registry loader | `app/evaluation/regression/qualification_registry.py` |
| R1 hermetic | `app/evaluation/profile_testbot/qualification/hermetic_coworker_reply.py` |
| R2 human review | `storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json` |
| R3 live canary | `docs/reply-quality/r3-live-canary-result.md`, `coworker_r4_registry.py` R3 constants |
| R4 registry / hashes | `app/evaluation/profile_testbot/qualification/coworker_r4_registry.py` |
| Quarantine | `coworker_r4_attempt1_orphan.py`, `digital-coworker-r4-attempt{N}-orphan-registry.json` |
| Postmerge pattern | `storage/status/_r4_*_postmerge_verify.py` |

# Todo A — Freeze and verify final evidence

1. Inventory canonical R1–R4 evidence paths (no parallel registry).
2. Implement `coworker_reply_quality_closure.py` with `evaluate_r5_closure_evidence()`.
3. Bind R2 from scored human-review artifact (`human_review_complete`, 0 FAIL, 0 PENDING, locked SHA256).
4. Bind R3 from `r3-live-canary-result.md` + `R3_QUALIFYING_SHA` / `R3_QUALIFYING_CAMPAIGN_ID`.
5. Bind R4 from Attempt 12 pass-record + execution report cross-check.
6. Verify Attempts 1–11 quarantine; PASS campaign not in quarantine set.
7. Write `storage/status/r5-closure-evidence-freeze-4ad74d4.json`.

Fail closed on missing, contradictory, or ambiguous provenance.

# Todo B — Qualification registry

Update `qualification_registry.yaml` only after Todo A PASS:

- `PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED` → `VALID`
- `source_sha: 4ad74d4ac19011d5edfb8ea160112f649052422d`
- `source_workflow_run: "31220948265"`
- Keep `PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED` and `PROFILE_DRIVEN_TESTBOT_PASS` as `PENDING`
- `default_production_activation: false`

Does not enable runtime features or automatic Gmail.

# Todo C — Parent plan and closure documentation

Update parent plan gates to canonical end state (R1–R5 PASS, Todo I/J completed, registry VALID). Correct stale `R2_PRECHECK: FAIL` / `R2_HUMAN_REVIEW: PENDING` only when R2 canonical evidence (scored human review) entitles PASS.

Update: `docs/01-current-truth.md`, `docs/07-decisions.md`, reply-quality docs as needed (create `known-limitations.md` only if missing).

# Todo D — Focused closure tests

`tests/test_coworker_reply_quality_r5_closure.py`:

1. Valid evidence → PASS
2. Missing R4 PASS → blocked
3. Wrong campaign → blocked
4. Quarantined campaign as PASS → blocked
5. Hash mismatch → blocked
6. Idempotent re-evaluation
7. Conflicting registry → fail-closed
8. automatic_gmail / production_activation remain false
9. No external writes in closure path

# Todo E — PR, CI, merge, post-merge closure

Branch: `release/digital-coworker-reply-quality-r5-closure`

1. Focused tests PASS
2. Mandatory CI PASS
3. Merge
4. Post-merge Release Gate PASS
5. Regression Main PASS
6. Write-free `_r5_closure_postmerge_verify.py` on closure merge SHA (documents closure evidence separately from registry provenance)

# Stop-gates

STOP if:

- Attempt 12 evidence cannot be verified
- Campaign / SHA / hash mismatch
- Attempts 1–11 can qualify
- R1–R4 cannot bind uniquely
- R2 status ambiguous
- Registry conflict
- automatic Gmail or production activation would become true
- Closure requires Gmail/LLM/external writes
- CI / Release Gate / Regression Main fails

# Definition of done

`PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED — R1–R5 complete; R4 live campaign PASS; qualification registered with locked provenance; automatic Gmail remains false; production activation remains false`
