# Customer card domain — repository current truth

> Read-only audit for `customer-card-domain` design track (todo A).  
> **Audit date:** 2026-07-26  
> **Main SHA:** `758502ed1b451929bdb4bd39c9b02aaf760c5aeb`  
> **Branch:** `design/customer-card-domain`  
> **Python:** 3.14.3

---

## 1. Baseline and audit scope

This document records verified repository evidence for customer-like concepts before introducing an isolated end-customer domain. No runtime code was changed during this audit.

**Start working tree (non-scope noise):** modified `storage/status/full-system-testbot-*.md`; untracked `docs/plans/customer-card-domain-plan.md`, `docs/plans/customer-workspace-plan.md`, and assorted `storage/status/` artifacts. These are outside the customer-domain commit scope and were not stashed or reset.

**Parallel tracks that may collide on naming (not on files yet):**

| Track | Branch / artifact | Overlap risk |
|-------|-------------------|--------------|
| Customer workspace UI | `docs/plans/customer-workspace-plan.md` (pending todos) | UI label “customer” = tenant user; `/ops/customers` = tenant accounts |
| Customer settings | `app/admin/customer_settings/**` | Tenant configuration, not end customers |
| Fortnox/Visma | integration mappers | External ERP `customer_id` / `customer_number` |
| Operator “customers” frontend | `frontend/src/features/customers/**` | Tenant directory, not end-customer CRM |

No `app/domain/customer/**` or end-customer SQLAlchemy table existed at audit time.

---

## 2. Tenant vs end customer

| Concept | Repository meaning | Primary symbols |
|---------|-------------------|-----------------|
| **Tenant** | Company using the platform | `tenant_id` on jobs, approvals, audit, configs |
| **Tenant account** | Operator UI “customer” / tenant onboarding | `/ops/customers`, `TenantListItem`, `TenantConfigRecord` |
| **End customer** | Tenant’s client (private or company) | **Not persisted** as aggregate; scattered in job payloads and AI extraction |
| **ERP customer** | Fortnox/Visma ledger customer | `customer_id`, `CustomerNumber` in integration payloads |

`Customer` in the new domain must mean **tenant’s end customer**, never tenant account.

---

## 3. Inventoried customer-like concepts (summary table)

| Område | Fil/symbol | Data | Tenantnyckel | Återanvändbar | Risk/anmärkning |
|--------|------------|------|--------------|---------------|-----------------|
| Styrning | `docs/01-current-truth.md` | Verified system state | N/A | Ja (read) | No end-customer model documented |
| Styrning | `docs/plans/customer-workspace-plan.md` | Workspace UI plan | Per tenant | Ja (separate track) | “Kund” = tenant user in product text |
| Domän jobs | `app/domain/workflows/models.py` `Job` | `tenant_id`, `input_data`, `result` | `tenant_id` | Ja (link target) | Aggregate root for pipeline, not customer |
| Domän integrations | `app/domain/integrations/models.py` | Integration events | `tenant_id` | Ja (link target) | No customer FK |
| Lead analysis | `app/lead/models.py` `customer_type` | `private`/`company`/`brf` | Via job | Ja (classification hint) | Not a customer record |
| Lead offer | `app/lead/models.py` `OfferDraft` | `customer_name`, `customer_email`, `customer_phone`, `address` | Via job | Ja (source facts) | Ephemeral analysis output |
| Support | `app/support/models.py` | Sentiment, ticket metadata | Via job | Ja | No contact persistence |
| AI extraction | `app/ai/schemas.py` `EntityExtractionEntities` | `customer_name`, `company_name`, `email`, `phone`, `organization_number`, `address`, `city` | Via job pipeline | Ja (provenance source) | `extra=forbid`; confidence on parent response |
| AI invoice | `app/ai/schemas.py` `InvoiceAnalysisData` | `supplier_name`, `organization_number` | Via job | Partial | Supplier ≠ end customer |
| Persistence jobs | `app/repositories/postgres/job_models.py` `JobRecord` | JSON `input_data`, `result` | `tenant_id` indexed | Ja | Gmail source in `input_data.source` |
| Persistence approvals | `approval_models.py` `ApprovalRequestRecord` | `job_id`, payloads | `tenant_id` indexed | Ja (timeline link) | No customer_id |
| Persistence actions | `action_execution_models.py` | `job_id`, execution payloads | `tenant_id` indexed | Ja (timeline link) | No customer_id |
| Persistence audit | `audit_models.py` `AuditEventRecord` | `details` JSON | `tenant_id` indexed | Ja | Generic event log |
| Persistence tenant | `tenant_config_models.py` | `settings` JSON blob | `tenant_id` PK | Ja | Tenant-owned config |
| Tenant settings contact | `app/admin/customer_settings/validation.py` | `primary_contact`, `contact_email`, `phone` | `tenant_id` | Ja (tenant account) | **Not** end-customer contact |
| Gmail intake | `app/main.py` `_process_gmail_messages` | `source.message_id`, `source.thread_id`, `sender` | `tenant_id` on job | Ja | Message dedup + thread continuation |
| Job repo dedup | `JobRepository.get_by_gmail_message_id` | `(tenant_id, gmail, message_id)` | `tenant_id` required | Ja | Intake dedup only |
| Job repo thread | `JobRepository.get_by_source_thread_id` | `(tenant_id, system, thread_id)` | `tenant_id` required | Ja | Continuation, not customer merge |
| Action dispatch | `action_dispatch_processor.py` | `sender_email`, `sender_phone` from job | Via job | Ja (observation) | Monday column mapping |
| Frontend ops customers | `frontend/src/features/customers/types.ts` | `TenantListItem`, `TenantDetailResponse` | `tenant_id` | Ja (operator) | Name collision: “customers” = tenants |
| Fortnox | `app/integrations/fortnox/mappers.py` | `customer_id`, `customer_number` | Tenant integration context | External ID only | ERP customer, not domain Customer |
| Visma | `app/integrations/visma/mappers.py` | `customer_id` in invoice payload | Tenant integration context | External ID only | Same as Fortnox |
| ERP in main | `app/main.py` Visma finance path | `customer_id` from Visma API | Tenant-scoped job | External | Invoice export side effect |

---

## 4. Contact fields and owners

| Field | Where stored | Owner | Verified? |
|-------|--------------|-------|-----------|
| `sender.name`, `sender.email`, `sender.phone` | `jobs.input_data` (Gmail path) | Job / intake observation | Unverified observation |
| `entities.customer_name`, `company_name`, `email`, `phone`, `organization_number`, `address`, `city` | `jobs.result` / processor history via entity extraction | AI extraction on job | Proposed, not verified |
| `customer_name`, `customer_email`, `customer_phone`, `address` | Lead `OfferDraft` in processor output | Lead analyzer | Draft fields |
| `primary_contact`, `contact_email`, `phone` | `tenant_configs.settings` (customer settings domains) | Tenant account | Tenant operator config |
| Monday `email`, `phone` column values | Action execution payloads | Dispatch snapshot | Per-job |
| Fortnox/Visma `customer_id` / number | Integration request/response | External ERP | Integration-scoped |

No table stores a canonical end-customer contact graph.

---

## 5. Job, Gmail, approval, action, and audit identifiers

| ID type | Format | Scoped by | Repository access |
|---------|--------|-----------|-------------------|
| `job_id` | UUID string | `tenant_id` | `JobRecord.job_id` PK |
| `approval_id` | String | `tenant_id` | `ApprovalRequestRecord` |
| `execution_id` | String | `tenant_id` | `ActionExecutionRecord` |
| `event_id` | String | `tenant_id` | `AuditEventRecord` |
| Gmail `message_id` | Provider opaque string | `tenant_id` + job | `input_data.source.message_id`; dedup query |
| Gmail `thread_id` | Provider opaque string | `tenant_id` + system `gmail` | `input_data.source.thread_id`; continuation query |
| `internet_message_id` | RFC message id | Job message history entries | Continuation payloads |

All repository list/get patterns observed for jobs, approvals, actions, and audit include `tenant_id` in filter predicates.

---

## 6. Tenant isolation evidence

- **Jobs:** `JobRecord.tenant_id` non-null, indexed; repository methods require `tenant_id`.
- **Approvals / actions / audit:** same pattern.
- **Tenant config:** `tenant_id` primary key.
- **Gmail dedup:** `get_by_gmail_message_id(db, tenant_id, message_id)` — cross-tenant message IDs never queried together.
- **Auth:** customer API resolves tenant from API key; forged `X-Tenant-ID` rejected when auth enabled (`docs/01-current-truth.md` verified).
- **Frontend `/ops/customers`:** lists `TenantListItem` by operator session — platform tenants, not end customers.

---

## 7. Gmail thread/message provenance

Gmail intake (`app/main.py`):

1. Lists messages via adapter `list_messages`.
2. **Dedup:** skips if `JobRepository.get_by_gmail_message_id` finds existing job for same `tenant_id` + `message_id`.
3. Fetches full message; applies intake gate (lifecycle/cutoff).
4. Parses `from` header → `sender_name`, `sender_email`; extracts phone from subject/body.
5. **Thread continuation:** if `thread_id` present, loads latest job via `get_by_source_thread_id(tenant_id, "gmail", thread_id)` and appends message to job history instead of creating new job.
6. New jobs store `input_data.source` with `system=gmail`, `message_id`, `thread_id`, and related fields.

Provenance is job-centric. Thread linkage does not create or update a customer entity.

---

## 8. Gmail deduplication vs customer deduplication

| Mechanism | Purpose | Key | Customer dedup? |
|-----------|---------|-----|-----------------|
| Message dedup | Prevent duplicate jobs for same email | `(tenant_id, gmail message_id)` | No — only intake idempotency |
| Thread continuation | Group conversation on one job | `(tenant_id, gmail, thread_id)` | No — operational grouping |
| Intake gate skip | Lifecycle/cutoff enforcement | tenant + message metadata | No |
| Dispatch duplicate guard | Prevent double external dispatch | job + action hint | No |

Same person emailing in **new thread** creates a **new job**. Same email in **two tenants** creates **two jobs** with no linkage. Therefore Gmail dedup **does not** imply end-customer deduplication.

---

## 9. Existing tables — end-customer representation

SQLAlchemy models under `app/repositories/postgres/` at audit time included: `jobs`, `approval_requests`, `action_executions`, `audit_events`, `tenant_configs`, `oauth_credentials`, onboarding tables, `operator_alerts`, `decision_records`, `live_eval_*`, etc.

**No table** named `customers`, `end_customers`, `contacts`, `companies`, or equivalent end-customer aggregate was found.

End-customer facts exist only as **JSON fields inside jobs** and **processor outputs**.

---

## 10. Active name and API collisions

| Surface | “Customer” meaning | Collision risk for new domain |
|---------|-------------------|------------------------------|
| `/ops/customers` | Tenant accounts | High naming — document as tenant account in API/docs |
| `/customer/*` HTTP API | Authenticated tenant’s own API surface | Medium — different auth tier |
| `CustomerSettings*` schemas | Tenant settings bundle | Medium — prefix distinguishes |
| `customer_type` in lead analysis | Private vs company lead | Low — attribute, not entity |
| `send_customer_auto_reply` action | Email to message sender | Low — workflow action name |
| Fortnox/Visma `customer_id` | ERP customer record | High for integration IDs — use `external_id` identity type |
| `CustomerAccountRequest` in `main.py` | Finance/onboarding request shape | Medium — tenant account |

Recommended new domain symbols: `Customer`, `Company`, `Contact`, `CustomerCard` under `app/domain/customer/` with explicit `end_customer` documentation in API todo E.

---

## 11. Recommended reuse

| Reuse | How |
|-------|-----|
| `tenant_id` scoping | Mirror existing repository tenant filter pattern |
| `job_id`, `approval_id`, `execution_id`, audit `event_id` | `CustomerJobLink`, timeline `reference_id` — reference only |
| Gmail `thread_id` / `message_id` | `CustomerThreadLink`, identity types `gmail_thread` / `gmail_message` within integration context |
| `EntityExtractionEntities` | Seed `CustomerSourceFact` with `source_type=ai_extraction` |
| `sender` on job input | Seed facts with `source_type=gmail_inbound` |
| Lead `customer_type` | Hint for `Customer.customer_type`, not authoritative |
| Tenant settings contact fields | Remain tenant-account owned; do not import into Customer |
| ERP customer numbers | `identity_type=customer_number` or `external_id` with integration source |

---

## 12. Identified gaps

1. No aggregate root for end customer across jobs/threads.
2. No verified vs proposed contact state — extraction and sender are mixed into jobs.
3. No duplicate review queue for end customers (only Gmail message dedup and ERP IDs).
4. No timeline spanning jobs for the same person/company.
5. No structured company/contact graph (multiple contacts per company).
6. Historical contact changes overwrite or scatter in job history without conflict model.
7. Operator UI has no end-customer card — only tenant detail.

---

## 13. Stop-gate assessment (todo A)

| Gate condition | Result |
|----------------|--------|
| Existing end-customer table or cohesive domain | **PASS** — none found |
| Parallel track building same models | **PASS** — workspace plan is UI-only; no `app/domain/customer` |
| Customer separable from tenant account | **PASS** — distinct IDs and UI surfaces |
| Tenant isolation on records to reuse | **PASS** — `tenant_id` on all core tables |
| Job/Gmail tables must change for audit | **PASS** — read-only audit sufficient |
| Audit requires changes outside allowed scope | **PASS** — documentation only |

**Todo A stop-gate: PASS** — proceed to domain model (todo B).

---

## 14. Extended inventory (grep anchors)

Repository search covered: `Customer`, `customer`, `customer_id`, `customer_number`, `company`, `contact`, `sender_email`, `organization_number`, `thread_id`, `message_id`, `tenant_id`, `duplicate`, `dedup`, `match`, `identity`, `address`.

**`app/domain/**`:** workflows and integrations packages only — no customer package pre-existing.

**Migrations:** `schema_migrations.py` adds onboarding, alerts, decision_records, live_eval — no customer tables.

**Tests:** extensive `customer_settings`, `tenant_isolation`, Fortnox customer lookup — all tenant or ERP scoped.
