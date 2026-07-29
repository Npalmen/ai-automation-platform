---
name: Testbot F2 shadow pipeline
overview: Bygg en tenant-isolerad och fail-closed kedja från intake till shadow customer observations och match proposals utan automatisk verifiering, länkning eller merge.
todos:
  - id: shadow-a-foundation
    content: Inför shadow observation ledger, state machine, provenance och idempotency
    status: completed
  - id: shadow-b-domain-services
    content: Implementera shadow command/read services, match proposals och cleanup
    status: completed
  - id: shadow-c-mock-intake
    content: Koppla syntetisk intake och extraction till shadow write boundary
    status: completed
  - id: shadow-d-scenarios
    content: Implementera TBF2-01 till TBF2-10 med strukturerade oracles
    status: completed
  - id: shadow-e-safety
    content: Implementera tenant isolation, fail-closed matching, replay och abuse controls
    status: completed
  - id: shadow-f-delivery
    content: Kör hermetiska och PostgreSQL-baserade tester, PR, merge och post-merge gates
    status: in_progress
  - id: shadow-g-closure
    content: Kvalificera F2a/F2b och stoppa före eventuell live Gmail-canary
    status: pending
isProject: true
---

# Testbot F2 — Shadow pipeline för kundkort

## 1. Beslut

Valt genomförandespår:

**Spår A — separat shadow observation ledger**

Kedjan ska vara:

```text
intake event
→ normalisering
→ extraction
→ shadow observation
→ identity signals
→ match assessment
→ match proposal / awaiting operator
→ explicit operator promotion
→ proposed fact i kunddomänen
→ separat operator verification
```

F2 får inte skriva AI-resultat direkt som verifierade kundfakta och får inte automatiskt länka, slå ihop eller ersätta befintlig kundinformation.

F2 delas i:

- **F2a — Shadow domain model**
- **F2b — Intake integration med mockad transport**
- **F2c — Eventuell live Gmail observe-canary, separat beslut**

F2a och F2b byggs först. F2c är inte inkluderad i denna implementation.

---

## 2. Verifierad baseline

- Testbot C: `completed`
- Testbot D: `completed`
- Testbot E: `completed`
- Testbot F: `in_progress`
- `CUSTOMER_CARD_STATEFUL_DIRECT_QUALIFIED`
- `CUSTOMER_CARD_HTTP_CONTRACT_QUALIFIED`
- Kunddomänen A–J är implementerad men inte produktaktiverad
- End-customer read/write-flaggor är default `false`
- Gmail/intake skriver inte kundfakta till end-customer-domänen
- `automatic_link_allowed = false`
- `automatic_merge_allowed = false`
- F1/F1b har verifierat TBF01–TBF10, HTTP-kontrakt, tenant isolation, idempotency och cleanup
- Ingen live Gmail, produktionsdata eller bred tenantaktivering ingår

---

## 3. Mål

F2 ska verifiera att verklig intake- och workflowkod kan skapa säkra, isolerade och idempotenta kundobservationer utan att förorena kunddomänens verifierade state.

F2 ska bevisa:

1. Ett intake-event kan ge en shadow observation.
2. Extraction och identitetssignaler får full provenance.
3. Matchning skapar förslag, inte automatisk länkning.
4. AI-observationer kan inte bli verified eller current.
5. Replay skapar inte dubbletter.
6. Konflikter och osäkra matchningar exponeras.
7. Tenantgränser hålls.
8. Cleanup kan ta bort exakt campaign-skapad shadowdata.
9. Inga externa adapters eller Gmail-svar används.
10. Operatorpromotion är en separat explicit write boundary.

---

## 4. Avgränsningar

### Tillåtet

- Nya shadow-tabeller eller motsvarande isolerad persistence
- Shadow observation service
- Shadow read service
- Match proposal service
- Intake-hook bakom separat feature flag
- Mockad Gmail-liknande transport
- Syntetiska extraction fixtures
- Hermetiska tester
- PostgreSQL stateful tester
- Strukturerade evalrapporter
- Campaign-bound cleanup
- Operatorpromotion till `PROPOSED` fact i isolerad evalmiljö, om detta ingår i F2a-kontraktet

### Förbjudet

- Live Gmail
- Gmail replies
- Produktionsaktivering
- Verkliga kunder
- Automatisk verification
- Automatisk current-state-ändring
- Automatisk customer link
- Automatisk merge
- Automatisk duplicate resolution
- Direkt AI-write till verified facts
- Kundkortets UI
- Sheets, Monday eller Visma
- Pris-, boknings-, ekonomiska eller avtalsmässiga actions
- Bred aktivering för andra tenants

---

## 5. Arkitektur

### 5.1 Primär modell: shadow observation ledger

Inför ett separat lager för olänkade eller ännu inte godkända observationer.

Föreslagen modell:

#### `end_customer_shadow_observations`

Minst:

- `id`
- `tenant_id`
- `campaign_run_id`
- `scenario_execution_id`
- `source_provider`
- `source_message_id`
- `source_thread_id`
- `source_event_id`
- `extraction_version`
- `observation_type`
- `state`
- `raw_payload_hash`
- `normalized_payload_hash`
- `confidence`
- `model_name`
- `model_prompt_version`
- `created_at`
- `updated_at`
- `rejected_at`
- `rejected_by`
- `cleanup_eligible`

#### `end_customer_shadow_identity_signals`

Minst:

- `id`
- `tenant_id`
- `observation_id`
- `signal_type`
- `raw_value_redacted`
- `normalized_value`
- `confidence`
- `source_path`
- `trust_level`
- `created_at`

Signaltyper kan vara:

- email
- phone
- person_name
- company_name
- organisation_number
- address
- reply_to
- sender
- thread_id

#### `end_customer_shadow_fact_proposals`

Minst:

- `id`
- `tenant_id`
- `observation_id`
- `field_name`
- `proposed_value`
- `normalized_value`
- `confidence`
- `source_type`
- `state`
- `target_end_customer_id`
- `promotion_status`
- `created_at`
- `promoted_at`
- `promoted_by`

#### `end_customer_shadow_match_proposals`

Minst:

- `id`
- `tenant_id`
- `observation_id`
- `candidate_end_customer_id`
- `match_score`
- `match_reasons`
- `deterministic_signals`
- `ambiguous_signals`
- `state`
- `created_at`
- `resolved_at`
- `resolved_by`
- `resolution`

### 5.2 Varför separat ledger

Det separata lagret väljs eftersom:

- olänkade observationer kan lagras utan att skapa falska kunder,
- AI-provenance hålls skild från verifierad kunddata,
- replay och extraction-versioner kan hanteras utan att skriva om kundhistorik,
- operatorn kan granska före promotion,
- cleanup blir tydlig,
- framtida promotion kan ske explicit och idempotent,
- nuvarande `automatic_link_allowed=false` kan behållas.

---

## 6. State machine

### 6.1 Shadow observation

```text
observed
→ normalized
→ extracted
→ match_assessed
→ awaiting_operator
→ promoted
→ rejected
→ superseded
```

Tillåtna systemövergångar:

- `observed → normalized`
- `normalized → extracted`
- `extracted → match_assessed`
- `match_assessed → awaiting_operator`
- `extracted → awaiting_operator` när matchning inte kan genomföras
- valfri tidigare state → `superseded` vid ny extraction-version

Endast operator får utföra:

- `awaiting_operator → promoted`
- `awaiting_operator → rejected`

Förbjudna direkta övergångar:

- observation → verified
- observation → current
- observation → linked
- observation → merged
- observation → duplicate_resolved

### 6.2 Match proposal

```text
proposed
→ awaiting_operator
→ confirmed_for_promotion
→ rejected
→ expired
```

`confirmed_for_promotion` betyder inte att en faktisk customer link skapas automatiskt. Det ger endast rätt att starta en separat, explicit promotion.

### 6.3 Fact proposal

```text
shadow
→ approved_for_promotion
→ promoted_as_proposed_fact
→ verified_by_operator
```

F2 får endast kvalificera fram till:

```text
promoted_as_proposed_fact
```

Verifiering ligger kvar i befintligt operatorflöde och är inte en AI- eller intake-åtgärd.

---

## 7. Write-matris

| Record | F2a | F2b | Villkor |
|---|---:|---:|---|
| Shadow observation | Ja | Ja | Tenant-, source- och campaign-bunden |
| Shadow identity signal | Ja | Ja | Endast observerad/proposed |
| Shadow fact proposal | Ja | Ja | Aldrig verified/current |
| Match proposal | Ja | Ja | Ingen faktisk link |
| Provisional customer | Nej | Nej | Skapar för stor risk för falska kunder |
| Proposed fact i kunddomänen | Endast explicit operatorpromotion | Endast explicit operatorpromotion | Idempotent och auditerad |
| Identity ownership/link | Nej | Nej | Kräver separat operatorbeslut |
| Job link | Nej automatiskt | Nej automatiskt | Endast proposal |
| Thread link | Nej automatiskt | Nej automatiskt | Thread-ID är inte identity proof |
| Verified fact | Nej | Nej | Operatorverification krävs |
| Duplicate resolution | Nej | Nej | Operator krävs |
| Merge | Nej | Nej | Förbjudet |
| Current-state overwrite | Nej | Nej | Förbjudet |

---

## 8. Matching och identitet

### 8.1 Begrepp

Håll separata:

1. extraherad signal
2. normaliserad signal
3. candidate lookup
4. deterministic match evidence
5. heuristic match evidence
6. match score
7. match proposal
8. operator-confirmed promotion target
9. customer link
10. duplicate decision

### 8.2 Signaler som aldrig ensamma får länka

- namn
- Gmail thread-ID
- företagsdomän
- adresslikhet
- LLM-confidence
- telefonnummer från ostrukturerad text
- Reply-To som skiljer sig från verifierad sender
- shared mailbox
- forwarded sender information

### 8.3 Exakt e-postmatchning

Exakt tenant-bunden normaliserad e-post får:

- hitta kandidater,
- skapa match proposal,
- höja match score,
- föreslå promotion target.

Den får inte:

- skapa faktisk customer link,
- flytta facts,
- verifiera identitet,
- mergea kunder,
- ersätta current state.

Detta bevarar `automatic_link_allowed=false`.

---

## 9. Idempotency

Canonical key:

```text
tenant_id
+ source_provider
+ source_message_id
+ extraction_version
+ observation_type
```

Ytterligare nycklar:

```text
observation:
shadow-observation:{tenant}:{provider}:{message}:{version}

identity signal:
shadow-signal:{observation}:{signal_type}:{normalized_hash}

fact proposal:
shadow-fact:{observation}:{field}:{normalized_hash}

match proposal:
shadow-match:{observation}:{candidate_customer_id}:{matcher_version}

promotion:
shadow-promotion:{observation}:{proposal}:{target_customer}:{operator_action_id}
```

Krav:

- samma message och extraction-version ger samma observation,
- ny extraction-version skapar ny version utan att skriva över gammal provenance,
- samma signal skapar inte extra rad,
- samma fact proposal skapas inte två gånger,
- samma promotion replayas idempotent,
- DB-timeout efter commit får inte skapa dublett,
- provider/workflow-retry får inte skapa ny observation,
- thread continuation med nytt message-ID skapar ny observation men behåller separat thread provenance.

---

## 10. Feature flags

Inför separata flags:

```text
END_CUSTOMER_SHADOW_INTAKE_ENABLED=false
END_CUSTOMER_SHADOW_MATCHING_ENABLED=false
END_CUSTOMER_SHADOW_PROMOTION_ENABLED=false
```

Ansvar:

- `SHADOW_INTAKE`: får skapa observationer/signaler/fact proposals
- `SHADOW_MATCHING`: får skapa match proposals
- `SHADOW_PROMOTION`: tillåter explicit operatorpromotion till befintlig kunddomän som `PROPOSED`

Krav:

- alla default `false`,
- tenant allowlist krävs,
- ingen global implicit aktivering,
- befintliga read/write flags ändras inte,
- activation audit krävs,
- operator kan pausa före nästa intake,
- eval readiness verifierar exakt tenant och flaggscope,
- F2b använder endast isolerad evalprocess.

---

## 11. F2-scenariomatris

### TBF2-01 — New sender

Förväntat:

- 1 shadow observation
- identitetssignaler sparas
- 0 verified facts
- 0 actual customer links
- 0 merges

### TBF2-02 — Returning exact email

Förväntat:

- ny observation för nytt message-ID
- match proposal till befintlig kund
- ingen automatisk link
- ingen duplicate observation
- thread och email signaler hålls separata

### TBF2-03 — Changed phone

Förväntat:

- nytt phone fact proposal
- tidigare verified phone kvar som current
- shadow conflict/pending exponeras
- 0 current-state-mutationer

### TBF2-04 — Conflicting identity

Förväntat:

- conflict/manual review
- ingen automatisk link
- ingen promotion
- inga verified facts

### TBF2-05 — Company multi-contact

Förväntat:

- två separata contact signals
- gemensam domän får inte slå ihop personer
- separata match proposals
- ingen actual link

### TBF2-06 — Ambiguous match

Förväntat:

- flera kandidater eller låg säkerhet
- explicit ambiguous state
- match reasons redovisas
- ingen link

### TBF2-07 — Thread continuation

Förväntat:

- nytt message-ID ger ny observation
- thread-ID binds som source provenance
- thread-ID används inte som customer identity
- ingen faktisk thread/customer link skapas automatiskt

### TBF2-08 — Duplicate intake/replay

Förväntat:

- exact-once observation
- inga extra signals
- inga extra fact proposals
- inga extra match proposals
- stabil semantic hash

### TBF2-09 — Low-confidence extraction

Förväntat:

- observation kan sparas
- extraction state visar låg confidence
- inga fact proposals promoveras
- operator review krävs

### TBF2-10 — Prompt injection eller malformed content

Förväntat:

- innehåll behandlas som data
- inga flags eller policies påverkas
- inga verified facts
- inga customer links
- inga externa actions
- redigerad safety event skapas

---

## 12. Strukturerade oracles

Varje scenario ska rapportera:

- `scenario_id`
- `scenario_execution_id`
- `tenant_id_hash`
- `source_message_id_hash`
- `source_thread_id_hash`
- `observation_count`
- `observation_state`
- `extraction_version`
- `identity_signal_counts`
- `fact_proposal_counts`
- `match_proposal_counts`
- `match_reasons`
- `candidate_customer_count`
- `actual_customer_links`
- `actual_job_links`
- `actual_thread_links`
- `verified_facts_created`
- `current_state_mutations`
- `automatic_merges`
- `automatic_duplicate_decisions`
- `idempotency_records`
- `timeline_events`
- `cross_tenant_findings`
- `external_side_effects`
- `semantic_hash`
- `cleanup_status`

Campaign PASS kräver:

```text
verified_facts_created = 0
automatic_merges = 0
automatic_duplicate_decisions = 0
unauthorized_customer_links = 0
external_side_effects = 0
cross_tenant_findings = []
```

Operatorpromotionstester ska redovisas separat och får endast skapa `PROPOSED` facts.

---

## 13. F2a — Shadow domain model

### Leverans

- migration för shadow ledger
- domain models
- repositories
- command service
- read service
- state transitions
- match proposal persistence
- idempotency
- cleanup
- structured reporting
- TBF2-01 till TBF2-10 i direct-domain/PG-läge

### Tester

- hermetiska state machine-tester
- normalization
- idempotency
- tenant isolation
- match proposal safety
- replay
- extraction-version drift
- operatorpromotion till proposed fact
- cleanup
- migration chain
- PostgreSQL campaign 10/10

### Qualification

Vid full PASS:

```text
CUSTOMER_CARD_SHADOW_DOMAIN_QUALIFIED
```

Testbot F förblir `in_progress`.

---

## 14. F2b — Intake integration med mockad transport

### Dataflöde

```text
synthetic Gmail-like event
→ befintlig normalization
→ befintlig extraction/classification
→ shadow write boundary
→ observation
→ identity/fact proposals
→ match assessment
→ structured oracle
```

### Krav

- verklig intake/workflowkod används,
- extern Gmail-adapter används inte,
- alla externa adapters blockeras,
- inga Gmail replies,
- inga approvals,
- inga execution intents för externa writes,
- tenant allowlist krävs,
- shadow flags aktiveras endast i evalprocessen,
- replay går genom verklig intake-idempotency,
- campaign cleanup återställer all shadowdata.

### Qualification

Vid full PASS:

```text
CUSTOMER_CARD_SHADOW_PIPELINE_QUALIFIED
```

Testbot F förblir `in_progress` tills closure-beslutet genomförs.

---

## 15. F2c — Live Gmail observe-canary

F2c implementeras inte i detta uppdrag.

Efter F2a/F2b ska ett separat operatorbeslut avgöra om live Gmail behövs.

Föreslaget maximalt scope:

- 2 syntetiska messages
- 0 replies
- 0 verified facts
- 0 automatic links
- 0 merges
- 0 non-customer external writes
- tenant `TENANT_LIVE_EVAL`
- exact source message/thread provenance
- full cleanup eller explicit persistent eval-state

---

## 16. Closure-rekommendation

Rekommenderat closurealternativ:

**F2a + F2b PASS räcker för `CUSTOMER_CARD_PASS`.**

Motivering:

- Gmailtransporten är redan verifierad i testbot C–E,
- F2b använder verklig intake/workflowkod,
- unik F2-evidens är write boundary, provenance, matching och replay,
- extern Gmail tillför främst transportbevis som redan finns,
- livekundkortskedjan ska inte kräva extern mutation för att verifieras.

F2c ska därför vara valfri transportcanary, inte closurekrav.

`testbot-f-customer-card-stateful` får markeras `completed` endast om:

- F1 är qualified,
- F1b är qualified,
- F2a är qualified,
- F2b är qualified,
- TBF2-01 till TBF2-10 PASS,
- shadow flags default `false`,
- verified facts created automatiskt = 0,
- unauthorized links = 0,
- automatic merges = 0,
- automatic duplicate decisions = 0,
- cross-tenant findings = 0,
- external side effects = 0,
- replay/idempotency PASS,
- cleanup PASS,
- redaction clean.

Registrera då:

```text
CUSTOMER_CARD_PASS
```

Qualified scope:

- direct-domain stateful customer card
- isolated HTTP contracts
- shadow observations
- mock-intake to shadow pipeline
- tenant-isolated match proposals
- explicit operatorpromotion to proposed facts
- replay and provenance

Not qualified:

- production activation
- broad tenant scope
- automatic verification
- automatic customer linking
- automatic merge
- live customer data
- customer-card UI
- Sheets, Monday och Visma

---

## 17. Säkerhets- och abusekrav

Tester ska täcka:

- cross-tenant identity collision
- spoofad sender
- shared mailbox
- forwarded email
- alias och plus-addressing
- group address
- Reply-To skiljer sig från sender
- prompt injection
- malicious attachment metadata
- mycket långt message
- Unicode-normalisering
- telefonnummer i fritext
- ogiltigt organisationsnummer
- model hallucination
- extraction-version drift

Trustnivåer:

- `trusted`: operatorverifierad intern konfiguration
- `observed`: transportmetadata
- `untrusted`: mail body, attachment metadata, forwarded headers
- `proposed`: AI-extraherad och normaliserad data
- `verified`: explicit operatorverifierad kunddata

---

## 18. Observability

Metrics:

- shadow observations created
- observations awaiting review
- extraction failures
- low-confidence observations
- match proposals created
- ambiguous matches
- conflicts
- rejected observations
- replay suppressions
- promotion attempts
- promotions completed
- cross-tenant blocks
- cleanup failures
- pipeline latency
- feature flag state

Loggar och rapporter får inte innehålla:

- hela mejl
- OAuth-token
- fullständiga adresser
- fullständiga telefonnummer
- onödiga personuppgifter

Använd hashes, redigerade värden och interna IDs.

---

## 19. Leveransordning

Branch:

```text
feat/testbot-f2-shadow-pipeline
```

Genomför:

1. skapa och lås denna planfil,
2. implementera F2a migration och domain model,
3. implementera shadow services och repositories,
4. implementera match proposal och idempotency,
5. implementera TBF2-01 till TBF2-10,
6. implementera structured oracles,
7. implementera cleanup,
8. kör hermetiska tester,
9. kör isolerad PostgreSQL F2a campaign,
10. implementera F2b mock-intake integration,
11. kör F2b stateful campaign,
12. kör F1/F1b regressioner,
13. kör migration chain,
14. kör full Release Gate,
15. öppna avgränsad PR,
16. squash-merga,
17. verifiera post-merge Release Gate,
18. registrera qualifications vid PASS,
19. uppdatera testbot F-status enligt closurekontraktet,
20. stoppa före F2c.

---

## 20. Obligatoriska tester

Minst:

1. Shadow flags default `false`.
2. Shadow intake är tenant-allowlistad.
3. TBF2-manifest innehåller exakt 10 scenarier.
4. Scenario IDs är unika.
5. New sender skapar en observation.
6. New sender skapar inga verified facts.
7. Exact email skapar match proposal men ingen link.
8. Changed phone ändrar inte current state.
9. Conflict ger manual review.
10. Company contacts hålls separata.
11. Shared domain ger ingen automatisk link.
12. Ambiguous match skapar ingen link.
13. Thread-ID används inte som identity proof.
14. Duplicate intake ger exact-once.
15. Ny extraction-version bevarar gammal provenance.
16. Low-confidence observation promoveras inte.
17. Prompt injection ändrar ingen policy eller flag.
18. Operatorpromotion skapar endast `PROPOSED` fact.
19. Promotion replay är idempotent.
20. Automatic verification är omöjlig.
21. Automatic merge är omöjlig.
22. Automatic duplicate decision är omöjlig.
23. Cross-tenant match blockeras.
24. Cross-tenant promotion blockeras.
25. Spoofed sender behandlas som untrusted.
26. Reply-To mismatch behandlas som risk.
27. Forwarded email auto-länkas inte.
28. Plus-addressing normaliseras enligt dokumenterat kontrakt.
29. External side effects = 0.
30. Cleanup tar endast campaign-skapad data.
31. Cleanup lämnar inga campaign rows.
32. Semantic hash är stabil.
33. F1/F1b regressioner PASS.
34. PostgreSQL migration chain PASS.
35. Full Release Gate PASS.
36. Redaction clean.

---

## 21. Failure

Vid failure:

- ingen F2c,
- ingen live Gmail,
- ingen automatisk fix utanför planens scope,
- testbot F förblir `in_progress`,
- berörd qualification registreras inte,
- rapportera första felande scenario och oracle,
- rapportera alla DB-mutationer,
- rapportera cleanup,
- föreslå minsta avgränsade fix eller forensics.

---

## 22. Stopp

Efter F2a/F2b delivery:

- vid full PASS enligt closurekontraktet får testbot F markeras `completed`,
- registrera `CUSTOMER_CARD_PASS`,
- genomför ingen F2c automatiskt.

Stoppa med:

```text
OPERATOR ACTION REQUIRED — Besluta om valfri F2c live Gmail observe-canary eller starta testbot G
```
