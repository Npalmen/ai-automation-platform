# Kapitel 12 — Release notes (pilot RC)

> **Releasebeslut:** **CONDITIONAL GO** (2026-07-18)  
> **RC image:** `krowolf-app:rc-56b18882a9aa` (pilot `api.krowolf.se`)

## Release decision

| Gate | Status |
|------|--------|
| Slice 1 | PASS |
| Slice 2 + RB-01 | PASS |
| Slice 3 | PARTIAL |
| Security | PASS (196 tests) |
| Full regression | PASS (3586 pass / 0 fail) |
| Authenticated browser | PARTIAL (credentials required) |
| **Overall** | **CONDITIONAL GO** |

**Pilot scope:** max 3 tenants; scheduler paused until operator enable; `/ops` primary UI; legacy `/ui` read-only only.

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
- Route policy + statisk browser/a11y-audit
- Legacy beslut **B** (read-only fallback)
- Security bundle PASS
- Full regression (se rapport för exakta tal)
- Runbook-dokumentationsövning

## Kända begränsningar (pilot)

- Legacy `/ui` finns kvar read-only — använd `/ops`
- Recovery via API/runbook, inte React
- OAuth tokens plaintext (F05, accepterad DEC-028)
- CSP ej satt (accepterad)
- Max 3 pilottenants rekommenderas; scheduler pausad tills operatör aktiverar

## Operatör — start

1. Logga in på `https://api.krowolf.se/ops/login`
2. Bekräfta scheduler `paused` per tenant
3. Följ `docs/08-runbook.md` och `docs/runbooks/backup-and-restore.md`
