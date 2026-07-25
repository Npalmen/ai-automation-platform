# Internal live pilot — Exekveringsrapport

**Plan:** `docs/plans/internal-live-pilot-plan.md` v1  
**Operator approval:** 2026-07-25 (uttryckligt)  
**Required deploy SHA:** `d97f1f9420128f3e1379a2ebd7bd7a4241fa4621`  
**Status:** **STOP — aktivering ej utförd**

---

## Resultat

| Steg | Status | Detalj |
|---|---|---|
| 1. Verifiera server-SHA | **FAIL** | Server `/opt/krowolf` @ `b196132` — inte `d97f1f9` |
| 2. Readiness utan Gmail | **BLOCKERAD** | `internal_pilot_readiness.py` ej deployad på server |
| 3. Precondition-check | **PARTIAL** | DB/Gmail OAuth OK; endast **2/3** nya mejl i scope |
| 4. Aktivering | **EJ KÖRD** | Blockerad av steg 1–3 |
| 5. Första livebatch | **EJ KÖRD** | — |
| 6. Post-batch verifiering | **EJ KÖRD** | — |
| Pause/rollback | **EJ BEHÖVD** | Ingen liveaktivering utförd |

---

## Steg 1 — Server-SHA

| Källa | SHA |
|---|---|
| Krav | `d97f1f9420128f3e1379a2ebd7bd7a4241fa4621` |
| `origin/main` (GitHub) | `d97f1f9` ✅ |
| Produktion `/opt/krowolf` HEAD | `b196132ff683ffeed577540d648072787c372776` ❌ |
| `app/internal_pilot/` på server | **Saknas** |
| `scripts/internal_pilot_*.py` på server | **Saknas** |

**Root cause:** Pilot-gates (PR #38) är mergade till `main` men **inte deployade** till `api.krowolf.se`. Operatörsmeddelande förbjöd deployment utöver angiven pilotversion — därför kunde agenten inte deploya.

---

## Steg 2–3 — Readiness (utan live batch)

### `stabilization_preflight.py` (DB, ingen write) — PASS

```json
{
  "tenant": "T_NIKLAS_DEMO_001",
  "health_http": 200,
  "tenant_count": 1,
  "scheduler_run_mode": "paused",
  "gmail_credential_source": "tenant_oauth",
  "gmail_connected": true,
  "backup": { "status": "success", "offsite_verified": true },
  "blockers": [],
  "pass": true
}
```

### Tenant settings (produktion DB)

| Kontroll | Status |
|---|---|
| Exakt rätt tenant | ✅ `T_NIKLAS_DEMO_001` (enda tenant) |
| Scheduler paused | ✅ |
| Gmail OAuth connected | ✅ `tenant_oauth` |
| `automatic_gmail_replies` | ✅ ej true (null) |
| `demo_mode` | ✅ false |
| `internal_pilot.live_scan_enabled` | ⚪ ej satt (modul ej deployad) |
| `auto_actions` | ⚪ tom dict (default policy vid runtime) |
| Aktiva Live Eval-runs | ✅ 0 (`evaluation_runs` tabell saknas på prod) |
| Backup/restore | ✅ success, offsite verified 2026-07-25 |

### Gmail dry-run precheck (`pilot_gmail_soak_first_scan.py 3`)

| Fält | Värde |
|---|---|
| Query | `label:krowolf-demo-niklas is:unread` |
| Scanned | 2 |
| Duplicates | 0 |
| **New candidates** | **2** |
| Min required | 3 |
| ready_for_live_scan | **false** |

**Root cause #2:** Endast 2 nya olästa mejl i label-scope — behöver minst **1 till** (lead + support + oklart).

---

## Säkerhet

| Invariant | Status |
|---|---|
| Live batch körd | **Nej** |
| `internal_pilot_activate.py` | **Ej körd** |
| External writes | 0 |
| Automatiska Gmail-svar | 0 |
| Scheduler aktiverad | Nej (fortfarande paused) |
| Pause-script | Ej kört (ej behövt) |

---

## Rekommendation

### GO/NO-GO för daglig soak: **NO-GO**

**Blockerare att lösa före ny aktiveringsförsök:**

1. **Deploy** `d97f1f9420128f3e1379a2ebd7bd7a4241fa4621` till `api.krowolf.se` (kräver separat deploy-godkännande enligt din scope-lista)
2. **Lägg till 1 nytt oläst testmejl** under `krowolf-demo-niklas` så batchen blir exakt 3 (lead + customer_inquiry + oklart/unsupported)

**Efter deploy + 3 mejl — kör i ordning på server:**

```bash
sudo docker exec -e PYTHONPATH=/app krowolf-app-1 \
  python3 /app/scripts/internal_pilot_readiness.py \
  --baseline-git-sha d97f1f9420128f3e1379a2ebd7bd7a4241fa4621

sudo docker exec -e PYTHONPATH=/app krowolf-app-1 \
  python3 /app/scripts/internal_pilot_activate.py --enable-live --confirm-operator

sudo docker exec -e PYTHONPATH=/app krowolf-app-1 \
  python3 /app/scripts/ops/pilot_gmail_soak_first_scan.py 3
```

---

## Todos

| Todo | Status |
|---|---|
| pilot-a | ✅ completed |
| pilot-b B1 | ✅ merged |
| pilot-b B3 aktivering | ⏸️ blocked (SHA + mejl) |
| pilot-c | ⏸️ ej påbörjad (medvetet) |
