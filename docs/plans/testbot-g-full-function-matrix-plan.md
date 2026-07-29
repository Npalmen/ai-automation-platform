---
name: Testbot G full-function matrix
overview: Verifiera plattformens samlade produkt- och operatörsfunktioner genom en versionsstyrd capability-matris med hermetiska, PostgreSQL-baserade och strikt avgränsade transporttester utan att likställa testkvalificering med produktionsaktivering.
todos:
  - id: testbot-g-a-current-truth
    content: Inventera samtliga exponerade produktfunktioner, actions, operatorflöden, integrationer, feature flags och befintlig kvalificering
    status: completed
  - id: testbot-g-b-capability-registry
    content: Inför en auktoritativ capability registry och en maskinläsbar full-function-matris
    status: completed
  - id: testbot-g-c-scenario-matrix
    content: Implementera en kuraterad TBG-scenariomatris som täcker produktflöden, negativa kontroller och återställning
    status: completed
  - id: testbot-g-d-oracles
    content: Implementera strukturerade oracles för beslut, writes, providerutfall, kundstate, audit och tenant isolation
    status: completed
  - id: testbot-g-e-execution
    content: Kör hermetiska och PostgreSQL-baserade full-function-kampanjer samt endast redan kvalificerade live-canaries
    status: in_progress
  - id: testbot-g-f-delivery
    content: Kör regressioner, PR, squash-merge och post-merge Release Gate
    status: pending
  - id: testbot-g-g-closure
    content: Registrera FULL_FUNCTION_MATRIX_PASS vid full evidens och stoppa före continuous regression
    status: pending
isProject: true
---

# Testbot G — Full-function matrix

## 1. Operatörsbeslut

F2c live Gmail observe-canary ska **inte** genomföras nu.

Testbot F är redan stängd genom:

- `CUSTOMER_CARD_STATEFUL_DIRECT_QUALIFIED`
- `CUSTOMER_CARD_HTTP_CONTRACT_QUALIFIED`
- `CUSTOMER_CARD_SHADOW_DOMAIN_QUALIFIED`
- `CUSTOMER_CARD_SHADOW_PIPELINE_QUALIFIED`
- `CUSTOMER_CARD_PASS`

Gmailtransporten har separat verifierats i testbot C–E. En extra F2c-körning skulle främst repetera transportbevis och ger mindre värde än att verifiera systemets samlade funktionsyta.

Nästa steg är:

`testbot-g-full-function-matrix`

Ingen produktionsaktivering följer automatiskt av Testbot G.

## 2. Baseline

| Kapitel | Status |
|---|---|
| Testbot A — current truth | completed |
| Testbot B — isolated environment | completed |
| Testbot C — observe | completed |
| Testbot D — semi-automatic | completed |
| Testbot E — automatic Gmail | completed |
| Testbot F — customer-card stateful | completed |
| Testbot G — full-function matrix | pending |
| Testbot H — continuous regression | pending |

Kvalificerat:

- observe-kampanjer
- approval/reject-flöden
- exact-once Gmail-dispatch
- automatic Gmail safe acknowledgements
- pre-write reply safety
- provider- och recipientverifiering
- customer-card direct-domain state
- customer-card HTTP-kontrakt
- shadow observation domain
- mock-intake till shadow pipeline
- tenant isolation, replay och cleanup inom respektive kapitel

Inte produktionskvalificerat:

- bred tenantaktivering
- verkliga kunddata
- automatic verification
- automatic customer linking
- automatic merge
- full automatic multi-integration
- live Sheets/Monday/Visma-writes
- prissättning, bokning, avtal eller tekniska garantier
- kundkortets fulla UI-produktionsflöde

## 3. Syfte

Testbot G ska svara på:

> Är varje verkligt exponerad funktion i plattformen antingen verifierad, uttryckligen blockerad, dokumenterat ej implementerad eller tydligt utanför scope?

Skapa en riskbaserad och spårbar capability-matris där varje capability har:

- ägare och kodyta
- feature flag eller policy gate
- tillåtet exekveringsläge
- tenant scope
- förväntad state transition
- extern write-budget
- testnivå
- evidens
- kvalificeringsstatus
- känt gap

Ingen capability får markeras PASS enbart för att en närliggande funktion har testats.

## 4. Statusmodell

| Status | Betydelse |
|---|---|
| `PASS` | Kontraktet är verifierat på angiven testnivå |
| `PASS_LIVE` | Kontraktet är verifierat mot uttryckligen tillåten extern transport |
| `BLOCKED_BY_POLICY` | Funktionen finns men ska faila stängt under aktuell konfiguration |
| `DISABLED_BY_FLAG` | Funktionen finns men feature flag är av |
| `SANDBOX_ONLY` | Verifierad endast i mock/sandbox |
| `NOT_IMPLEMENTED` | Funktionsytan finns inte eller är endast stub |
| `NOT_APPLICABLE` | Kombinationen är inte giltig |
| `UNQUALIFIED` | Funktionen finns men tillräcklig evidens saknas |
| `FAIL` | Observerat beteende avviker från kontraktet |

`PASS`, `PASS_LIVE` och `SANDBOX_ONLY` ska länka till konkret evidens.

## 5. Current-truth-inventering

Cursor ska läsa aktuell `main` och inventera minst följande.

### 5.1 Intake och normalisering

- Gmail intake
- message/thread correlation
- sender/recipient normalization
- duplicate intake
- no-reply detection
- malformed messages
- attachment metadata
- source provenance
- tenant binding

### 5.2 Klassificering och extraction

- lead
- customer inquiry/support
- invoice
- unknown
- mixed/ambiguous
- contact/company extraction
- invoice fields
- service-profile routing
- low-confidence handling
- prompt injection/malicious content

### 5.3 Decisioning och policy

- `auto_execute`
- `send_for_approval`
- `hold_for_review`
- `manual_review`
- action authorization
- restricted intent
- pre-write reply safety
- budget gates
- tenant automation rules
- feature flags

### 5.4 Actions

Inventera den verkliga actionregistryn. Minst kända kandidater:

- `send_customer_auto_reply`
- `send_internal_handoff`
- `create_monday_item`
- Google Sheets export/action
- Visma-relaterade actions
- invoice/manual accounting routing
- human handoff
- no-op/blocked actions

Använd endast actions som faktiskt finns på aktuell `main`.

### 5.5 Approval och operatorflöden

- pending approval
- approve
- reject
- stale/CAS conflict
- duplicate approve
- retry/replay
- reclassify
- re-extract
- resend/re-dispatch där det finns
- manual review
- needs-help/incidentkoppling där relevant
- pause/resume automation
- scheduler pause/resume

### 5.6 Customer-card

- direct-domain current state
- HTTP contracts
- shadow observations
- match proposals
- operatorpromotion till proposed facts
- replay
- duplicate candidates
- conflict
- tenant isolation
- cleanup

### 5.7 Integrationer

- Gmail
- Monday
- Google Sheets
- Visma
- internal stub
- sandbox/mock
- disabled configuration
- missing credentials
- provider timeout
- provider accepted
- recipient verification där tillämpligt

### 5.8 Drift och observability

- audit events
- integration events
- execution intents/outcomes
- provider metadata
- operation IDs
- idempotency
- scheduler state
- runtime SHA
- release gate
- redaction

## 6. Capability registry

Skapa exempelvis:

`app/evaluation/full_function/capabilities.yaml`

Varje capability ska minst innehålla:

```yaml
id: gmail.customer_reply.auto
domain: action
entrypoint: send_customer_auto_reply
supported_modes:
  - hermetic
  - postgres
  - live_gmail
required_flags: []
required_integrations:
  - google_mail
external_write_type: gmail_reply
max_external_writes_per_scenario: 1
tenant_scoped: true
expected_default_status: DISABLED_BY_FLAG
qualified_by:
  - AUTOMATIC_GMAIL_CORE_QUALIFIED
```

Fält:

- `id`
- `domain`
- `description`
- `entrypoint`
- `code_owner_path`
- `supported_modes`
- `required_flags`
- `required_integrations`
- `required_roles`
- `tenant_scoped`
- `external_write_type`
- `max_external_writes_per_scenario`
- `expected_default_status`
- `safety_class`
- `qualified_by`
- `known_limitations`

Validera registry mot faktisk kod där det är rimligt.

## 7. Full-function matrix

Skapa:

`app/evaluation/full_function/resources/full_function_matrix.yaml`

Matrisens primära funktionsfamiljer:

1. intake
2. classification
3. extraction
4. decisioning
5. policy authorization
6. approval lifecycle
7. manual review/hold
8. action dispatch
9. provider outcome
10. operator recovery
11. customer-card
12. tenant isolation
13. feature flags
14. observability/audit
15. integration state

Exekveringslägen:

- hermetic
- PostgreSQL
- mock transport
- sandbox
- live Gmail endast där redan kvalificerat
- disabled/fail-closed

Konfigurationer:

- integration enabled
- integration disabled
- credentials missing
- automation paused
- approval required
- safe auto-action
- restricted action
- duplicate/replay
- provider timeout
- cross-tenant attempt

Använd pairwise/riskbaserad täckning, inte full kartesisk produkt.

## 8. TBG-scenariomatris

Implementera följande kärnkontrakt. Cursor får lägga till scenarier när current-truth visar luckor.

### TBG01 — Safe lead observe

Lead classification, extraction, observe/no external write och korrekt provenance.

### TBG02 — Support/manual review

Support eller complaint ska ge hold/manual review och inga external-write intents.

### TBG03 — Invoice/manual accounting

Invoice classification och manual routing utan obehörig Gmail-, Monday-, Sheets- eller Visma-write.

### TBG04 — Unknown/ambiguous

Unknown ska faila stängt till manual review utan actions.

### TBG05 — Safe automatic Gmail acknowledgement

Low-risk, pre-write safety PASS, `auto_execute`, exakt en reply samt provider- och recipientverifiering. Tidigare kvalificerad live-evidens får återanvändas om kontraktet är kompatibelt.

### TBG06 — Restricted reply blocked

Pris, bokning, bindande besked eller garanti ska blockeras före adapter. 0 replies.

### TBG07 — Approval approve

Approval, operator approve, exakt en avsedd write, audit och idempotent replay. Extern write mockas om transporten inte redan är kvalificerad och separat auktoriserad.

### TBG08 — Approval reject

Reject ska ge 0 external writes och terminal audit.

### TBG09 — Duplicate/stale approval

Duplicate approve exact-once och stale/CAS blockeras.

### TBG10 — Provider timeout/outcome unknown

Timeout ska ge `outcome_unknown`, ingen automatisk resend och operator/recovery-behov.

### TBG11 — Internal handoff

Giltig intern recipient/config, korrekt preview och tydlig separation från customer reply.

### TBG12 — Monday disabled

0 Monday writes och strukturerad blockeringsorsak. Mock/sandbox får klassas `SANDBOX_ONLY` om implementerat.

### TBG13 — Google Sheets contract

Disabled fail-closed, preview/row mapping, tenant isolation och idempotency. Ingen live Sheets-write.

### TBG14 — Visma contract

Credentials missing fail-closed, sandbox/mock path och invoice routing enligt befintligt kontrakt. Ingen live ekonomisk write.

### TBG15 — Automation paused

Paus före intake ska stoppa auto-actions och ge audit.

### TBG16 — Scheduler paused

Inga bakgrundsjobb; manuell trigger fungerar enligt kontrakt utan oväntade writes.

### TBG17 — Recovery actions

Täck faktiska retry/replay/reclassify/re-extract-routes. Kräv tenant scope, audit, idempotency och ingen oavsiktlig resend.

### TBG18 — Cross-tenant block

Blockera cross-tenant access till jobb, approvals, customer card, integration config, recovery och audit.

### TBG19 — Customer-card returning customer

Återanvänd samma kundstate utan duplicate customer, med korrekt timeline/job/thread provenance.

### TBG20 — Shadow observation pipeline

Mock intake till shadow observation och match proposal, 0 verified facts och 0 automatic links/merges.

### TBG21 — Prompt injection/malformed message

Innehåll behandlas som data; inga policy-/flagändringar och inga unauthorized actions.

### TBG22 — No-reply/spam/phishing

Inget kundsvar till no-reply och inga obehöriga integration writes.

### TBG23 — Concurrent duplicate intake

Samma source event parallellt ska ge exact-once job/observation/action.

### TBG24 — Audit and telemetry completeness

Verifiera intake, decision, authorization, intent/outcome, provider metadata, operator action, customer shadow event och cleanup med tenant scope och redaction.

### TBG25 — Default flags fail-closed

Customer-, shadow-, automatic- och integrationsflags ska vara av eller fail-closed enligt current-truth.

## 9. Oracles

Varje scenario ska producera strukturerad JSON med minst:

- `scenario_id`
- `capability_ids`
- `execution_mode`
- `tenant_id_hash`
- `runtime_sha`
- `input_count`
- `job_count`
- `classification`
- `extracted_entities_hash`
- `decision`
- `authorization`
- `approval_count`
- `operator_action_count`
- `manual_review_count`
- `execution_intent_count`
- `execution_outcome_count`
- `adapter_invocations`
- `provider_accepted`
- `recipient_verified`
- `external_writes_by_type`
- `unauthorized_writes`
- `idempotency_result`
- `customer_state_mutations`
- `shadow_observations`
- `verified_facts_created`
- `automatic_links`
- `automatic_merges`
- `audit_event_types`
- `cross_tenant_findings`
- `redaction_status`
- `cleanup_status`
- `semantic_hash`
- `status`

Matrix PASS kräver explicit status och evidens för varje capability-cell.

## 10. Externa write-budgetar

Testbot G får inte skapa nya live writes enbart för att fylla matrisen.

Tillåtet:

- återanvänd tidigare kvalificerad live Gmail-evidens
- mockad Gmail/Sheets/Monday/Visma
- befintlig officiell sandbox
- read-only providerkontroller
- lokal/PG action dispatch

Inte tillåtet utan nytt operatörsbeslut:

- ny live Gmail-kampanj
- live Sheets-write
- live Monday-write
- live Visma-write
- ekonomisk transaktion
- verklig kundrecipient
- fler tenants

Använd `SANDBOX_ONLY`, `BLOCKED_BY_POLICY`, `DISABLED_BY_FLAG` eller `UNQUALIFIED` i stället för att fejka `PASS_LIVE`.

## 11. Testlager

### G1 — Registry och hermetiska kontrakt

- capability registry
- matrix schema
- action/flag/integration consistency
- scenario manifests
- deterministic oracles
- safety assertions
- no-network guards

### G2 — PostgreSQL full-function campaign

- verkliga repositories och migrations
- job/approval/action lifecycle
- customer-card/shadow state
- tenant isolation
- idempotency
- cleanup
- mock/sandbox adapters

### G3 — Evidence binding

Bind tidigare kvalificerade live-runs till rätt matrix-celler. Om evidens inte är kompatibel markeras cellen `UNQUALIFIED`; ingen ny livekörning startas.

## 12. Readiness

Före full-function campaign:

- aktuell main SHA verifierad
- post-merge Release Gate PASS
- capability registry validerad
- matrix validerad
- inga duplicate capability IDs
- alla references finns
- feature flag defaults verifierade
- no-network guard aktiv
- externa write-budgetar = 0 för ny campaign
- eval DB verifierad
- tenantprefix godkänt
- syntetisk data PASS
- cleanup targets explicita
- redaction clean

## 13. Cleanup

- explicit campaign run ID
- explicita tenant IDs
- explicit row inventory
- inga globala deletes
- inga deletes av verkliga tenants
- inga provider-side cleanup-writes
- post-cleanup counts = 0 för campaign rows
- pre/post normalized hash match
- cleanup failure gör campaign FAIL

## 14. Failure-hantering

Klassificera fel som scenario-, fixture-, assertion-, registry- eller produktfel. Bekräfta med minsta reproduktion. Ändra inte expected-resultat för att matcha felaktigt beteende. Gör endast minsta korrekta fix och lägg regressionstest. Bred refaktorering eller extern write kräver nytt beslut.

## 15. Obligatoriska tester

Minst:

1. Capability IDs är unika.
2. Alla registry-entrypoints finns.
3. Alla flagreferenser finns.
4. Alla integration references finns.
5. Matrix refererar endast registrerade capabilities.
6. Varje capability har explicit status.
7. `PASS` kräver evidens.
8. `PASS_LIVE` kräver verifierbar live-evidens.
9. Blockerade capabilities räknas inte som exekverade.
10. Okänd capability failar validering.
11. Kärnmatris TBG01–TBG25 finns.
12. Lead observe PASS.
13. Support hold PASS.
14. Invoice manual PASS.
15. Unknown hold PASS.
16. Safe reply är kompatibel med E-kvalificering.
17. Restricted reply stoppas pre-write.
18. Approval approve exact-once.
19. Approval reject ger 0 writes.
20. Duplicate/stale approval blockeras.
21. Provider timeout ger ingen resend.
22. Internal handoff hålls separat från customer reply.
23. Monday disabled ger 0 writes.
24. Sheets disabled/mock PASS.
25. Visma disabled/sandbox PASS.
26. Automation pause stoppar auto-actions.
27. Scheduler pause stoppar bakgrundskörning.
28. Recovery actions är tenant-isolerade.
29. Recovery orsakar inte oavsiktlig resend.
30. Cross-tenant access blockeras.
31. Customer-card stateful regression PASS.
32. Shadow pipeline regression PASS.
33. Prompt injection ger 0 unauthorized actions.
34. No-reply får inget kundsvar.
35. Concurrent duplicate intake exact-once.
36. Audit/telemetry är komplett och redigerad.
37. Default flags fail-closed.
38. External writes i ny G-campaign = 0.
39. Cleanup tar endast campaign rows.
40. Cleanup lämnar 0 campaign rows.
41. Determinism/semantic hash PASS.
42. Befintliga C–F regressioner PASS.
43. PostgreSQL migration chain PASS.
44. Docker PASS.
45. Full Release Gate PASS.
46. Redaction clean.

## 16. Rapportering

Skapa lokalt:

`storage/status/testbot-g-full-function-matrix-<run-id>.md`

och ett maskinläsbart JSON-artifact.

Rapportera:

- main SHA
- PR/merge/gate
- campaign run ID
- antal capabilities
- antal matrix-celler
- statusfördelning
- scenarioresultat
- evidensreferenser
- external/unauthorized writes
- tenant isolation
- cleanup
- produktfel och fixar
- UNQUALIFIED och NOT_IMPLEMENTED
- qualified/not-qualified scope

Committera inte `storage/status/*` eller artifacts.

## 17. Leverans

Branch:

`feat/testbot-g-full-function-matrix`

Genomför autonomt:

1. skapa och lås planfilen
2. inventera current-truth
3. implementera capability registry
4. implementera matrix schema
5. implementera TBG-scenarier
6. implementera oracles och report
7. implementera readiness och cleanup
8. kör riktade hermetiska tester
9. kör PostgreSQL full-function campaign
10. bind kompatibel tidigare live-evidens
11. kör C–F regressioner
12. kör migration chain
13. kör Docker
14. kör full Release Gate
15. öppna avgränsad PR
16. squash-merga
17. verifiera post-merge Release Gate
18. kör exakt en formell no-new-live-writes G-campaign på post-merge SHA
19. registrera closure vid PASS
20. stoppa före Testbot H

PR-beskrivningen ska ange:

- F2c är deferred
- Testbot F är completed
- capability registry och matrix
- statusfördelning
- nya G-campaignens externa writes = 0
- hur äldre live-evidens binds
- tenant isolation och cleanup
- att produktionsaktivering inte följer av closure

## 18. Closure

`testbot-g-full-function-matrix` får markeras `completed` endast om:

- capability registry är komplett mot aktuell exponerad funktionsyta
- varje capability har explicit matrix-status
- alla obligatoriska TBG-scenarier PASS
- inga matrix-celler står i `FAIL`
- `UNQUALIFIED` och `NOT_IMPLEMENTED` är dokumenterade och blockerar inte definierad G-scope
- unauthorized writes = 0
- nya live external writes = 0
- cross-tenant findings = 0
- idempotency PASS
- cleanup PASS
- redaction clean
- post-merge Release Gate PASS
- formell G-campaign PASS

Registrera:

`FULL_FUNCTION_MATRIX_PASS`

Closure betyder inte att alla integrationer är live, alla tenants får automation eller att Sheets/Monday/Visma är godkända för verkliga writes.

## 19. Stopp

Efter PASS:

```text
OPERATOR ACTION REQUIRED — Starta testbot H continuous regression
```

Vid failure:

- ingen automatisk ny livekörning
- ingen bred fix
- testbot G förblir `in_progress`
- rapportera första felande capability/scenario
- rapportera samtliga möjliga writes
- rapportera cleanup
- föreslå minsta avgränsade fix eller forensics
