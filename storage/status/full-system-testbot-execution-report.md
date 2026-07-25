# Full-System Testbot — Execution Report

**Last updated:** 2026-07-25  
**Phase:** C executed — **gates NOT passed (3/5 scenarios)**

---

## Status

```
OPERATOR ACTION REQUIRED — Auktorisera semi-automatisk testkampanj
```

Observe-kampanjen kördes i isolerad `live-gmail-eval`-miljö. Säkerhetsinvariants passerade. Produktgate **5/5 entydiga resultat** misslyckades (3/5).

**Rekommendation:** `NO_GO_FOR_SEMI_AUTOMATIC`

---

## SHA Verification

| Reference | Full SHA | Verified |
|-----------|----------|----------|
| Operator-authorized base (`4402eae`) | `4402eae7da8db1670c0d8dd15b9ff327777dd7a2` | ✅ ancestor of `origin/main` |
| Release Gate `30174539095` | head `4402eae7da8db1670c0d8dd15b9ff327777dd7a2` | ✅ success |
| Campaign deploy (workflow) | `35d59a80a5938fc04a340f6b3c363b65ff86610c` | ✅ includes base + observe runner + CLI fix (PR #42) |
| Production server (`api.krowolf.se`) | `b196132ff683ffeed577540d648072787c372776` | **NOT deployed to** |

---

## Isolated Environment

| Item | Value |
|------|-------|
| Host | GitHub Actions `live-gmail-eval` environment (ephemeral CI runner + local Postgres) |
| App URL | `http://127.0.0.1:8010` (not production) |
| `ENV` | `test` |
| Tenant | `TENANT_LIVE_EVAL` |
| Label | `krowolf-live-eval` |
| Sender fingerprint | `6b7a900e01ae` (from S01 baseline) |
| Recipient fingerprint | `32b8ba3bb1e7` (from S01 baseline) |
| Scheduler | not active (ephemeral CI) |
| Production resources | none configured |

No separate SSH test host exists. Production `/opt/krowolf` was **not** used.

---

## Workflow Runs (Phase C)

| Run | SHA | Result | Notes |
|-----|-----|--------|-------|
| `30175762348` | `05b5410` | **failed** | CLI argparse bug (`--tenant-id` not on subparser) |
| `30176969268` | `35d59a8` | **failed** | Campaign executed; 3/5 scenarios passed |

Fix: PR #42 merged — `run_full_system_testbot_campaign.py` subparser args.

---

## Readiness (Run `30176969268`)

| Check | Result |
|-------|--------|
| `FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED` | ✅ yes |
| Tenant | ✅ `TENANT_LIVE_EVAL` |
| Sender/recipient allowlist | ✅ exactly 1 each |
| Label | ✅ `krowolf-live-eval` |
| Gmail reply budget | ✅ 0 |
| External write budget | ✅ 0 |
| `/health` | ✅ HTTP 200 |
| Runtime SHA | ✅ matches deploy SHA |
| Production resource gate | ✅ PASS |
| Rollback command | ✅ documented (not exercised) |

Note: per-run env budget `LIVE_EVAL_MAX_GMAIL_SENDS=1` (5 sequential single-send runs). Total campaign sends = 5.

---

## Campaign Safety Invariants (Absolute Gates)

| Gate | Required | Actual | Status |
|------|----------|--------|--------|
| Testbot Gmail sends | 5 | 5 | ✅ |
| Delivered scenarios | 5 | 5 | ✅ |
| App Gmail replies | 0 | 0 | ✅ |
| Approval resolutions | 0 | 0 | ✅ |
| External writes | 0 | 0 | ✅ |
| Cross-tenant findings | 0 | 0 | ✅ |
| Duplicate executions | 0 | 0 | ✅ |
| Label/scope violations | 0 | 0 | ✅ |
| Budget violations | 0 | 0 | ✅ |
| Production resource writes | 0 | 0 | ✅ |
| Entydigt resultat (5/5) | 5 | 3 | ❌ |

---

## Todo Status

| Todo | Status |
|------|--------|
| `testbot-a-current-truth` | **completed** |
| `testbot-b-isolated-environment` | **completed** |
| `testbot-c-observe-campaign` | **NOT completed** — safety PASS, product gate 3/5 |
| `testbot-d-semi-automatic-campaign` | blocked — operator approval required |
| `testbot-e-automatic-campaign` | blocked |
| `testbot-f-customer-card-stateful` | blocked |
| `testbot-g-full-function-matrix` | blocked |
| `testbot-h-continuous-regression` | blocked |

---

## Product Findings (Non-Blocking per Plan)

1. **TBS03_invoice_observe** — classification `invoice` (0.9) correct; job routed to `manual_review` / `hold_for_review` instead of expected `awaiting_approval` with pending approval.
2. **TBS04_unknown_observe** — classification `unknown` (0.5) correct; same `manual_review` routing mismatch.

Root cause hypothesis: invoice and unknown job types use `hold_for_review` policy path instead of approval-first observe path used by lead/customer_inquiry.

---

## Rollback

Not required (safety invariants held). Documented rollback for production host:

```bash
cd /opt/krowolf && git checkout b196132 && docker compose up -d --build
```

CI environment is ephemeral — no persistent rollback needed.

---

## Next Step

```
OPERATOR ACTION REQUIRED — Auktorisera semi-automatisk testkampanj
```

Do **not** proceed to `testbot-d-semi-automatic-campaign` until operator reviews findings and explicitly authorizes semi-auto campaign.

Recommendation: **`NO_GO_FOR_SEMI_AUTOMATIC`** until invoice/unknown observe routing is aligned with approval-first expectations or assertions are updated to match intended product behavior.
