# Customer card domain — API contract

> Todo E design contract. **No routers mounted.** **No runtime implementation.**

---

## 1. Naming collisions (verified)

| Surface | Meaning | Risk |
|---------|---------|------|
| `/ops/customers` | Tenant accounts (operator UI) | High — not end customers |
| `/customer/*` | Authenticated tenant API surface | Medium — auth tier name |
| `CustomerSettings*` | Tenant configuration | Medium |
| ERP `customer_id` | Fortnox/Visma ledger customer | High — external ID |
| Domain `customer_id` | Tenant's **end customer** | Target meaning |

**Recommended tenant route prefix:** `/end-customers`

Motivering: undviker kollision med befintlig tenant-API-yta och operator “customers”, tydlig i SDK och dokumentation, ERP `customer_id` mappas till `external_id` / `customer_number` identity types.

Operator routes: `/admin/tenants/{tenant_id}/end-customers/...`

---

## 2. Resources (future)

| Operation | Tenant route (proposed) | Operator route |
|-----------|----------------------|----------------|
| List end customers | `GET /end-customers` | `GET /admin/tenants/{tenant_id}/end-customers` |
| Open customer card | `GET /end-customers/{customer_id}` | `GET .../end-customers/{customer_id}` |
| Create manually | `POST /end-customers` | `POST .../end-customers` |
| Update verified fact | `PATCH /end-customers/{customer_id}/facts` | same under admin prefix |
| Add contact | `POST /end-customers/{customer_id}/contacts` | same |
| Timeline | `GET /end-customers/{customer_id}/timeline` | same |
| Linked jobs | `GET /end-customers/{customer_id}/jobs` | same |
| Linked threads | `GET /end-customers/{customer_id}/threads` | same |
| Duplicate list | `GET /end-customer-duplicates` | `GET .../end-customer-duplicates` |
| Duplicate detail | `GET /end-customer-duplicates/{id}` | same |
| Duplicate decision | `POST /end-customer-duplicates/{id}/decision` | same |
| Search | `GET /end-customers/search` | same |
| Match proposal | `POST /end-customer-match-proposals` | same |

---

## 3. Tenant isolation

- `tenant_id` från autentiserat server-side scope (API key / session).
- Tenant write-requests **innehåller inte** fritt `tenant_id`.
- `customer_id` alone insufficient — all queries filter `tenant_id`.
- Cross-tenant ID → `404 CUSTOMER_NOT_FOUND` or `403 TENANT_SCOPE_VIOLATION` (policy choice at implementation).

---

## 4. Role matrix (proposed)

| Operation | Tenant user | read_only | operations | admin |
|-----------|:-----------:|:---------:|:----------:|:-----:|
| List/read card, timeline, links | Yes | Yes | Yes | Yes |
| Create customer | Provisional | No | Yes | Yes |
| Update verified facts | Future workspace | No | Yes | Yes |
| Add contact | Future workspace | No | Yes | Yes |
| Duplicate decision | Future workspace | No | Yes | Yes |
| Merge | **Blocked** | No | No | No* |

\*Unless separately approved.

---

## 5. Pagination

- `limit` (default 50, max 100), `offset` (≥ 0)
- Response: `items`, `total`, `limit`, `offset`
- Tenant filter **before** pagination
- Stable sort + secondary opaque ID sort

---

## 6. Search

- Fields: display name, email, phone, org number, customer number (normalized)
- Min query length: 2
- Tenant-scoped server-side
- `exact_match` flag for identity fields
- No cross-tenant results

---

## 7. Optimistic locking

- Writable aggregates carry `version`
- Mutations require `expected_version`
- Mismatch → `409 CUSTOMER_VERSION_CONFLICT`

---

## 8. Idempotency

Header: `Idempotency-Key` for create, add contact, fact update, duplicate decision.

- Same tenant + operation + key + same payload → original result
- Same key + different payload → `409 IDEMPOTENCY_CONFLICT`

Documented in `CustomerWriteHeaders` schema (not duplicated in body).

---

## 9. Audit (writes)

Record: tenant, actor, operation, target type/ID, previous/new version, provenance, reason, idempotency key, outcome.

---

## 10. Error codes

`CustomerErrorCode` enum covers all required codes including `DUPLICATE_TIMELINE_EVENT` and `INVALID_TIMELINE_METADATA`.

---

## 11. UI contract (workspace — not implemented)

Workspace later needs: customer list, card, contacts, timeline, linked jobs/threads, open conflicts, duplicate queue, permissions, version conflicts, loading/empty/error states.

---

## 12. Stop-gate (todo E)

| Condition | Result |
|-----------|--------|
| Major auth change required | **PASS** — existing roles sufficient |
| Router required for tests | **PASS** — isolated Pydantic tests |
| `app/main.py` change required | **PASS** |
| `/ops/customers` collision unmanageable | **PASS** — `/end-customers` naming |
| ERP ID collision | **PASS** — identity type separation |
| Client-controlled tenant_id | **PASS** — omitted from writes |

**Todo E stop-gate: PASS**
