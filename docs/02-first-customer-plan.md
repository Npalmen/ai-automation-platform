# First Customer Plan

> Governed by `docs/00-master-plan.md`. If this document conflicts with the master plan, the master plan wins.

---

## Purpose

Define exactly what is required to get the first customer live, what is acceptable manual work, what is not acceptable, and what the go/no-go criteria are.

---

## First customer type

1. **Intern testkund** — internal use, zero risk, maximum learning.
2. **Vänner/pilotkunder** — närstående bolag, low risk, real feedback.
3. **Första betalande kund** — a real customer, ideally from the existing lead list of ~200 small businesses.

---

## Customer setup approach

- Admin/manuell konfig är okej för första kund.
- Kunden behöver inte full self-service onboarding från dag ett.
- Initial setup kan ske med hjälp.
- After setup, common fixes shall be resolvable remotely without an on-site visit.

---

## Required systems

- Gmail (intake-kanal, first priority)
- Monday (operations/project flow, where available)
- Fortnox (read/preview/approval-gated only — no free bookkeeping)
- Admin panel for tenant config
- Approval queue for high-risk actions

---

## Minimum live flow

Systemet ska minst kunna:

1. Läsa inkommande information (Gmail inbox sync).
2. Förstå uppgiftstyp (classification — lead/support/customer_inquiry/invoice/unknown/spam) och hellre välja `unknown`/mänsklig hantering än felaktig självsäker automation.
3. Skapa/uppdatera ärende (case record in DB).
4. Föreslå eller utföra låg-risk action enligt policy.
5. Svara eller förbereda svar (approval-gated email draft).
6. Skicka vidare till rätt system/person (Monday item, internal handoff).
7. Visa status och sparad tid (customer dashboard / wow-statistik).

---

## Admin responsibilities

- Create tenant via Super Admin.
- Store API key securely (shown once).
- Configure modules, integrations, automation levels.
- Run setup verification and pilot readiness check.
- Monitor needs-help queue during pilot.
- Own escalation path for critical issues.

---

## Customer-facing UI requirement

- Must show: status overview, ROI/saved time, recent cases.
- Must not expose: raw job IDs, routing internals, environment details, raw payloads.
- Nice to have: daily digest email, notification settings.
- Full self-service is not required for first customer.

---

## Acceptable manual work

- Skapa tenant/kund manuellt via admin eller script.
- Hjälpa kunden koppla integrationer vid första onboarding.
- Sätta routing-regler och automation policy manuellt.
- Justera kundens systemkarta efter första scan.
- Göra första kontrollen av integration health manuellt.
- Godkänna känsliga actions manuellt.
- Anpassa vissa kundspecifika fält under första veckan.

---

## Unacceptable manual work

- Behöva logga in hos kunden varje dag för att hålla systemet igång.
- Manuellt flytta varje mejl till rätt ärende.
- Manuellt skapa alla ärenden som appen borde skapa.
- Manuellt upptäcka döda integrationer genom kundklagomål.
- Manuellt läsa råloggar för att förstå enkla fel.
- Manuellt rätta dubletter som systemet skapar löpande.
- Behöva åka ut till kunden för vanliga fixes efter initial setup.

---

## Live verification requirement

**Live verification must be green before the first sharp pilot starts.**

The complete live verification plan is in `docs/10-live-verification-plan.md`.
It covers production health, admin/auth, tenant provisioning, customer endpoints,
integration health, Gmail OAuth, Monday/Fortnox/Visma safe checks, approval queue,
customer UI, and smoke check.

All 16 go/no-go gates in Phase L of the live verification plan must pass before
declaring Fas 2 pilot ready. Initial setup may be done admin/manually — full
self-service onboarding is not required for the first customer.

---

## Go/no-go checklist

Minst följande måste vara sant innan pilot:

- [ ] Gmail intake works (inbox sync reads and creates cases).
- [ ] Customer/tenant config works (admin can provision and configure).
- [ ] Integration health is visible (`GET /integrations/health`).
- [ ] Failed jobs are visible (needs-help queue or case error section).
- [ ] Approval queue works (email and dispatch approvals can be approved/rejected).
- [ ] Basic case/task flow works (lead → case → approval → send/dispatch).
- [ ] Admin can see what happened (audit trail, case detail, support console).
- [ ] Low-risk actions follow customer policy (full_auto or semi based on config).
- [ ] High-risk actions are approval-gated (email send, Fortnox export).
- [ ] Customer/wow view shows status and saved time.
- [ ] No dev-mode dependency in production (`ENV=production`, auth fails closed).
- [ ] No raw internal payloads exposed to customer in UI.
- [ ] OAuth/token issues are visible before they cause silent failures.
- [ ] Scheduler runs correctly (or manual trigger is documented and viable).
- [ ] At least one backup has been completed and verified.

---

## Local pre-live setup checklist

Run these steps locally before any live tenant onboarding. No live tokens required.
All commands use the local dev server (`http://localhost:8000`).

- [ ] **Provision pilot tenant via admin API**
  ```bash
  POST /admin/tenants
  Header: X-Admin-API-Key: <ADMIN_API_KEY>
  Body: {"name": "Intern Pilot AB", "slug": "intern-pilot",
         "enabled_job_types": ["lead", "customer_inquiry"],
         "allowed_integrations": ["google_mail", "monday"],
         "auto_actions": {"lead": false, "customer_inquiry": false}}
  # → tenant_id: T_INTERN_PILOT  |  api_key: kw_xxx... (store immediately, shown once)
  ```
- [ ] **Generate tenant API key** — included in the create response above. Rotate if needed:
  ```bash
  POST /admin/tenants/T_INTERN_PILOT/rotate-key
  Header: X-Admin-API-Key: <ADMIN_API_KEY>
  ```
- [ ] **Verify tenant API key accesses customer endpoints**
  ```bash
  GET /tenant
  Header: X-API-Key: kw_xxx...
  # → {"current_tenant": "T_INTERN_PILOT", ...}
  ```
- [ ] **Verify tenant key cannot access admin endpoints**
  ```bash
  GET /admin/tenants
  Header: X-API-Key: kw_xxx...    # wrong key type
  # → 401 or 403
  ```
- [ ] **Verify admin can inspect tenant**
  ```bash
  GET /admin/tenants
  Header: X-Admin-API-Key: <ADMIN_API_KEY>
  # → T_INTERN_PILOT listed
  ```
- [ ] **Verify pilot readiness reports missing live integrations**
  ```bash
  GET /pilot/readiness
  Header: X-API-Key: kw_xxx...
  # → overall_status: not_ready or almost_ready (expected before live)
  # → check which of 11 items are failing
  ```
- [ ] **Verify integration health reports disconnected/not configured state safely**
  ```bash
  GET /integrations/health
  Header: X-API-Key: kw_xxx...
  # → overall_status: not_configured (expected — no live tokens)
  # → no secrets in response
  ```
- [ ] **Verify customer dashboard loads with empty state (no crash)**
  ```bash
  GET /customer/results
  GET /customer/health
  Header: X-API-Key: kw_xxx...
  # → empty or zero-state response, HTTP 200
  ```
- [ ] **Verify test lead creation works (no external calls)**
  ```bash
  POST /onboarding/test-lead
  Header: X-API-Key: kw_xxx...
  # → job created, status: completed or awaiting_approval
  ```
- [ ] **Verify approval queue behavior with test action**
  ```bash
  GET /approvals/pending
  Header: X-API-Key: kw_xxx...
  # → [] for new tenant, or pending item if test lead triggered approval
  ```
- [ ] **Verify no live credentials are required for above steps** — all should complete
  without `GOOGLE_MAIL_ACCESS_TOKEN`, `MONDAY_API_KEY`, or live OAuth tokens.
- [ ] **Verify local core intelligence quality gate**
  ```bash
  python -m pytest tests/test_core_intelligence_quality.py -q
  ```
  # Expected: Swedish lead/support/customer inquiry/invoice/risk/approval evals pass
- [ ] **Verify local service profile qualification gate**
  ```bash
  python -m pytest tests/test_service_profiles_qualification.py -q
  ```
  # Expected: 82 service-profile tests pass (registry, selection, missing fields, follow-up questions, risk routing, tenant override seam)
- [ ] **Verify local golden path (service-profile aware pipeline)**
  ```bash
  python -m pytest tests/test_service_profile_pipeline.py tests/test_customer_reply_quality.py tests/test_tenant_routing_hints.py tests/test_local_golden_path.py -q
  ```
  # Expected: 82 tests pass (pipeline wiring, reply quality, tenant routing, golden path scenarios)

### Service profile / customer profile note

The system uses **service profiles** to adapt qualification, required fields, follow-up questions, and routing to the specific type of job (laddbox, solceller, elcentral, elfel, faktura, inkasso, etc.).

**Service profiles are now wired into the live pipeline (as of 2026-07-06 Local Final Spurt):**
- `lead_analyzer_processor` selects a service profile after analyzing the lead type; the profile drives question generation and is included in the payload as `service_profile_type`.
- `support_analyzer_processor` selects a service profile after analyzing the support ticket; included in payload as `service_profile_type`.
- `action_dispatch_processor` reads `generated_question_message` / `support_generated_question_message` from analyzer payloads and uses them for the customer auto-reply body when available.
- High-risk and risk-flagged cases (inkasso, legal threats, safety risk, reklamation) produce safe acknowledgement replies with `_needs_approval=True`.

During tenant setup/onboarding, the `TenantLeadContext` can be used to:
- restrict which service profiles are active (`services` list)
- override required fields per profile (`lead_requirements`)
- override routing per profile (`routing_hints`)
- personalise follow-up questions with company name (`company_name`)

Full self-service onboarding UI for this is deferred. For the first pilot customer, these settings are configured manually in tenant memory/settings via the admin API. See `app/service_profiles/qualification.py` → `apply_tenant_overrides()` for the seam description.

---

## Pilot baseline — T_NIKLAS_DEMO_001 (2026-07-20)

> **Status:** Clean operational baseline PASS. Redo för soak Dag 1 (live scan väntar på 3–5 nya olästa mejl).

| Item | Value |
|------|--------|
| Pilot tenant | `T_NIKLAS_DEMO_001` only (whitelist cleanup 2026-07-19) |
| Canonical commit | See `docs/DOCUMENT_INDEX.md` — tag `krowolf-pilot-baseline-20260720-final` |
| Gmail OAuth | Tenant-bound (`credential_source=tenant_oauth`) via `/ops/customers/...` |
| Krowolf Gmail scopes | `gmail.readonly`, `gmail.modify` only |
| Stored Google grant | May include legacy scope superset (`gmail.send`, `spreadsheets`) — **do not invoke** |
| Gmail send | **Disabled** — approval-first; `action_executor` send-gap documented in backlog |
| Scheduler | **Paused** — manual scans only during soak |
| Legacy `/ui` | Read-only — use `/ops` |
| Backup | Offsite S3 verified; canonical cron `krowolf-backup-canonical.sh` |

### Go/no-go för soak Dag 1

- [x] Kapitel 12 GO (DEC-030)
- [x] Tenant OAuth connected + test-read PASS
- [x] Clean baseline: jobs=0, approvals=0, tenant alerts=0
- [x] Scheduler paused
- [ ] Operator adds 3–5 new unread messages under `label:krowolf-demo-niklas`
- [ ] First live scan (`pilot_gmail_soak_first_scan.py`) — **not run yet**

### Deprecated pilot docs

Do not use for current truth: `docs/NIKLAS_DEMO_SETUP.md`, `docs/niklas-demo-production-testlog.md`, `docs/MARTENS_DEMO_*`. See `docs/DOCUMENT_INDEX.md`.

---

## Pilot success criteria

After the pilot is live, the following define success:

- Kunden lägger märkbart mindre tid på manuell e-posthantering.
- Inga leads tappas utan att operatören notifieras.
- Inga mail skickas till kunder utan godkännande.
- Admin kan hantera vanliga driftproblem utan att kontakta plattformsteam.
- Systemet körs stabilt i minst 2 veckor utan manuell omstart.

---

## Support model

| Issue type | Response |
|------------|---------|
| System down | Platform team — omedelbart |
| OAuth/token problem | Platform team — inom 1h (se `docs/08-runbook.md`) |
| Felklassificering | Rapportera via ärendedetalj → Manuell granskning |
| Kundmail skickat fel | Platform team + pilot-kund — omedelbart |
| Felaktig dispatch | Avbryt via approval-reject, kontakta platform team |
| Dataproblem | Platform team — within business hours |

Remote support is the norm after initial setup. On-site visits are not part of the standard support model.
