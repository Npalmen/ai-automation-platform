# AI Receptionist — MVP Gate Results

> Companion results document to `docs/ai-receptionist-mvp-gate.md`.
> Records the outcome of a readiness verification pass ahead of the first friend test.

---

## Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-07-15 (readiness pass) + 2026-07-15 (final live gate run — see "Live gate run" section) |
| Operator | Execution agent |
| Environment (readiness pass) | Local repository, no live server session |
| Environment (final live run) | Local dev server (`ENV=dev`) against existing local Postgres DB with real provisioned tenants. **Not** the production deployment (`api.krowolf.se`) — no production or live-Gmail credentials were available in this session; this is documented explicitly rather than fabricating a production run |
| Verification method | Static code inspection + existing automated test suite (3165 tests) for the readiness pass; live HTTP calls against a local server for the final run (tenant config, Gmail scan, daily summary) |
| Code changed | None in either pass |
| Tests run | None (no code changed; per execution rules, pytest is not required when only docs/results are updated) |
| Temporary helper scripts | 3 read-only one-off scripts were created to query the local DB and call HTTP endpoints (each compiled with `py_compile` before running); all were deleted immediately after use and are not part of the repository |

---

## Verification approach

Since no live server/Gmail/Sheets session was available in this pass, each area below was verified by:

1. Reading the governing docs (`ai-receptionist-mvp-gate.md`, `ai-receptionist-test-mail-scenarios.md`, `ai-receptionist-friend-test-guide.md`).
2. Tracing the actual code path for each behavior (pipeline orchestrator, processors, tenant config, action dispatch, approval service).
3. Cross-checking against the existing automated test suite status recorded in `docs/01-current-truth.md` (3165 passed, 0 failed, most recently after Sprint 5).
4. Flagging any place where the **default/live behavior differs from what the friend-test guide promises**, even if not literally a bug.

This is weaker evidence than a live gate run, so overall status is capped at **PASS WITH NOTES**, not a bare **GO**, until the live sections are executed once against the deployed test tenant.

---

## Results table

| Area | Status | Evidence |
|---|---|---|
| Gmail intake | PASS WITH NOTES | `app/main.py` `_run_gmail_inbox_sync` (dedup by `message_id`, thread continuation, tenant-gated job type). **Note:** default `query` is `is:unread` — scans the **whole inbox**, not just a test label, unless the operator explicitly passes `query=label:<test-label> is:unread`. Not a code bug, but a live-run precondition. |
| Classification | PASS | `classification_processor` → `policy_processor` reads `detected_job_type`; orchestrator branches lead / customer_inquiry / invoice / unknown correctly (`app/workflows/orchestrator.py`). Behavior covered by existing test suite (no code changed this sprint). |
| Lead handling | PASS | `lead_analyzer_processor` runs deterministic analysis → missing info → score → next action → offer draft, gated by service profile playbooks. Unaffected paths unchanged; Sprint 5 only touched `_infer_lead_status` and `OfferDraft` fields. |
| Missing info → waiting_for_customer | PASS | `_infer_lead_status("ask_questions", ...)` now returns `"waiting_for_customer"` (fixed in Sprint 5, verified by `test_infer_lead_status_ask_questions_returns_waiting_for_customer`). `generate_question_message` still produced when `completeness_score < 0.7`. |
| Quote draft preparation | PASS | `build_offer_draft()` only returns a draft when `completeness_score >= 0.7`; always sets `human_approval_required=True`; includes customer contact fields and `missing_fields`. `offer_draft` is never referenced by `action_dispatch_processor` — it cannot trigger an automatic customer-facing send. Verified by `test_offer_draft_includes_contact_and_approval_flag`, `test_offer_draft_none_when_incomplete`. |
| Invoice routing | PASS | `classify_invoice_routing()` is a pure, deterministic keyword classifier; output (`invoice_routing`, `risk_signals`, `routing_reason`) is informational only. The invoice pipeline branch (`ENTITY_EXTRACTION → INVOICE → POLICY → HUMAN_HANDOFF`) never reaches `ACTION_DISPATCH`, so no invoice routing recommendation can trigger an automatic action — it is recommendation-only by construction. Verified by 5 routing tests in `tests/test_sprint5_phase1_value.py`. |
| Risk handling | PASS | `policy_processor` forces `decision = hold_for_review`, `approval_route = manual_review` whenever `assess_content_risk()` detects risk, regardless of job type; this overrides any prior decision. `derive_job_status()` surfaces this as `risk_review_required`. Complaint/emergency override logic in `service_profiles/playbook.py` unchanged. |
| Approval-first behavior | PASS | `_email_needs_approval()` is fail-closed: only literal `True`, `"auto"`, or `"full_auto"` in tenant `auto_actions[job_type]` bypass approval; anything else (`None`, `False`, `"manual"`, `"semi"`) requires approval. Fresh tenants created via `POST /admin/tenants` or `POST /tenant` default `auto_actions={}` unless explicitly overridden in the request body — i.e. approval-required by default. `action_executor.py` has no Visma/Fortnox code paths at all, so no invoice/finance write can occur from the dispatch pipeline. |
| Daily summary endpoint | PASS WITH NOTES | `GET /reports/daily-summary` registered in `app/main.py`, tenant-scoped via `get_verified_tenant`, calls `generate_daily_report()` (read-only: `JobRepository.list_jobs` + `ApprovalRequestRepository.count_pending_for_tenant`, no writes). Verified via mocked unit test `test_daily_report_counts_and_rendered_text`. **Note:** not yet called against a live tenant with real job history in this pass — recommend one live smoke call before the friend test. |
| Tenant isolation / safety | PASS | `get_verified_tenant()` resolves tenant strictly from API key / admin+header / session, checks `status == "active"`; all job/approval queries in `JobRepository` / `ApprovalRequestRepository` filter by `tenant_id`. Integration allowlist (`allowed_integrations`) defaults to `[]` for new tenants — fail-closed. No code changed in this area during Sprint 5. |

---

## Section-by-section mapping to `docs/ai-receptionist-mvp-gate.md`

| Gate section | Verifiable now (static/tests) | Requires live run |
|---|---|---|
| A — Gmail ingestion | A4 (job type mapping logic) | A1, A2, A3, A5 (need live Gmail + real scan) |
| B — Playbook quality | Logic unchanged this sprint, covered by existing suite | Full scenario run against live tenant |
| C — Safety routing | Risk/complaint override logic traced in code | Live scenario 5 & 8 confirmation |
| D — Approval-first | D1–D5 logic traced (fail-closed `_email_needs_approval`) | D6 (live Gmail send — optional) |
| E — Sheets export | Not touched this sprint | Full section requires live Sheet |
| F — Tenant isolation | F1–F4 logic traced | Live cross-tenant HTTP check recommended |
| G — Allowlist enforcement | G1–G4 logic traced (empty allowlist by default, no Visma/Fortnox in executor) | Live confirmation of `/integration-events` |
| H — Observability | Not touched this sprint | Live log inspection |
| I — Phase 1 value layer | I1–I4, I6 fully verified via `tests/test_sprint5_phase1_value.py` (25/25 passed) | I5 (live call to `/reports/daily-summary`) |

---

## Concrete blockers tied to friend-test safety

1. **Gmail scan is not label-scoped by default.** `_run_gmail_inbox_sync` defaults to `query="is:unread"` (the entire unread inbox) unless the operator explicitly passes a label-scoped `query` (e.g. `label:krowolf-test is:unread`) in the `POST /gmail/process-inbox` request body. If the friend-test mailbox is a shared/production mailbox, running the default scan would process real, non-test mail.
   - **Not blocking code-wise** — the capability to scope by label exists.
   - **RESOLVED (docs-only, 2026-07-15):** this is now documented as a hard, explicit GO/NO-GO requirement in `docs/ai-receptionist-test-customer-onboarding.md` (top-of-file warning + Steps 5/6/7 + safety checklist + "What NOT to enable" table) and in `docs/ai-receptionist-mvp-gate.md` (prerequisite checklist item, Section A `A0` check, GO criteria, and NO-GO criteria). No code was changed — the underlying default query behavior in `_run_gmail_inbox_sync` is unchanged; the risk is mitigated by making the operational requirement explicit and unmissable before any friend-test Gmail scan.

2. **Live configuration has not been confirmed on an actual tenant in this session.** All "safe by default" claims above are code-level defaults. The specific friend-test tenant's live `auto_actions`, `scheduler.run_mode`, and `allowed_integrations` must still be confirmed via `GET /tenant/config/{tenant_id}` (or equivalent) before sending the first test email, per Step 4 of `docs/ai-receptionist-test-customer-onboarding.md`.

No other blockers found. No FAIL or NO-GO conditions were identified in code.

---

## Overall MVP gate status (superseded — see "Live gate run" above)

~~PASS WITH NOTES~~ — **updated after the 2026-07-15 live gate run to `BLOCKED`.** See below for the current, final status.

---

## Final MVP gate status (after live run, 2026-07-15)

**BLOCKED**

Rationale: the live run found one concrete, safety-relevant blocker (`T_KROWOLF_E2E_TEST` has `auto_actions.lead=true` and `auto_actions.customer_inquiry=true`, plus Monday/Fortnox/Visma enabled in `allowed_integrations`) and one environmental blocker (expired Gmail OAuth token preventing a full live Gmail scan). Neither requires a code fix — both are configuration/credential issues. The gate is `BLOCKED` specifically for `T_KROWOLF_E2E_TEST` and for live end-to-end Gmail scanning; it is **not** blocked for the underlying application code, which passed every check it could reach (approval-first logic, quote draft/invoice routing recommendation-only behavior, daily report, tenant isolation).

---

## Friend test: allowed or blocked (final decision)

**BLOCKED for `T_KROWOLF_E2E_TEST`. Allowed for `T_NIKLAS_DEMO_001`, conditional on reconnecting Gmail.**

| Condition | Status | Detail |
|---|---|---|
| `auto_actions=false`/`manual` for all job types | **FAIL for `T_KROWOLF_E2E_TEST`** (`lead=true`, `customer_inquiry=true`) / **PASS for `T_NIKLAS_DEMO_001`** (`manual`/`manual`) | Live-confirmed via `GET /tenant` on 2026-07-15 |
| `scheduler.run_mode=manual` | **PASS for both tenants** | Live-confirmed via `GET /dashboard/control` on 2026-07-15 |
| No Visma/Fortnox production writes | **PASS (code-level)** — but `T_KROWOLF_E2E_TEST`'s `allowed_integrations` includes `fortnox`/`visma`/`monday`, which is inconsistent with intended test-tenant scope even though the pipeline itself cannot write to them | Do not use `T_KROWOLF_E2E_TEST` until `allowed_integrations` is corrected |
| No customer-facing action without approval | **FAIL for `T_KROWOLF_E2E_TEST`** (auto_actions bypasses approval for lead/inquiry) / **PASS for `T_NIKLAS_DEMO_001`** | Direct consequence of the `auto_actions` finding above |
| Gmail scan is label-scoped | **Mechanism confirmed working; live execution BLOCKED** | Query `label:krowolf-test is:unread` was accepted and forwarded correctly; failed only due to expired Gmail OAuth token (503) |
| Quote drafts are approval-first | **PASS** | Verified in code + Sprint 5 tests; unaffected by tenant choice |
| Invoice routing is recommendation/approval-first | **PASS** | Verified in code + Sprint 5 tests; unaffected by tenant choice |
| Daily report works for the test tenant | **PASS — live HTTP 200 confirmed** for `T_NIKLAS_DEMO_001` on 2026-07-15 | See "Live gate run" section above |

**Decision:**
1. **Do not use `T_KROWOLF_E2E_TEST` for the friend test** until an operator explicitly corrects its `auto_actions` (set `lead` and `customer_inquiry` to `false`/`"manual"`) and removes `monday`/`fortnox`/`visma` from `allowed_integrations` via `PUT /tenant/config/{tenant_id}`, then re-confirms with `GET /tenant`.
2. **`T_NIKLAS_DEMO_001` passes every check that could be executed** and may be used for the friend test **once the Gmail OAuth grant is reconnected/refreshed** and one live label-scoped Gmail dry-run succeeds (HTTP 200, not 503) against the mailbox that will actually receive friend-test emails.
3. No code changes are required to reach GO — both remaining items are operator actions (tenant config correction, OAuth reconnection).

---

## Remaining notes (pre-live-run)

- No new product features were added in this pass; this was a verification-only exercise.
- No code was changed, so the full pytest suite was not re-run. The 25 Sprint 5 tests (`tests/test_sprint5_phase1_value.py`) and the full suite (3165 tests) remain green as last recorded in `docs/01-current-truth.md`.
- Recommend the operator run the actual live gate (`docs/ai-receptionist-mvp-gate.md`, Sections A, D6, E, H, I5) once against the deployed test tenant and record results in that file's "Gate run history" table — this document supplements but does not replace that live run.
- **Docs-only safety update completed (2026-07-15):** the Gmail label-scoping requirement is now a hard, explicit GO/NO-GO check in both `docs/ai-receptionist-test-customer-onboarding.md` and `docs/ai-receptionist-mvp-gate.md`. No code was changed — the underlying default query behavior is unchanged; operators must now explicitly confirm this before every friend-test Gmail scan.

---

## Live gate run — 2026-07-15 (final pre-friend-test check)

### Environment used

No credentials for the production deployment (`api.krowolf.se`) or a live-connected Gmail account with a valid OAuth grant were available in this session. The closest available "live/deployed" environment was the **local dev server** (`app.main:app`, `ENV=dev`) running against the **existing local Postgres database** (`ai_platform`), which already contains real provisioned tenants from prior onboarding work. This is documented honestly here rather than presenting a fabricated production run.

A temporary local server instance was started on port 8010 with an operator-set `ADMIN_API_KEY` (ephemeral, local-only, not a real/production secret) to allow calling tenant-scoped endpoints via `X-Admin-API-Key` + `X-Tenant-ID` impersonation, since plaintext tenant API keys are not recoverable (hashed at rest). The server was stopped and all temporary helper scripts (`_gate_check_*.py`, compiled with `py_compile` before running, read-only, no data mutations) were deleted immediately after the checks below. No `.py` files in the repository were modified.

Two candidate test tenants existed in the local DB: `T_KROWOLF_E2E_TEST` and `T_NIKLAS_DEMO_001`.

### 1. Tenant config confirmation (`GET /tenant`)

| Tenant | `auto_actions` | `allowed_integrations` | `scheduler.run_mode` | Result |
|---|---|---|---|---|
| `T_KROWOLF_E2E_TEST` | `{"lead": true, "invoice": false, "customer_inquiry": true}` | `["crm","accounting","monday","fortnox","visma","google_mail"]` | `manual` (live-confirmed via `GET /dashboard/control`) | **FAIL** — `lead` and `customer_inquiry` are `true` (auto-execute, bypasses approval). `monday`/`fortnox`/`visma` are enabled, contradicting the onboarding doc's "What NOT to enable" table |
| `T_NIKLAS_DEMO_001` | `{"lead": "manual", "customer_inquiry": "manual"}` | `["google_mail"]` | `manual` (live-confirmed) | **PASS** — approval-required for all job types; only Gmail integration enabled |

**Concrete, safety-relevant blocker found:** `T_KROWOLF_E2E_TEST` is **not safe to use for the friend test as currently configured**. If this tenant were used, outbound customer-facing lead and inquiry replies would be auto-executed without operator approval — a direct violation of the "no customer-facing action without approval" requirement — and Monday/Fortnox/Visma writes would not be blocked by the allowlist.

This is **tenant configuration data**, not application code, so per the task instructions ("only fix code if the blocker is real and safety-relevant") no code change was made. Correcting `T_KROWOLF_E2E_TEST`'s `auto_actions`/`allowed_integrations` is a live configuration change (`PUT /tenant/config/{tenant_id}`) that should be made deliberately by the operator, not silently applied by this check. **`T_NIKLAS_DEMO_001` passes this check and is safe to use for the friend test as-is.**

### 2. Gmail processing with label-scoped query

Request: `POST /gmail/process-inbox` with body `{"dry_run": true, "query": "label:krowolf-test is:unread", "max_results": 10}`, run against both tenants.

Result: **BLOCKED (environmental, not code)** — HTTP 503:
```
Gmail list_messages failed: Gmail token refresh failed (400): {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
```

The label-scoped query was accepted and passed through to the Gmail adapter without any validation error — confirming the query-scoping mechanism itself works structurally. The failure is a stored Gmail OAuth refresh token that has expired/been revoked, which is an environment/credentials issue, not a code defect. The system failed closed and safely (503, no job created, no partial processing) rather than falling back to an unscoped scan or silently succeeding — this is the correct, safe failure mode.

**Action required before friend test:** operator must reconnect/refresh the Gmail OAuth grant for the account that will receive friend-test emails, then re-run this exact check with the label-scoped query before the first real test email is sent.

### 3. Daily summary report (`GET /reports/daily-summary`)

Request: `GET /reports/daily-summary?since_hours=24` against `T_NIKLAS_DEMO_001`.

Result: **PASS** — HTTP 200 OK.

```json
{
  "tenant_id": "T_NIKLAS_DEMO_001",
  "period_hours": 24,
  "counts": {
    "new_leads": 0, "leads_ready_for_quote": 0, "leads_waiting_for_customer": 0,
    "inquiries_needing_response": 0, "invoice_items_needing_action": 0,
    "risk_review_required": 0, "pending_approvals": 4
  },
  "top_priorities": [],
  "rendered_text": "God morgon.\n\nKrowolf hittade sedan igår:\n\n* 4 väntande godkännanden"
}
```

`rendered_text` contains "Krowolf" as required. The endpoint correctly read real pending-approval data (4) from the local DB, confirming it queries live data rather than returning a stub. (Note: PowerShell's `Invoke-RestMethod` initially displayed the Swedish characters garbled in the console — this was verified via a raw UTF-8 HTTP check to be a PowerShell console-encoding artifact only; the actual HTTP response bytes are correctly UTF-8 encoded.)

### Updated overall assessment

- Tenant config check: **PASS for `T_NIKLAS_DEMO_001`, FAIL for `T_KROWOLF_E2E_TEST`**
- Gmail label-scoped query mechanism: **structurally confirmed working; live execution BLOCKED by an expired Gmail OAuth token (environmental, not code)**
- Daily summary endpoint: **PASS, live HTTP 200 confirmed with real tenant data**

---

## Gate results run history

| Date | Operator | Type | Overall status | Notes |
|------|----------|------|-----------------|-------|
| 2026-07-15 | Execution agent | Readiness/pre-flight (static + test-suite evidence, no live server) | PASS WITH NOTES | See blockers above; live sections (A, D6, E, H, I5) still require one live run before first friend-test email |
| 2026-07-15 | Execution agent | Docs-only safety update — Gmail label-scoping made a hard GO/NO-GO requirement | PASS WITH NOTES (unchanged) | No code changed. Onboarding doc + MVP gate updated with explicit warnings, GO/NO-GO checks (A0), and NO-GO criteria for unscoped Gmail queries. Operational risk mitigated via documentation; live confirmation still required per items above |
| 2026-07-15 | Execution agent | Final live gate run against local dev server + real local tenant data (no production/Gmail credentials available) | **BLOCKED** | `T_KROWOLF_E2E_TEST` has unsafe `auto_actions`/`allowed_integrations` — do not use for friend test. `T_NIKLAS_DEMO_001` passes tenant config check. Gmail live scan blocked by expired OAuth token (environmental). Daily summary endpoint confirmed live, HTTP 200. See "Live gate run" section above for full detail |
