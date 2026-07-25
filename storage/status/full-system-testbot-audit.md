# Full-System Testbot — Current-Truth Audit

**Todo:** `testbot-a-current-truth`  
**Generated:** 2026-07-25  
**Plan version:** `full-system-testbot-campaign-v1`

---

## SHA Baseline

| Reference | SHA | Notes |
|-----------|-----|-------|
| `origin/main` | `d97f1f9420128f3e1379a2ebd7bd7a4241fa4621` | Includes internal pilot gates (PR #38) |
| Production server (`api.krowolf.se`) | `b196132ff683ffeed577540d648072787c372776` | **Behind main** — campaign code not deployed |

---

## Gate Verdict

**PROCEED** — Testbot can be extended without weakening tenant isolation, approval-first, action authorization, idempotency, or 2E–2G baseline. Campaign layer is additive on top of closed 2F foundation.

---

## Existing Testbot Capabilities (2F)

| Component | Status | Location |
|-----------|--------|----------|
| Live eval registry (`live_eval_runs`) | Implemented | `app/evaluation/live/registry.py` |
| Gmail transport (send/reconcile) | Implemented | `app/evaluation/live/gmail_transport.py` |
| Correlation token (`KROWOLF-EVAL/...`) | Implemented | `app/evaluation/live/subject_parser.py` |
| Journal + resume + reconcile | Implemented | `app/evaluation/live/journal.py` |
| Write policy (reply-only) | Implemented | `app/evaluation/live/write_policy.py` |
| Live LLM S01 (fixture_input) | Closed | `app/evaluation/live/llm_operations.py` |
| 2G hermetic generator (160 scenarios) | Closed | `app/evaluation/generation/` |
| CLI `run_live_eval.py` | Implemented | `scripts/run_live_eval.py` |

**2F.2 locked scope:** Single scenario `S01_lead_laddbox_quality`, budgets send=1/reply=0.

---

## Mode Support Matrix (Pre-Implementation Audit)

| Mode | Pre-B Status | Post-B Status |
|------|-------------|---------------|
| `observe` | Partial (S01 only) | **Registry + 5 transport-smoke scenarios** |
| `semi_automatic` | Policy exists, no campaign | **Gates defined; scenarios pending (todo C/D)** |
| `automatic` | Policy exists, blocked in pilot | **Gates defined; scenarios pending (todo E)** |
| `customer_card_stateful` | **NOT_IMPLEMENTED** | Documented gap; no CRM model |
| `integration_sandbox` | Adapters exist, no live eval writes | **Gates defined; scenarios pending (todo G)** |
| `full_regression` | 2G hermetic only | **Campaign type defined; wiring pending (todo H)** |

---

## Customer Card Status

**NOT_IMPLEMENTED** as dedicated product feature.

- No `customer_card` model in `app/repositories/`
- Customer identity is job-derived (`customer_name`, `customer_email` in job input/entities)
- Operator tenant UI exists (`CustomerDetailPage`, `CustomerLifecyclePanel`) — tenant admin, not end-customer CRM
- Todo F must document gap and not smuggle CRM into testbot campaign

---

## Integration Matrix

| Integration | Adapter | Live Eval Write | Test Resource |
|-------------|---------|-----------------|---------------|
| Gmail | `mail_client.py` | Reply-only allowlisted | `TENANT_LIVE_EVAL` + `krowolf-live-eval` label |
| Google Sheets | `sheets_client.py` | Blocked | Not configured |
| Monday | `monday/adapter.py` | Blocked | Not configured |
| Visma | `visma/adapter.py` | Blocked | Sandbox scripts exist, not wired to testbot |

---

## Tenant Isolation

| Tenant | Purpose | Testbot Allowed |
|--------|---------|-----------------|
| `TENANT_LIVE_EVAL` | Dedicated live eval | **Yes** |
| `T_NIKLAS_DEMO_001` | Internal pilot | **No** — blocked by campaign gates |

---

## Automation Modes (Product)

| Mode | `tenant_automation.py` | Internal Pilot | Campaign |
|------|------------------------|----------------|----------|
| `manual` / approval_required | Yes | Default | Observe default |
| `semi` | Maps to approval_required | Allowed | Todo D |
| `auto` / full_auto | Yes | **Blocked** | Todo E (allowlisted only) |

---

## Missing Security Gates (Pre-B)

1. No campaign scenario registry — **FIXED in B**
2. No multi-scenario Gmail allowlist — **FIXED in B**
3. No `FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED` gate — **FIXED in B**
4. No production-resource check for campaigns — **FIXED in B**
5. No synthetic scenario generator for Gmail — **FIXED in B**
6. Semi-auto operator actor — **Pending (todo D)**
7. Integration sandbox allowlists — **Pending (todo G)**

---

## File Scope for B–H

### B (this slice)
- `app/evaluation/live/campaign/*`
- `app/evaluation/live/resources/campaign/*`
- `scripts/full_system_testbot_readiness.py`
- `scripts/run_full_system_testbot_campaign.py`
- `tests/evaluation/live/test_campaign_*.py`
- Minor extensions: `safety.py`, `gmail_transport.py`, `runner.py`

### C–H (future)
- Campaign runner orchestration (multi-scenario send loop)
- Testbot approval actor (semi-auto)
- Integration sandbox scenarios + allowlists
- Customer card audit + stateful families
- Continuous regression workflow

---

## Manual Steps Required

1. Deploy `d97f1f9`+ (with campaign code) to isolated test host
2. Configure `TENANT_LIVE_EVAL` OAuth (sender + recipient)
3. Set env fingerprint (see execution report)
4. Operator approval before first Gmail send
