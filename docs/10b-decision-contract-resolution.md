# Kapitel 2B — Decision Contract & Action Authorization Resolution

> **Status:** Implemented (local) — 2026-07-20  
> **Baseline audit:** `docs/10a-core-intelligence-audit.md`  
> **Locked decision:** `docs/07-decisions.md` DEC-033

---

## Problem statement (from 2A)

The AI decisioning layer emitted `auto_route` / `manual_review` / `hold`, while policy read legacy authorization tokens (`auto_execute` / `send_for_approval`) and defaulted to `auto_execute` when values did not match. External writes (email, Monday, Slack) could bypass per-action approval depending on builder path and injected `input_data.actions`.

---

## Resolution summary

| Layer | Internal truth | Backward-compatible projection |
|-------|----------------|--------------------------------|
| AI decisioning | `decisioning_recommendation` (`auto_route`, `manual_review`, `hold`) | `decision` field in decisioning payload (unchanged AI schema) |
| Policy | `policy_authorization` (`hold_for_review`, `approval_required`, `execution_allowed`, `no_action`) | `decision` (`hold_for_review`, `send_for_approval`, `auto_execute`) |
| Action dispatch | `_authorization` per action + `_needs_approval` when gated | Existing approval records (`next_on_approve: action_execute`) |

---

## Legacy normalization (fail-closed)

`auto_execute` and `send_for_approval` in the **decisioning** payload are legacy authorization tokens on the wrong layer. They normalize to `manual_review` and never grant `execution_allowed` on their own.

Historical values may be read for display/analysis but do not grant active authorization without fresh policy evaluation against tenant automation mode.

**Regression:** `tests/test_decision_contract.py::TestLegacyNormalization::test_auto_execute_never_grants_execution_allowed`

---

## Policy resolver (single exit, risk first)

`resolve_policy_authorization()` in `app/workflows/decision_contract.py` is the single resolver:

1. **Content risk** → `hold_for_review` (cannot be bypassed)
2. Invoice-specific rules
3. Unknown job type → `hold_for_review`
4. `force_approval_test` → `approval_required` (only when `ALLOW_FORCE_APPROVAL_TEST=True`)
5. Fallback / low confidence / missing recommendation → `hold_for_review`
6. `manual_review` / `hold` → `hold_for_review`
7. `auto_route` + tenant `full_auto` → `execution_allowed`
8. `auto_route` + non-full_auto → `approval_required`

`force_approval_test` in job `input_data` is stripped at job creation when the server flag is false.

**Regression:** `tests/test_decision_contract.py::TestRiskPrecedence::test_risk_blocks_force_approval_test`

---

## Tenant automation mode (central)

`app/workflows/tenant_automation.py` is the authoritative normalizer:

- `normalize_automation_mode()` — bool/string → `manual` | `semi` | `full_auto`
- `resolve_automation_mode()` — per job type from `auto_actions`
- `allows_direct_external_execution()` / `requires_action_approval()`

No parallel bool/string logic in processors.

---

## Action authorization (dispatch boundary)

All executable actions pass through `_apply_dispatch_authorization()` in `action_dispatch_processor`, regardless of source (builder, `input_data.actions`, replay, approval resume).

Central registry: `app/workflows/action_authorization.py` (`ACTION_REGISTRY`).

| Action type | Effect | Integration |
|-------------|--------|-------------|
| `send_customer_auto_reply` | external_write | google_mail |
| `send_internal_handoff` | external_write | google_mail |
| `send_email` | external_write | google_mail |
| `create_monday_item` | external_write | monday |
| `notify_slack` | external_write | slack |
| `notify_teams` | internal_stub | teams |
| `create_internal_task` | internal_record | — |

Unknown or unsupported action types → `_skip` with `_skip_reason: action_blocked`.

---

## Per-action approval

External writes that require approval get a separate approval record via `_create_action_approval_record()` with `next_on_approve: action_execute`. Each approval authorizes only its `delivery_payload` action.

Resume/approve is idempotent: `_resolve_email_approval()` returns early when approval is already `approved` or `rejected` without re-executing.

**Regressions:**

- `tests/test_action_dispatch_authorization_boundary.py`
- `tests/test_email_approval.py::TestResolveEmailApproval::test_double_approve_is_idempotent`

---

## Targeted test plan (2B)

| Scenario | Test location |
|----------|---------------|
| Legacy `auto_execute` fail-closed | `test_decision_contract.py` |
| Risk cannot be bypassed by `force_approval_test` | `test_decision_contract.py` |
| Injected known external-write requires authorization | `test_action_dispatch_authorization_boundary.py` |
| Injected unknown action blocked | `test_action_dispatch_authorization_boundary.py` |
| Multi-action job → separate approvals | `test_action_dispatch_authorization_boundary.py` |
| Approval resume executes only selected action | `test_email_approval.py` |
| Double resume/retry idempotent | `test_email_approval.py` |
| `notify_slack` and all actions classified | `test_action_authorization.py` |
| Policy processor contract | `test_mvp_flow.py::TestPolicyProcessor` |
| Email gate at dispatch boundary | `test_email_approval.py` |
| Sensitive/risk policy routing | `test_core_intelligence_quality.py` |

**Last run (local):** 125+ tests in 2B bundle — all passed.

---

## Out of scope (unchanged in 2B)

- Invoice export / Fortnox / Visma finance approval paths
- DecisionRecord persistence (Kapitel 2C)
- Gmail live soak / production deployment

---

## GO / NO-GO after 2B

| Gate | Status |
|------|--------|
| Decision contract locked | ✅ Local implementation + regression |
| Action dispatch boundary | ✅ |
| Kapitel 2C DecisionRecord | **CONDITIONAL GO** — proceed with harness design |
| Execution-dependent Fas 2 live flows | **CONDITIONAL GO** — after broader CI run on merge branch |
