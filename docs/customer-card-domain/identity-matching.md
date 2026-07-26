# Customer card domain — identity matching

> Todo C contract. Implements **assessment only** — no candidate generation, database queries, or merge.

---

## 1. Pipeline stages

| Stage | Todo C scope | Future work |
|-------|--------------|-------------|
| Candidate generation | Not implemented | Query tenant-scoped identity index |
| Match assessment | `assess_customer_match()` | API `POST /customer-match-proposals` |
| Merge decision | Not implemented | Operator workflow after review |

Match and merge are separate. Strong assessment never implies merge.

---

## 2. Normalization rules

| Identity | Function | Conservative rules |
|----------|----------|-------------------|
| Email | `normalize_email` | NFKC, trim, casefold domain/local; preserve plus-tags; reject invalid `@`; flag role-based local parts |
| Phone | `normalize_phone` | Strip safe separators; `00` → `+`; SE `0` → `+46` only when `country_code=SE`; reject ambiguous |
| Org number (SE) | `normalize_organization_number` | Digits only; 12-digit `16…` → 10 digits; reject invalid length |
| Name | `normalize_name` | NFKC, collapse whitespace, casefold; never sufficient alone for strong match |
| Address | `normalize_structured_address` | Structured fields only; no geocoding |

All normalizers are pure: no I/O, network, database, or environment reads.

---

## 3. Score matrix

| Evidence | Score |
|----------|------:|
| Verified organization number (same tenant, country) | 0.90 |
| Verified customer number (same source) | 0.85 |
| Normalized email | 0.65 |
| Normalized phone | 0.55 |
| Gmail thread (same integration context) | 0.60 |
| Company relation ID | 0.50 |
| Structured address | 0.25 |
| Normalized name | 0.20 |

Total confidence is capped at `1.0`.

---

## 4. Confidence thresholds

| Confidence | Decision |
|------------|----------|
| `< 0.50` | `no_match` |
| `0.50–0.74` | `possible_duplicate` |
| `0.75–0.89` | `strong_candidate` |
| `>= 0.90` | `exact_candidate` |

Blocking rules and manual-review rules may override thresholds.

---

## 5. Blocking conflicts

Always `blocked` with `confidence=0.0`:

- Different `tenant_id`
- Tenant account compared to end customer
- Person compared to company as same entity
- Different verified organization numbers
- Different verified customer numbers from same authoritative source
- Missing tenant on either subject

---

## 6. Manual review rules

Forces `manual_review_required` or caps confidence to `0.74`:

- Same phone, different verified names
- Same email, different verified company names
- Role-based email without company relation or verified company name
- Historical verified phone contradicts current observation
- Strong/exact candidates still require review (`requires_manual_review=true`)

Weak-only signals downgrade to `no_match`:

- Name alone (`0.20`)
- Address without stronger identity (`0.25` only)

---

## 7. Role-based email

Local parts `info`, `support`, `faktura`, `invoice`, `order`, `kontakt`, `kundservice`, `admin` are flagged. They are not treated as unique person identity without company relation or verified company name.

Plus-tags in email are preserved (not stripped).

---

## 8. Gmail thread context

Thread ID match scores `0.60` only when:

- Same `tenant_id`
- Same `integration_type`
- Same `integration_account_reference`
- Equal `gmail_thread_id`

Cross-tenant thread comparison is blocked at tenant gate, not low confidence.

---

## 9. Company vs contact

`Contact` / private `Customer` compared to `Company` / company `Customer` yields `blocked` (`person_vs_company`).

---

## 10. Automatic merge prohibition

All assessment results:

```text
automatic_merge_allowed = false
automatic_link_allowed = false
```

Schema validator rejects `true` on `CustomerMatchAssessment`.

---

## 11. Determinism

- Evidence sorted by `(-score, code)`
- Conflicts sorted by `code`
- Reason codes sorted by enum value

Same input produces identical serialized assessment.

---

## 12. Stop-gate (todo C)

| Condition | Result |
|-----------|--------|
| Database required | **PASS** |
| Gmail adapter change required | **PASS** |
| External normalization service | **PASS** |
| Automatic merge for tests | **PASS** |
| Cross-tenant block | **PASS** |
| Deterministic codes | **PASS** (verified by tests) |

**Todo C stop-gate: PASS** (verified by tests)
