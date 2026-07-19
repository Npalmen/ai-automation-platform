# Kapitel 12 — Release notes (pilot RC)

> **Releasebeslut:** **GO** (2026-07-19)  
> **Pilot:** `api.krowolf.se` — `ADMIN_ROLE=admin` (avsedd operatörsroll)

## Release decision

| Gate | Status |
|------|--------|
| Slice 1 | PASS |
| Slice 2 + RB-01 | PASS |
| Slice 3 | PASS |
| Security | PASS (240 tests, 2026-07-19) |
| Full regression | PASS (3589 pass / 0 fail) |
| Authenticated browser | PASS (read_only, operations, admin) |
| Browser aggregate | PASS (`/opt/krowolf/storage/status/kapitel12_browser_report.json`) |
| Frontend gates | PASS |
| **Overall** | **GO** |

**Pilot scope:** max 3 tenants; scheduler paused until operator enable; `/ops` primary UI; legacy `/ui` read-only only.

## Browser matrix (2026-07-19)

| Role | Report | Status |
|------|--------|--------|
| read_only | `k12_browser_read_only_report.json` | PASS |
| operations | `k12_browser_operations_report.json` | PASS (+ Del 7 alert/incident) |
| admin | `k12_browser_admin_report.json` | PASS (+ suppress, key rotation) |

All reports: `credentials_exposed=false`, `external_side_effects=0`.

Aggregate: `sudo python3 /opt/krowolf/scripts/kapitel12_browser_aggregate.py --status-dir /opt/krowolf/storage/status`

## Accepterade safe boundaries (pilot)

These are **not** counted as executed PASS and do **not** block the browser aggregate:

| Item | Status | Motivering | Verifiering |
|------|--------|------------|-------------|
| Alert suppress UI | `not_mounted` | Ingen suppress-knapp i `AlertDetailPage` | Admin suppress **API PASS**; registry `suppress_allowed`; security bundle |
| Recovery retry (success path) | `not_executed_safe_boundary` | Pipeline rerun kan trigga integrationer | Cross-tenant block PASS (Del 7); `tests/test_recovery_actions.py` |
| replay/reclassify/re-extract/resend/gmail | `not_executed_safe_boundary` | Externa writes/e-post/Gmail | Security bundle + kontraktstester |
| controlled_dispatch approve | `not_executed_safe_boundary` | Kan skriva till integration adapter | Reject + stale 409 PASS; approve permissions i security bundle |

**Bedömning:** accepterade pilotbegränsningar — **inte releaseblockerare**. Suppress UI = post-pilot UI-gap (F14).

## Verifierat i denna release

### Slice 1 — Golden paths och roller
- Golden paths A–I (pytest)
- Approval-first i React `/ops`
- Roller: `read_only`, `operations`, `admin`
- Tenantisolering

### Slice 2 — Pilot, backup, RB-01
- Reproducerbar RC deploy + rollback
- Profil A/B mot live pilot
- S3 offsite backup + restore från offsite-kopia
- Isolerad restore-app (`:8001`)
- Backupincidenter
- Canonical cron via `krowolf-backup-canonical.sh`
- **RB-01 PASS**

### Slice 3 — Browser, legacy, security, regression
- Autentiserad CDP-browsermatris alla tre roller
- Operations Del 7 (alert/incident/audit/stale/cross-tenant)
- Admin suppress + API-key rotation (fingerprint only in reports)
- Route policy + statisk browser/a11y-audit
- Legacy beslut **B** (read-only fallback)
- Security bundle PASS (240)
- Full regression 3589/0
- Runbook-dokumentationsövning

## Kända begränsningar (pilot)

- Legacy `/ui` finns kvar read-only — använd `/ops`
- Recovery via API/runbook, inte React
- Alert suppress: API only, ingen UI-knapp (F14)
- OAuth tokens plaintext (F05, accepterad DEC-028)
- CSP ej satt (accepterad)
- Max 3 pilottenants rekommenderas; scheduler pausad tills operatör aktiverar
- Rapport-redaction: fält som innehåller substring `admin` kan visas som `[REDACTED]` om browser-credentials innehåller samma substring — körlogg bekräftar roll

## Operatör — start

1. Logga in på `https://api.krowolf.se/ops/login`
2. Bekräfta scheduler `paused` per tenant
3. Följ `docs/08-runbook.md` och `docs/runbooks/backup-and-restore.md`
