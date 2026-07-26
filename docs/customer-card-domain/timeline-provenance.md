# Customer card domain — timeline and provenance

> Todo D design contract. **Not implemented** in runtime or persistence.

**Baseline:** `docs/customer-card-domain/domain-model.md` (2026-07-26)

---

## 1. Referens-ID:n från repository (read-only audit)

Timeline events ska referera till befintliga records utan att kopiera payloads:

| Reference type | Repository anchor | Tenant key |
|----------------|-------------------|------------|
| `job` | `jobs.job_id` | `jobs.tenant_id` |
| `gmail_thread` | job `input_data.source.thread_id` | job `tenant_id` |
| `gmail_message` | job `input_data.source.message_id` | job `tenant_id` |
| `approval` | `approval_requests.approval_id` | `approval_requests.tenant_id` |
| `action_execution` | `action_executions.execution_id` | `action_executions.tenant_id` |
| `integration_event` | integration events repository | `tenant_id` |
| `source_fact` | future `customer_source_facts` | `tenant_id` |

Ingen ändring av källtabeller krävs för kontraktet.

---

## 2. Source fact

Varje fact bär:

- `fact_id`, `tenant_id`
- `subject_type`, `subject_id`
- `field_name`, `raw_value`, `normalized_value`
- `fact_state`, `source_type`, `source_reference`, `source_actor`
- `confidence` (0.0–1.0)
- `observed_at`, `recorded_at`, `verified_at`, `verified_by`
- `supersedes_fact_id`, `conflicts_with_fact_ids`

Facts är append-only i design: korrigering skapar ny fact eller explicit beslut, inte radering.

---

## 3. Fact states och övergångar

| State | Meaning |
|-------|---------|
| `known` | Observerad utan verifiering |
| `proposed` | Förslag som kräver review |
| `verified` | Administrativt eller auktorativt verifierad |
| `conflicting` | Motsäger annan fact |
| `historical` | Ersatt men bevarad |
| `rejected` | Avvisad observation |

Tillåtna övergångar implementeras i `provenance.py` (`ALLOWED_FACT_TRANSITIONS`).

Förbjudna direktövergångar inkluderar `historical → *` och `verified → proposed` utan ny fact.

---

## 4. Source precedence (beslutsprincip, inte overwrite)

Rank (högre = starkare):

1. `admin_correction`
2. `user_input` (verifierad)
3. `integration` (verifierad)
4. `import`
5. `gmail_inbound` (direkt observation)
6. `ai_extraction`
7. `system_derived`

`lower_source_cannot_supersede_verified()` blockerar att lägre källa automatiskt ersätter verifierad fact.

---

## 5. Timeline event

Fält: `timeline_event_id`, `tenant_id`, `customer_id`, `event_type`, `occurred_at`, `recorded_at`, actor, `source_type`, `reference_type`, `reference_id`, `summary`, allowlistad `metadata`.

`occurred_at` = när händelsen inträffade; `recorded_at` = när plattformen registrerade den.

---

## 6. Eventtyper

Alla `TimelineEventType` enum-värden är dokumenterade. Merge-relaterade (`merge_approved`, `merge_completed`) kan representeras i kontrakt men **aktiverar inte merge**.

---

## 7. Reference policy

- Referens-ID är opaka strängar.
- Fullständiga job-, mejl-, approval- eller actionpayloads får inte kopieras.
- `reference_type` + `reference_id` räcker för UI-länkning.

---

## 8. Ordering

Deterministisk sortering (`sort_timeline_events`):

1. `occurred_at`
2. `recorded_at`
3. `timeline_event_id` (opakt stabilt ID)

Sena/backfillade events med tidigare `occurred_at` placeras korrekt i tidslinjen medan `recorded_at` bevarar registreringsordning vid lika `occurred_at`.

---

## 9. Idempotens och replay

- `TimelineReplayIdentity` = `tenant_id + customer_id + event_type + source_reference_key`
- `build_source_reference_key()` normaliserar `SourceReference`
- `is_duplicate_replay()` detekterar dubbel registrering
- Konflikt uttrycks som `DUPLICATE_TIMELINE_EVENT` (API-felkod)

---

## 10. Metadata allowlist

Tillåtna nycklar: `job_type`, `job_status`, `approval_state`, `action_type`, `action_status`, `field_name`, `fact_state`, `integration_type`, `thread_id`, `message_id`, `duplicate_status`, `confidence`, `reason_code`, m.fl.

Förbjudna: `payload`, `body_text`, `token`, `credential`, `secret`, `api_key`, m.fl.

Validering: `validate_timeline_metadata()` och schema-validator på `CustomerTimelineEvent`.

---

## 11. Stop-gate (todo D)

| Condition | Result |
|-----------|--------|
| Source tables must change | **PASS** |
| Runtime hooks required | **PASS** |
| Uncontrolled JSON only | **PASS** |
| Tenant isolation | **PASS** |
| Fact mutation/deletion required | **PASS** |
| Full payload copy required | **PASS** |

**Todo D stop-gate: PASS**
