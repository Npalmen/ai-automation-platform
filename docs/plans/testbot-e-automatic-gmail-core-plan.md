---
name: Testbot E automatic Gmail core
overview: Kvalificera Phase 1 automatic Gmail safe-actions över en fast matris med tre låg-risk-svar och fem fail-closed hold-scenarier
todos:
  - id: auto-core-a-contract
    content: Definiera automatic Gmail core-manifest och åtta scenariokontrakt
    status: completed
  - id: auto-core-b-harness
    content: Implementera campaign type, registry, fixture bundles och runner-wiring
    status: completed
  - id: auto-core-c-readiness
    content: Implementera budget-, scope-, fixture- och tenantautomation-readiness
    status: completed
  - id: auto-core-d-tests
    content: Implementera hermetiska och PostgreSQL-baserade tester
    status: completed
  - id: auto-core-e-delivery
    content: Kör regressioner, PR, squash-merge och post-merge Release Gate
    status: completed
  - id: auto-core-f-live
    content: Kör exakt en åttascenario automatic Gmail core-kampanj
    status: completed
  - id: auto-core-g-closure
    content: Bedöm testbot E closure och stoppa före nästa testbotkapitel
    status: completed
isProject: true
---

# Testbot E2 — Automatic Gmail core campaign

Plan technical content is **read-only** after approval; only todo status may change (`pending → in_progress → completed`).

**Scope:** E2 breadth qualification only. **Not** full multi-integration automatic campaign.

**Branch:** `feat/testbot-e-automatic-gmail-core`

## Verified baseline (E1)

| Item | Value |
|------|-------|
| E1 status | `AUTOMATIC_GMAIL_CANARY_QUALIFIED` |
| E1 PR | #93 @ `13e2338` |
| E1 run | `30435651905` — 2/2 PASS |
| testbot C/D | `completed` |
| testbot E | `in_progress` |

## Bindande korrigeringar (operator)

### 1. Pre-write reply safety (obligatorisk)

Produktkedja:

```text
classification → decision/risk → reply candidate → structured pre-write safety gate
→ tenant automation policy → authorization → execution intent → dispatch
→ Gmail adapter → post-write content verification
```

Pre-write gate blocks before external write on forbidden content (price, booking, guarantees, legal/economic commitments, etc.). On failure: no `auto_execute`, 0 intents, 0 adapter calls, 0 replies, hold/manual review, structured reason code. Post-write verifies sent content matches safety-approved candidate.

Implementation: general `reply_candidate_safety` action-safety boundary — no scenario-ID special cases.

### 2. Auto_execute ≠ job_type alone

`lead=auto` / `customer_inquiry=auto` is eligibility only. Full auto-execution requires: action type allowlist, tenant rule, low decision/risk, no restricted intents, reply safety PASS, recipient allowlist, budget, idempotency.

TBA06 (customer_inquiry + complaint risk) and TBA07 (lead + price/booking) are mandatory contrast tests proving same classification can yield different authorization.

### 3. Fail-fast and cleanup

On first critical scenario failure: stop remaining sends, pause automation, restore config, verify hash match, no stale intents/adapter/replies. Report executed/skipped scenarios and all possible writes.

### 4. Campaign membership

TBA01/TBA02 belong to both `automatic-gmail-canary` and `automatic-gmail-core`. Authoritative multi-value membership in registry; budget, readiness, reporting use same source.

### 5. Live authorization gates

No live run until tests prove: pre-write safety before adapter, TBA06/TBA07 holds, unsafe candidate = 0 writes, fail-fast stop, cleanup after safety failure, E1 compatibility, Release Gate PASS.

## Campaign type

| Field | Value |
|-------|-------|
| type | `automatic-gmail-core` |
| confirmation | `RUN_AUTOMATIC_GMAIL_CORE` |
| scenarios | TBA01–TBA08 (8) |
| budget | 8 sends / 3 replies / 0 non-Gmail writes |

## Scenario matrix

| ID | Variant | Replies |
|----|---------|--------:|
| TBA01 | safe lead ack | 1 |
| TBA02 | unknown hold | 0 |
| TBA03 | safe general inquiry ack | 1 |
| TBA04 | noisy safe lead ack | 1 |
| TBA05 | invoice hold | 0 |
| TBA06 | support/complaint hold | 0 |
| TBA07 | price/booking/commitment hold | 0 |
| TBA08 | sensitive/safety hold | 0 |

## Closure (full 8/8 PASS only)

Mark `testbot-e-automatic-campaign` = `completed`. Register `AUTOMATIC_GMAIL_CORE_QUALIFIED`.

**Qualified:** Phase 1 automatic Gmail safe acknowledgements; allowlisted live-eval tenant; low-risk pre-write-safety-approved cases.

**Not qualified:** real customer rollout; broader tenant scope; Sheets/Monday/Visma; pricing/booking/commitments; economic/legal/technical decisions.

Stop: `OPERATOR ACTION REQUIRED — Starta testbot F customer-card stateful evaluation`
