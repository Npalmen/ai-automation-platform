# Niklas Demo — Production Testlog & Demo Script

> **Tenant:** `T_NIKLAS_DEMO_001`  
> **Host:** `https://api.krowolf.se`  
> **Deploy:** `0c17256` (app; db/caddy unchanged)  
> **Last verified:** 2026-07-16 (Chapters 2–3 Visma sandbox + cleanup)  
> **Status:** **PASS WITH CONDITIONS** (internal demo + sandbox Visma proof)

---

## Chapter 2–3 addendum (2026-07-16)

| Area | Result |
|------|--------|
| **Visma OAuth** | Connected; test-read `api_readable=true`; sandbox/test account |
| **Visma allowlist** | `google_mail`, `google_sheets`, `visma` enabled; `auto_actions` all false |
| **Sandbox export** | One approval-gated customer-invoice export (v6 job); idempotent `already_exported` on repeat |
| **Write safety** | Tenant OAuth; no dispatcher auto-write; `reconciliation_required` path exists |
| **Stale approvals** | 5 pre-fix pending exports rejected via normal reject endpoint; v6 approval remains `approved` |
| **Sandbox artifacts** | 2 Krowolf invoices + 2 sandbox customers in Visma test company (1 controlled + 1 diagnostic); retained — optional manual UI cleanup |
| **Regression** | R1 release gate + 3265 local tests passed |

**Do not oversell:** Real-customer Visma accounting writes are **not** generally released. Quotations and supplier invoices are **not** implemented.

---

## Pilot transition rehearsal (2026-07-16)

| Area | Result |
|------|--------|
| **Rehearsal** | PASS — read-only production walkthrough; script `scripts/ops/run_internal_demo_rehearsal_prod.py` |
| **Demo blockers** | None |
| **Visma writes** | None during rehearsal |
| **Polish** | Drain 8 legacy email approvals before pilot; processor detail in `result.processor_history`; no customer portal |
| **Pilot pack** | `docs/PILOT_TRANSITION.md` |

---

## 1. Executive summary (2026-07-15 baseline)

### What is verified

| Area | Result |
|------|--------|
| **Deploy** | App live; `/` and `/health` → 200; `/reports/daily-summary` → 401 without auth, 200 with tenant API key |
| **Tenant safety** | `auto_actions` all `false`; `scheduler.run_mode: manual`; `allowed_integrations: ["google_mail"]` only; unknown tenant fail-closed |
| **Gmail OAuth** | Refresh works; `GOOGLE_MAIL_USER_ID=niklas.palm@sol-f.se` |
| **Label-scoped intake** | Label `krowolf-demo-niklas`; query **always** `label:krowolf-demo-niklas is:unread`; 11 demo-only messages; no real customer mail |
| **Dry-run** | HTTP 200; scanned 11; failed 0 |
| **Live scan** | HTTP 200 (after one transient Gmail 500 on first attempt; retry succeeded, no duplicate processing); scanned/processed 11; failed 0; messages marked read |
| **Jobs** | 11 created; DB split **6 lead / 5 customer_inquiry**; **2 manual_review** (complaint + safety); **9** internal handoff approvals created |
| **Approval gate** | **1** internal handoff approved and sent to `niklas.palm@sol-f.se`; **8** still pending; **no** customer-facing emails sent |
| **Integrations** | No Sheets or Visma actions triggered |
| **Daily report** | HTTP 200; 6 leads waiting, 3 inquiries needing response, 2 risk items, 8 pending approvals; top priorities surface complaint/safety cases |

### Current demo status

**PASS WITH CAVEATS** — Safe for an **internal Phase 1** demo of controlled Gmail intake, risk stopping, and approval-first internal handoff. Not ready to sell autonomous customer replies or Sheets/Visma without separate setup.

### What should not be oversold

- Customer-facing auto-replies are **not** production-ready in this demo.
- Pending approvals are **internal handoff summaries** to `niklas.palm@sol-f.se`, not polished kundsvar.
- Dashboard `ready_cases` and per-job status after email approval are **partially stale** (see caveats).
- Sheets and Visma are **not** verified on production for this tenant.
- Gmail scan **cannot be re-run** on the same demo batch (messages are read).

---

## 2. Demo narrative / talk track

**Framing (use in Swedish):**

> Krowolf läser en kontrollerad Gmail-label, förstår inkommande ärenden, sorterar dem till leads/kundfrågor, stoppar riskärenden, lägger säkra ärenden i approval queue och kan skicka intern handoff efter godkännande.

**Supporting points:**

1. **Controlled intake** — Only mail under label `krowolf-demo-niklas`, unread at scan time. Not the whole inbox.
2. **Understanding** — Pipeline classifies and enriches (service profile, priority, missing info).
3. **Risk stop** — Complaint and safety content lands in `manual_review`, not the approval queue.
4. **Approval-first** — `auto_actions` off; outbound email requires explicit operator approval.
5. **Internal handoff** — Approved action sends an ops summary to `niklas.palm@sol-f.se`, not a customer reply.

---

## 3. Recommended demo flow

Run in this order. Have tenant API key ready (server path: `/opt/krowolf/storage/tenant_keys/T_NIKLAS_DEMO_001.api_key` — **do not display in UI or slides**).

### Step 1 — Tenant safety config (~2 min)

```bash
curl -sS https://api.krowolf.se/tenant \
  -H "X-API-Key: $(cat /opt/krowolf/storage/tenant_keys/T_NIKLAS_DEMO_001.api_key)" | python3 -m json.tool
```

**Show:** `auto_actions` all `false`, `allowed_integrations: ["google_mail"]`, `enabled_job_types`.

```bash
curl -sS https://api.krowolf.se/dashboard/control \
  -H "X-API-Key: $(cat ...)" | python3 -m json.tool
```

**Show:** `scheduler.run_mode: manual`, `followups_enabled: false`, `support_email: niklas.palm@sol-f.se`.

**Say:** Manual scheduler, no auto customer follow-ups, approval-first.

---

### Step 2 — Gmail label-scoped setup (~2 min)

**In Gmail UI:** Open label `krowolf-demo-niklas` on `niklas.palm@sol-f.se`.

**Show:** Demo/fictitious scenarios only; messages are now **read** (post live scan).

**Say:** Production uses a fixed query — never the default `is:unread` inbox.

```
label:krowolf-demo-niklas is:unread
```

**Do not:** Re-run `/gmail/process-inbox` live (0 unread under label).

---

### Step 3 — 11 processed jobs (~3 min)

List jobs via API or operator UI.

**Facts to state:**

| Metric | Value |
|--------|-------|
| Total jobs | 11 |
| `job_type` | 6 lead, 5 customer_inquiry |
| `manual_review` | 2 |
| `awaiting_approval` (DB status) | 9 |

**Optional:** Open one lead and one inquiry job; show subject, inferred profile, pipeline summary.

---

### Step 4 — Two manual_review risk cases (~3 min)

| Job ID | Subject | Why stopped |
|--------|---------|-------------|
| `39d88cf1-72e3-40b3-9bc1-287d4e2c2b58` | Inte nöjd med jobbet | `risk:complaint` |
| `6bf6bbcf-6ee6-48d3-9523-bf38170e51eb` | Det luktar bränt | `risk:safety_risk` |

**Show:** Daily report top priorities (“Granska riskärende för Lena / Sara”).

**Say:** These never entered the approval queue — fail-closed on risk.

**Do not:** Approve or attempt to auto-reply.

---

### Step 5 — Eight pending approvals (~3 min)

```bash
curl -sS "https://api.krowolf.se/approvals/pending?limit=20" \
  -H "X-API-Key: $(cat ...)" | python3 -m json.tool
```

**Show:** 8 pending; titles like “E-post: Nytt lead [HIGH]…”; summary mentions `send_internal_handoff` to `niklas.palm@sol-f.se`.

**Say:** These are **internal** handoff drafts, not customer replies.

**Do not:** Approve all; do not approve complaint/safety jobs (they have no pending approval).

---

### Step 6 — One approved internal handoff (~2 min)

**Approved in test:**

| Field | Value |
|-------|-------|
| Approval ID | `eml_bb713db199a445739549` |
| Job ID | `89ed08a0-54f5-43ab-84aa-92366e95c1ee` |
| Subject | Fråga om batterilager till befintlig solcellsinstallation |
| Recipient | `niklas.palm@sol-f.se` |
| Action | `send_internal_handoff` |

**In Gmail:** Open inbox for `niklas.palm@sol-f.se`; show received internal handoff email (“Nytt lead [HIGH]: …”).

**Say:** Approval gate worked end-to-end — one explicit approve → one internal email.

---

### Step 7 — Daily summary (~2 min)

```bash
curl -sS https://api.krowolf.se/reports/daily-summary \
  -H "X-API-Key: $(cat ...)" | python3 -m json.tool
```

**Highlight `rendered_text` excerpt:**

- 6 leads som väntar på kundinformation  
- 3 kundärenden som behöver svar  
- 2 högriskärenden  
- 8 väntande godkännanden  

**Show:** `top_priorities` — complaint and safety cases first.

---

### Step 8 — Dashboard caveat (if shown) (~1 min)

```bash
curl -sS https://api.krowolf.se/dashboard/summary \
  -H "X-API-Key: $(cat ...)" | python3 -m json.tool
```

**If you show `ready_cases: 9`:** Explain it counts DB `awaiting_approval` job rows, not live pending approvals (**true pending = 8**). Job `89ed08a0` still shows stale `awaiting_approval` after its handoff was approved.

**Prefer in demo:** Use `/approvals/pending` and daily summary counts instead of `ready_cases` without explanation.

---

## 4. Exact phrases to use

| Situation | Phrase |
|-----------|--------|
| Auto-send | “Systemet skickar inget till kund automatiskt i det här läget.” |
| Value prop | “Det här är säker receptionistlogik: förstå, prioritera, stoppa risk och föreslå nästa steg.” |
| Customer reply layer | “Kundsvaret är nästa lager; just nu verifierar vi trygg intake och intern handoff.” |
| Approvals | “Godkännanden här är interna handoff-mail till oss — inte färdiga kundmail.” |
| Risk cases | “Klagomål och säkerhetsrisk går till manuell granskning och får inte auto-flöde.” |
| Label scope | “Vi läser bara labeln `krowolf-demo-niklas`, inte hela inkorgen.” |
| Re-scan | “Vi kör inte om skanningen — mailet är redan hanterat och markerat som läst.” |

---

## 5. Caveats / do not claim

| Do not claim | Reality |
|--------------|---------|
| Customer replies are production-ready | `send_customer_auto_reply` actions were **skipped**; approvals are internal handoff only |
| Sheets export works on production demo | Not enabled on tenant; not tested |
| Visma is verified | Not enabled; no actions triggered |
| Dashboard status is perfect after approval | `89ed08a0` still `awaiting_approval`; `ready_cases` 9 vs 8 pending |
| “9 cases ready for approval” | Only **8** pending approvals; one already approved |
| Name extraction is accurate | Self-sent demos: From = Niklas; body signatures may say Lena/Sara/Anders |
| Gmail scan can be repeated | Messages under label are read; re-scan returns 0 |
| First live scan was flawless | First attempt hit transient Gmail connection reset; retry succeeded |

---

## 6. Backlog fixes from this test

| Priority | Item |
|----------|------|
| **P1** | Fix approval-completed job status for `email_send` / `send_internal_handoff` path (`89ed08a0` stale `awaiting_approval`) |
| **P1** | Fix `ready_cases` to count live pending approvals, not all jobs with `status=awaiting_approval` |
| **P2** | Add `handled` / `internal_handoff_sent` count to daily summary |
| **P2** | Record approved handoff in job action audit trail |
| **P3** | Improve name extraction for self-sent demo mail (body signature vs From header) |
| **P3** | Optional: harden Gmail transient retry in `/gmail/process-inbox` (connection reset) |
| **Ops** | Add `POSTGRES_PASSWORD=` to `.env.production` before any future **db** container recreate |
| **Later** | Decide when to enable Google Sheets manual export (`google_sheets` + `spreadsheet_id`) |
| **Later** | Decide when to enable Visma sandbox read-only checks |

---

## 7. Current GO / NO-GO

| Decision | Verdict |
|----------|---------|
| **GO** — Internal Phase 1 demo: safe Gmail intake + approval-first internal handoff | **YES** |
| **NO-GO** — Customer-facing autonomous replies | **YES** (not verified) |
| **NO-GO** — Sheets / Visma demo on this tenant | **YES** (not configured/tested) |
| **NO-GO** — Re-running Gmail live scan on same demo batch | **YES** (messages read) |
| **NO-GO** — Bulk-approving all 8 pending handoffs without narrative | **YES** (approve selectively if at all) |

---

## Appendix — Source-of-truth snapshot

### Deploy checks

| Endpoint | Status |
|----------|--------|
| `/` | 200 |
| `/health` | 200 |
| `/reports/daily-summary` (no auth) | 401 |
| `/reports/daily-summary` (tenant auth) | 200 |
| `/docs`, `/openapi.json` | 404 |

### Job inventory (11)

| Job ID | Type | Status | Notes |
|--------|------|--------|-------|
| `39d88cf1` | customer_inquiry | manual_review | Complaint |
| `a4b4e0c3` | lead | awaiting_approval | Pending handoff |
| `6bf6bbcf` | customer_inquiry | manual_review | Safety |
| `d100eb61` | lead | awaiting_approval | Pending handoff |
| `20311795` | customer_inquiry | awaiting_approval | Pending handoff |
| `89ed08a0` | lead | awaiting_approval* | Handoff **approved**; status stale |
| `a8e0b63b` | lead | awaiting_approval | Pending handoff |
| `131124c7` | customer_inquiry | awaiting_approval | Pending handoff |
| `95d89d7a` | lead | awaiting_approval | Pending handoff |
| `c73723fa` | customer_inquiry | awaiting_approval | Pending handoff |
| `96c26833` | lead | awaiting_approval | Pending handoff |

\*Known reporting bug — see backlog.

### Approval inventory

| State | Count |
|-------|-------|
| Originally created | 9 |
| Approved (internal handoff) | 1 (`eml_bb713db199a445739549`) |
| Still pending | 8 |

### Related docs

- `docs/NIKLAS_DEMO_SETUP.md` — setup runbook  
- `docs/NIKLAS_DEMO_READINESS_CHECKLIST.md` — rehearsal checklist  
- `docs/demo/martens-gmail-demo-scenarios.md` — scenario ideas (label-scoped only on prod)

---

*Document purpose: operator demo script + production testlog. No secrets. No Gmail re-processing.*
