# AI Receptionist — MVP Gate

> **Purpose:** Chapter-level verification checklist for the full AI Receptionist MVP flow.
> Run this before opening to external/friend test customers.
>
> **When to run:** After all Sprint 1–3 changes are deployed to the live environment.
> This gate verifies end-to-end behavior, not individual unit tests.
>
> **Who runs it:** Internal operator. Requires live server access, admin key, and tenant key.
>
> **Status options:**
> - `PASS` — Criterion met, no action needed
> - `PASS WITH NOTES` — Criterion met but with minor deviation; note it
> - `BLOCKED` — Cannot verify (environment issue, missing config) — fix before continuing
> - `FAIL` — Criterion not met — do not proceed to external tests

---

## Gate prerequisite checklist

Before running the gate:

- [ ] Server is running and `/health` returns `{"status": "ok", "env": "production"}`
- [ ] A test tenant is set up using `docs/ai-receptionist-test-customer-onboarding.md`
- [ ] Gmail label exists and test emails from `docs/ai-receptionist-test-mail-scenarios.md` are applied
- [ ] Google Sheet created with tabs **Leads**, **Support**, **Logg** (if testing Sheets)
- [ ] `auto_actions = false` for all job types — confirmed
- [ ] `scheduler.run_mode = manual` — confirmed
- [ ] No previous test jobs exist for this tenant (or use `GET /jobs` to establish baseline)
- [ ] **GO/NO-GO — Gmail query is label-scoped:** every planned `/gmail/process-inbox` call for this gate run and for the friend test uses an explicit label-scoped `query` (e.g. `label:krowolf-test is:unread`). `/gmail/process-inbox` defaults to `query: "is:unread"` (the entire unread inbox) when `query` is omitted. **This default is NOT allowed for friend tests or any production/shared mailbox.** Do not proceed past this checklist until confirmed.

---

## Section A — Gmail ingestion

> **GO/NO-GO before running this section:** confirm every `/gmail/process-inbox` call
> below (A1–A3) explicitly passes `"query": "label:<test-label> is:unread"` (or
> equivalent). Do NOT omit `"query"` and rely on the default (`is:unread` across the
> whole mailbox) — this is not allowed for friend tests or any production/shared
> mailbox. If any call in this section was made without an explicit label-scoped
> query, mark Section A `BLOCKED` and re-run with the correct query.

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| A0 | Gmail query is label-scoped | Every scan in this section used an explicit `query` scoped to the test label — never the default `is:unread` | | |
| A1 | Dry-run scan finds correct emails | `dry_run=true` returns the expected email count (no extras) | | |
| A2 | Live scan creates jobs | `jobs_created` = number of test emails sent | | |
| A3 | Duplicate protection | Re-running scan does not duplicate jobs | | |
| A4 | Job types are correct | Lead emails → `lead`, inquiry emails → `customer_inquiry` | | |
| A5 | No external actions fired | All jobs show `external_actions_count = 0` immediately after scan | | |

---

## Section B — Playbook and reply quality

Run for Scenarios 1–4 and 7 from test mail scenarios.

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| B1 | Customer name extracted correctly | Greeting uses correct name from email body signature | | |
| B2 | EV charger asks correct questions | Asks main_fuse / panel distance; does NOT ask generic location | | |
| B3 | Battery add-on suppresses wrong questions | Does NOT ask property_type; asks inverter/backup | | |
| B4 | Battery classified separately from solar | `profile_type = battery_storage`, not `solar_installation` | | |
| B5 | Solar issue asks relevant questions | Asks for production data, app readings, when issue started | | |
| B6 | Building/carpentry generates intro question | Asks for timeline and scope | | |
| B7 | Replies are non-binding | No legal/financial commitments in any auto-reply body | | |
| B8 | No hallucinated content | Reply body refers only to what the customer mentioned | | |

---

## Section C — Safety and manual review routing

Run for Scenarios 5 and 8 from test mail scenarios.

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| C1 | Emergency (luktar bränt) → manual_review | Job status = `manual_review`, no pending customer reply | | |
| C2 | Complaint → manual_review | Job status = `manual_review`, no pending customer reply | | |
| C3 | Emergency has internal handoff | `human_handoff_processor` payload exists in processor_history | | |
| C4 | Complaint has internal handoff | `human_handoff_processor` payload exists in processor_history | | |
| C5 | No auto-reply for C1/C2 | `GET /approvals/pending` shows ZERO approvals for these job IDs | | |

---

## Section D — Approval-first

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| D1 | Lead email has pending approval | Approval visible in `/approvals/pending` | | |
| D2 | Support email has pending approval | Approval visible in `/approvals/pending` | | |
| D3 | Approval type is `action_dispatch` | `type = action_dispatch`, `next_on_approve = email_send` | | |
| D4 | Approval contains readable reply body | Body field is non-empty and readable Swedish | | |
| D5 | Rejecting approval does not send email | After reject, no `gmail_send` event in `/integration-events` | | |
| D6 | Approving sends to Gmail thread | After approve, email appears in correct Gmail thread (live check) | | |

> Note: D6 requires a live Gmail send and is optional for internal-only tests. Mark `PASS WITH NOTES` if skipped.

---

## Section E — Google Sheets export

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| E1 | Lead job exports to Leads tab | Response: `{"status": "exported", "tab": "Leads"}` | | |
| E2 | Support job exports to Support tab | Response: `{"status": "exported", "tab": "Support"}` | | |
| E3 | Wrong tenant job returns 404 | Using a job_id from a different tenant returns HTTP 404 | | |
| E4 | Missing spreadsheet_id returns blocked | Config without spreadsheet_id returns `configuration_missing` | | |
| E5 | Row appears in spreadsheet | Verify row in Google Sheet (live check) | | |
| E6 | Audit event created | `/audit-events` shows `action: google_sheets_export` | | |

---

## Section F — Tenant isolation

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| F1 | Test tenant cannot see other tenant jobs | `GET /jobs` with test key returns only test tenant jobs | | |
| F2 | Test tenant cannot approve other tenant approvals | Approval from another tenant returns 404 | | |
| F3 | Admin key rejected as tenant key | `GET /jobs` with admin key returns 403 | | |
| F4 | Tenant key rejected on admin endpoints | `GET /admin/tenants` with tenant key returns 401 | | |

---

## Section G — Integration allowlist enforcement

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| G1 | google_sheets not in allowed → blocked | `export-job` returns `integration_not_allowed` | | |
| G2 | No Monday writes triggered | `/integration-events` shows no `monday_create` events | | |
| G3 | No Visma writes triggered | `/integration-events` shows no `visma_*` events | | |
| G4 | No auto-send without approval | No `gmail_send` events in `/integration-events` before explicit approve | | |

---

## Section H — Observability and audit

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| H1 | Audit events are scoped to tenant | `/audit-events` shows only this tenant's events | | |
| H2 | Workflow events visible | `step_started`/`step_completed` events present for each job | | |
| H3 | No 500 errors in server logs | Server logs clean — no Traceback or 500 Internal Server Error | | |
| H4 | No leaked secrets in any response | No token values in API responses | | |

---

## Section I — Phase 1 value layer (Sprint 5)

Run these checks after Sprint 5 is deployed. Can be verified via unit tests or manual API inspection.

| # | Check | Pass criteria | Status | Notes |
|---|-------|---------------|--------|-------|
| I1 | Complete lead → quote draft prepared | A lead with completeness ≥ 0.7 produces `offer_draft` in `lead_analyzer_processor` payload; payload includes `human_approval_required: true` and customer contact fields | | |
| I2 | Incomplete lead → waiting_for_customer | A lead with completeness < 0.7 produces `lead_status = waiting_for_customer` and a `generated_question_message` in the payload | | |
| I3 | Risky/unclear lead → risk_review_required | A complaint or emergency lead reaches `MANUAL_REVIEW` status; `derive_job_status` returns `risk_review_required`; no offer draft produced | | |
| I4 | Invoice email → routing recommendation | An invoice job payload includes `invoice_routing` field; debt-collection keywords produce `debt_collection_review`; clean invoice produces `forward_to_accounting` | | |
| I5 | Daily report generates without error | `GET /reports/daily-summary` returns HTTP 200 with `counts`, `top_priorities`, and `rendered_text`; `rendered_text` contains "Krowolf" | | |
| I6 | Approval command parsing | `parse_approval_command("GODKÄNN")` → `command: approve`; `parse_approval_command("STOPPA")` → `command: reject`; `parse_approval_command("ÄNDRA: ny text")` → `command: change, change_text: ny text` | | |

> Note: I1–I4 can be verified against the unit test suite (`tests/test_sprint5_phase1_value.py`). I5 requires a running server. I6 is unit-testable.

---

## Gate result

Fill in after running all checks:

| Section | Status | Notes |
|---------|--------|-------|
| A — Gmail ingestion | | |
| B — Playbook quality | | |
| C — Safety routing | | |
| D — Approval-first | | |
| E — Sheets export | | |
| F — Tenant isolation | | |
| G — Allowlist enforcement | | |
| H — Observability | | |
| I — Phase 1 value layer | | |
| **Overall gate** | | |

### GO criteria (all must be PASS or PASS WITH NOTES)

- [ ] A0 PASS (Gmail query label-scoped — hard requirement, no exceptions for friend tests or shared mailboxes)
- [ ] A1–A5 all PASS
- [ ] B1–B8 all PASS (B7/B8 are critical — FAIL blocks proceed)
- [ ] C1–C5 all PASS (any FAIL blocks proceed — safety routing must work)
- [ ] D1–D5 all PASS (D6 may be PASS WITH NOTES)
- [ ] E1–E4 PASS (E5 may be PASS WITH NOTES for internal-only)
- [ ] F1–F4 all PASS (tenant isolation is non-negotiable)
- [ ] G1–G4 all PASS (no unauthorized writes — non-negotiable)
- [ ] H1–H4 all PASS
- [ ] I1–I6 all PASS (I5 may be PASS WITH NOTES if server unavailable for manual check)

### NO-GO criteria (any triggers a stop)

- Any complaint or emergency email generates a pending customer auto-reply
- Any email is sent without going through approval-first
- Any cross-tenant data is returned
- Any Monday or Visma write event appears without explicit configuration
- Server logs contain 500 errors or leaked tokens during the gate run
- Any `/gmail/process-inbox` call during the gate run or friend test omitted `"query"` or used the default `is:unread` against a production/shared mailbox

---

## After gate

If overall gate = PASS or PASS WITH NOTES with no blocking fails:

→ Proceed to friend test using `docs/ai-receptionist-friend-test-guide.md`

If gate BLOCKED or has any NO-GO:

→ Fix the issue, re-run only the affected section, re-score.
→ Do not run full pytest unless code was changed.
→ Document the fix and re-run date in this file under "Gate run history".

---

## Gate run history

| Date | Operator | Overall status | Notes |
|------|----------|----------------|-------|
| — | — | — | Not yet run |
