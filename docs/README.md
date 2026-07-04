# Documentation Index

> `docs/00-master-plan.md` is the governing document. If any other document conflicts with it, the master plan wins.

---

## Start here

| Document | Purpose |
|----------|---------|
| [`00-master-plan.md`](00-master-plan.md) | **Governing document** — product direction, scope, phase plan, forbidden scope, execution governance |

---

## Current execution

| Document | Purpose |
|----------|---------|
| [`01-current-truth.md`](01-current-truth.md) | Verified system state — what actually works, what is unverified |
| [`02-first-customer-plan.md`](02-first-customer-plan.md) | First customer go/no-go plan, acceptable manual work, success criteria |
| [`04-execution-rules.md`](04-execution-rules.md) | Rules for AI bots and consultants — read order, stop conditions, reporting format |
| [`90-cursor-prompt-template.md`](90-cursor-prompt-template.md) | Copyable prompt template for every new Cursor execution session |

---

## Technical

| Document | Purpose |
|----------|---------|
| [`05-architecture.md`](05-architecture.md) | System architecture — layers, pipelines, integrations, data stores, risk boundaries |
| [`08-runbook.md`](08-runbook.md) | Operations — failed jobs, integration health, OAuth, scheduler, approvals, escalation |
| [`09-testing-and-release.md`](09-testing-and-release.md) | Test commands, release gate, smoke check, pre-launch checklist |
| [`10-live-verification-plan.md`](10-live-verification-plan.md) | **Live verification plan** — sequential production verification for first pilot tenant (not yet run) |

---

## Planning

| Document | Purpose |
|----------|---------|
| [`03-product-roadmap.md`](03-product-roadmap.md) | Phase roadmap — constrained to master plan; long-term items marked clearly |
| [`06-backlog.md`](06-backlog.md) | Backlog — Now / Next / Later / Explicitly Not Now |
| [`07-decisions.md`](07-decisions.md) | Locked product decisions DEC-001 to DEC-022 |

---

## Historical (archive)

Old documents are in [`archive/`](archive/). They are for reference only. They are not governing.

Each archived file starts with:
> `Archived document. Historical reference only. Current governing source is docs/00-master-plan.md.`

Notable archives:
- `archive/legacy-05-current-state.md` — detailed historical implementation log
- `archive/legacy-08-handoff.md` — full session handoff history
- `archive/legacy-07-technical-decisions.md` — old technical ADRs (DEC-001 to DEC-006)
- `archive/legacy-12-production-guide.md` — full production deployment guide (historical)
- `archive/legacy-runbook-oauth.md` — Gmail OAuth runbook (historical)
- `archive/legacy-runbook-scheduler.md` — scheduler runbook (historical)
- `archive/legacy-runbook-pilot-support.md` — pilot support playbook (historical)
- `archive/legacy-15-golden-path.md` — lead-to-invoice golden path walkthrough (historical)
