# Kapitel 12 — Legacy parity och pilotfallback (Slice 3)

> **Beslut:** **B — Begränsad pilotfallback** (2026-07-18)  
> **Primär UI:** `/ops` (React)  
> **Legacy:** `/ui` read-only med deprecation-banner

## Paritetsmatris

| Flöde | React `/ops` | Legacy `/ui` | Pilotkritiskt | Status |
|-------|--------------|--------------|---------------|--------|
| Overview | `/ops` | Dashboard | Ja | **PASS** |
| Customers + onboarding | `/ops/customers` | Wizard | Ja | **PASS** |
| Needs-help + manual review | `/ops/needs-help` | Admin needs-help | Ja | **PASS** |
| Approvals approve/reject | Operator actions | Approvals tab | Ja | **PASS** |
| Incidents | `/ops/incidents` | — | Ja | **PASS** |
| Alerts + detail | `/ops/alerts` | — | Ja | **PASS** |
| Digests | `/ops/digests` | — | Ops+ | **PASS** |
| Usage | `/ops/usage` | KPI views | Ja (read) | **PASS** |
| System / backup status | `/ops/system` | Integration health | Ja | **PASS** |
| Recovery | API/runbook | Recovery console | Medel | **PARTIAL** — React saknas |
| Jobs browser | Metrics på kunddetalj | Job views | Medel | **PARTIAL** |
| Manual review queue | Counts på overview | — | Medel | **PARTIAL** |
| Alert snooze/suppress | API only | — | Låg | **PARTIAL** |

## Legacy-säkerhet (verifierat)

| Kontroll | Status |
|----------|--------|
| `LEGACY_UI_READ_ONLY = true` | PASS |
| Inga `localStorage.setItem(LS_ADMIN_KEY)` | PASS |
| `_purgeLegacyAdminKeyStorage()` | PASS |
| Skrivblock i `adminApiFetch` | PASS |
| Deprecation-banner | PASS |
| GET-only state-changing inventory | PASS |

## Kvarvarande gap — ägare och deadline

| Gap | Workaround | Ägare | Deadline |
|-----|------------|-------|----------|
| Recovery UI | `POST /admin/recovery/*` + runbook | Platform | Efter första pilot |
| Jobs list/detail | Customer detail metrics + API | Platform | Efter första pilot |
| Dedikerad manual-review-kö | Overview / needs-help | Platform | Efter första pilot |
| Alert snooze UI | API `/admin/alerts/{id}/suppress` | Platform | Efter första pilot |

## Full avveckling (ej nu)

Full avveckling (410/redirect, ta bort `app/ui/index.html` ur runtime) kräver:

1. Recovery-flöde i React eller godkänd runbook-only permanent
2. Ingen operatör använder legacy för dagliga flöden (verifierat: `/ops` primary)
3. Tester som förhindrar write-bypass i legacy

**Mål:** post-first-pilot release.
