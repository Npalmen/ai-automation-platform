# Full-System Testbot — Campaign Report

**Last updated:** 2026-07-25  
**Campaign type:** `transport-smoke` (observe)  
**Workflow run:** `30176969268`  
**Deploy SHA:** `35d59a80a5938fc04a340f6b3c363b65ff86610c`  
**Overall status:** `failed` (3/5 scenarios passed)

---

## Campaign Summary

| Metric | Value |
|--------|-------|
| Gmail sends | 5 |
| Delivered | 5 |
| Scenarios passed | 3 |
| Scenarios failed | 2 |
| App Gmail replies | 0 |
| Approval resolutions | 0 |
| External writes | 0 |
| Safety violations | 0 |
| Cross-tenant | 0 |

---

## Per-Scenario Results

### TBS01_lead_observe — PASS

| Field | Value |
|-------|-------|
| Version | v1 |
| Correlation token (redacted) | `KROWOLF-EVAL/c5a81751…/TBS01_lead_observe/1` |
| Gmail transport | confirmed, label applied |
| Job ID | `c5a81751-db7b-47a1-8eb9-12ad516c5851` (eval run id) |
| Classification | `lead` (fixture) |
| Service profile | lead pipeline |
| Routing | approval-first |
| Job status | `awaiting_approval` |
| Approval status | pending |
| Needs-help | not triggered |
| Customer card | `NOT_IMPLEMENTED` |
| Safety invariants | PASS |
| Cleanup | deferred |

### TBS02_support_observe — PASS

| Field | Value |
|-------|-------|
| Version | v1 |
| Correlation token (redacted) | `KROWOLF-EVAL/4c805c07…/TBS02_support_observe/1` |
| Gmail transport | confirmed |
| Job ID | `68c205f7-894e-4184-9a17-c5ba506e9744` |
| Classification | `customer_inquiry` (confidence 0.88) |
| Service profile | support |
| Routing | approval-first |
| Job status | `awaiting_approval` |
| Approval status | pending |
| Needs-help | not triggered |
| Customer card | `NOT_IMPLEMENTED` |
| Safety invariants | PASS |
| Cleanup | deferred |

### TBS03_invoice_observe — FAIL (product finding)

| Field | Value |
|-------|-------|
| Version | v1 |
| Correlation token (redacted) | `KROWOLF-EVAL/d17eec08…/TBS03_invoice_observe/1` |
| Gmail transport | confirmed |
| Job ID | `4a438c7f-b733-46c0-9771-fc48cf3977e5` |
| Classification | `invoice` (confidence 0.9) ✅ |
| Service profile | accounting |
| Routing | `hold_for_review` → `manual_review` ❌ |
| Job status | `manual_review` (expected `awaiting_approval`) |
| Approval status | none (expected pending) |
| Needs-help | not triggered |
| Customer card | `NOT_IMPLEMENTED` |
| Safety invariants | PASS |
| Cleanup | not run |
| Finding | `unexpected_terminal_status` — invoice observe path does not create approval queue entry |

### TBS04_unknown_observe — FAIL (product finding)

| Field | Value |
|-------|-------|
| Version | v1 |
| Correlation token (redacted) | `KROWOLF-EVAL/72d23eb0…/TBS04_unknown_observe/1` |
| Gmail transport | confirmed |
| Job ID | `70d791d6-b5c7-4ee6-a009-4b1c7ccbd342` |
| Classification | `unknown` (confidence 0.5) ✅ |
| Service profile | n/a |
| Routing | `hold_for_review` → `manual_review` ❌ |
| Job status | `manual_review` (expected `awaiting_approval`) |
| Approval status | none |
| Needs-help | not triggered |
| Customer card | `NOT_IMPLEMENTED` |
| Safety invariants | PASS |
| Cleanup | not run |
| Finding | `unexpected_terminal_status` — unknown observe path routes to manual review without approval |

### TBS05_noisy_observe — PASS

| Field | Value |
|-------|-------|
| Version | v1 |
| Correlation token (redacted) | `KROWOLF-EVAL/429e7d7b…/TBS05_noisy_observe/1` |
| Gmail transport | confirmed |
| Job ID | `c2a9034e-0a52-42c3-b350-b1c3e97a5336` |
| Classification | `lead` (confidence 0.75, multi-intent noisy) |
| Service profile | lead pipeline |
| Routing | approval-first |
| Job status | `awaiting_approval` |
| Approval status | pending |
| Needs-help | not triggered |
| Customer card | `NOT_IMPLEMENTED` |
| Safety invariants | PASS |
| Cleanup | deferred |

---

## Closure

| Gate | Status |
|------|--------|
| Safety invariants | ✅ PASS |
| 5/5 entydiga resultat | ❌ FAIL (3/5) |
| `testbot-c-observe-campaign` | **NOT completed** |

```
OPERATOR ACTION REQUIRED — Auktorisera semi-automatisk testkampanj
```

**Recommendation:** `NO_GO_FOR_SEMI_AUTOMATIC`

Rationale: invoice and unknown job types do not follow the approval-first observe path observed for lead/customer_inquiry. Semi-auto campaign would exercise approval resolution on scenarios that may not reach the approval queue consistently.
