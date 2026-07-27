# Customer card domain — closure

> **Status:** `CUSTOMER_DOMAIN_CLOSED` (documentation closure — not product activation)  
> **Closure date:** 2026-07-27  
> **Authoritative detail:** This document supersedes stale pre-implementation statements in `implementation-gate.md` where they conflict.

---

## 1. Executive status

The **end-customer domain** (tenant-isolated CRM-style customer cards) is **implemented, evaluated, and closed** for the approved first scope:

- Persistence foundation (migrations 022–023)
- Read-only HTTP API (flag-gated)
- Operator-controlled writes (flag-gated)
- Deterministic current-state projection on detail reads
- Pure matching assessment and duplicate review **without merge**
- Isolated stateful PostgreSQL evaluation (five scenario families)

**Not included in closure:** production activation, UI, Gmail runtime coupling, backfill, automatic matching/linking, or merge.

| Dimension | Status |
|-----------|--------|
| Implementation (todo H) | Complete |
| Stateful evaluation (todo I) | Complete — PASS @ `cc4ecfe` |
| Closure documentation (todo J) | Complete — this document |
| Product activated | **No** — feature flags default `false` |

---

## 2. Final repository baseline

| Field | Value |
|-------|-------|
| Closure merge baseline | `4afb0b71a18f99b35dcaaeb239b8a9900b76c1f2` (`origin/main` at closure PR) |
| Evaluated SHA (stateful eval) | `cc4ecfe3834948e2d22214ab17c09ef0a6b7aeee` |
| Delta since evaluated SHA | One commit (#81 semi-auto canary) — **no** changes under `app/domain/customer/`, `app/evaluation/customer_domain/`, end-customer services, routers, or migrations 022/023 |
| Latest migration | `023` (`LATEST_MIGRATION_VERSION` in `migration_runner.py`) |
| Plan todos A–J | All `completed` after closure PR |

---

## 3. Delivered architecture

```
HTTP (flag-gated)
  end_customers.py          — tenant + operator GET
  end_customer_writes.py    — operator POST/PATCH only

Services
  EndCustomerReadService    — list, search, card, timeline, jobs, threads, duplicates
  EndCustomerCommandService — create, update, facts, verify, identity, job-link, duplicate decision

Domain (pure)
  assess_customer_match()   — candidate assessment only (no writes)
  current_state resolver    — deterministic projection for detail API

Persistence
  EndCustomerRepository + EndCustomerIdempotencyRepository
  PostgreSQL 022 (10 tables) + 023 (idempotency)

Evaluation (isolated)
  app/evaluation/customer_domain/ — CLI runner, guards, five families (not production runtime)
```

**No runtime wiring:** Gmail intake, workflows, approvals, dispatch, scheduler do not call end-customer command paths.

---

## 4. Persistence model

### Migration 022 — foundation

Tenant-scoped tables: `end_customer_companies`, `end_customer_contacts`, `end_customers` (with `version`), `end_customer_source_facts`, `end_customer_identities`, `end_customer_relationships`, `end_customer_job_links`, `end_customer_thread_links`, `end_customer_timeline_events`, `end_customer_duplicate_candidates`.

### Migration 023 — idempotency

`end_customer_idempotency_records` with unique `(tenant_id, operation_type, idempotency_key)`.

### Contracts

- `tenant_id` on all customer-domain rows
- Optimistic locking via `end_customers.version`
- Source facts and timeline are append-oriented in service contract (not DB-trigger-enforced)
- No automatic merge or record-fusion operations in repository or service layer
- No `end_customer_addresses` table (deferred from design)

---

## 5. Read and write APIs

### Feature flags (both default `false`)

| Flag | Default | Effect |
|------|---------|--------|
| `END_CUSTOMER_READ_API_ENABLED` | `false` | Mounts read routers when `true` |
| `END_CUSTOMER_WRITE_API_ENABLED` | `false` | Mounts operator write routers when `true` (requires read `true`) |

### Read routes (when read flag `true`)

**Tenant (API key):** `GET /end-customers`, `/search`, `/{id}`, `/timeline`, `/jobs`, `/threads`; `GET /end-customer-duplicates`.

**Operator:** `GET /admin/tenants/{tenant_id}/end-customers/...` (same read surface).

### Write routes (when read + write `true`, operator only)

- `POST /admin/tenants/{tenant_id}/end-customers` — atomic create (private or company)
- `PATCH /{customer_id}` — optimistic update
- `POST /{customer_id}/facts`, `POST /facts/{fact_id}/verify`
- `POST /{customer_id}/identities`, `POST /{customer_id}/job-links`
- `POST /admin/tenants/{tenant_id}/end-customer-duplicates/{candidate_id}/decision`

### Not exposed as HTTP commands

- Add secondary contact (repository `create_contact`)
- Create thread link (repository `create_thread_link`)
- Create duplicate candidate (repository `create_duplicate_candidate`)
- Tenant-facing writes
- Merge or `approve_merge`

---

## 6. Auth and tenant isolation

- Tenant reads: `get_verified_tenant` — scoped to authenticated tenant
- Operator reads/writes: `require_operator_role` + `require_same_origin` on writes
- Cross-tenant customer ID → `404` without existence leak (verified in stateful eval tenant controls)
- Identity collisions fail closed (`IDENTITY_COLLISION_REVIEW_REQUIRED`)
- Idempotency scoped per tenant

---

## 7. Current-state and provenance

- Detail response includes additive `current_state` (`EndCustomerCardDetailResponse`)
- Resolver is pure, deterministic, order-independent
- Verified facts are not overwritten by lower-trust sources; verification creates successor facts
- Proposed/conflicting values surface in pending/conflicts; historical chain preserved
- Timeline events with replay identity keys prevent duplicate timeline on idempotent replay

---

## 8. Matching and duplicate handling

- `assess_customer_match()` — pure function; `automatic_link_allowed=false`, `automatic_merge_allowed=false` always
- Duplicate candidates can be listed; decisions: `reject_merge`, `resolve_without_merge` only
- `approve_merge` rejected at API schema and command service (`AUTOMATIC_MERGE_FORBIDDEN`)
- No physical record fusion

---

## 9. Stateful evaluation evidence

Sanitized summary (full raw reports are local-only, not committed):

| Field | Value |
|-------|-------|
| Evaluated git SHA | `cc4ecfe3834948e2d22214ab17c09ef0a6b7aeee` |
| PostgreSQL | 18.3 |
| Database class | Dedicated eval (`ai_platform_customer_domain_eval`), isolated cluster |
| `scenario_count` | 5 |
| `passed_count` | 5 |
| `failed_count` | 0 |
| `blocked_count` | 0 |
| `repeat_run_consistent` | `true` |
| Cross-CLI semantic hashes | Match (two full CLI runs) |
| `external_side_effects` | 0 |
| `credentials_exposed` | `false` |
| `non_eval_rows_changed` | 0 |

**Controls:** tenant isolation, concurrent create/update/duplicate-decision, timeline replay, feature flags, security — all PASS.

**Families:** private customer; returning customer + match; changed information (current-state via detail API); company multi-contact; ambiguous identity + duplicate decision.

**Limitation:** Synthetic eval tenants only — **not** evidence for production rollout or Gmail-coupled behavior.

---

## 10. Feature flags and activation posture

**Closure does not activate the domain.**

Default deployment: no end-customer routes in OpenAPI; no startup backfill; no scheduler or intake hooks.

### Future activation gate (separate operator approval required)

1. Product decision on first UI surface (operator vs tenant workspace)
2. Data source / backfill strategy
3. Tenant configuration
4. Operator permission review
5. Observability and audit dashboards
6. Support runbook
7. Rollback procedure
8. Pilot tenant selection
9. Manual acceptance test on real data
10. Explicit operator sign-off

---

## 11. Supported capabilities

- Tenant-isolated persistent end-customer domain
- Private and company customers (atomic operator create)
- Company and Contact as separate entities
- Source facts, provenance, timeline
- Deterministic current-state on detail reads
- Tenant and operator read APIs (when read flag enabled)
- Operator-controlled writes with idempotency and audit (when write flag enabled)
- Explicit job links and thread references (persistence + read; thread link create via repository in eval)
- Duplicate queue read and reject/resolve-without-merge decisions
- Pure matching assessment
- Stateful synthetic evaluation package

---

## 12. Internal-only capabilities

- Read/write APIs (disabled by default flags)
- Repository arrange paths: extra contact, thread link, duplicate candidate (used in eval, not production HTTP)
- Evaluation CLI: `python -m app.evaluation.customer_domain.runner` (requires safe eval database URL)
- Operator write surface requires operator session + same-origin

---

## 13. Deferred capabilities

- Tenant-facing writes
- Operator HTTP routes for add-contact, thread-link, duplicate-candidate create
- Customer workspace / operator end-customer UI
- Gmail runtime customer creation or auto-link
- Automatic matching, linking, or candidate creation in intake
- Backfill and import tooling
- `end_customer_addresses` table
- Idempotency record retention/cleanup policy
- Search optimization beyond current implementation

---

## 14. Explicit non-capabilities

- `approve_merge` and physical record fusion
- Automatic overwrite of verified facts by untrusted sources
- Cross-tenant matching or identity sharing
- AI-created verified facts without operator verification flow
- Gmail body or credential storage in customer domain tables
- Production rollout (not activated by closure)

---

## 15. Known risks

| Risk | Classification |
|------|----------------|
| Feature flags default disabled | Accepted |
| No production customer data / backfill | Accepted |
| No Gmail runtime coupling | Accepted |
| Append-only not DB-trigger-enforced | Accepted |
| Soft references to jobs/Gmail threads | Accepted |
| No end-customer UI | Deferred |
| Synthetic eval only | Accepted (scope limit) |
| Idempotency retention undefined | Deferred |
| Eval at `cc4ecfe`; main advanced without domain diff | Accepted (verified no domain file changes) |

---

## 16. Rollback and disable strategy

**Disable (no code revert):** keep `END_CUSTOMER_READ_API_ENABLED=false` and `END_CUSTOMER_WRITE_API_ENABLED=false` — routes unmounted.

**Revert closure docs:** revert closure PR — no production code or data impact.

**Schema:** migrations 022/023 remain applied if already run; tables are inactive without routes and without writers.

---

## 17. Future chapter boundaries

| Chapter | Boundary |
|---------|----------|
| Customer workspace UI | Separate plan (`docs/customer-workspace/`); requires read API activation + UI work |
| Gmail intake linking | Separate gate; no automatic customer create in current domain |
| Backfill | Separate operator gate; dry-run mandatory |
| Merge | Rejected unless new locked decision |
| Testbot customer-card stateful | `docs/plans/full-system-testbot-plan.md` todo F — not part of this closure |

---

## 18. Traceability

| Delivery | PR | Merge SHA | Key paths | Verification |
|----------|-----|-----------|-----------|--------------|
| Design & contracts | #58 | `6323380b9045833468c7d739cc8897bdd138f2b6` | `docs/customer-card-domain/*` | Design merge |
| Persistence foundation | #62 | `33b083c3855db97dc206b11ce291545525940d66` | `022_*.sql`, ORM, repository | `test_end_customer_migration_pg`, repository PG |
| Read-only API | #67 | `cd1d561913b01a798bb8ba3b981197470406a9f9` | `end_customers.py`, read service | API + read service tests |
| Operator writes + idempotency | #70 | `6ea4b60a16f64764b2efae8c576aa0f59a49e807` | `023_*.sql`, command service, writes router | command/API/idempotency tests |
| Current-state projection | #74 | `3837c739a5e85c8abb02735c20937f756b010efa` | resolver, detail `current_state` | `test_customer_current_state` |
| Stateful eval (initial) | #75 | `aaf3932ca0a82924817dff5299481d3352324926` | `app/evaluation/customer_domain/` | `pg_eval` + contract tests |
| Eval runner hardening | #79 | `9039801becc3d2b5588cefe2b3911c6baa44d9de` | `controls.py`, `runner.py` | Full CLI PASS + PG control tests |
| Credential scan fix | #80 | `cc4ecfe3834948e2d22214ab17c09ef0a6b7aeee` | `reporting.py` | `credentials_exposed=false` in reports |

**Closure documentation:** this file + `docs/01-current-truth.md`, `docs/06-backlog.md`, `docs/09-testing-and-release.md` updates.
