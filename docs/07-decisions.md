# Decisions

Each decision records a locked product or execution decision. Execution agents may reference decisions but may not change them unless explicitly instructed by the user via a master plan update.

> Historical technical ADRs (DEC-001 to DEC-006 from earlier sessions) are preserved in `docs/archive/legacy-07-technical-decisions.md`.

---

## DEC-001 — Product category

**Status:** Locked  
**Decision:** The product is an operational AI control system for installation and service companies.  
**Reason:** This is the chosen product direction.  
**Consequence:** Features must support operational control, not generic chatbot behavior.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-002 — Core value proposition

**Status:** Locked  
**Decision:** The product shall reduce administrative work around the company's actual occupation.  
**Reason:** Customers should spend time on their core work, not administration.  
**Consequence:** Features that add administrative overhead rather than remove it are out of scope.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-003 — First customer strategy

**Status:** Locked  
**Decision:** First customer strategy is: internal test → friends/pilot → paying customer → lead list presentation.  
**Reason:** Risk-controlled entry to market. Learn before selling broadly.  
**Consequence:** Do not optimize for self-serve before the first paying customer.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-004 — Scope of first version

**Status:** Locked  
**Decision:** The first version shall not be a total complete solution for all niche companies.  
**Reason:** Scope must be contained to ship quickly and learn from real use.  
**Consequence:** Narrow niche features are out of scope until explicitly decided.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-005 — Task-driven system

**Status:** Locked  
**Decision:** The system shall be task-driven, not a single linear workflow.  
**Reason:** Different case types (lead/support/invoice) need different flows.  
**Consequence:** Architecture must support multiple pipelines, not one monolithic flow.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-006 — Automation risk control

**Status:** Locked  
**Decision:** Automation is allowed early but risk must be limited through customer policy, approval gates, and limited external actions.  
**Reason:** Customer trust depends on controlled, reversible automation.  
**Consequence:** High-risk actions must be approval-gated. Low-risk actions may be configured per customer.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-007 — Admin config is sufficient for first version

**Status:** Locked  
**Decision:** Admin configuration is sufficient for the first version. Full self-service onboarding is not required before first customer.  
**Reason:** Simpler to ship; customers can be onboarded with assistance.  
**Consequence:** Self-service onboarding is a later-phase feature.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-008 — Customer UI wow-statistics

**Status:** Locked  
**Decision:** Pilot customer UI should show wow-statistics, especially saved time and status.  
**Reason:** Demonstrates value visibly to the customer.  
**Consequence:** ROI/dashboard view is required for pilot. Deep analytics are not.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-009 — Primary integration areas

**Status:** Locked  
**Decision:** Primary integration areas are mail, economics/finance, and CRM/operations.  
**Reason:** These cover the core administrative friction for the target customer.  
**Consequence:** Integrations outside these areas are deprioritized.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-010 — Broad integrations before narrow

**Status:** Locked  
**Decision:** Broad integrations are prioritized before narrow niche integrations.  
**Reason:** Broad integrations serve more customers; narrow ones serve edge cases.  
**Consequence:** Do not build a narrow niche integration before broad coverage is adequate.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-011 — Execution agents choose technical path

**Status:** Locked  
**Decision:** Execution bots may choose the best technical path but may not change product strategy, prioritization or roadmap.  
**Reason:** Technical decisions belong to the execution agent; strategic decisions belong to the master plan.  
**Consequence:** Any strategic change must go through master plan update and this decisions log.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-012 — Pause and report on plan issues

**Status:** Locked  
**Decision:** If a bot discovers the plan appears wrong, it shall pause and report, not adjust the plan itself.  
**Reason:** Prevents uncontrolled strategic drift by execution agents.  
**Consequence:** Execution agents have a defined stop condition; see `docs/04-execution-rules.md`.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-013 — Aggressive documentation cleanup before building

**Status:** Locked  
**Decision:** Documentation shall be cleaned aggressively before continued building, but without losing verified technical history.  
**Reason:** Stale conflicting docs cause execution agents to drift.  
**Consequence:** Old docs go to archive; new governing structure is the source of truth.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-014 — Keep existing codebase

**Status:** Locked  
**Decision:** The current codebase is kept. No major rewrite before first customer.  
**Reason:** Rewriting delays shipping and destroys verified working behavior.  
**Consequence:** Improve incrementally; refactor only what is broken and within task scope.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-015 — Frontend only where needed for pilot

**Status:** Locked  
**Decision:** Frontend is improved only where needed for pilot, wow-statistics and understandability. No new frontend stack before first customer.  
**Reason:** Frontend stack change introduces large risk and scope creep.  
**Consequence:** Single-file `app/ui/index.html` (vanilla HTML/CSS/JS) remains the frontend. No React, Vite, Tailwind.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-016 — No new large integrations before first customer

**Status:** Locked  
**Decision:** New large integrations are forbidden before first customer, except integrations required for the chosen first customer.  
**Reason:** Integration work is large scope; must be deferred until customer needs are confirmed.  
**Consequence:** Only Gmail, Monday and Fortnox/Visma read-only are in scope for first customer.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-017 — Automatic actions allowed if low-risk and reversible

**Status:** Locked  
**Decision:** Automatic external actions are allowed if they are customer-configured, low-risk and reversible. High-risk actions shall be approval-gated.  
**Reason:** Automation must be safe and controllable.  
**Consequence:** See automation risk policy in `docs/00-master-plan.md`.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-018 — Fortnox/Visma read/preview/approval-gated

**Status:** Locked  
**Decision:** Fortnox and Visma shall initially be read/preview/underlag/approval-gated. Not free bookkeeping automation.  
**Reason:** Bookkeeping errors are high-risk and hard to reverse.  
**Consequence:** Any Fortnox write path must go through an approval gate. Dry-run preview is always available without write.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-019 — Gmail first intake channel

**Status:** Locked  
**Decision:** Gmail is the first prioritized intake channel because it already exists in the repo. Outlook/Microsoft Mail comes next.  
**Reason:** Existing implementation is the fastest path to first customer.  
**Consequence:** Do not build Outlook intake before Gmail is stable in pilot.  
**Can change if:** The master plan is explicitly revised.

---

## DEC-020 — Monday as primary operations channel

**Status:** Locked  
**Decision:** Monday is the primary operations/project channel until another CRM/operations system is chosen for a paying customer.  
**Reason:** Monday integration is already live-verified.  
**Consequence:** Build Monday depth before broad CRM expansion.  
**Can change if:** First paying customer explicitly requires a different system.

---

## DEC-021 — Krowolf brand retained

**Status:** Locked  
**Decision:** Krowolf is used until further notice technically. Brand rename is out of scope before first customer.  
**Reason:** Brand work is a distraction from shipping.  
**Consequence:** All technical references to Krowolf remain unchanged until a brand decision is made.  
**Can change if:** A separate strategic brand decision is made.

---

## DEC-022 — Pricing in roadmap but not blocking

**Status:** Locked  
**Decision:** Pricing strategy shall be added to the roadmap but shall not block technical first-customer work.  
**Reason:** Price discovery happens through pilot; it should not delay shipping.  
**Consequence:** First customer may be unpaid/pilot. Pricing model is defined in a later decision.  
**Can change if:** A separate pricing decision is made and documented here.

---

## DEC-023 — Pre-live UI is an internal operator console

**Status:** Locked  
**Decision:** Pre-live UI is an internal operator console. Polished customer UI is deferred.  
**Reason:** Before live verification, the owner needs a simple, readable admin/operator surface for tenant setup, readiness, integration health, approvals, cases, and support triage.  
**Consequence:** `app/ui/index.html` stays a single-file vanilla HTML/CSS/JS UI with minimal black/white styling. Do not optimize for a polished customer SaaS dashboard before Phase A-C is green and the pilot path is stable.  
**Can change if:** The master plan is explicitly revised or pilot feedback shows a customer-facing UI improvement is needed for first-customer operation.

---

## DEC-024 — New operator panel frontend stack approved (supersedes DEC-015 for this scope only)

**Status:** Locked

**Decision:** A new internal Krowolf operator panel may be built with a new frontend stack: React, TypeScript, Vite, shadcn/ui, Tailwind CSS, React Router, TanStack Query, and TanStack Table (only where advanced tables justify it).

**Reason:** The product owner has determined that the existing single-file `app/ui/index.html` operator console (DEC-004/DEC-015/DEC-023) is no longer a sustainable foundation for operating the platform at scale across many tenants, and that a structured, typed, testable frontend is required for the internal operator surface specifically. This is a deliberate, explicit product-owner decision made outside the normal roadmap cadence (Kapitel 0A/0B), not an execution-agent judgment call.

**Scope (what this decision covers):**
- Applies only to Krowolf's **internal operator panel** (the surface used by Krowolf staff to operate the platform across tenants).
- Does **not** apply to the customer portal, or to any other frontend initiative. DEC-015's restriction on a new frontend stack remains fully in force outside this specific scope.
- The backend continues to build on the existing FastAPI + PostgreSQL architecture. No backend rewrite is approved by this decision (DEC-014 is unaffected).
- Existing, working backend logic, auth mechanisms, data models, and endpoints must be reused where suitable, not rebuilt. New endpoints may be added per chapter where a concrete gap is identified, following normal execution rules.

**Deployment principle:**
- First recommended model: the frontend is built via a Node build stage; the resulting static frontend artifacts are packaged into the existing application image; FastAPI or a same-origin reverse proxy serves the panel.
- No separate frontend container is introduced in the first release unless a concrete need requires it.
- This is a first recommended model, not a permanent prohibition on a separate frontend deployment later — a later chapter may revisit this if independent deploy cadence becomes a real need.

**Security principle:**
- The browser must not store a raw admin API key as normal authentication for the new panel.
- Normal operator login must use a secure HttpOnly session.
- Operator identity and role must be derived server-side, not trusted from client state.
- Critical operator actions must be authorization-checked and audited.
- Tenant context must never substitute for authentication or authorization.

**Responsiveness principle:**
- The new panel must be a responsive web application — not two separate applications — supporting mobile, tablet, small laptop, desktop, and large screens.
- No supported view may have unintended global horizontal scroll, overlapping content, or controls positioned outside the viewport.

**Design governance:**
- The frontend's visual and functional rules shall be governed by machine-readable design contracts: `krowolf-ui-profile.json`, `component-contracts.json`, `page-contracts.json`.
- These contracts are created in a later chapter (Kapitel 1B per the Kapitel 0A chapter plan) and become authoritative for the frontend implementation once they exist. They do not exist yet as of this decision.

**Legacy UI policy:**
- `app/ui/index.html` is frozen legacy as of this decision. It is not removed, restructured, or partially dismantled during the initial frontend chapters (Kapitel 1A–1C and immediately following chapters).
- It must not be used as the visual or structural basis for the new panel.
- It remains available and fully functional for existing pilot and operations flows for as long as it exists.
- New functionality is built in the new panel once frontend work starts, not in legacy UI — unless an acute operational need requires an emergency fix in legacy UI, in which case the fix is applied to legacy UI and noted as a known duplication risk.
- A function-parity checklist (one line per existing `switchView` capability in `app/ui/index.html`) must exist and be verified complete before legacy UI is removed. This checklist is created in the chapter that begins legacy retirement work (Kapitel 5 per the Kapitel 0A chapter plan), not in this decision and not in Kapitel 0B.
- Legacy UI is removed only as a single, deliberate action once critical function parity and regression verification are approved for the whole surface — not via ad hoc, view-by-view deletion.

**Supersession — exactly what is overridden:**
- This decision supersedes **DEC-015 only for the scope defined above** (Krowolf's internal operator panel).
- DEC-015 remains fully **Locked and in force** for: the customer portal, any other frontend initiative, and any broader rewrite not explicitly approved by this decision.
- `docs/00-master-plan.md`'s "Forbidden scope now" entries "React/frontend rewrite." and "Ny frontend-stack." are narrowed by this decision to exclude the internal operator panel; they remain in force for all other frontend work (see updated note in that document).
- DEC-014 ("Keep existing codebase") is unaffected and continues to govern the backend without exception.
- DEC-023 (pre-live UI is an internal operator console) is unaffected as historical record of why `app/ui/index.html` looks the way it does; it does not block this decision's forward-looking scope.

**Can change if:** The master plan is explicitly revised, or a subsequent decision further restricts or expands this scope.

---

### DEC-024 — Deploy readiness matrix

Tracked here until items are verified, at which point verified items move to `docs/01-current-truth.md`.

**Required before Kapitel 1A (frontend foundation) — all items below must be true before any `frontend/` code is written:**

- [x] New governance decision locked — this entry (DEC-024).
- [x] Contradicting documents updated — `docs/00-master-plan.md`, `docs/05-architecture.md` (Kapitel 0B).
- [x] Legacy-UI policy documented — see "Legacy UI policy" above.
- [x] `frontend/` folder boundary decided — new top-level `frontend/` directory, sibling to `app/`, not nested inside it (decided in Kapitel 0A, restated here; not created in Kapitel 0B).
- [x] First deployment model documented — see "Deployment principle" above.

**Required before production deploy of the new panel (NOT required before Kapitel 1A):**

- [ ] Actual Caddy routing verified against the real production `infra/Caddyfile` (not retrieved in Kapitel 0B — see Caddy status in `docs/01-current-truth.md`).
- [ ] Caddy configuration version-controlled or reproducible from a committed source.
- [ ] Same-origin auth (session cookie + `X-Admin-API-Key`) verified against the real deployment target for the new panel.
- [ ] Frontend build integrated into the application image (Docker multi-stage build).
- [ ] Static routes and SPA fallback routing verified (deep links, 404 handling).
- [ ] Cache policy for static assets verified (does not serve stale bundles after deploy).
- [ ] Legacy UI (`app/ui/index.html`) confirmed still reachable and functional after the new panel is deployed alongside it.
- [ ] Rollback path documented (how to revert to legacy-only if the new panel deploy fails).

---

## DEC-025 — Operation status metadata schema (Kapitel 8)

**Status:** Locked  
**Date:** 2026-07-17

**Decision:** Backup, restore-rehearsal, and Docker build identity use small JSON files with `schema_version: 1`, written atomically (temp + rename), no credentials/commands/paths in payload.

| Artifact | Env / path | Writer |
|----------|------------|--------|
| Backup status | `BACKUP_STATUS_FILE` | `scripts/backup_postgres.sh` via `scripts/write_operation_status.py` |
| Restore status | `RESTORE_STATUS_FILE` | `scripts/restore_postgres_rehearsal.sh` via `scripts/write_operation_status.py` |
| Build metadata | `BUILD_METADATA_PATH` (`/app/build-metadata.json`) | `scripts/write_build_metadata.py` in Docker build |

Operation exit codes are independent of metadata write success. API reads files only; metadata-write failures after successful operations are visible in script logs, not in system status API.

**Can change if:** A deploy pipeline introduces a new cross-tool artifact format — then extend `schema_version` with a new decision, do not break v1 readers silently.

---

## DEC-026 — Tenant settings schema v2 for onboarding Slice 2A

**Status:** Locked  
**Date:** 2026-07-17

**Decision:** Slice 2A materializes onboarding drafts into existing `tenant_configs.settings` JSON (no new SQL migration). Additive `settings.schema_version: 2` with:

| Path | Purpose |
|------|---------|
| `memory.lead_config.services[]` | Selected service profiles |
| `memory.lead_config.lead_requirements[service_type]` | `{required, optional}` field lists (`inherit` not stored) |
| `memory.internal_routing_hints[service_type]` | Intern profilrouting (ny writes) |
| `memory.routing_hints` | Legacy mirror + extern dispatch dict fallback (2B) — written only atomically at activate from canonical `external_routing_targets`; **no new onboarding writes**. Runtime reads canonical first (`docs/07-decisions.md` DEC-2B-routing-mirror). |
| `intake.mode`, `intake.activation_cutoff_at`, `intake.enforcement` | Datastart metadata (`metadata_only`) |

`service_type` is canonical in onboarding; `lead_type` resolved via `app/admin/onboarding/type_mapping.py` only where legacy paths require it.

**Can change if:** Master plan revises canonical config paths or moves intake enforcement beyond metadata-only.

### DEC-2B-routing-mirror — `memory.routing_hints` avvecklingsplan

**Decision:** Canonical external dispatch source is `settings.integrations.external_routing_targets`. `memory.routing_hints` is a **legacy mirror** only.

| Phase | Behavior |
|-------|----------|
| Now (Slice 2B) | Onboarding writes canonical draft only; activate mirrors dict hints atomically. Runtime (`ControlledDispatchEngine`, `maybe_auto_dispatch_job`, `/tenant/routing-preview`) reads canonical first, legacy dict fallback second. Invalid canonical fails closed to manual_review — no legacy fallback. |
| Next | Remove direct `POST /tenant/routing-hints/apply` usage from operator flows; monitor audit `external_routing_materialized`. |
| Later | Drop legacy mirror write at activate when all tenants have schema v3 + no consumers read `memory.routing_hints` for external dispatch. |

**Can change if:** Master plan defines a different migration window or removes the mirror earlier with a data migration.

---

## DEC-027 — Alert vs incident vs needs-help (Kapitel 10)

**Status:** Locked  
**Date:** 2026-07-18

**Decision:** Three separate operator surfaces with distinct lifecycles:

| Domain | Purpose | Persistence | Detection |
|--------|---------|-------------|-----------|
| **Operator alert** (`operator_alerts`) | Auto-detected operational state from DB/metadata signals | `operator_alerts` table; dedup by `deduplication_key` | Evaluation engine + registry |
| **Incident** | Operator-managed composite event with timeline, ownership, manual signals | `incidents` tables | Manual create/link only |
| **Needs-help** | Prioritized work queue of actionable tenant problems | Ephemeral triage rows (read-only aggregation) | Shared signal helpers; enriched with `related_alert_id` when matching alert exists |

**Rules:**
- Alerts do not replace incidents or needs-help rows.
- Needs-help enriches matching rows with alert metadata; it does not duplicate alert rows.
- Total platform/DB outage is **externally_detected** (health script + `ALERT_COMMAND`), not an internal `operator_alerts` type.
- Tenant legacy email alerts (`app/alerts/engine.py`) remain tenant-scoped; platform operator alerts are separate.

**Can change if:** Master plan explicitly merges domains (not expected for MVP).

---

## DEC-028 — Security contracts and accepted limitations (Kapitel 11)

**Status:** Locked  
**Date:** 2026-07-18

**Decision:** Platform security hardening is enforced via a declarative critical-action registry (`app/admin/security/critical_actions.py`), contract integrity tests (`tests/test_admin_security_contracts.py`), and consistent guards on legacy and modern admin routes.

| Control | Rule |
|---------|------|
| Critical writes | `require_operator_role` + `require_same_origin` on cookie mutations |
| `read_only` | 403 on all mutations (legacy routes included) |
| State-changing GET | Disallowed — `GET /admin/alerts/run-all` → `POST` |
| Tenant context | `X-Tenant-ID` middleware does not default a tenant when header absent |
| Idempotency | Integration idempotency keys scoped by `tenant_id` when provided |
| Audit | Recovery + operator-alert audit writes fail-closed (500 if audit cannot persist) |
| OAuth | Legacy Visma `state=tenant_id` callback blocked; onboarding opaque state only |
| Abuse | In-memory rate limits on login and selected high-risk endpoints |
| Headers | App middleware + `infra/Caddyfile.example` for `/ops` |

**Accepted limitations (not blocking K11 PASS):**

| ID | Limitation | Plan |
|----|------------|------|
| F05 | OAuth tokens plaintext in DB | See **F05 risk acceptance** below — post-pilot encryption; not a Kapitel 12 release-gate item |
| F14 | Alert suppress UI not in React detail page | API-only; optional UI in later slice |
| F15 | Single global operator account (`ADMIN_USERNAME` / password) | Per-user operators / SSO deferred |
| F16 | In-memory rate limiter (per process) | Distributed limiter or edge rate limit in K12 |

### F05 risk acceptance — OAuth tokens plaintext at rest

**Status:** Accepted for pilot and pre-encryption MVP operation  
**Owner:** Platform operator (Niklas / Krowolf operator owner)  
**Review date:** 2026-09-30 (or first production DB credential rotation, whichever is earlier)

| Item | Decision |
|------|----------|
| **Risk** | `oauth_credentials` table stores access/refresh tokens in plaintext. DB backup leak or unauthorized DB read could expose integration tokens. |
| **Pilot allowed before encryption?** | **Yes**, with compensating controls below and this explicit acceptance. |
| **Encryption requirement timing** | **Post-pilot / hardening backlog** — not a blocker for Kapitel 12 release verification gate. Kapitel 12 scope is release/prestanda verification, not token encryption delivery. |
| **Target implementation** | Application-level encryption or external secrets manager (e.g. envelope encryption with KMS) — tracked as post-pilot security work, not K12 “build chapter”. |

**Compensating controls (required now):**

1. **DB access:** PostgreSQL not exposed publicly; credentials in env only; least-privilege DB user for app (no superuser).
2. **Backups:** Encrypted at rest on backup volume; backup access restricted to operator owner; no tokens in backup filenames/logs.
3. **Network:** App reachable only via reverse proxy/TLS; no direct DB port on public internet.
4. **Audit:** OAuth connect/disconnect/refresh failures logged; operator actions audited; no tokens in API responses, audit payloads, or frontend DOM (verified by `tests/test_security_secret_scan.py`).
5. **Rotation on incident:** If DB or backup compromise suspected — rotate `DATABASE_URL` password, revoke OAuth per tenant via disconnect + reconnect, rotate `ADMIN_API_KEY`/`SESSION_SECRET_KEY`, review `audit_events` for anomalous operator actions.

**Can change if:** Master plan elevates encryption to pre-pilot blocker or assigns delivery to a specific chapter with an explicit deadline.

---

## DEC-030 — Kapitel 12 slutgate GO (2026-07-19)

**Date:** 2026-07-19  
**Status:** Active — pilot `api.krowolf.se`, `ADMIN_ROLE=admin`

| Item | Decision |
|------|----------|
| **Release** | **GO** — browseraggregat PASS (read_only, operations, admin); backend **3589/0**; security **240/0**; frontend gates PASS |
| **Pilot operator role** | **`ADMIN_ROLE=admin`** — avsedd pilotroll; ingen återställning till operations efter slutgate |
| **Browser safe boundaries** | Accepterade pilotbegränsningar (ej PARTIAL-blocker): suppress UI **not_mounted** (API PASS); recovery/replay/reclassify/re-extract/resend/gmail **not_executed_safe_boundary**; approve controlled_dispatch **not_executed_safe_boundary** — motsvarande permissions/kontrakt verifierade via security bundle + syntetiska prober |
| **Post-pilot UI gap** | Alert suppress-knapp i React `/ops/alerts/{id}` — backend klar, UI ej monterad (F14) |
| **Reports** | `/opt/krowolf/storage/status/kapitel12_browser_report.json`, per-roll `k12_browser_*_report.json` |

---

## DEC-029 — Kapitel 12 releasebeslut (CONDITIONAL GO)

**Date:** 2026-07-18  
**Status:** Superseded by **DEC-030** for release gate; retained for history

| Item | Decision |
|------|----------|
| **Release** | **CONDITIONAL GO** — backend regression **3586/0** (2026-07-18); full GO blocked until authenticated browser matrix on pilot |
| **Pilot scope** | Max **3** pilot tenants; scheduler **paused** until operator enables per tenant; **`/ops` primary** |
| **Legacy** | **Beslut B** — `/ui` read-only with deprecation banner; no `localStorage` admin key; full 410 deferred post-first-pilot |
| **Security** | K11 bundle **PASS** (196 tests) |
| **RB-01** | **PASS** (S3 offsite + restore verified on pilot) |
| **Blockers cleared for pilot** | Approval-first React, tenant isolation, backup/restore/cron, session auth |
| **Accepted for pilot** | F05, F06, F15, F16, CSP gap, recovery without React UI, legacy read-only fallback |
| **Reports** | `scripts/kapitel12_slice3_report.json`, `docs/kapitel-12-release-notes.md` |

---

## DEC-031 — Pilot stabilization baseline (2026-07-20)

**Status:** Active — `api.krowolf.se`, single tenant `T_NIKLAS_DEMO_001`

| Topic | Decision |
|-------|----------|
| **Canonical tag** | `krowolf-pilot-baseline-20260720-final` on final reconciliation commit (immutable; earlier tag `krowolf-pilot-baseline-20260720` on `7855151` retained for history) |
| **Deploy model** | **Modell A** — server Git HEAD aligned to `origin/main`; runtime files (`.env.*`, `storage/`, `backups/`, tenant keys) gitignored and preserved; product code deployed via RC-bundle + Docker image |
| **Tenant scope** | Exactly **one** tenant: `T_NIKLAS_DEMO_001` |
| **Gmail** | Tenant OAuth only; Krowolf uses `readonly` + `modify`; send disabled; legacy grant scope superset tolerated but not invoked |
| **Scheduler** | **Paused** until explicit operator enable after soak |
| **Operational data** | Clean baseline (jobs/approvals/tenant-alerts=0); pre-clean archive at `pre_live_niklas_archive.json` |
| **Next step** | Soak Dag 1 live scan — blocked on operator test emails only |

---

## DEC-032 — Onboarding 2.0 architecture (2026-07-20)

**Status:** Active — feature branch `feature/onboarding-2.0`

| # | Rule | Consequence |
|---|------|-------------|
| 1 | **Paus är driftstatus** | `paused` ∉ `lifecycle_status`; use `settings.scheduler.run_mode` / `settings.operations.paused` |
| 2 | **super_admin via operator-ID** | `SUPER_ADMIN_OPERATOR_IDS` binds to stable `OperatorInfo.id` |
| 3 | **Archive = admin; delete = super_admin** | Archive/restore: admin; permanent test-tenant delete: super_admin only |
| 4 | **TenantDeletionService** | API + CLI share `app/admin/tenant_lifecycle/deletion_service.py` |
| 5 | **OAuth state DB lookup only** | `oauth_state_resolver`; no opaque heuristics on callback path |
| 6 | **Readiness ↔ config_version** | Stale readiness when `config_version` changes after last check |
| 7 | **Immutable activation snapshots** | `tenant_activation_snapshots` append-only |
| 8 | **Intake UTC + dedupe alerts** | Gmail `internalDate` → UTC; dedupe per tenant+dedupe_key |
| 9 | **Service catalog in service_profiles/** | Onboarding is presenter/filter only |
| 10 | **Connected account after invite** | Store/display `connected_account_email`; never tokens in UI |

Reference: `docs/onboarding-2.0-architecture.md`

---

## DEC-033 — Decision contract & action authorization (2026-07-20)

**Status:** Active — Kapitel 2B

| # | Rule | Consequence |
|---|------|-------------|
| 1 | **AI recommendation ≠ authorization** | `decisioning_recommendation` (`auto_route`, `manual_review`, `hold`) is normalized separately from `policy_authorization` |
| 2 | **Legacy tokens fail-closed** | `auto_execute` / `send_for_approval` in decisioning payload → `manual_review`; never grant `execution_allowed` alone |
| 3 | **Risk first** | `resolve_policy_authorization()` checks content risk before any lower-priority branch; no early return may bypass it |
| 4 | **`force_approval_test` server-gated** | Honored only when `ALLOW_FORCE_APPROVAL_TEST=True`; stripped from job input otherwise |
| 5 | **Dispatch boundary authorization** | All actions (builder, injected, replay, resume) pass `_apply_dispatch_authorization()` |
| 6 | **Central action registry** | Unknown actions blocked; external writes classified in `ACTION_REGISTRY` |
| 7 | **Per-action approval** | Each external write may get its own approval; resume is idempotent and scoped to `delivery_payload` |
| 8 | **Central automation mode** | `tenant_automation.py` is the single normalizer for `auto_actions` |
| 9 | **Backward-compatible projection** | `policy_authorization` is internal truth; legacy `decision` string is a projection for orchestrator/consumers |

Reference: `docs/10b-decision-contract-resolution.md`

---

## DEC-034 — Append-only decision trace (2026-07-20)

**Status:** Active — Kapitel 2C

| # | Rule | Consequence |
|---|------|-------------|
| 1 | **Append-only `decision_records`** | No updates/deletes except tenant lifecycle purge |
| 2 | **`event_sequence` DB-generated** | No application `MAX()+1` |
| 3 | **`action_operation_id`** | Stable UUID per logical operation; independent of HMAC and `pipeline_run_id` |
| 4 | **`action_fingerprint` diagnostic** | Optional HMAC with `fingerprint_key_version`; NULL without key |
| 5 | **Explicit `PipelineRunContext`** | Parameter propagation; no thread-local |
| 6 | **External write two-phase** | Auth → intent → adapter → outcome; unresolved blocks auto retry |
| 7 | **`processor_history` reset unchanged** | Full trace in `decision_records` only |
| 8 | **Metadata allowlist** | Max 2048 bytes; no raw payloads/tokens |
| 9 | **`DECISION_RECORD_ENFORCE_WRITES` default-on** | Forbidden off in production; startup verifies migration 015 |
| 10 | **Migration before code** | Documented deploy order |

Reference: `docs/10c-decision-trace-foundation.md`

---

## DEC-035 — Deterministic evaluation harness (2026-07-20)

**Status:** Active — Kapitel 2D

| # | Rule | Consequence |
|---|------|-------------|
| 1 | **YAML scenarios are normative** | Baseline stores status/metrics only, not behavior |
| 2 | **`fixture_ai` default** | Schema-valid fixtures; `forced_fallback` only when explicit |
| 3 | **Real `execute_action` + fake adapter** | No adapter bypass; `real_external_calls` must be 0 |
| 4 | **Safety veto before quality** | Per-metric gates; weighted score diagnostic only |
| 5 | **Baseline exit code 21** | Separate from safety/quality failures |
| 6 | **No production logic in harness** | Missing hooks reported as gaps, not hidden |
| 7 | **No live LLM in 2D** | Extension point only; no `--with-llm` |

Reference: `docs/10d-evaluation-harness.md`

---

## DEC-036 — Tenant integration health gated by selection (Slice A, 2026-07-21)

**Status:** Active — Customer settings / integration selection

| # | Rule | Consequence |
|---|------|-------------|
| 1 | **Canonical key `google_mail`** | Legacy `gmail` accepted only at ingest/alias boundary (`app/integrations/keys.py`) |
| 2 | **Platform vs tenant health are separate layers** | Global/platform capability (e.g. Fortnox env) must not surface as tenant warning when integration is not selected |
| 3 | **`not_selected` → `not_applicable`** | No tenant health warning, triage row, prioritized action, or open alert for that integration |
| 4 | **`selected_optional` + unconfigured → neutral `not_connected`** | Not a warning state |
| 5 | **Slice A resolver fallback only** | Derive selection from credentials + `allowed_integrations`; no migration 015 until Slice B |
| 6 | **Resolve stale alerts with reason** | `integration_not_selected_after_selection_model_migration`; do not SQL-delete without audit |

Reference: `app/admin/integrations/selection_resolver.py`, `app/health/integration_health.py`

---

## DEC-037 — Explicit integration selections source of truth (Slice B, 2026-07-21)

**Status:** Active — in progress on `feature/integration-selection-slice-b`

| # | Rule | Consequence |
|---|------|-------------|
| 1 | **`settings.integrations.selections` is SoT** after backfill/activation | Legacy fallback only when selections absent |
| 2 | **`migration_review_required` is boolean** | Not a `selection_status` value |
| 3 | **Migration 016 SQL ≠ backfill** | SQL creates structure/table; `run_integration_selection_backfill.py` classifies tenants |
| 4 | **Backfill actor** | `configured_by=system:migration_016`, `requirement_source=legacy_backfill` |
| 5 | **Runtime writes** | `enabled_external_writes` separate from `allowed_integrations`; selection/verification alone never enables writes |
| 6 | **Sheets cautious backfill** | `google_sheets` in allowlist without tenant evidence → `selected_optional` + `migration_review_required=true` |
| 7 | **Sync fail-closed** | `sync_allowed_integrations_from_selections` never expands external writes without verification |

Reference: `app/admin/integrations/selection_backfill.py`, `selection_sync.py`, `selection_materialize.py`
