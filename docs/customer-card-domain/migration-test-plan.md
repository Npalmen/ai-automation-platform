# Customer card domain — migration, backfill, and test plan

> Todo F design document. **No migrations, tables, repositories, or backfill code.**

**Verified migration mechanism:** versioned SQL files in `migrations/` applied by `app/repositories/postgres/migration_runner.py` (`ORDERED_MIGRATION_FILES`). Baseline tables via `scripts/create_tables.py`. **Not Alembic.**

---

## A. Persistence architecture

### Alternative 1 — Normalized (recommended)

Separate tables for customers, companies, contacts, relationships, identities, addresses, source_facts, timeline_events, job_links, thread_links, duplicate_candidates, merge_decisions.

| Pros | Cons |
|------|------|
| Clear tenant FK boundaries | More migrations |
| Append-only facts/timeline natural | More repositories |
| Company/contact separation preserved | |

### Alternative 2 — Combined facts projection

Single `customer_facts` wide table with JSON subject discriminator.

| Pros | Cons |
|------|------|
| Fewer tables | Weak FK enforcement |
| | Harder provenance queries |
| | Risk of CRM-style blob |

**Recommendation:** Alternative 1 — minimal normalized model aligned with isolated schemas.

---

## B. Proposed table order

1. `end_customers` (aggregate root + version)
2. `end_customer_companies`
3. `end_customer_contacts`
4. `end_customer_relationships`
5. `end_customer_identities`
6. `end_customer_addresses`
7. `end_customer_source_facts` (append-only)
8. `end_customer_job_links`
9. `end_customer_thread_links`
10. `end_customer_timeline_events` (append-only)
11. `end_customer_duplicate_candidates`
12. `end_customer_merge_decisions` (append-only)

Prefix `end_customer_` avoids collision with ERP/tenant naming.

---

## C. Tenant invariants

- `tenant_id` NOT NULL on every table
- Composite uniqueness: `(tenant_id, …)` never global on email/phone/org alone
- Repository methods always filter `tenant_id` first
- Cross-tenant FK forbidden
- Same email in two tenants = two rows

---

## D. Indexes (proposed)

| Index | Purpose |
|-------|---------|
| `(tenant_id, status)` | Active customer lists |
| `(tenant_id, normalized_email)` | Candidate generation |
| `(tenant_id, normalized_phone)` | Candidate generation |
| `(tenant_id, organization_number)` | Company lookup |
| `(tenant_id, source_type, customer_number)` | ERP identity |
| `(tenant_id, integration_type, account_ref, thread_id)` | Thread context |
| `(tenant_id, customer_id, occurred_at, recorded_at)` | Timeline order |
| `(tenant_id, duplicate_status)` | Review queue |
| `(tenant_id, idempotency_key)` | Write idempotency |

Match indexes are candidate-generation only — not merge proof.

---

## E. Append-only and versioning

| Entity | Append-only | Version field |
|--------|-------------|---------------|
| source_facts | Yes | — |
| timeline_events | Yes | — |
| merge_decisions | Yes | — |
| customers | No | `version` |
| duplicate_candidates | No | `version` |
| companies/contacts | No | optional |

Optimistic locking on `customers` and `duplicate_candidates`.

---

## F. Rollout (future)

1. SQL migration creates tables — no runtime import
2. Verify constraints in CI/staging
3. Deploy with feature flag `customer_domain_enabled=false`
4. Implement repositories + contract tests
5. Backfill single test tenant (dry-run first)
6. Enable read-only card API
7. Enable manual writes + duplicate decisions
8. Match proposals (no auto-link/merge)
9. Workspace read-only UI
10. Production gate (todo G + operator approval)

---

## G. Rollback

| Stage | Rollback |
|-------|----------|
| Migration only | Drop new tables if empty |
| Runtime before backfill | Disable flag, no data loss |
| Backfill in progress | Stop job; mark tenant checkpoint |
| Bad facts | Quarantine + reject facts; no job mutation |
| Bad timeline | Mark events superseded; no source delete |
| API enabled | Feature flag off |
| Wrong duplicates | Close/reject candidates |

Rollback never mutates `jobs`, Gmail records, approvals, or actions.

---

## H. Backfill principles

- Tenant-scoped, idempotent, restartable, checkpointed
- Read-only against source jobs/Gmail
- Creates `proposed` facts and duplicate candidates only
- Quarantine uncertain rows
- Count/hash report before/after
- **No automatic merge or link**

---

## I. Backfill sources

| Source | Authority | Default fact state | Verified allowed? |
|--------|-----------|-------------------|-------------------|
| Gmail sender | Medium observation | proposed | No |
| AI entity extraction | Low | proposed | **No** |
| Lead/support processor output | Low–medium | proposed | No |
| Job input `source` | Medium | proposed | No |
| Gmail thread ID | Medium link signal | link only | No |
| ERP customer number | High if integration verified | proposed/verified | Yes with integration proof |
| Admin correction | Highest | verified | Yes |

---

## J. Synthetic fixture families

Five JSON fixtures under `tests/fixtures/customer_domain/`:

1. `family_01_new_private_customer.json`
2. `family_02_returning_customer_new_thread.json`
3. `family_03_changed_contact.json`
4. `family_04_company_multiple_contacts.json`
5. `family_05_ambiguous_duplicate.json`

Each includes `schema_version`, tenant, observations, expected facts/timeline/links, duplicate outcome, `automatic_merge_allowed=false`.

---

## K. Test matrix

| Level | What | Environment | Before gate G? |
|-------|------|-------------|----------------|
| 1 | Schema/contract tests | Unit | Yes |
| 2 | Normalization/matching | Unit | Yes |
| 3 | PostgreSQL repositories | Test DB | After H foundation |
| 4 | Migration forward/rollback | CI DB | After H foundation |
| 5 | Backfill dry-run | Staging | After H + flag |
| 6 | Tenant isolation HTTP | Test client | After API chapter |
| 7 | API contracts | Unit + HTTP | Split |
| 8 | Optimistic locking | Integration | After writes |
| 9 | Idempotency | Integration | After writes |
| 10 | Stateful evaluation | Fixtures + DB | Todo I |
| 11 | Workspace read-only | Frontend contract | After UI chapter |
| 12 | Post-deploy smoke | Pilot | Todo J |

---

## L. Implementation chapters (proposed only)

1. `feat/customer-card-foundation` — migration + core tables
2. `feat/customer-card-repositories` — tenant-isolated repos
3. `feat/customer-card-timeline` — facts + timeline writes
4. `feat/customer-card-matching-persistence` — duplicate candidates
5. `feat/customer-card-api-read` — read-only routes
6. `feat/customer-card-api-write` — manual writes + decisions
7. `feat/customer-card-workspace-ui` — read-only workspace
8. `feat/customer-card-evaluation` — stateful eval + rollout

---

## Stop-gate (todo F)

| Condition | Result |
|-----------|--------|
| Safe table order describable | **PASS** |
| Tenant invariants without source table changes | **PASS** |
| Backfill has tenant evidence | **PASS** — via job.tenant_id |
| Rollback without destructive source edits | **PASS** |
| Auto merge required | **PASS** — forbidden |
| Migration mechanism verified | **PASS** — SQL files + runner |
| Workspace/testbot collision | **PASS** — separate tracks |

**Todo F stop-gate: PASS**
