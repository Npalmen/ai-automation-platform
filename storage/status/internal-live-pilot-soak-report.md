# Internal live pilot — Soak logg

**Tenant:** `T_NIKLAS_DEMO_001`  
**Scope:** `label:krowolf-demo-niklas is:unread`  
**Status:** **Ej påbörjad — aktivering blockerad**

---

## Dag 0 — aktiveringsförsök (2026-07-25)

Operatörsgodkännande mottaget. Agenten körde preflight men **ingen live batch**.

### Blockerare

1. **Deploy-SHA:** produktion @ `b196132` ≠ krav `d97f1f9` (pilot-gates ej deployade)
2. **Testmejl:** dry-run visar **2** nya kandidater, krav **3**

### Dry-run precheck (read-only Gmail list)

| Metric | Value |
|---|---|
| phase | awaiting_operator |
| scanned | 2 |
| duplicates | 0 |
| new_candidates | 2 |
| min_required | 3 |
| ready_for_live_scan | false |
| live_scan | skipped |

### Metrics (oförändrade)

| Metric | Value |
|---|---|
| live_scans | 0 |
| emails_processed | 0 |
| external_writes | 0 |
| app_replies_sent | 0 |
| approval_bypasses | 0 |
| incidents | 0 |

---

## Planerad första batch (ej körd)

| # | Typ | Status |
|---|---|---|
| 1 | Lead | ⏳ väntar 3:e mejlet + deploy |
| 2 | customer_inquiry/support | ⏳ |
| 3 | oklart/unsupported | ⏳ |
| 4 | Faktura | Medvetet utelämnad tills batch 1 verifierad |

---

## Findings

| ID | Kategori | Beskrivning |
|---|---|---|
| F-001 | `scheduler_issue` / deploy | Pilotversion `d97f1f9` ej deployad till produktion |
| F-002 | `operator_ui_friction` | Endast 2/3 testmejl i label-scope |

---

## GO/NO-GO daglig soak

**NO-GO** — löses först deploy + tredje testmejl, sedan ny aktiveringskörning.

---

## Daily entries

_(inga live-dagar ännu)_
