---
name: Kundkort och kunddomän
overview: Definiera och senare implementera ett tenantisolerat kundkort med identitet, historik, provenance och säker deduplicering
todos:
  - id: customer-domain-a-current-truth
    content: Audita befintliga kund-, kontakt-, jobb-, Gmail- och tenantmodeller
    status: completed
  - id: customer-domain-b-domain-model
    content: Definiera customer, company, contact, address, identity och relationer
    status: completed
  - id: customer-domain-c-identity-matching
    content: Definiera matchning, deduplicering, confidence och manual-review-regler
    status: completed
  - id: customer-domain-d-timeline-provenance
    content: Definiera kundtidslinje, historik, källor och konfliktregler
    status: completed
  - id: customer-domain-e-api-contract
    content: Definiera read/write-API, behörigheter, tenantisolering och UI-kontrakt
    status: completed
  - id: customer-domain-f-migration-test-plan
    content: Ta fram migrationsordning, backfillstrategi, fixtures och testmatris
    status: completed
  - id: customer-domain-g-implementation-gate
    content: Granska helheten och stoppa för uttryckligt godkännande före implementation
    status: completed
  - id: customer-domain-h-implementation
    content: Implementera kunddomänen efter separat operatörsgodkännande
    status: in_progress
  - id: customer-domain-i-stateful-evaluation
    content: Testa återkommande syntetiska kunder, tidslinje och deduplicering
    status: pending
  - id: customer-domain-j-closure
    content: Slutverifiera kundkortet och dokumentera produktgränser
    status: pending
isProject: true
---

# Kundkort och kunddomän

**Planstatus:** Auktoritativ exekveringsplan  
**Planversion:** `customer-card-domain-plan-v1`  
**Designbranch:** `design/customer-card-domain`  
**Normalläge:** Tenantisolerat, append-only där det är relevant, fail-closed och utan runtimeintegration  
**Implementationsstatus:** Blockerad till och med todo G  
**Startbaseline:** Ska registreras i den lokala exekveringsrapporten vid första körningen och får inte skrivas in genom senare tekniska ändringar i denna plan.

---

## 1. Uppdrag och produktgräns

Detta utvecklingsspår ska skapa en liten, stabil och framtidssäker kunddomän som gör det möjligt att förstå:

- vem en slutkund är,
- om slutkunden är en privatperson eller ett företag,
- vilka kontaktpersoner som hör till företaget,
- vilka kommunikationsidentiteter som har observerats,
- vilka uppgifter som är kända, föreslagna, verifierade, konfliktande eller historiska,
- vilka jobb, Gmail-trådar, approvals och actions som hör till kundrelationen,
- om två observationer sannolikt avser samma slutkund,
- när en osäker matchning måste granskas manuellt.

Spåret ska inte bygga ett generellt CRM-system. Det ska etablera den minsta domängrund som krävs för kundkort, kundhistorik, säkra matchförslag och senare integration med kundens arbetsyta.

Kunddomänen ska vara ett separat sammanhangslager. Den får inte fatta beslut om approvals, action authorization, action dispatch eller extern kommunikation.

---

## 2. Låst terminologi

Följande terminologi ska användas konsekvent i dokumentation, schemas, tester och framtida API-kontrakt.

### Tenant

Ett företag som använder plattformen.

En tenant äger och isolerar all kunddata. En tenant är inte samma sak som en post i den nya `Customer`-domänen.

### Tenant account

Tenantens eget konto, konfiguration och användarorganisation.

Befintliga operatorvyer som benämner tenants som “customers” ska dokumenteras som tenantkonto eller plattformskund när risk för sammanblandning finns.

### End customer

Tenantens kund.

Det är denna part som den nya kunddomänen representerar.

### Customer

Den tenantisolerade kundrelationen och domänens aggregate root.

`Customer` representerar relationen mellan tenantföretaget och en privatkund eller företagskund. Den ska inte användas som synonym för tenant.

### Company

En juridisk eller organisatorisk part som kan vara kund, arbetsgivare, förening eller annan organisation.

### Contact

En fysisk person som kan vara privatkund eller kontaktperson för ett företag.

### Customer card

En härledd och läsoptimerad presentation av kundrelationen.

Kundkortet är inte den auktoritativa källan för alla fakta och ska inte i första hand utformas som en separat skrivbar tabell.

### Customer identity

En kommunikations- eller verksamhetsidentitet, exempelvis e-postadress, telefonnummer, organisationsnummer, kundnummer eller externt integrations-ID.

### Source fact

En observerad eller inmatad uppgift tillsammans med provenance, confidence, status och eventuell koppling till den uppgift den ersätter eller motsäger.

### Duplicate candidate

Ett granskningsärende som anger att två kundposter eller observationer kan avse samma kund.

### Match

En bedömning att två observationer eller poster sannolikt avser samma kund.

### Merge

En explicit och auditerad sammanslagning av två redan existerande kundposter.

Match och merge är separata operationer. En stark match får inte automatiskt innebära merge.

---

## 3. Auktoritetsordning och obligatorisk läsning

Varje Cursor-körning ska innan ändringar läsa:

1. `docs/00-master-plan.md`
2. `docs/01-current-truth.md`
3. `docs/04-execution-rules.md`
4. `docs/05-architecture.md`
5. `docs/07-decisions.md`
6. `docs/09-testing-and-release.md`
7. `docs/plans/customer-card-domain-plan.md`
8. de filer som direkt berör det aktuella todot.

Repositoryt är källan till sanning. Chatthistorik får inte användas som bevis för befintlig implementation.

Vid konflikt gäller följande:

1. stoppa det aktuella todot,
2. dokumentera konflikten,
3. identifiera minsta säkra lösning,
4. ändra inte planens tekniska innehåll,
5. invänta operatörsbeslut.

---

## 4. Låsning av planen

Efter operatörsgodkännande är följande read-only:

- tekniskt scope,
- filscope,
- domänprinciper,
- matchningsprinciper,
- kvalitetsgates,
- stop-villkor,
- definition of done,
- ordningen mellan todos.

Endast `status` i YAML-frontmatter får ändras:

```text
pending → in_progress → completed
```

Ingen todo får markeras `completed` utan repositoryevidens och genomförda tester eller uttryckligen dokumenterade read-only-kontroller.

En efterföljande todo får inte sättas till `in_progress` innan föregående todos som den är beroende av är `completed`.

---

## 5. Faslås och implementationsgate

### Tillåtet före nytt operatörsgodkännande

Endast följande todos får genomföras:

- `customer-domain-a-current-truth`
- `customer-domain-b-domain-model`
- `customer-domain-c-identity-matching`
- `customer-domain-d-timeline-provenance`
- `customer-domain-e-api-contract`
- `customer-domain-f-migration-test-plan`
- `customer-domain-g-implementation-gate`

### Blockerat före nytt operatörsgodkännande

Följande todos ska förbli `pending`:

- `customer-domain-h-implementation`
- `customer-domain-i-stateful-evaluation`
- `customer-domain-j-closure`

Todo G ska alltid avslutas med ett uttryckligt stopp.

Följande får inte ske som en implicit fortsättning efter todo G:

- skapande av ORM-modeller,
- skapande eller körning av migration,
- koppling till `Base.metadata`,
- skapande av repositoryklass,
- montering av FastAPI-router,
- koppling till intake eller Gmail,
- backfill av befintliga jobb,
- skrivning till produktionstabeller,
- frontendimplementation,
- PR-merge som innehåller runtimeimplementation.

---

## 6. Domänprinciper

### 6.1 Tenantisolering

Alla domänobjekt, matchningsunderlag, source facts, länkar, duplicate candidates och merge decisions ska innehålla `tenant_id`.

Ingen operation får:

- söka matchningar över flera tenants,
- generera matchbevis över flera tenants,
- dela normaliserade identitetsindex mellan tenants,
- länka poster från olika tenants,
- använda en global e-postadress eller ett telefonnummer som global kundnyckel.

Samma e-postadress i två tenants ska behandlas som två helt separata identiteter.

En cross-tenant-jämförelse ska ge ett explicit blockerat resultat, inte låg confidence.

### 6.2 Fail-closed

När information är ofullständig, motsägelsefull eller tvetydig ska systemet:

- bevara befintlig verifierad information,
- skapa ett förslag eller en konflikt,
- skapa duplicate candidate eller manual review när det är relevant,
- inte genomföra merge,
- inte skriva över verifierade värden,
- inte skapa säkra samband genom gissning.

### 6.3 Företag och personer är olika entiteter

`Company` och `Contact` ska ha separata identiteter och kontrakt.

Systemet får inte:

- tolka en företagsadress som en fysisk persons unika identitet,
- behandla ett företagsnamn som kontaktperson,
- behandla en rollbaserad e-postadress som unik personidentitet,
- slå samman företag och kontaktperson till samma record.

### 6.4 Kundkortet är en projektion

`CustomerCard` ska vara ett läskontrakt som sammanställer:

- kundrelation,
- primärt företag eller primär kontakt,
- aktuella verifierade kontaktuppgifter,
- öppna konflikter,
- länkade jobb och trådar,
- senaste aktivitet,
- duplicate status,
- datakvalitet.

Kundkortet ska inte bli den enda auktoritativa lagringsplatsen för kundfakta.

### 6.5 Append-only för historik och fakta

Source facts, timeline events och merge decisions ska utformas som append-only eller logiskt immutabla records.

Korrigering ska normalt ske genom:

- ny fact,
- ny status,
- `supersedes_fact_id`,
- konfliktmarkering,
- explicit beslut.

Historisk information ska inte raderas för att den inte längre är aktuell.

### 6.6 Referera i stället för att kopiera

Kundtidslinjen och länkmodellerna ska referera till befintliga records när det är möjligt:

- `job_id`,
- `gmail_thread_id`,
- `gmail_message_id`,
- `approval_id`,
- `action_execution_id`,
- `integration_event_id`,
- `invoice_reference`,
- framtida support- eller projektreferenser.

Fullständiga jobb-, mejl- eller actionpayloads ska inte dupliceras i kunddomänen.

### 6.7 Ingen automatisk merge i första implementationen

Följande ska vara låst till `false` under todos A–G och den första framtida implementationen om inget separat godkännande ges:

```text
automatic_merge_allowed = false
```

Även mycket stark matchning ska resultera i:

- länkförslag,
- matchförslag,
- duplicate candidate,
- manual review,

inte automatisk sammanslagning.

---

## 7. Verifierade repositoryankare som ska auditeras

Följande områden ska behandlas som read-only under audit:

### Styrande dokument

- `docs/00-master-plan.md`
- `docs/01-current-truth.md`
- `docs/04-execution-rules.md`
- `docs/05-architecture.md`
- `docs/07-decisions.md`
- `docs/09-testing-and-release.md`
- befintliga filer under `docs/plans/`

### Domän och schemas

- `app/domain/**`
- `app/lead/models.py`
- `app/support/models.py`
- relevanta schemas under `app/ai/**`
- relevanta schemas under `app/core/**`

### Persistence

- `app/repositories/postgres/job_models.py`
- `app/repositories/postgres/job_repository.py`
- `app/repositories/postgres/approval_models.py`
- `app/repositories/postgres/action_execution_models.py`
- `app/repositories/postgres/audit_models.py`
- `app/repositories/postgres/integration_repository.py`
- `app/repositories/postgres/tenant_config_models.py`
- `app/repositories/postgres/oauth_credential_models.py`
- `app/repositories/postgres/schema_migrations.py`
- `app/repositories/postgres/database.py`

### API och auth

- `app/api/**`
- `app/main.py`
- relevanta filer under `app/admin/**`
- `app/core/auth.py`
- `app/core/admin_auth.py`
- `app/core/admin_session.py`
- `app/core/tenancy.py`

### Gmail och intake, endast read-only

- Gmail-adapters och Google Mail-integrationer,
- Gmail scanners,
- inbox sync,
- Gmail deduplicering,
- intakeprocessor,
- entity extraction,
- job creation och job persistence.

### Kund- och operatorgränssnitt, endast read-only

- `frontend/src/features/customers/**`
- `frontend/src/features/customerSettings/**`
- `frontend/src/api/**`
- `app/ui/**`
- tester för befintliga customer/tenant surfaces.

Auditens syfte är att hitta återanvändbara ID:n, kontrakt och tenantgränser. Den får inte resultera i ändringar av dessa filer.

---

## 8. Exakt tillåtet filscope före implementation

### 8.1 Plan och dokumentation

Följande filer får skapas:

- `docs/plans/customer-card-domain-plan.md`
- `docs/customer-card-domain/current-truth.md`
- `docs/customer-card-domain/domain-model.md`
- `docs/customer-card-domain/identity-matching.md`
- `docs/customer-card-domain/timeline-provenance.md`
- `docs/customer-card-domain/api-contract.md`
- `docs/customer-card-domain/migration-test-plan.md`
- `docs/customer-card-domain/implementation-gate.md`

Efter att planfilen skapats får endast todo-status ändras i den.

### 8.2 Isolerade domänkontrakt

Följande nya filer får skapas:

- `app/domain/customer/__init__.py`
- `app/domain/customer/enums.py`
- `app/domain/customer/schemas.py`
- `app/domain/customer/normalization.py`
- `app/domain/customer/matching.py`

Dessa filer får inte importeras av runtimekod före todo H.

De får inte:

- importera SQLAlchemy,
- importera repositories,
- importera `app.main`,
- importera workflows,
- importera Gmail-adapters,
- utföra I/O,
- använda databas,
- anropa nätverk,
- läsa environmentvariabler,
- skapa externa sidoeffekter.

Endast standardbiblioteket och redan installerad Pydantic får användas.

### 8.3 Isolerade tester och fixtures

Följande nya filer får skapas:

- `tests/test_customer_domain_schemas.py`
- `tests/test_customer_identity_matching.py`
- `tests/fixtures/customer_domain/*.json`

Fixturefiler får inte skapas förrän de behövs av todo F eller av ett uttryckligt kontraktstest.

Tester får inte:

- importera `app.main`,
- starta FastAPI,
- använda `lifespan_client`,
- skapa databastabeller,
- skriva till PostgreSQL,
- använda externa tjänster,
- ändra befintliga scenariofiler.

### 8.4 Lokala rapporter

Lokala rapporter ska skrivas under:

```text
storage/status/customer-card-domain-*.md
```

Rapporterna får inte committas.

---

## 9. Förbjudet filscope före implementation

Följande får inte ändras under todos A–G:

- `app/main.py`
- `app/workflows/**`
- `app/decisioning/**`
- `app/policies/**`
- `app/evaluation/live/**`
- `app/integrations/**`
- Gmail-adapters,
- Gmail scanners,
- intakeprocessor,
- entity extraction,
- approvaltabeller,
- approvalkontrakt,
- action execution-modeller,
- execution intent/outcome-kontrakt,
- decision contract,
- tenant automation-kontrakt,
- testbotens scenariofiler,
- gold dataset,
- live-eval workflows,
- `.github/workflows/**`,
- `migrations/**`,
- `scripts/create_tables.py`,
- `app/repositories/postgres/**`,
- `app/api/routes/**`,
- `app/admin/**`,
- `frontend/**`,
- `app/ui/**`,
- `requirements.txt`,
- `env.example`,
- Docker- eller deploymentfiler,
- befintliga produktionstabeller,
- `docs/00-master-plan.md`,
- `docs/01-current-truth.md`,
- `docs/07-decisions.md`.

Ett föreslaget arkitekturbeslut ska dokumenteras som förslag under `docs/customer-card-domain/`. Det får inte läggas in som accepterat beslut i `docs/07-decisions.md` före implementation-gaten och operatörsgodkännandet.

---

## 10. Föreslagen konceptuell domänmodell

Modellen i detta avsnitt är det kontrakt som todo B ska verifiera mot repositoryt.

Om audit visar en befintlig slutkundsdomän som överlappar modellen ska arbetet stoppa före schemas skapas.

### 10.1 Customer

`Customer` är tenantens relation till en slutkund.

Minsta kontrakt:

- `customer_id`
- `tenant_id`
- `customer_type`
- `status`
- `display_name`
- `primary_company_id`
- `primary_contact_id`
- `version`
- `created_at`
- `updated_at`

Tillåtna `customer_type`:

- `private`
- `company`
- `association`
- `unknown`

`Customer` ska kunna finnas innan alla uppgifter är verifierade.

### 10.2 Company

Minsta kontrakt:

- `company_id`
- `tenant_id`
- `legal_name`
- `display_name`
- `organization_number_fact_id`
- `status`
- `created_at`
- `updated_at`

Organisationsnummer ska representeras genom identitet eller source fact. Ett rått organisationsnummer ska inte ensamt användas som global primary key.

### 10.3 Contact

Minsta kontrakt:

- `contact_id`
- `tenant_id`
- `given_name`
- `family_name`
- `display_name`
- `title`
- `status`
- `created_at`
- `updated_at`

En privatkund kan representeras genom ett `Customer` med en primär `Contact` och utan `Company`.

En företagskund kan representeras genom ett `Customer` med en primär `Company` och en eller flera relaterade `Contact`-poster.

### 10.4 CustomerAddress

Minsta kontrakt:

- `address_id`
- `tenant_id`
- `owner_type`
- `owner_id`
- `address_type`
- `street`
- `postal_code`
- `city`
- `region`
- `country_code`
- `fact_state`
- `source_fact_id`
- `valid_from`
- `valid_to`

Tillåtna ägare ska minst kunna vara:

- `customer`
- `company`
- `contact`

Adressmatchning ska vara strukturerad och får inte använda extern geokodning i första fasen.

### 10.5 CustomerIdentity

Minsta kontrakt:

- `identity_id`
- `tenant_id`
- `owner_type`
- `owner_id`
- `identity_type`
- `raw_value`
- `normalized_value`
- `fact_state`
- `verification_status`
- `source_fact_id`
- `first_seen_at`
- `last_seen_at`

Tillåtna identity types:

- `email`
- `phone`
- `organization_number`
- `customer_number`
- `external_id`
- `gmail_thread`
- `gmail_message`
- `other`

### 10.6 CustomerRelationship

Minsta kontrakt:

- `relationship_id`
- `tenant_id`
- `customer_id`
- `subject_type`
- `subject_id`
- `relationship_type`
- `is_primary`
- `valid_from`
- `valid_to`

Exempel på relationship types:

- `private_customer`
- `customer_company`
- `primary_contact`
- `billing_contact`
- `technical_contact`
- `site_contact`
- `former_contact`
- `other`

### 10.7 CustomerSourceFact

Minsta kontrakt:

- `fact_id`
- `tenant_id`
- `subject_type`
- `subject_id`
- `field_name`
- `raw_value`
- `normalized_value`
- `fact_state`
- `source_type`
- `source_reference`
- `source_actor`
- `confidence`
- `observed_at`
- `recorded_at`
- `verified_at`
- `verified_by`
- `supersedes_fact_id`
- `conflicts_with_fact_ids`

Tillåtna fact states:

- `known`
- `proposed`
- `verified`
- `conflicting`
- `historical`
- `rejected`

Tillåtna source types:

- `gmail_inbound`
- `user_input`
- `integration`
- `import`
- `ai_extraction`
- `admin_correction`
- `system_derived`

### 10.8 CustomerTimelineEvent

Minsta kontrakt:

- `timeline_event_id`
- `tenant_id`
- `customer_id`
- `event_type`
- `occurred_at`
- `recorded_at`
- `actor_type`
- `actor_id`
- `source_type`
- `reference_type`
- `reference_id`
- `summary`
- `metadata`

`metadata` ska vara allowlistad och får inte innehålla kopior av hela mejl-, jobb- eller actionpayloads.

### 10.9 CustomerJobLink

Minsta kontrakt:

- `link_id`
- `tenant_id`
- `customer_id`
- `job_id`
- `link_type`
- `confidence`
- `source_type`
- `created_at`
- `created_by`

### 10.10 CustomerThreadLink

Minsta kontrakt:

- `link_id`
- `tenant_id`
- `customer_id`
- `integration_type`
- `integration_account_reference`
- `thread_id`
- `link_type`
- `confidence`
- `source_type`
- `created_at`

En trådidentifierare får endast användas inom samma tenant och samma integrationskontext.

### 10.11 CustomerDuplicateCandidate

Minsta kontrakt:

- `candidate_id`
- `tenant_id`
- `left_customer_id`
- `right_customer_id`
- `status`
- `confidence`
- `evidence`
- `conflicts`
- `created_at`
- `updated_at`
- `version`

Tillåtna statusar:

- `open`
- `approved`
- `rejected`
- `superseded`
- `resolved_without_merge`

### 10.12 CustomerMergeDecision

Minsta kontrakt:

- `decision_id`
- `tenant_id`
- `candidate_id`
- `decision`
- `survivor_customer_id`
- `merged_customer_id`
- `reason`
- `actor_type`
- `actor_id`
- `expected_version`
- `decided_at`

Todo B och F ska utvärdera om dessa koncept ska bli separata tabeller eller kombineras i en mindre persistensmodell.

Ingen tabellstruktur är godkänd förrän todo G har passerat och operatören har godkänt implementation.

---

## 11. Schema- och modellinvarianter

De isolerade schemas som skapas under todo B ska upprätthålla följande:

1. `tenant_id` är obligatoriskt på alla tenantägda records.
2. Relationer får endast länka objekt med samma `tenant_id`.
3. Confidence ska ligga inom intervallet `0.0–1.0`.
4. Tidsstämplar ska vara timezone-aware.
5. Okända extra fält ska avvisas i kontraktsmodeller där kompatibilitet inte uttryckligen kräver annat.
6. Tomma strängar ska inte behandlas som verifierade identiteter.
7. `normalized_value` får vara `null` när normalisering inte säkert kan utföras.
8. `CustomerCard` ska kunna serialiseras utan interna payloads eller hemligheter.
9. Identifierare ska behandlas som opaka strängar i kontraktsfasen.
10. Company- och Contact-ID:n får inte användas omväxlande.
11. Ett source fact får inte referera till sig själv genom `supersedes_fact_id`.
12. `automatic_merge_allowed` ska alltid vara `false`.
13. `automatic_link_allowed` ska alltid vara `false` under designfasen.
14. Matchningsresultat ska innehålla stabila reason codes, inte bara fri text.
15. Schemafiler får inte innehålla ORM- eller runtimekoppling.

---

## 12. Normalisering

Normalisering ska vara deterministisk, ren och konservativ.

### 12.1 E-post

Normalisering ska:

- trimma yttre whitespace,
- använda Unicode NFKC,
- casefolda adressen,
- kontrollera att exakt ett meningsfullt `@` finns,
- avvisa tom lokal- eller domändel,
- bevara plus-taggar,
- inte gissa alias,
- inte slå samman olika domäner,
- inte göra rollbaserade adresser till unika personidentiteter.

Exempel på rollbaserade lokaldelar som ska betraktas försiktigt:

- `info`
- `support`
- `faktura`
- `invoice`
- `order`
- `kontakt`
- `kundservice`
- `admin`

### 12.2 Telefonnummer

Normalisering ska:

- ta bort säkra presentationsseparatorer,
- bevara eller skapa internationellt prefix endast när regionen är uttrycklig,
- kunna hantera `00` som internationellt prefix,
- endast konvertera svenskt inledande `0` till `+46` när `country_code=SE`,
- avvisa för korta eller uppenbart ogiltiga nummer,
- returnera `null` när landet eller betydelsen är tvetydig,
- inte använda extern telefonbibliotekstjänst i designfasen.

### 12.3 Organisationsnummer

För svensk kontext ska normalisering:

- ta bort säkra separatorer,
- kunna hantera tio siffror,
- kunna reducera ett tolvsiffrigt svenskt format med `16`-prefix,
- validera format konservativt,
- returnera `null` om värdet inte kan normaliseras säkert,
- bevara angivet land i matchningsunderlaget.

### 12.4 Namn

Normalisering ska:

- använda Unicode NFKC,
- trimma och slå samman whitespace,
- casefolda för jämförelse,
- bevara diakritiska tecken,
- inte ta bort delar av person- eller företagsnamn aggressivt,
- aldrig ge tillräckligt bevis för automatisk merge på egen hand.

### 12.5 Adress

Adressnormalisering ska:

- använda strukturerade fält,
- trimma och normalisera whitespace,
- normalisera landkod,
- inte använda extern geokodning,
- inte anta att liknande adresstext är samma fastighet,
- kombinera adress med annan evidens innan stark matchning föreslås.

---

## 13. Matchning och deduplicering

### 13.1 Separera candidate generation, assessment och merge

Matchningsområdet ska delas i tre steg:

1. **Candidate generation**  
   Identifierar vilka poster som är relevanta att jämföra.

2. **Match assessment**  
   Beräknar evidens, konflikter, confidence och rekommenderat utfall.

3. **Merge decision**  
   Ett explicit, auditerat operatörsbeslut.

Todo C får endast implementera rena normaliserings- och assessmentfunktioner.

Ingen candidate query, databasoperation eller mergefunktion får implementeras.

### 13.2 Matchningsutfall

Tillåtna resultat:

- `blocked`
- `no_match`
- `possible_duplicate`
- `strong_candidate`
- `exact_candidate`
- `manual_review_required`

Alla resultat utom `blocked` och `no_match` ska fortfarande kräva manuell granskning före merge.

### 13.3 Grundpoäng

Följande grundpoäng ska användas i den isolerade kontraktsimplementationen:

| Evidens | Poäng |
|---|---:|
| Exakt verifierat organisationsnummer inom samma tenant och land | 0.90 |
| Exakt verifierat kundnummer inom samma källa och tenant | 0.85 |
| Exakt normaliserad e-postadress | 0.65 |
| Exakt normaliserat telefonnummer | 0.55 |
| Exakt befintlig Gmail-trådreferens inom samma integrationskontext | 0.60 |
| Exakt företagsrelation | 0.50 |
| Exakt strukturerad adress | 0.25 |
| Exakt normaliserat namn | 0.20 |

Total confidence ska begränsas till `1.0`.

### 13.4 Trösklar

| Confidence | Grundutfall |
|---|---|
| `< 0.50` | `no_match` |
| `0.50–0.74` | `possible_duplicate` |
| `0.75–0.89` | `strong_candidate` |
| `>= 0.90` | `exact_candidate` |

En konfliktregel kan alltid ersätta grundutfallet med `blocked` eller `manual_review_required`.

### 13.5 Blockerande regler

Följande ska ge `blocked`:

- olika `tenant_id`,
- försök att jämföra tenantkonto med slutkund,
- person jämförs direkt med företag som om de vore samma entitet,
- två olika verifierade organisationsnummer,
- två olika verifierade kundnummer från samma auktoritativa källa,
- saknad tenantinformation,
- ogiltigt matchningsunderlag.

### 13.6 Manuella review-regler

Följande ska ge `manual_review_required` eller begränsa confidence:

- samma telefonnummer men väsentligt olika verifierade namn,
- samma e-postadress men olika verifierade företag,
- samma adress men olika verifierade personer,
- rollbaserad e-post utan stödjande företagssignal,
- samma namn utan starkare identitet,
- förändrad telefon eller adress där gammal uppgift är verifierad,
- en stark AI-extraktion som motsäger administrativt verifierad information,
- ett företag med flera kontaktpersoner som delar domän eller växelnummer.

### 13.7 Hårda säkerhetsregler

Följande ska alltid returneras av assessmentkontraktet under todos A–G:

```text
automatic_merge_allowed = false
automatic_link_allowed = false
requires_manual_review = true
```

Undantag:

- `blocked` och `no_match` behöver inte skapa reviewärende,
- men får fortfarande aldrig tillåta merge.

### 13.8 Stabil evidens

Assessmentresultatet ska minst innehålla:

- `tenant_id`
- `decision`
- `confidence`
- `evidence`
- `conflicts`
- `reason_codes`
- `requires_manual_review`
- `automatic_link_allowed`
- `automatic_merge_allowed`

Evidens och reason codes ska sorteras deterministiskt så att samma input ger samma serialiserade resultat.

---

## 14. Provenance och konfliktregler

### 14.1 Source provenance

Varje fact ska kunna ange:

- var uppgiften kom från,
- vilket externt eller internt record som var källan,
- vem eller vad som registrerade uppgiften,
- när uppgiften observerades,
- när den registrerades,
- om den extraherades av AI,
- confidence,
- om den har verifierats,
- vilken tidigare fact den ersätter eller motsäger.

### 14.2 Prioritetsprincip

Följande är en beslutsprincip, inte automatisk overwrite-logik:

1. explicit administrativ verifiering,
2. explicit verifierad användarinmatning,
3. verifierad auktoritativ integration,
4. validerad import,
5. upprepad direkt observation,
6. enstaka direkt observation,
7. AI-extraktion,
8. systemhärledd gissning.

En lägre källa får aldrig automatiskt skriva över en verifierad högre källa.

### 14.3 Konflikthantering

När en ny fact motsäger en verifierad fact ska systemet senare:

- bevara båda,
- markera den nya som `conflicting` eller `proposed`,
- referera till den gamla genom `conflicts_with_fact_ids`,
- skapa timeline event,
- exponera konflikten på kundkortet,
- kräva manuell resolution när uppgiften är operativt relevant.

### 14.4 Historiska värden

När en verifierad uppgift ersätts genom ett godkänt beslut ska den gamla facten bli `historical`.

Historisk information ska behålla:

- giltighetsperiod,
- provenance,
- verifieringsmetadata,
- relation till ersättande fact.

---

## 15. Kundtidslinje

Tidslinjen ska minst kunna representera:

- `first_contact`
- `gmail_message_received`
- `gmail_thread_linked`
- `job_created`
- `job_classified`
- `job_status_changed`
- `approval_created`
- `approval_decided`
- `reply_prepared`
- `reply_sent`
- `external_action_requested`
- `external_action_completed`
- `external_action_failed`
- `note_added`
- `contact_fact_proposed`
- `contact_fact_verified`
- `contact_fact_changed`
- `contact_fact_conflict`
- `duplicate_candidate_created`
- `duplicate_candidate_rejected`
- `merge_approved`
- `merge_completed`
- `support_case_linked`
- `invoice_linked`
- `economic_event_linked`

Tidslinjeevent ska skilja mellan:

- `occurred_at`: när händelsen faktiskt inträffade,
- `recorded_at`: när plattformen registrerade händelsen.

Tidslinjen ska kunna visa en sammanhängande kundhistorik även när relaterade records ligger i andra domäner.

---

## 16. Framtida API-kontrakt

Todo E ska definiera schemas och dokumentation för följande framtida API-yta.

Ingen router får implementeras eller monteras före todo H.

### 16.1 Tenant-scopade endpoints

Föreslagen resursyta:

```text
GET    /customers
GET    /customers/{customer_id}
POST   /customers
PATCH  /customers/{customer_id}

POST   /customers/{customer_id}/contacts
GET    /customers/{customer_id}/timeline
GET    /customers/{customer_id}/jobs
GET    /customers/{customer_id}/threads

GET    /customer-duplicates
GET    /customer-duplicates/{candidate_id}
POST   /customer-duplicates/{candidate_id}/decision

GET    /customer-search
POST   /customer-match-proposals
```

### 16.2 Operatorendpoints

Föreslagen operatorvariant:

```text
GET    /admin/tenants/{tenant_id}/customers
GET    /admin/tenants/{tenant_id}/customers/{customer_id}
GET    /admin/tenants/{tenant_id}/customer-duplicates
POST   /admin/tenants/{tenant_id}/customer-duplicates/{candidate_id}/decision
```

Operatorendpoints får inte ersätta tenantisolering med klientstyrd tenantdata. Tenantens scope ska verifieras server-side.

### 16.3 Behörighetsmatris

| Operation | Tenant-auth | read_only | operations | admin |
|---|---:|---:|---:|---:|
| Lista och läsa kundkort | Tillåten inom egen tenant | Tillåten | Tillåten | Tillåten |
| Läsa tidslinje och länkar | Tillåten inom egen tenant | Tillåten | Tillåten | Tillåten |
| Skapa kund manuellt | Provisoriskt tillåten inom egen tenant | Nej | Tillåten | Tillåten |
| Uppdatera verifierade fakta | Kräver framtida workspace-behörighet | Nej | Tillåten | Tillåten |
| Skapa duplicate decision | Kräver framtida workspace-behörighet | Nej | Tillåten | Tillåten |
| Merge | Blockerad i första implementationen | Nej | Nej | Endast efter separat godkännande |

Om detta kräver en ny authplattform eller större rolländring ska todo E stoppa.

### 16.4 Pagination

Listor ska använda repositoryts befintliga grundmönster:

- `limit`
- `offset`
- `items`
- `total`

Krav:

- default `limit=50`,
- max `limit=100`,
- stabil sortering,
- sekundär sortering på opakt ID,
- tenantfilter före pagination.

### 16.5 Versionshantering och optimistic locking

Varje skrivbart aggregate ska ha ett heltalsfält:

```text
version
```

Mutationer ska kräva:

```text
expected_version
```

Mismatch ska ge:

```text
409 CUSTOMER_VERSION_CONFLICT
```

En mutation får inte tyst skriva över en nyare version.

### 16.6 Idempotens

Följande framtida mutationer ska kräva `Idempotency-Key`:

- skapa kund,
- lägga till kontaktperson,
- skapa duplicate decision,
- godkänna en framtida merge.

Samma tenant, operation och nyckel:

- samma payload ska returnera ursprungligt resultat,
- annan payload ska ge `409 IDEMPOTENCY_CONFLICT`.

### 16.7 Audit

Alla writes ska registrera:

- `tenant_id`
- actor
- operation
- target type
- target ID
- expected version
- previous version
- new version
- reason
- idempotency key
- source provenance
- result status

### 16.8 Felkoder

API-kontraktet ska minst definiera:

- `CUSTOMER_NOT_FOUND`
- `CUSTOMER_VERSION_CONFLICT`
- `TENANT_SCOPE_VIOLATION`
- `INVALID_CUSTOMER_IDENTITY`
- `INVALID_SOURCE_PROVENANCE`
- `CUSTOMER_RELATIONSHIP_CONFLICT`
- `DUPLICATE_REVIEW_REQUIRED`
- `DUPLICATE_CANDIDATE_NOT_FOUND`
- `DUPLICATE_DECISION_CONFLICT`
- `AUTOMATIC_MERGE_FORBIDDEN`
- `IDEMPOTENCY_CONFLICT`
- `UNSUPPORTED_CUSTOMER_TRANSITION`

---

## 17. Todo A — Current truth

### Mål

Skapa en verifierad nulägesbild över alla befintliga strukturer som kan överlappa kunddomänen.

### Arbete

Audit ska minst inventera:

- customer-, account-, tenant-, company- och contactbegrepp,
- kontaktuppgifter i tenant settings,
- kontaktuppgifter i lead- och supportresultat,
- entity extraction,
- Gmail sender, message och thread identifiers,
- job input och result,
- approvals koppling till jobb,
- actions koppling till jobb,
- audit events,
- integration events,
- operatorpanelens tenantlista,
- kundens arbetsyta om sådan kod finns,
- befintlig Gmail-deduplicering,
- befintliga customer- eller CRM-liknande tabeller,
- befintliga migrationsmönster.

### Leverans

Skapa:

```text
docs/customer-card-domain/current-truth.md
```

Dokumentet ska innehålla:

1. repositorybaseline och auditdatum,
2. inventerade filer och symboler,
3. dataägare per uppgift,
4. befintliga tenantgränser,
5. återanvändbara ID:n,
6. befintliga customer-begrepp och namnkonflikter,
7. gap mellan nuvarande system och målbild,
8. dupliceringsrisk,
9. rekommenderat exakt filscope,
10. stop-gate-resultat.

### Tester och kontroller

Todo A är primärt read-only.

Minimikontroller:

- repositorysökning efter relevanta begrepp,
- kontroll av samtliga SQLAlchemy-modeller,
- kontroll av Gmail thread/messagefält,
- kontroll av tenantfilter i relevanta repositories,
- kontroll av nuvarande `/ops/customers`-betydelse,
- `git diff --name-only` ska endast visa plan- och auditdokument.

### Stop-gate

Stoppa före todo B om:

- en befintlig slutkundsmodell eller kundtabell hittas,
- ett parallellt spår redan har skapat samma domän,
- ett nytt customer-begrepp skulle kollidera med aktiv workspaceimplementation,
- tenantisolering inte kan verifieras,
- audit kräver ändring av förbjuden fil,
- repositoryt avviker så kraftigt att planens filscope inte är säkert.

### Definition of done

Todo A är klar när:

- nulägesdokumentet är komplett,
- alla relevanta strukturer är klassificerade som återanvänd, ersätt inte, eller saknas,
- ingen befintlig slutkundsdomän riskerar att dupliceras,
- exakt tillåtet scope för B och C är verifierat,
- stop-gaten har passerat,
- todo A har status `completed`.

---

## 18. Todo B — Domänmodell

### Mål

Definiera minsta hållbara modell för Customer, Company, Contact, Address, Identity och relationer.

### Arbete

Todo B ska:

1. jämföra minst två rimliga modellalternativ,
2. dokumentera varför den valda modellen är minst riskfylld,
3. tydligt separera tenant, customer, company och contact,
4. definiera aggregate boundaries,
5. definiera invariants,
6. definiera vilka records som är source of truth respektive projektion,
7. definiera framtida persistensbehov utan ORM,
8. skapa isolerade Pydantic-kontrakt.

### Leveranser

Skapa:

```text
docs/customer-card-domain/domain-model.md
app/domain/customer/__init__.py
app/domain/customer/enums.py
app/domain/customer/schemas.py
tests/test_customer_domain_schemas.py
```

### Schemaomfattning

Schemas ska minst kunna representera:

- Customer
- Company
- Contact
- CustomerAddress
- CustomerIdentity
- CustomerRelationship
- CustomerCard
- CustomerSourceFact
- CustomerTimelineEvent
- CustomerJobLink
- CustomerThreadLink
- CustomerDuplicateCandidate
- CustomerMergeDecision
- matchningsinput och matchningsresultat.

### Tester

Tester ska verifiera:

- obligatorisk `tenant_id`,
- confidenceintervall,
- timezone-aware timestamps,
- serialisering,
- förbjudna extra fält,
- separata company/contact-kontrakt,
- faktastatus,
- source types,
- att automatic merge är false,
- att schemas inte importerar SQLAlchemy eller runtimekod.

Kommando:

```bash
python -m pytest tests/test_customer_domain_schemas.py -q
```

### Stop-gate

Stoppa om:

- modellen kräver ändring av befintlig tabell,
- modellen kräver ny dependency,
- modellerna måste importeras i runtime för att kunna testas,
- Customer inte kan skiljas från tenant account,
- företag och kontaktperson inte kan modelleras separat,
- en schemaändring kräver auth- eller workflowändring.

### Definition of done

Todo B är klar när:

- modellalternativen är dokumenterade,
- en minimal konceptuell modell är rekommenderad,
- kontrakten är isolerade,
- testerna passerar,
- ingen persistence eller runtimekoppling finns,
- todo B har status `completed`.

---

## 19. Todo C — Identitet och matchning

### Mål

Definiera och isolerat implementera deterministisk normalisering, matchningsbedömning och manual-review-regler.

### Arbete

Todo C ska:

- implementera konservativa normaliserare,
- implementera ett rent matchningsassessment,
- använda den låsta poängmatrisen,
- implementera blockerande konfliktregler,
- generera stabila reason codes,
- säkerställa cross-tenant block,
- säkerställa att matchning aldrig tillåter merge,
- dokumentera candidate generation som framtida arbete utan databasquery.

### Leveranser

Skapa:

```text
docs/customer-card-domain/identity-matching.md
app/domain/customer/normalization.py
app/domain/customer/matching.py
tests/test_customer_identity_matching.py
```

### Obligatoriska testfall

Minst följande ska testas:

1. samma e-post inom samma tenant,
2. samma e-post i två olika tenants,
3. samma namn utan annan evidens,
4. samma telefon och samma namn,
5. samma telefon men olika verifierade namn,
6. samma verifierade organisationsnummer,
7. olika verifierade organisationsnummer,
8. företagskund jämförd med fysisk person,
9. rollbaserad e-post utan företagssignal,
10. samma Gmail-tråd inom samma tenant och integrationskontext,
11. samma tråd-ID i olika tenants,
12. adress och namn utan stark identitet,
13. ändrat telefonnummer med gammalt verifierat värde,
14. deterministisk ordning på evidence och reason codes,
15. `automatic_merge_allowed=false` i samtliga resultat.

Kommando:

```bash
python -m pytest tests/test_customer_identity_matching.py -q
```

Gemensam riktad gate:

```bash
python -m pytest \
  tests/test_customer_domain_schemas.py \
  tests/test_customer_identity_matching.py \
  -q
```

### Stop-gate

Stoppa om:

- matchning kräver databasquery,
- Gmail-adapter måste ändras,
- normalisering kräver extern tjänst,
- automatisk merge krävs för att testerna ska passera,
- cross-tenant-jämförelse inte kan blockeras,
- score eller reason codes blir nondeterministiska.

### Definition of done

Todo C är klar när:

- matchningsreglerna är dokumenterade,
- normalisering är konservativ och deterministisk,
- assessment är en ren funktion,
- samtliga obligatoriska testfall passerar,
- ingen databas- eller runtimeintegration finns,
- todo C har status `completed`.

---

## 20. Todo D — Tidslinje och provenance

### Mål

Definiera hur kundhistorik, source facts, konflikter och referenser ska representeras.

### Tillåtet arbete

- dokumentation,
- utökning av isolerade schemas,
- kontraktstester,
- rena transformationsfunktioner om de saknar I/O.

### Leverans

Skapa:

```text
docs/customer-card-domain/timeline-provenance.md
```

Dokumentet ska definiera:

- eventtyper,
- source types,
- fact states,
- reference types,
- konfliktövergångar,
- historical transitions,
- immutability,
- sorteringsregler,
- replay- och idempotensprinciper,
- vilka metadatafält som är tillåtna.

### Tester

Utöka isolerade schematester med:

- tidslinjeordning,
- occurred/recorded semantics,
- self-reference guard,
- conflict references,
- historiska facts,
- inga fullständiga externa payloads.

### Stop-gate

Stoppa om tidslinjen kräver ändring av jobb-, approval-, action- eller Gmail-tabeller.

### Definition of done

Todo D är klar när tidslinje- och provenancekontraktet är komplett och isolerat testat.

---

## 21. Todo E — API-kontrakt

### Mål

Definiera framtida tenant- och operator-API utan att skapa produktionsrouter.

### Tillåtet arbete

- API-dokumentation,
- request/response-schemas i isolerat customer-paket,
- kontraktstester,
- behörighetsmatris,
- felkoder,
- pagination,
- versionering,
- idempotens.

### Leverans

Skapa:

```text
docs/customer-card-domain/api-contract.md
```

### Tester

Tester ska verifiera:

- tenant_id tas från autentiserat scope och inte godtycklig payload,
- version krävs vid writes,
- idempotency key-kontrakt,
- stabila felkoder,
- customer card saknar interna payloads,
- listrespons följer items/total/limit/offset.

### Stop-gate

Stoppa om:

- större authändring krävs,
- en router måste monteras för att kontraktet ska kunna definieras,
- app/main måste ändras,
- workspace-spårets aktiva API-kontrakt kolliderar,
- befintliga operatorroller inte räcker.

### Definition of done

Todo E är klar när API-kontraktet kan implementeras utan öppna säkerhets- eller authfrågor.

---

## 22. Todo F — Migration och testplan

### Mål

Ta fram en säker framtida persistens-, backfill- och teststrategi utan att skapa migration eller tabell.

### Leverans

Skapa:

```text
docs/customer-card-domain/migration-test-plan.md
```

### Migrationsdesign

Planen ska definiera:

1. föreslagen tabellordning,
2. foreign keys och tenantinvarianter,
3. index,
4. uniquenessbegränsningar,
5. versionsfält,
6. append-only-tabeller,
7. rollbackstrategi,
8. shadow/read-only-läge,
9. backfill från befintliga jobb,
10. konflikt- och quarantineflöde,
11. verifiering före aktivering,
12. feature flag eller annan runtimegate.

Ingen faktisk migrationsfil får skapas.

### Backfillprincip

Backfill ska vara:

- tenantvis,
- idempotent,
- återstartbar,
- read-only mot källrecords,
- utan automatisk merge,
- kapabel att skapa duplicate candidates,
- verifierbar med före/efter-rapport,
- blockerad om tenantisolering inte kan bevisas.

### Syntetiska kundfamiljer

Minst följande familjer ska specificeras:

1. ny privatkund,
2. återkommande kund i ny mejltråd,
3. kund med ändrat telefonnummer eller adress,
4. företagskund med flera kontaktpersoner,
5. oklar eller duplicerad identitet.

Varje familj ska innehålla:

- tenant,
- observationer över tid,
- källor,
- förväntade facts,
- förväntade konflikter,
- förväntad tidslinje,
- förväntade länkar,
- förväntat duplicate outcome,
- förbud mot osäker merge.

### Stop-gate

Stoppa om:

- backfill kräver ändring av källrecords,
- befintliga Gmail- eller jobbrecords saknar tillräcklig tenantinformation,
- en säker rollback inte kan beskrivas,
- automatiserad merge krävs,
- schemaordningen kräver ändring av approvals eller execution contracts.

### Definition of done

Todo F är klar när framtida implementation kan delas i säkra migrations- och implementationskapitel med tydliga tester och rollback.

---

## 23. Todo G — Implementation gate

### Mål

Granska hela designen och avgöra om implementation kan rekommenderas.

### Leverans

Skapa:

```text
docs/customer-card-domain/implementation-gate.md
```

### Obligatorisk gate-matris

Dokumentet ska ge PASS, FAIL eller BLOCKED för:

- repository current truth,
- ingen duplicerad kunddomän,
- tenantisolering,
- terminology separation,
- minimal datamodell,
- source provenance,
- konfliktregler,
- deterministic matching,
- ingen automatisk merge,
- tidslinjereferenser,
- API-auth,
- optimistic locking,
- idempotens,
- audit,
- migrationsordning,
- backfill,
- rollback,
- syntetisk testmatris,
- workspace-kollision,
- testbot-/approval-/dispatch-kollision,
- exakt framtida filscope.

### Beslutsunderlag

Gate-dokumentet ska innehålla:

- rekommenderad persistensmodell,
- rekommenderad implementationsordning,
- föreslagna branches,
- föreslagna migrationer,
- föreslagen ADR-text,
- identifierade kvarstående risker,
- uppskattad blast radius,
- explicit GO/NO-GO-rekommendation.

### Obligatoriskt stopp

Efter att todo G har rapporterats ska Cursor stoppa.

Todo H får inte sättas till `in_progress`.

Ingen implementationbranch får skapas.

Ingen migration får skapas.

Ingen design-PR får mergeas om operatören inte uttryckligen godkänt både designen och övergången till implementation.

### Definition of done

Todo G är klar när operatören har ett komplett och evidensbaserat beslutsunderlag.

Todo G:s status får markeras `completed` när dokumentet är klart, men implementation förblir blockerad tills ett separat godkännande har lämnats.

---

## 24. Todo H — Implementation

### Status

Blockerad.

### Tillåten start

Todo H får endast starta efter ett uttryckligt operatörsbeslut som minst anger:

- godkänd datamodell,
- godkänd migrationsordning,
- godkänt API-scope,
- godkänd authmodell,
- godkänd matchningspolicy,
- godkänd mergepolicy,
- godkänd branchordning.

### Föreslagen senare branchordning

1. `feat/customer-card-foundation`
2. `feat/customer-card-timeline`
3. `feat/customer-card-matching`
4. `feat/customer-card-api`
5. `feat/customer-card-ui`

Varje branch ska ha separat gate, tester och rollback.

---

## 25. Todo I — Stateful evaluation

### Status

Blockerad tills foundation, timeline, matching och API är implementerade.

### Framtida mål

Verifiera att kunddomänen behåller korrekt identitet och historik genom flera observationer över tid.

Testerna ska minst verifiera:

- tenantisolering,
- create/update,
- customer card projection,
- source provenance,
- tidslinje,
- jobblänkar,
- threadlänkar,
- ändrade kontaktuppgifter,
- företagskund med flera kontakter,
- duplicate candidate,
- manual decision,
- ingen osäker merge,
- idempotent replay.

---

## 26. Todo J — Closure

### Status

Blockerad.

### Framtida mål

Slutverifiera:

- produktgräns,
- driftbarhet,
- säkerhet,
- datakvalitet,
- observability,
- runbook,
- rollback,
- workspaceintegration,
- post-merge- och post-deploy-evidens.

Todo J får inte stängas med enbart enhetstester.

---

## 27. Teststrategi

### 27.1 Designfas A–G

Designfasen ska prioritera riktade, hermetiska tester.

För A–C:

```bash
python -m pytest \
  tests/test_customer_domain_schemas.py \
  tests/test_customer_identity_matching.py \
  -q
```

Tillåten importkontroll:

```bash
python -m compileall app/domain/customer
```

Full testsuite krävs inte i första A–C-körningen eftersom ingen runtimekod får importera customer-paketet.

Full testsuite får köras som extra kontroll om den är lokalt tillgänglig, men ett misslyckande utanför detta scopes ändrade filer ska rapporteras och inte repareras inom spåret.

### 27.2 Förbjudna testtyper under A–G

- live Gmail,
- live OpenAI,
- live integration,
- database migration,
- PostgreSQL backfill,
- production smoke,
- external writes,
- browsertest,
- workspaceimplementationstest,
- ändring av testbot-scenarier.

### 27.3 Testkvalitet

Tester ska:

- vara deterministiska,
- sakna nätverk,
- sakna databas,
- sakna global tenantstate,
- använda tydliga expected reason codes,
- testa negativa och konfliktande fall,
- uttryckligen testa cross-tenant-förbud,
- uttryckligen testa att automatisk merge inte tillåts.

---

## 28. Branch-, commit- och PR-strategi

### Designfas A–G

Använd:

```text
design/customer-card-domain
```

Branchen ska skapas från uppdaterad `main`.

Vid start ska följande registreras i lokal rapport:

- main SHA,
- branch SHA,
- working tree-status,
- aktiva parallella branches om de kan identifieras,
- eventuella filer som redan ändrats av andra spår.

Todos A–G får genomföras på samma designbranch med avgränsade commits.

Föreslagen commitindelning:

```text
docs(customer-domain): record current repository truth
feat(customer-domain): add isolated domain contracts
feat(customer-domain): add deterministic identity assessment
docs(customer-domain): define timeline and provenance
docs(customer-domain): define API contracts
docs(customer-domain): define migration and evaluation plan
docs(customer-domain): complete implementation gate
```

### Första körningen A–C

Första körningen ska:

- skapa eller använda designbranchen,
- genomföra A–C,
- göra riktade tester,
- skapa en eller flera tydliga commits,
- pusha branchen om credentials finns,
- inte öppna implementationbranch,
- inte mergea,
- stoppa med resultatrapport.

### Design-PR

En design-PR får tidigast öppnas efter todo G.

Den får inte mergeas före uttryckligt operatörsgodkännande.

### Implementation

Implementation ska ske på nya branches från den då godkända main-baselinen.

Ingen implementationbranch får ärva oredovisade ändringar från designbranchen.

---

## 29. Lokala rapporter

Rapporter ska använda följande mönster:

```text
storage/status/customer-card-domain-abc.md
storage/status/customer-card-domain-def.md
storage/status/customer-card-domain-gate.md
```

De ska inte committas.

Varje rapport ska innehålla:

```text
Baseline:
- Main SHA:
- Start branch:
- Working tree:

Completed:
- ...

Current-truth findings:
- ...

Domain decisions:
- ...

Changed files:
- ...

Tests/checks run:
- ...

Tests/checks not run:
- ...

Forbidden-scope verification:
- ...

Plan status changes:
- ...

Issues / stop conditions:
- ...

Open risks:
- ...

Next allowed work:
- ...
```

Rapporten ska vara ärlig om allt som inte verifierats.

---

## 30. Globala stop-villkor

Stoppa omedelbart om:

- repositoryt redan har en slutkundsmodell som planen riskerar att duplicera,
- ett parallellt spår har skapat överlappande customer-domain-filer,
- en migration behöver skapas eller köras,
- en ORM-modell behöver skapas före todo H,
- befintliga jobb-, Gmail-, approval- eller actiontabeller måste ändras,
- tenantisolering inte kan bevisas,
- matchning kräver cross-tenant-index,
- deduplicering kräver automatisk merge,
- ett verifierat värde måste skrivas över automatiskt,
- intake, entity extraction, decisioning, policy eller dispatch måste ändras,
- Gmail-flödet måste ändras,
- API-kontraktet kräver en större authändring,
- workspace-spårets aktiva kontrakt kolliderar,
- testbotens eller live-evalueringens filer måste ändras,
- en ny dependency krävs,
- mer än två korrigeringscykler krävs för samma isolerade testgate,
- working tree innehåller okända ändringar,
- branchbaselinen inte kan verifieras,
- uppdraget endast kan slutföras genom att försvaga säkerhetsreglerna.

Agenten får inte “lösa” ett stop-villkor genom att utöka scope.

---

## 31. Definition of done för designfasen

Todos A–G är komplett när:

1. repository current truth är dokumenterad,
2. ingen befintlig slutkundsdomän dupliceras,
3. tenant och end customer är tydligt separerade,
4. minsta domänmodell är definierad,
5. source provenance och konflikter är definierade,
6. matchning är deterministisk och fail-closed,
7. automatisk merge är förbjuden,
8. timelinekontraktet refererar befintliga records,
9. API-kontraktet definierar auth, pagination, locking, audit och idempotens,
10. migrations- och backfillplanen är reversibel,
11. de fem syntetiska kundfamiljerna är definierade,
12. implementationens blast radius är känd,
13. implementation-gaten innehåller GO/NO-GO-underlag,
14. inga runtime-, database-, Gmail-, approval-, dispatch- eller frontendändringar har gjorts,
15. operatören har fått ett uttryckligt stopp före todo H.

---

## 32. Godkännandetext för övergång till implementation

Todo H får endast öppnas efter ett beslut med motsvarande innebörd:

```text
Jag godkänner customer-card-domain-planens implementation-gate och tillåter att
customer-domain-h-implementation startas enligt den godkända datamodellen,
migrationsordningen, tenantisoleringen, API-gränsen och matchningspolicyn.

Automatisk merge är fortsatt förbjuden om den inte godkänns separat.
```

Utan detta beslut ska todo H förbli `pending`.
