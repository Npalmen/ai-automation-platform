# Document Index (Canonical)

> **Governing hierarchy:** `docs/00-master-plan.md` → this index → listed canonical docs → deprecated/archive docs.
> Last updated: **2026-07-20** (Stabilization reconciliation — tag `krowolf-pilot-baseline-20260720-final`).

---

## Canonical (use these)

| Document | Purpose |
|----------|---------|
| `docs/00-master-plan.md` | Product direction, phase order, scope control |
| `docs/01-current-truth.md` | Verified system state (no vision) |
| `docs/02-first-customer-plan.md` | First customer / Niklas pilot scope |
| `docs/04-execution-rules.md` | How execution agents work |
| `docs/05-architecture.md` | Architecture reference |
| `docs/06-backlog.md` | Completed work and open items |
| `docs/07-decisions.md` | Locked decisions (DEC-*) |
| `docs/08-runbook.md` | Pilot operations runbook |
| `docs/09-testing-and-release.md` | Test and release gates |
| `docs/google-cloud-oauth-setup.md` | Google Cloud + tenant OAuth setup |
| `docs/niklas-gmail-soak-log.md` | 7-day Gmail soak procedure and status |
| `docs/kapitel-12-release-notes.md` | Kapitel 12 GO decision and release scope |
| `frontend/README.md` | Frontend build, contracts, operator panel |
| `docs/DOCUMENT_INDEX.md` | This file |
| `docs/onboarding-2.0-architecture.md` | Onboarding 2.0 architecture (DEC-032) |

---

## Pilot baseline (2026-07-20)

| Item | Value |
|------|-------|
| **Canonical Git commit** | `krowolf-pilot-baseline-20260720-final` (see `git rev-parse`) |
| **Historical tag** | `krowolf-pilot-baseline-20260720` → `7855151` (superseded, retained) |
| **Pilot tenant** | `T_NIKLAS_DEMO_001` only |
| **Scheduler** | `paused` |
| **Gmail** | `credential_source=tenant_oauth`, send disabled |
| **Deploy model** | Modell A — Git HEAD = canonical; RC-bundle + `krowolf-app:rc-<sha12>` |
| **Image tag pattern** | `krowolf-app:rc-<sha12>` |

---

## Runtime evidence (server, not Git)

| Path | Purpose |
|------|---------|
| `/opt/krowolf/storage/status/pre_live_niklas_archive.json` | Pre-clean Niklas data archive (Del H) |
| `/opt/krowolf/storage/status/niklas_live_clean_baseline.json` | Post-clean operational baseline (Del J) |
| `/opt/krowolf/storage/status/stabilization_server_inventory.json` | Server reconciliation inventory (Del D) |
| `/opt/krowolf/storage/status/backup_status.json` | Latest backup/offsite status |

---

## Deprecated / superseded (do not use for current truth)

| Document | Superseded by |
|----------|----------------|
| `docs/NIKLAS_DEMO_SETUP.md` | `docs/02-first-customer-plan.md`, `docs/08-runbook.md` |
| `docs/NIKLAS_DEMO_READINESS_CHECKLIST.md` | `docs/PILOT_READINESS_CHECKLIST.md` |
| `docs/MARTENS_DEMO_SETUP.md` | N/A — Martens tenant removed from pilot |
| `docs/MARTENS_DEMO_READINESS_CHECKLIST.md` | N/A — Martens tenant removed |
| `docs/niklas-demo-production-testlog.md` | `docs/niklas-gmail-soak-log.md`, `docs/01-current-truth.md` |
| `docs/chapter-9-inventory.md` | `docs/01-current-truth.md` |
| `docs/kapitel-12-release-inventory.md` | `docs/kapitel-12-release-notes.md` |
| `docs/kapitel-12-slice3-legacy-parity.md` | `docs/kapitel-12-release-notes.md` (legacy `/ui` read-only note) |
| `docs/PILOT_TRANSITION.md` | `docs/02-first-customer-plan.md` (historical transition pack) |

---

## Archive policy

- Historical release/browser reports under `/opt/krowolf/storage/status/archive/` are read-only evidence.
- Do not delete release/security regression reports without archiving first.
- Secrets, tokens, and `.env*` files are never committed to Git.
