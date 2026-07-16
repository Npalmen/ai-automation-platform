# Pilot Transition Pack

> **Governing document:** `docs/00-master-plan.md`  
> **Verified state:** `docs/01-current-truth.md`  
> **Status:** Phase 1 technical build complete — transition to internal demo + first controlled pilot  
> **Last updated:** 2026-07-16

This document consolidates pilot scope, onboarding, operations, metrics, and commercial framing. It does **not** release real-customer Visma accounting writes.

---

## Part A — Internal demo rehearsal (completed 2026-07-16)

**Method:** Read-only production walkthrough on `T_NIKLAS_DEMO_001` via `scripts/ops/run_internal_demo_rehearsal_prod.py`. No Visma writes. No Gmail reprocessing.

| Demo step | Result |
|-----------|--------|
| Lead example | Found — `Elcentralbyte villa Uppsala`, `awaiting_approval`, pending approval |
| Customer inquiry example | Found — `Akut elfel`, `awaiting_approval`, pending approval |
| Manual-review example | Found — `Det luktar bränt`, `manual_review`, no pending approval |
| Manual-review queue | HTTP 200, 8 unresolved (includes Visma sandbox test jobs — explain or filter in UI) |
| Google Sheets | Leads 2 rows, Support 2 rows, Sammanfattning 21 rows, Logg header only |
| Visma | Connected, test-read OK, v6 job preview local-only, export `already_exported`, approval `approved` |
| Tenant safety | `auto_actions` all false, scheduler manual, integrations allowlisted |
| Visma writes during rehearsal | **None** |

### Rehearsal findings

**Demo blockers:** None

**Non-blocking polish:**
- Operator console is API/internal — no customer-facing portal yet
- Job API exposes intelligence in `result.processor_history` — demo narrative should open job detail / processor payload, not only top-level fields
- 8 legacy `email_send` approvals still pending from first demo batch — reject or drain before first real pilot
- Manual-review queue includes Visma sandbox test jobs — filter by subject or resolve after demo
- Gmail integration health may show `warning` after demo batch processed (expected)
- Dashboard job status may show `awaiting_approval` when pending approvals exist (enrichment overlay)

**Recommended demo talk track:** See `docs/niklas-demo-production-testlog.md` §2–3.

---

## Part B — First pilot scope

### Included (what we offer)

| Capability | Description |
|------------|-------------|
| Gmail reading | Label-scoped inbox sync (`label:<tenant-label> is:unread`) — never whole inbox by default |
| Lead classification | Job type `lead`, service profile, priority, missing fields |
| Customer inquiry classification | Job type `customer_inquiry`, routing and response preparation |
| Information extraction | Structured fields from Swedish installation/service emails |
| Priority & risk detection | Policy processor flags; high-risk → `manual_review` |
| Proposed next actions | Approval requests with `next_on_approve` — no automatic execution |
| Approval before external action | All outbound email and integration writes require operator approval |
| Manual-review queue | Unresolved risk cases; Gmail unread + `krowolf-manual-review` label |
| Google Sheets overview | Append-only Leads/Support; replace-range Sammanfattning |
| Daily summary | Tenant-scoped counters and priority rows — no full email bodies |

### Excluded (explicitly not in first pilot)

- Real-customer Visma accounting writes
- Automatic invoice creation or dispatch
- Automatic customer responses without approval
- Supplier invoice import
- Visma quotations
- Customer-facing self-service portal
- Unsupervised / scheduled automation (`auto_actions` remain false; scheduler manual unless explicitly agreed)
- Monday/Fortnox production writes (unless separately scoped and tested)

### Pilot parameters

| Parameter | Recommendation |
|-----------|----------------|
| **Suitable customer profile** | Swedish installation/service company (el, solar, VVS, service), 5–50 employees, Gmail as primary intake, willing to use approval-first workflow |
| **Expected email volume** | 50–300 emails/month in pilot inbox; max 500/month included |
| **Supported inboxes** | 1 primary Gmail mailbox per pilot tenant; label-scoped only |
| **Support hours** | Business days 09:00–17:00 CET; incident email/phone for BLOCKER issues |
| **Incident contact** | Named operator + backup (fill before sign-off) |
| **Pilot duration** | 6 weeks (extendable to 8 by agreement) |
| **Operator time** | ~30–45 min/day review; ~2 h/week quality review |

### Success metrics (see Part E)

### Stop criteria

Stop or pause pilot immediately if:
- Any customer-facing email sent without approval
- Duplicate external action (double send, double export)
- Cross-tenant data exposure
- Unexpected Visma or Fortnox write
- Gmail OAuth cannot be restored within 4 business hours
- Operator loses confidence in approval gate

### Rollback / offboarding

1. `POST /admin/support/{tenant_id}/pause-automation` (admin)
2. `PUT /dashboard/control` → `scheduler.run_mode: "paused"`
3. Set `auto_actions` all false
4. Reject or drain pending approvals
5. Revoke tenant API key (`rotate-key`)
6. Remove Gmail label rules / disconnect OAuth per `docs/runbooks/customer-offboarding.md`
7. Archive Google Sheet (do not delete customer data without agreement)
8. Export audit events for handover
9. Document open manual-review items

---

## Part C — Customer onboarding checklist

Use for each new pilot tenant. Estimated operator setup: **4–8 hours** (excluding customer questionnaire response time).

### 1. Tenant

- [ ] Create tenant via admin (`POST /admin/tenants`) — unique slug
- [ ] Record tenant ID and API key (secure store only)
- [ ] `enabled_job_types`: `lead`, `customer_inquiry` (add `invoice` only if pre-accounting scoped)
- [ ] `allowed_integrations`: start with `google_mail`; add `google_sheets` when sheet ready; **do not** add `visma` for standard pilot unless sandbox-only demo agreed
- [ ] `auto_actions`: all `false`
- [ ] `scheduler.run_mode`: `manual`
- [ ] `support_email` set in dashboard control
- [ ] `demo_mode`: `false` only when ready for live label-scoped sync

### 2. Gmail

- [ ] Confirm mailbox owner and OAuth consent
- [ ] Connect OAuth / verify token refresh
- [ ] Create dedicated label (e.g. `krowolf-<customer-slug>`)
- [ ] Document query: `label:krowolf-<slug> is:unread` — **mandatory for all process-inbox calls**
- [ ] Define included mail: label-scoped only
- [ ] Define excluded: whole inbox, sent mail, other labels, personal mail outside label
- [ ] Prepare 3–5 test messages (lead, inquiry, risk/manual-review scenarios)
- [ ] Dry-run `POST /gmail/process-inbox` with explicit query before live scan

### 3. Business configuration

- [ ] Company profile (name, services, geography)
- [ ] Service profiles / routing hints in tenant config
- [ ] Risk words and do-not-touch categories
- [ ] Lead qualification required fields
- [ ] Support categories and escalation paths
- [ ] Approval policy: who may approve, channels, no auto-approve
- [ ] Internal handoff recipient(s)

### 4. Google Sheets

- [ ] Create spreadsheet with tabs: Leads, Support, Logg, Sammanfattning
- [ ] Store spreadsheet ID in tenant config only (not in repo)
- [ ] Share with customer ops contact + operator service account
- [ ] Explain append-only behavior on Leads/Support (duplicates possible on re-export)
- [ ] Explain Sammanfattning replace-range (current-state snapshot)
- [ ] Test one manual export per tab type

### 5. Safety

- [ ] Confirm no automatic external action (`auto_actions` false)
- [ ] Named escalation contact on customer side
- [ ] Manual-review ownership assigned
- [ ] Backup freshness verified (`check_backup_freshness.sh`)
- [ ] Offsite backup + restore rehearsal per `docs/PILOT_READINESS_CHECKLIST.md`
- [ ] Incident response contact and runbooks read

### 6. Acceptance test (pilot go-live gate)

- [ ] One lead processed end-to-end (classify → approval visible)
- [ ] One customer inquiry processed
- [ ] One manual-review case visible in queue with Gmail handoff
- [ ] One approval actioned (approve or reject) with audit trail
- [ ] One Sheets export (lead or support tab)
- [ ] Daily summary reflects counts
- [ ] No unexpected integration writes in audit/integration events

**Checklist also available in:** `docs/ai-receptionist-test-customer-onboarding.md`, `docs/PILOT_READINESS_CHECKLIST.md`

---

## Part D — Pilot operating model

### Daily routine (operator, ~30–45 min)

| Step | Action | Owner | Target |
|------|--------|-------|--------|
| 1 | Read Sammanfattning / daily summary | Operator | By 10:00 |
| 2 | Triage manual-review queue | Operator | Same day for high-risk |
| 3 | Process pending approvals (no bulk approve) | Operator | Within 4 business hours |
| 4 | Inspect failed jobs / needs-help | Operator | Same day |
| 5 | Check integration health | Operator | Once daily |
| 6 | Label-scoped inbox sync (manual trigger only) | Operator | As agreed |

### Weekly routine (~2 h)

| Step | Action |
|------|--------|
| 1 | Review classification quality (sample 10 jobs) |
| 2 | Review misrouted or corrected items |
| 3 | Check duplicate Sheets rows |
| 4 | Collect customer/operator feedback |
| 5 | Review audit events for anomalies |
| 6 | Verify backup freshness |

### Incident triggers and ownership

| Trigger | Severity | Owner | Response target |
|---------|----------|-------|-----------------|
| Incorrect customer response sent | CRITICAL | Operator + product owner | Immediate pause; customer notify within 1 h |
| Duplicate external action | CRITICAL | Operator | Pause tenant; reconcile within 4 h |
| Gmail OAuth failure | HIGH | Operator | 4 business hours |
| Integration failure (Sheets) | MEDIUM | Operator | 1 business day |
| Cross-tenant concern | CRITICAL | Product owner | Immediate isolation review |
| Unresolved high-risk email in manual review | HIGH | Customer ops + operator | 4 business hours |
| Unexpected Visma write | CRITICAL | Operator | Immediate pause; reconciliation per runbook |

**Support gap to close before first paid pilot:** Named on-call rotation and customer-facing incident email not yet formalized in contract.

---

## Part E — Pilot success metrics

Use directionally — not statistical precision in a 6-week pilot.

| Metric | How measured | Proposed pilot target |
|--------|--------------|----------------------|
| Classification accuracy | Operator review sample (weekly) | ≥ 80% correct job_type |
| Correct routing | manual_review vs approval appropriateness | ≥ 85% |
| Manual correction rate | Jobs reclassified or rejected | ≤ 20% |
| Handling-time reduction | Customer estimate vs baseline | Subjective improvement reported |
| Missed emails | Label-scoped sync audit | 0 missed in scoped label |
| Duplicate external actions | Integration/audit events | **0** |
| Approval turnaround | Request → decision timestamp | < 1 business day median |
| Manual-review age | Days unresolved | High-risk < 1 day; others < 3 days |
| Operator satisfaction | Weekly 1–5 check-in | ≥ 4/5 |
| Customer satisfaction | End-of-pilot survey | ≥ 4/5 |
| Incidents | Count by severity | 0 CRITICAL |

---

## Part F — Commercial pilot proposal (internal draft)

Suitable for small installation/service companies in Sweden. Adjust before customer-facing quote.

| Item | Recommendation |
|------|----------------|
| **Setup fee** | 19 500 SEK ex VAT — tenant setup, Gmail label, Sheets, test scenarios, acceptance test, operator training (2 h) |
| **Monthly pilot fee** | 6 900 SEK ex VAT / month |
| **Included volume** | 1 Gmail inbox, up to 500 emails/month in scoped label |
| **Included support** | Email support business days; 1 h/month review call |
| **Excluded** | Visma production writes, Fortnox, Monday writes, extra inboxes, auto-dispatch, custom integrations |
| **Pilot duration** | 6 weeks |
| **Cancellation** | Either party 14 days notice; data export on exit |
| **Conversion** | Pilot fee credited 50% toward first 3 months of standard subscription if signed within 30 days of pilot end |
| **Standard subscription (indicative)** | From 9 900 SEK/month — scope TBD post-pilot |
| **Visma writes** | Not included; separate statement of work if ever offered |

---

## Readiness assessment

| Area | Status |
|------|--------|
| Internal demo rehearsal | **PASS** |
| Pilot scope defined | **PASS** |
| Onboarding checklist | **PASS** |
| Operating model | **PASS WITH CONDITIONS** — name incident owners |
| Success metrics | **PASS** |
| Commercial draft | **PASS** — internal only until pricing validated |
| Ready to book first pilot | **YES WITH CONDITIONS** |

### Exact remaining blockers

1. Drain/reject 8 legacy demo `email_send` approvals (or confirm pilot uses fresh tenant)
2. Named customer incident contact + operator on-call for pilot period
3. Offsite backup + restore rehearsal sign-off per `PILOT_READINESS_CHECKLIST.md` (if not already done for production host)

### Recommended first customer profile

Owner-operated or small-team **installation/service company** (el, solar, laddbox, service) already using **Gmail**, comfortable with **approval-first** workflows, not expecting ERP automation or customer portal in phase 1.

---

## Related documents

| Document | Purpose |
|----------|---------|
| `docs/niklas-demo-production-testlog.md` | Demo script and talk track |
| `docs/PILOT_READINESS_CHECKLIST.md` | Pre-pilot infrastructure safety |
| `docs/ai-receptionist-test-customer-onboarding.md` | Detailed tenant setup steps |
| `docs/NIKLAS_DEMO_READINESS_CHECKLIST.md` | Internal rehearsal checklist |
| `docs/runbooks/customer-onboarding.md` | Operator runbook |
| `docs/runbooks/customer-offboarding.md` | Exit procedure |
