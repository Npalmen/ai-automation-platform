# Customer card domain — implementation gate

> Todo G gate review. **Audit date:** 2026-07-26  
> **Design branch:** `design/customer-card-domain` @ `73c971f`  
> **Compared main:** `origin/main` @ `a3542d2` (1 commit ahead of design merge-base `758502e`)

---

## Executive summary

| Field | Value |
|-------|-------|
| **Gate recommendation** | **GO** |
| **Todo G outcome** | Review complete — implementation **not** authorized |
| **First chapter after operator approval** | Customer Domain Foundation (persistence only) |
| **Automatic merge** | Forbidden — unchanged |
| **Manual merge execution** | Deferred (`defer_all_merge_execution`) |

GO means the design is sufficiently evidenced for the **operator** to decide on todo H. It does **not** authorize implementation without explicit operator approval text defined in the master plan.

### Conditions under GO

| Chapter | Condition |
|---------|-----------|
| Foundation (tables + repos) | May start after operator approval |
| Read-only API | Requires locked `/end-customers` route + workspace API alignment check |
| Manual writes | Requires duplicate-decision flow without merge execution |
| Backfill | Separate operator gate; dry-run mandatory; AI → `proposed` only |
| Workspace UI | After read-only API; align with `docs/customer-workspace/` contracts on `main` |
| Manual merge | Separate gate; not in initial implementation |

---

## Six review summaries

### Review 1 — Repository current truth

Re-verified 2026-07-26:

- No `end_customer` SQLAlchemy models, migrations, or repositories exist.
- `app/domain/customer/**` exists only on design branch; **not imported** from `app/main.py`, workflows, API, or admin runtime (grep: imports only within `app/domain/customer/`).
- Tenant account vs end customer still separable: `/ops/customers` = `TenantListItem`; domain `Customer` = tenant's client.
- Jobs, approvals, action executions, audit events all carry indexed `tenant_id` (`job_models.py`, `approval_models.py`, `action_execution_models.py`, `audit_models.py`).
- Reference IDs for timeline exist: `job_id`, Gmail `thread_id`/`message_id` in job `input_data`, `approval_id`, `execution_id`.
- Parallel track on `main`: `a3542d2` added `docs/customer-workspace/*` only — **no file overlap** with `app/domain/customer/` or planned `end_customer_*` tables.

**Result:** PASS

### Review 2 — Domain model and minimal persistence

Customer as aggregate root with separate Company/Contact is consistent with isolated schemas and audit gaps. CustomerCard remains a projection (no table).

#### Table classification matrix

| Koncept/tabell | Klassificering | Krävs i första implementationen | Motivering | Risk om uppskjuten |
|----------------|----------------|----------------------------------|------------|-------------------|
| `end_customers` | `required_initial` | Yes | Aggregate root + `version` | Cannot store end customers |
| `end_customer_companies` | `required_initial` | Yes | Company/contact separation | Company customers collapse into blob |
| `end_customer_contacts` | `required_initial` | Yes | Private + company contacts | No person entity |
| `end_customer_relationships` | `required_initial` | Yes | Primary/secondary contacts | Cannot model company + contacts |
| `end_customer_identities` | `required_initial` | Yes | Matching + dedup signals | Matching only in job JSON |
| `end_customer_source_facts` | `required_initial` | Yes | Provenance SoT | No verified vs proposed |
| `end_customer_job_links` | `required_initial` | Yes | Timeline without payload copy | No job association |
| `end_customer_thread_links` | `required_initial` | Yes | Gmail context per integration | Thread linkage lost |
| `end_customer_timeline_events` | `required_initial` | Yes | Append-only history | No customer timeline |
| `end_customer_duplicate_candidates` | `required_initial` | Yes | Safe dedup review queue | No duplicate workflow |
| `end_customer_addresses` | `defer` | No | Address facts can live in `source_facts` initially | Structured address index later |
| `end_customer_merge_decisions` | `defer` | No | Merge execution deferred by policy | No physical merge until separate gate |

#### Recommended models

1. **Minimal initial persistence (10 tables):** customers, companies, contacts, relationships, identities, source_facts, job_links, thread_links, timeline_events, duplicate_candidates.
2. **Full future model:** add `end_customer_addresses`, `end_customer_merge_decisions` when address indexing and manual merge are approved.
3. **Not building initially:** merge decision table, address table, CustomerCard table (projection).

Model is **not** an unnecessary CRM: no pipeline, campaigns, or ERP write-back as SoT.

**Result:** PASS

### Review 3 — Identity matching and merge boundary

Verified in code + 19 matching tests:

- Cross-tenant → `blocked` (`matching.py`, tests 2, 11).
- Person vs company → `blocked`.
- Verified org/customer-number conflicts → `blocked`.
- Deterministic evidence/reason ordering (tests 14–15).
- Confidence capped at 1.0.
- Role-based email → manual review path.
- Plus-tags preserved (`normalization.py`, test).
- Name/address alone → weak / no_match.
- `automatic_merge_allowed` and `automatic_link_allowed` hard-coded `false` with Pydantic validators (`schemas.py`, `api_schemas.py`, `matching.py`).

#### Merge policy recommendation

| Question | Recommendation |
|----------|----------------|
| `CustomerMergeDecision` as data contract in schemas? | **Yes** — already in isolated schemas; table **deferred** |
| Manual merge execution in first implementation? | **No** — `defer_all_merge_execution` |
| First implementation duplicate flow | Create/review/reject candidates; link proposals manual; **no record fusion** |

Rollback for merge requires reference remapping across facts, links, and timeline — not defined enough for initial scope.

**Result:** PASS (manual merge boundary: CONDITIONAL → deferred, not FAIL)

### Review 4 — Timeline, provenance, backfill

Verified in `provenance.py` + 26 timeline tests:

- Append-only fact design; transitions in `ALLOWED_FACT_TRANSITIONS`.
- `occurred_at` ≠ `recorded_at`; deterministic sort.
- Metadata allowlist; forbidden keys include `payload`, `token`, `credential`.
- Idempotent replay via `TimelineReplayIdentity`.
- `lower_source_cannot_supersede_verified()` blocks AI overwriting verified facts.

#### Backfill source matrix

| Källa | Tenantbevis | Auktoritet | Tillåten initial fact state | Får skapa Customer | Får skapa duplicate candidate | Risk |
|-------|-------------|------------|----------------------------|--------------------|------------------------------|------|
| Gmail sender | `job.tenant_id` | Medium | `proposed` | Yes (as observation) | Yes | Medium — observation only |
| Gmail thread | `job.tenant_id` + integration context | Medium | link only | No alone | Yes (thread signal) | Low |
| AI entity extraction | `job.tenant_id` | Low | **`proposed` only** | No without review | Yes | High if verified |
| Lead processor output | `job.tenant_id` | Low–medium | `proposed` | No alone | Yes | Medium |
| Support processor output | `job.tenant_id` | Low–medium | `proposed` | No alone | Yes | Medium |
| Job `input_data` | `job.tenant_id` | Medium | `proposed` | Yes | Yes | Low |
| ERP reference | integration + tenant | High if integration verified | `proposed` / verified with proof | Yes | Yes | ERP ID confusion |
| User input (workspace) | auth tenant | High | `verified` after explicit verify | Yes | No | Auth scope |
| Admin correction | operator tenant | Highest | `verified` | Yes | No | Operator error |

Backfill design supports tenant-scoped, idempotent, restartable dry-run without mutating jobs/Gmail/approvals/actions (`migration-test-plan.md` §H).

**Result:** PASS

### Review 5 — API, auth, naming

#### Route decision

**Recommendation:** `/end-customers` (tenant) and `/admin/tenants/{tenant_id}/end-customers` (operator).

| Factor | `/end-customers` | `/customers` |
|--------|------------------|--------------|
| `/ops/customers` collision | Avoided | High confusion |
| `/customer/*` tenant API | Distinct prefix | Overlapping semantics |
| ERP `customer_id` | Clearer in docs | Worse |
| SDK clarity | Higher | Lower |

#### Persistence prefix decision

**Recommendation:** `approve_end_customer_prefix` (`end_customer_*`).

Disambiguates tenant accounts, ERP customers, and `send_customer_auto_reply` workflow language.

#### Workspace alignment

- **Verified on `main`:** `docs/customer-workspace/product-contract.md`, `api-contract.md` — workspace covers jobs, approvals, leads, activity (tenant user's operational view).
- **Not verified in code:** no `frontend/src/customer/**` implementation yet.
- **Not authoritative:** untracked local `docs/plans/customer-workspace-plan.md` on design branch working tree.

**Classification:** **CONDITIONAL** — workspace and end-customer API are separate surfaces today; alignment required before workspace shows end-customer cards. **Does not block foundation.**

#### Auth

Existing roles sufficient for documented matrix (`read_only`, `operations`, `admin`, `super_admin` in `app/admin/operator_actions.py`). Tenant API key resolution pattern exists. No new auth platform required for foundation or read-only API design.

**Result:** PASS (workspace: CONDITIONAL)

### Review 6 — Migration, test, operability

- **Mechanism verified:** `migrations/*.sql` + `migration_runner.py` `ORDERED_MIGRATION_FILES`; next file likely `022_*.sql`; not Alembic.
- Tenant-scoped uniqueness documented; no global email/phone unique.
- Rollback per stage documented (`migration-test-plan.md` §G).
- Test suite: **78 passed** (schemas, matching, timeline, API contracts).
- Five synthetic fixtures with `schema_version`.
- Stateful evaluation (todo I) correctly blocked until persistence + API exist.

**Result:** PASS (observability metrics deferred to rollout chapter — acceptable)

---

## Gate matrix

| Gate | Resultat | Repositoryevidens | Kvarstående risk | Krävd åtgärd |
|------|----------|-------------------|------------------|--------------|
| Repository current truth | PASS | `current-truth.md`; re-grep 2026-07-26; no end-customer tables | Naming collisions remain in UI language | Document in API + UI copy |
| Ingen duplicerad kunddomän | PASS | No `end_customer` persistence; isolated package only on design branch | — | — |
| Tenantisolering | PASS | `tenant_id` on all core tables; match blocks cross-tenant | Repository enforcement pending implementation | Tenant filter in every repo method |
| Terminologisk separation | PASS | Domain docs + `/end-customers` proposal | `/ops/customers` unchanged | Keep operator label "tenant" in UI |
| Minimal datamodell | PASS | 10-table initial recommendation | 12-table full plan is superset | Defer addresses + merge_decisions |
| Company/Contact-separation | PASS | Separate schemas + tests | — | Enforce FK owner types in repos |
| Source provenance | PASS | `provenance.py`, fact states, tests | Runtime ingestion not built | Implement fact writer in chapter 3 |
| Konfliktregler | PASS | Transitions + `lower_source_cannot_supersede_verified` | — | — |
| Deterministisk matching | PASS | 19 matching tests + sorted evidence | Candidate DB query not built | Chapter 4 |
| Ingen automatisk merge | PASS | Validators + matching always false | — | — |
| Manuell mergegräns | PASS | `defer_all_merge_execution` recommended | Merge table deferred | Separate operator gate for merge |
| Timeline references | PASS | Reference types + no payload in events | — | Link validation at write time |
| Metadata och secrets | PASS | Allowlist + tests reject `token`/`payload` | — | — |
| API route naming | PASS | `api-contract.md` recommends `/end-customers` | Not mounted | Lock at API chapter |
| Persistence naming | PASS | `end_customer_*` prefix proposed | Long names | Accept for clarity |
| Tenant API-auth | PASS | Design omits client `tenant_id` on writes | — | Implement auth deps in API chapter |
| Operator API-auth | PASS | Admin tenant-scoped routes pattern exists | — | Mirror onboarding admin routes |
| Optimistic locking | PASS | `version` + `expected_version` in schemas | — | Enforce in repositories |
| Idempotens | PASS | Header contract + error code | — | Implement idempotency store |
| Audit | PASS | Documented write audit fields | Not implemented | Audit in write chapter |
| Migrationmekanism | PASS | `migration_runner.py` + SQL files | New 022 file needed | Follow ORDERED_MIGRATION_FILES |
| Migrationordning | PASS | FK-safe order in migration-test-plan | — | Single foundation migration first |
| Backfill | PASS | Documented tenant/idempotent/quarantine | Not implemented | Separate backfill gate |
| Rollback | PASS | Per-stage rollback table | Untested until migration exists | Test rollback in foundation chapter |
| Syntetisk testmatris | PASS | 5 fixtures + 12-level matrix | PG tests pending | Add in foundation chapter |
| Workspace alignment | CONDITIONAL | Workspace docs on main; no end-customer UI | API surface alignment TBD | Pre-API alignment review |
| Testbot/approval/dispatch isolation | PASS | No changes to workflows/testbot on design branch | Future hooks must stay out of intake | Keep foundation isolated |
| Drift och observability | CONDITIONAL | Rollout doc mentions flags | No customer-domain metrics yet | Add metrics at API rollout |
| Exakt framtida filscope | PASS | Plan §8–9 + migration chapters | — | Enforce per-branch scope |

**Counts:** PASS 27, CONDITIONAL 2 (workspace, observability), FAIL 0, BLOCKED 0.

---

## Mandatory conclusions

1. **Existing end-customer domain duplicated?** No — only isolated contracts on design branch.
2. **Minimal initial persistence?** 10 tables (no addresses, no merge_decisions).
3. **Deferred tables?** `end_customer_addresses`, `end_customer_merge_decisions`.
4. **Customer as aggregate root?** Yes — recommended.
5. **Company/Contact separation?** Yes — separate schemas, IDs, and tables.
6. **Route prefix `/end-customers`?** Yes — recommended.
7. **Table prefix `end_customer_*`?** Yes — recommended.
8. **Manual merge in first version?** No — duplicate review only; `defer_all_merge_execution`.
9. **AI extraction in backfill?** `proposed` only; never auto-verified.
10. **Tenant isolation without source table changes?** Yes — links reference existing IDs; no FK into jobs table required for foundation.
11. **Foundation without Gmail/approval/dispatch impact?** Yes — no runtime wiring in foundation chapter.
12. **First implementation chapter?** Customer Domain Foundation.
13. **First chapter allowed files?** See §First implementation chapter below.
14. **Tests before next chapter?** PG repository tests + migration forward/rollback + tenant isolation tests.
15. **Rollback?** Drop empty new tables or disable feature flag; no source mutation.
16. **Separate operator decisions?** Todo H approval text; manual merge gate; backfill gate; workspace API alignment.

---

## Proposed ADR (not in `docs/07-decisions.md`)

**Title:** End-customer domain foundation (proposed)

**Status:** Proposed — pending operator approval

**Context:** Tenant accounts, ERP customers, and tenant's end customers use overlapping "customer" language. Jobs hold scattered contact data without provenance or dedup safety.

**Decision:**

- **Tenant account** ≠ **end customer** (`Customer` aggregate).
- Separate **Company** and **Contact** entities.
- **Source facts** and **timeline events** are append-only; **CustomerCard** is a projection.
- **Automatic merge and automatic link forbidden** in product policy.
- **Manual merge execution deferred**; duplicate candidates + reject/resolve only in v1.
- HTTP routes: `/end-customers`; tables: `end_customer_*` prefix.
- **Initial scope:** persistence + repositories only; no intake/Gmail/workflow hooks.
- **Backfill:** tenant-scoped, read-only sources, AI → `proposed`, separate operator gate.
- **Workspace:** end-customer card is a later read surface; align with `docs/customer-workspace/` before UI.

**Consequences:** New migration `022_*`; feature flag; no change to job/approval/action tables in foundation chapter.

---

## First implementation chapter (not started)

**Name:** Customer Domain Foundation  
**Branch (future):** `feat/customer-card-foundation`  
**Goal:** Create 10 `end_customer_*` tables, SQLAlchemy models, repositories with strict `tenant_id` filtering, feature flag default off.

### May create/change

- `migrations/022_end_customer_foundation.sql`
- `app/repositories/postgres/migration_runner.py` — add file to `ORDERED_MIGRATION_FILES`
- `app/repositories/postgres/end_customer_models.py` (or split by entity)
- `app/repositories/postgres/end_customer_repository.py` (or split)
- `tests/test_end_customer_repository.py` (PostgreSQL / test DB)
- `tests/test_end_customer_migration.py` (forward/rollback smoke)
- Reuse **read-only** imports from `app/domain/customer/schemas.py` for validation at repository boundary

### Forbidden

- `app/main.py`, routers, workflows, Gmail, intake, entity extraction
- approvals, decisioning, policies, dispatch changes
- backfill scripts writing to new tables from jobs
- merge execution
- `automatic_merge_allowed` / `automatic_link_allowed` true anywhere
- frontend, workspace, testbot scenarios
- importing customer package from runtime pipeline code

### Tests required (definition of done)

- Migration applies and rolls back on empty DB
- Every repository method rejects missing/wrong `tenant_id`
- Optimistic locking on `end_customers` and `duplicate_candidates`
- Append-only: no UPDATE/DELETE on `source_facts` and `timeline_events` in repository API
- `python -m pytest tests/test_end_customer_*.py -q` pass
- Existing 78 contract tests still pass
- `grep` confirms no `app/main.py` import of customer domain

### Stop-gates

- STOP if migration touches `jobs`, `approval_requests`, `action_executions`
- STOP if global unique on email/phone without `tenant_id`
- STOP if runtime mounts routes or runs backfill
- STOP if automatic merge/link enabled

---

## NO-GO triggers (none active)

Would apply if: duplicate end-customer tables found, cross-tenant match allowed, AI auto-verified in backfill design, or foundation required workflow changes. None observed.

---

## Deferred concerns from A–F (not repaired in G)

| Item | Classification |
|------|----------------|
| Address as separate table | Deferred — use source_facts initially |
| Merge decision persistence | Deferred — policy `defer_all_merge_execution` |
| Workspace end-customer API routes | Deferred — align before API chapter |

No blocking defects found in A–F contracts requiring redesign.

---

## Verification log (2026-07-26)

| Check | Result |
|-------|--------|
| `pytest` customer domain suite | 78 passed |
| `compileall app/domain/customer` | OK |
| Runtime imports `app.domain.customer` | None outside package |
| SQLAlchemy in customer package | None |
| FastAPI in customer package | None (comment only) |
| Customer migrations | None |
| Design branch commits `8af2d37`…`73c971f` | Present |
| `git diff origin/main...HEAD` | Design-only files (22 paths) |
| Main ahead commit | `a3542d2` workspace docs only — no foundation conflict |

---

## Operator approval still required

Todo H remains **pending**. Required before implementation:

```text
Jag godkänner customer-card-domain-planens implementation-gate och tillåter att
customer-domain-h-implementation startas enligt den godkända datamodellen,
migrationsordningen, tenantisoleringen, API-gränsen och matchningspolicyn.

Automatisk merge är fortsatt förbjuden om den inte godkänns separat.
```

**Explicit stop:** Do not start todo H, create implementation branch, or merge design branch without operator decision.
