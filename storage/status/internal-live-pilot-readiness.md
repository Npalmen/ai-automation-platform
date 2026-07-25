# Internal live pilot — Readiness audit (pilot-a)

**Plan:** `docs/plans/internal-live-pilot-plan.md` v1  
**Auditdatum:** 2026-07-25  
**Baseline:** `origin/main @ 9c16f66f6cddcf5ea5fb8e1e26b4a312ea9d354a`  
**Release Gate:** `30170515163` — success  
**Metod:** Read-only audit (ingen Gmail, OAuth, scheduler eller extern write)

---

## Vald pilotkonfiguration

| Parameter | Värde | Evidens |
|---|---|---|
| Pilottenant | `T_NIKLAS_DEMO_001` | DEC-030, `docs/00-master-plan.md`, `docs/niklas-gmail-soak-log.md` |
| Gmail label scope | `demo-niklas` | `app/admin/onboarding/integration_fingerprint.py:52-58` |
| Gmail query | `label:krowolf-demo-niklas is:unread` | `scripts/ops/pilot_gmail_soak_first_scan.py:16` |
| Max batch | 5 mejl | `GmailProcessInboxRequest.max_results` default 5; pilot cap 5 |
| Första batch | 3–5 mejl | Plan §B3, soak script `MIN_NEW=3` |
| Scheduler | `paused` / `manual` | `docs/niklas-gmail-soak-log.md`, master plan 2026-07-20 |
| Gmail send | disabled | Approval-first; `PILOT_GMAIL_SCOPES` = readonly+modify |
| External writes | blocked | Monday/Visma/Sheets ej auto i pipeline |

---

## Readiness PASS/FAIL per kontroll

| Kontroll | Status | Evidens |
|---|---|---|
| `origin/main` grön | **PASS** | CI `30170515163` |
| 2G closure intakt | **PASS** | Artifact `632a159`, `overall_status=passed` |
| Exakt en pilottenant (policy) | **PASS** | `T_NIKLAS_DEMO_001` whitelist i docs |
| Tenant OAuth (historisk) | **PASS** | `01-current-truth.md` — connect 2026-07-19 |
| Mailbox scope begränsat | **PASS** | Label query `krowolf-demo-niklas` |
| Approval-first | **PASS** | `action_dispatch_processor._email_needs_approval`, default `semi` |
| Scheduler pausbar | **PASS** | `disable-scheduler`, `pause-automation` endpoints |
| Operatör `/ops` | **PASS** | overview, customers, needs-help, incidents, system |
| Cockpit API | **PASS** | `GET /dashboard/cockpit` (`app/main.py:2539`) |
| Backup/restore signal | **PASS** | K12 offsite verified 2026-07-19/20 per soak log |
| Live scan ej körd | **BLOCKER (operatör)** | Soak log: 0 nya kandidater; behöver 3–5 olästa märkta mejl |
| Pilot live gate (kod) | **PASS (efter B1 merge)** | `app/internal_pilot/gates.py` — `live_scan_enabled` required |
| Legacy kund-UI approvals | **WARN** | `LEGACY_UI_READ_ONLY=true` — ej primär aktiveringsyta |

**Overall readiness:** **PASS med operatörsblocker** — teknisk förberedelse OK; liveaktivering väntar på operatör + testmejl.

---

## Jobbtyper i pilot

| Typ | Ingår | Policy |
|---|---|---|
| lead | Ja | approval-first, offer draft preliminary |
| customer_inquiry | Ja | approval-first reply draft |
| invoice | Ja | routing/handoff, ej auto-send |
| unknown | Ja | fail-closed → manual review |

---

## Integrationer

| Integration | Pilotläge |
|---|---|
| Gmail read/modify | Tillåten efter operatörsgodkännande, scoped query only |
| Gmail send | **BLOCKERAD** (approval path only; ej auto) |
| Monday | Read/write endast via approval; ej auto full_auto i pilot |
| Sheets | Manuell export only |
| Visma | Approval-gated export only |

---

## Rollbackkommandon

```bash
# DB-safe pause (efter B1 deploy)
python scripts/internal_pilot_pause.py --execute

# API-alternativ
curl -X POST https://api.krowolf.se/admin/support/T_NIKLAS_DEMO_001/disable-scheduler ...
curl -X POST https://api.krowolf.se/admin/support/T_NIKLAS_DEMO_001/pause-automation ...
```

---

## Manuella steg före live (operatör)

1. Lägg 3–5 **nya olästa** mejl under `label:krowolf-demo-niklas` (lead, support, oklart, ev. faktura)
2. Verifiera `/ops` → kund `T_NIKLAS_DEMO_001` → Gmail OAuth connected
3. Kör readiness: `python scripts/internal_pilot_readiness.py`
4. Efter godkännande: `python scripts/internal_pilot_activate.py --enable-live --confirm-operator`
5. Första batch: `python scripts/ops/pilot_gmail_soak_first_scan.py 3`
6. Granska jobs/approvals i `/ops/needs-help`; **godkänn inte send** utan explicit beslut

---

## Rekommenderad pilotperiod

5–10 arbetsdagar (plan §C), mål 50–100 mejl totalt efter första batch.

---

## Gate

**Fortsätt till B1 implementation:** JA  
**Fortsätt till live Gmail (B3):** NEJ — kräver `OPERATOR ACTION REQUIRED`
