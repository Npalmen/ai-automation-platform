---
name: Fullständig testbotkampanj
overview: "Aktivera den befintliga testboten som ett isolerat självtestande system: den skapar syntetiska kundmejl, skickar dem mellan dedikerade testkonton, låter applikationen behandla dem i observe-, semi-automatiskt och automatiskt läge, verifierar svar och externa testwrites, testar stateful kundkort och kör därefter representativa kampanjer över samtliga faktiskt implementerade funktioner — utan verkliga kunder, produktionsresurser eller okontrollerade externa sidoeffekter."
todos:
  - id: testbot-a-current-truth
    content: Audita testbot, Live Gmail, beslut/policy, integrationer, kundkort och aktuell serverdrift samt lås den faktiska testmatrisen
    status: completed
  - id: testbot-b-isolated-environment
    content: Deploya verifierad main och konfigurera dedikerad testtenant, testkonton, labels, budgets, testresurser och fail-closed säkerhetsgränser
    status: completed
  - id: testbot-c-observe-campaign
    content: Kör testbotgenererade Gmail-scenarier i observe/approval-first-läge och verifiera intake, klassificering, extraction, routing, jobs, cockpit och approvals
    status: completed
  - id: testbot-d-semi-automatic-campaign
    content: Testa semi-automatiskt läge där testbotens operatörsdel godkänner eller avslår förväntade actions och verifierar idempotens och outbound-resultat
    status: in_progress
  - id: testbot-e-automatic-campaign
    content: Testa automatiskt läge endast för allowlistade actions mot isolerade testresurser och verifiera policy, budgets, resultat, cleanup och fail-closed behavior
    status: pending
  - id: testbot-f-customer-card-stateful
    content: Testa skapande, uppdatering, deduplicering, tidslinje och historik för syntetiska kundkort genom flermejls- och flertrådsscenarier
    status: pending
  - id: testbot-g-full-function-matrix
    content: Testa varje faktiskt implementerad funktion och integration i rätt test- eller sandboxmiljö och dokumentera saknade eller ofullständiga produktförmågor
    status: pending
  - id: testbot-h-continuous-regression
    content: Etablera återkörbara kampanjer, kvalitetsrapporter, failure triage och closurebeslut för fortsatt intern användning och senare kundpilot
    status: pending
isProject: true
---

# Fullständig testbotkampanj

**Planstatus:** Auktoritativ exekveringsplan  
**Planversion:** `full-system-testbot-campaign-v1`  
**Syfte:** Testa den verkliga produkten genom att testboten genererar, skickar, observerar och verifierar egna syntetiska ärenden  
**Normalläge:** Isolerad testtenant, dedikerade testkonton, tydliga budgets och fail-closed  
**Föregående interna pilotplan:** Ersätts av denna plan för systemtest; verklig intern användning kommer efter verifierad testbotkampanj

---

## Agentregler

Läs hela planen innan någon ändring eller extern körning görs.

Planens scope, säkerhetsgränser, testlägen, kvalitetsgates och stop-villkor är read-only. Endast todo-status får ändras:

```text
pending → in_progress → completed
```

Agenten får arbeta autonomt genom audit, implementation, hermetiska tester, commit, PR, CI, squash-merge och post-merge-verifiering.

Agenten måste stoppa för operatörsgodkännande före:

- deployment,
- OAuth- eller secretändring,
- första riktiga Gmail-send,
- första semi-automatiska outbound action,
- första automatiska externa testwrite,
- aktivering av nya testresurser i Visma, Sheets eller Monday.

Efter att varje extern fas uttryckligen godkänts får agenten genomföra den fasen autonomt inom planens exakta budget och allowlist.

Lokal exekveringsrapport:

```text
storage/status/full-system-testbot-execution-report.md
```

Lokal kampanjrapport:

```text
storage/status/full-system-testbot-campaign-report.md
```

Dessa ska inte committas.

---

# 1. Korrigerad teststrategi

Testboten ska inte förlita sig på att operatören manuellt skapar varje testmejl.

Den ska själv:

1. välja ett versionsstyrt syntetiskt scenario,
2. skapa unik correlation token,
3. skicka mejlet från dedikerat testbotkonto,
4. verifiera leverans till dedikerad mottagare och label,
5. låta applikationen behandla mejlet,
6. observera jobb, beslut, approvals, kundkort och telemetri,
7. utföra eller simulera testoperatörens beslut,
8. verifiera eventuellt svar eller testwrite,
9. städa endast exakta testobjekt,
10. producera redigerad evidens.

Testboten ska alltså testa produkten mot sig själv, men med hårda transport-, policy- och write-gränser.

---

# 2. Två kompletterande testnivåer

## 2.1 Hermetisk skala

2G används fortsatt för:

- 60 scenariofall i PR,
- 160 scenariofall på main,
- deterministiska mutationer,
- kvalitetsgränser,
- snabb och billig regression.

Dessa scenarier ska inte alla skickas via Gmail.

## 2.2 Live end-to-end-representation

Testboten använder Gmail och sandboxresurser för ett mindre men representativt urval som verifierar den verkliga kedjan:

```text
syntetiskt kundmejl
→ Gmail transport
→ intake
→ klassificering/extraction
→ decision/policy
→ job
→ approval eller auto-authorization
→ outbound testaction
→ verifiering
→ kundkort/tidslinje
→ audit/telemetri
```

Livekampanjer testar transport och integrationsverklighet. Hermetiska kampanjer testar bredd och variation.

---

# 3. Testlägen

## 3.1 Observe mode

Applikationen får:

- läsa scoped testmejl,
- klassificera,
- extrahera,
- skapa jobb,
- skapa kundkort om funktionen finns,
- föreslå routing,
- skapa approvals,
- skapa utkast.

Applikationen får inte:

- skicka svar,
- lösa approval,
- skriva till externa integrationer.

## 3.2 Semi-automatiskt läge

Applikationen förbereder action och kräver approval.

Testbotens separata operatörsdel får inom dedikerad testtenant:

- verifiera att expected approval skapades,
- godkänna eller avslå enligt scenariospecifikation,
- verifiera idempotens,
- verifiera eventuellt outbound-resultat.

Ett semi-automatiskt scenario får aldrig godkännas om tenant eller correlation token inte matchar, action saknar testmarkör, målresurs inte är allowlistad, approval state är stale eller write-budget är förbrukad.

## 3.3 Automatiskt läge

Automatisk exekvering får endast testas för actions som är explicit allowlistade, går till dedikerad testresurs, har testtenant, har full correlation token, har scenario som uttryckligen förväntar auto-execution, har per-run write-budget och har verifierad cleanup eller sandboxisolering.

Automatiskt läge får inte riktas mot verkliga kunder, ordinarie inboxmottagare, riktiga ekonomidata, produktionsboards eller kalkylark, riktiga kalenderbokningar eller okända/dynamiska mottagare.

---

# 4. Isolerade resurser

## Gmail

- dedikerad testbotavsändare,
- dedikerad appmottagare,
- dedikerad label,
- sender/recipient allowlist,
- full correlation token,
- per-run send/reply budget,
- inga fria mottagare.

## Google Sheets

- separat testsheet,
- separat tabschema,
- testmarkör i varje rad,
- cleanup genom exakta row-/runreferenser där API-kontraktet stödjer det,
- annars persistent sandboxdata med tydlig testprefix.

## Monday

- separat testboard,
- testgrupp eller testworkspace,
- inga writes till produktionsboard,
- testboten verifierar exakt item-id och correlation token.

## Visma

- endast sandbox,
- inga verkliga kunder, fakturor eller bokföringsdata,
- syntetiska organisations- och kunduppgifter,
- inga production credentials.

## Övriga integrationer

Varje integration kräver explicit testresurs, explicit allowlist, write-budget, redigerad evidens samt verifierbar rollback eller sandboxisolering.

---

# 5. Scenariomodell

Varje live scenario ska minst innehålla:

```json
{
  "scenario_id": "stable-id",
  "scenario_version": "v1",
  "mode": "observe|semi_automatic|automatic",
  "job_type": "lead|customer_inquiry|invoice|unknown",
  "service_profile": "expected-or-null",
  "synthetic_customer_id": "customer-family-id",
  "thread_id": "scenario-thread-id",
  "sender": "allowlisted-testbot",
  "recipient": "allowlisted-app-mailbox",
  "label": "dedicated-test-label",
  "expected_classification": {},
  "expected_entities": {},
  "expected_routing": {},
  "expected_approval": {},
  "expected_customer_card": {},
  "expected_external_actions": [],
  "budgets": {
    "gmail_sends": 1,
    "gmail_replies": 0,
    "external_writes": 0
  }
}
```

Scenariohash och expected outcome-hash ska vara deterministiska.

---

# 6. Live kampanjnivåer

## Nivå 1 — Transport smoke

Antal:

```text
5 scenarios
```

Innehåll:

- lead,
- support/customer inquiry,
- invoice,
- unknown/unsupported,
- noisy eller multi-intent.

Läge:

```text
observe
```

## Nivå 2 — Semi-automatisk kampanj

Antal:

```text
8–12 scenarios
```

Innehåll:

- approve expected,
- reject expected,
- stale approval,
- duplicate submit,
- reply draft,
- routing/handoff,
- action authorization.

Läge:

```text
semi_automatic
```

## Nivå 3 — Automatisk kampanj

Antal:

```text
5–10 scenarios
```

Endast allowlistade testactions, exempelvis:

- svar tillbaka till testbotavsändaren,
- rad till testsheet,
- item till testboard,
- sandboxunderlag.

Läge:

```text
automatic
```

## Nivå 4 — Stateful kundkort

Antal:

```text
5 syntetiska kundfamiljer
3–6 mejl per familj
```

Testar nytt kundkort, återkommande kontakt, samma kund med ny tråd, ändrad telefon/adress, duplicate, flera kontaktpersoner, företag kontra privatperson, tidslinje, länkade jobb samt approvals/actions i historiken.

## Nivå 5 — Full funktionsmatris

Representativ kampanj för varje faktiskt implementerad produktförmåga och integration.

Ingen funktion ska märkas PASS enbart för att kod finns. Den måste ha testscenario, verifierat resultat, säkerhetsbevis, operatörssynlighet och redigerad evidens.

---

# A. Current-truth-audit

**Todo:** `testbot-a-current-truth`

## Mål

Fastställ exakt vad testboten och produkten redan kan, vad som är deployat och vad som kräver komplettering.

## Granska

- 2F Live Gmail testbot,
- 2F Live LLM,
- 2G scenario generator,
- scenario registry och journal,
- send/reply budgets,
- resume/reconcile,
- Gmail sender/recipientkonton,
- dedicated labels,
- approvals,
- action authorization,
- auto-execute,
- scheduler,
- tenant automation config,
- external adapters,
- customer card eller motsvarande modeller/endpoints,
- operator UI,
- incident/needs-help,
- test- och sandboxkonfiguration.

## Output

Skapa:

```text
storage/status/full-system-testbot-audit.md
```

Rapportera aktuell full `origin/main` SHA, faktisk server-SHA, testbotens nuvarande funktioner, vad som endast fungerar observe-only, vad som redan stöder semi-auto, vad som redan stöder auto, customer-card-status, integrationsmatris, saknade säkerhetsgates, exakt filscope för B–H och nödvändiga manuella steg.

## Gate

Fortsätt endast om testboten kan byggas vidare utan att försvaga tenantisolering, approval-first, action authorization, idempotens eller 2E–2G-baseline.

---

# B. Isolerad testmiljö

**Todo:** `testbot-b-isolated-environment`

## Mål

Sätt upp ett testuniversum där automatiska och semi-automatiska actions kan köras utan påverkan på verklig verksamhet.

## Krav

- exakt en testtenant,
- testbot sender allowlist,
- app recipient allowlist,
- dedikerad label,
- scenariospecifik full token,
- read/write budgets per run,
- schedulerläge per kampanj,
- testoperator identity,
- testsheet,
- testboard,
- Visma sandbox om integrationen ingår,
- cleanup eller tydlig sandboxretention,
- drift- och incidentstopp.

## Deploy

Agenten ska förbereda deployment och stoppa med:

```text
OPERATOR ACTION REQUIRED — Deploy och aktivera testbotmiljö
```

Rapporten ska innehålla exakt main-SHA, serverns nuvarande SHA, diff/commits, migrationstatus, lokala serverändringar, secrets/config som redan finns, secrets/config som saknas, exakt deploykommando, readinesskommando och rollbackkommando.

Deployment får genomföras först efter uttryckligt godkännande.

## Gate

- rätt SHA deployad,
- `/health` PASS,
- runtime SHA verifierad,
- scheduler initialt paused,
- alla testresurser isolerade,
- allowlists exakta,
- budgets låsta,
- no-production-resource-check PASS,
- rollback verifierad.

---

# C. Observe-kampanj

**Todo:** `testbot-c-observe-campaign`

## Mål

Verifiera verklig Gmailtransport och hela pipelinekedjan utan outbound action.

## Testboten ska själv

1. skapa fem syntetiska mejl,
2. skicka dem från testbotavsändaren,
3. verifiera leverans och label,
4. trigga eller invänta scoped intake,
5. verifiera jobb,
6. verifiera classification/extraction/routing,
7. verifiera approvals,
8. verifiera cockpit/needs-help,
9. verifiera customer card om funktionen finns,
10. cleanup/arkivera exakta testobjekt.

## Absoluta invariants

- Gmail sends från testbot = exakt scenarioantal,
- app Gmail replies = 0,
- external writes = 0,
- approval resolutions = 0,
- cross-tenant = 0,
- duplicates = 0,
- scope violations = 0.

## Gate

Samtliga fem scenarios ska ha ett entydigt resultat. Produktfel får registreras, men säkerhetsfel stoppar kampanjen.

---

# D. Semi-automatisk kampanj

**Todo:** `testbot-d-semi-automatic-campaign`

## Mål

Testa verkliga approvals och efterföljande actions i isolerad miljö.

## Testoperatör

Skapa eller återanvänd en test-only operator identity.

Den får endast läsa approvals i testtenant, godkänna/avslå scenarios med full token, agera enligt expected outcome och aldrig använda wildcard tenant eller recipient.

## Scenarier

Minst:

- två approve,
- två reject,
- ett duplicate submit,
- ett stale/version conflict,
- ett forbidden action,
- ett manual-review/hold,
- ett scenario där outbound reply går tillbaka till testbotkonto om Gmail reply uttryckligen aktiverats.

## Verifiera

- rätt approval skapades,
- rätt actor,
- rätt state transition,
- CAS/idempotens,
- endast tillåten action exekverades,
- testboten mottog och verifierade eventuellt svar,
- reject skapade ingen write,
- stale och duplicate skapade ingen dubbel write,
- audit/telemetri korrekt.

## Obligatoriskt operatörsstopp

Före första semi-auto outbound write:

```text
OPERATOR ACTION REQUIRED — Auktorisera semi-automatisk testkampanj
```

---

# E. Automatisk kampanj

**Todo:** `testbot-e-automatic-campaign`

## Mål

Verifiera att policybaserad auto-execution fungerar säkert för uttryckligen allowlistade testactions.

## Förkrav

- observe PASS,
- semi-auto PASS,
- inga öppna säkerhetsincidenter,
- auto mode aktiverat endast för testtenant,
- testactions allowlistade,
- write budgets exakta,
- destinationsresurser verifierade som test/sandbox.

## Scenarier

Minst:

- auto-reply till testbotkonto,
- auto-route utan extern write,
- testsheet write,
- testboard write,
- sandboxunderlag om Visma-kontraktet är produktklart,
- forbidden recipient,
- budget exceeded,
- missing token,
- unknown scenario,
- adapter timeout/outcome unknown.

## Verifiera

- tillåtna actions exekveras exakt en gång,
- förbjudna actions blockeras,
- outcome unknown hanteras fail-closed,
- retry skapar inte dubbel write,
- destinationer är testresurser,
- cleanup/retention korrekt,
- testboten kan observera och jämföra faktisk effekt.

## Obligatoriskt operatörsstopp

Före första automatiska externa testwrite:

```text
OPERATOR ACTION REQUIRED — Auktorisera automatisk testkampanj
```

---

# F. Stateful kundkort

**Todo:** `testbot-f-customer-card-stateful`

## Mål

Testa kundkort och kundhistorik som en verklig stateful produktfunktion, inte som isolerade engångsmejl.

## Första audit i todo F

Identifiera faktiska modeller, endpoints och UI för customer, contact, company, customer card, timeline, linked jobs, notes/memory points och duplicate resolution.

Om kundkort inte finns ska agenten dokumentera exakt vad som saknas, föreslå minsta separata produktkapitel och inte smygbygga en generell CRM-modul inom testkampanjen.

Om kundkort finns helt eller delvis ska följande testas.

## Kundfamiljer

### Familj 1 — Ny privatkund

- första lead,
- kontaktuppgifter,
- nytt kundkort,
- länkat jobb.

### Familj 2 — Återkommande kund

- nytt mejl i ny tråd,
- samma e-post,
- befintligt kort återanvänds,
- tidslinje uppdateras.

### Familj 3 — Uppdaterade uppgifter

- ändrat telefonnummer eller adress,
- konflikt hanteras,
- ingen oavsiktlig overwrite.

### Familj 4 — Företagskund

- företag,
- flera kontaktpersoner,
- korrekt relation företag–kontakt–jobb.

### Familj 5 — Duplicat/oklar identitet

- variation i namn,
- samma telefon men annan e-post,
- systemet auto-mergar inte osäkert,
- manual review vid behov.

## Verifiera

- create/update/dedupe,
- tenantisolering,
- timeline,
- job links,
- approvals/actions,
- source provenance,
- operatörs- eller kundvy,
- inga verkliga personuppgifter.

---

# G. Full funktionsmatris

**Todo:** `testbot-g-full-function-matrix`

## Mål

Testa alla faktiskt implementerade funktioner gradvis.

## Minsta matris

| Område | Observe | Semi-auto | Auto | Sandbox/testresurs |
|---|---:|---:|---:|---|
| Lead intake | Ja | Ja | Endast safe routing/reply | Gmail test |
| Customer inquiry | Ja | Ja | Endast allowlistat | Gmail test |
| Invoice intake | Ja | Ja | Endast sandbox | Visma sandbox |
| Unknown/manual review | Ja | Ja | Nej | Intern |
| Customer reply | Utkast | Godkänd send | Testbot-only auto | Gmail test |
| Sheets export | Förslag | Godkänd write | Testsheet auto | Testsheet |
| Monday export | Förslag | Godkänd write | Testboard auto | Testboard |
| Visma underlag | Förslag | Godkänd sandbox | Endast om säkert | Sandbox |
| Needs-help | Ja | Operatörsåtgärd | Nej | Intern |
| Incident | Ja | Operatörsåtgärd | Nej | Intern |
| Scheduler | Manual | Kontrollerad | Begränsad kampanj | Testtenant |
| Customer card | Create/update | Review conflicts | Safe deterministic only | Testtenant |

Anpassa matrisen efter audit. Markera varje funktion:

- `PASS`
- `PARTIAL`
- `BLOCKED`
- `NOT_IMPLEMENTED`
- `OUT_OF_SCOPE`

## Regel

En funktion får inte kallas PASS om den endast har unit test. Den måste ha representativ end-to-end-verifiering i korrekt miljö.

---

# H. Kontinuerlig regression och closure

**Todo:** `testbot-h-continuous-regression`

## Mål

Göra testbotkampanjen återkörbar och användbar för produktförbättring.

## Kampanjtyper

- `transport-smoke`
- `observe-core`
- `semi-auto-core`
- `auto-safe-actions`
- `customer-card-stateful`
- `integration-sandbox`
- `full-regression`

## Rapport

Skapa:

```text
full_system_testbot_report.json
```

Minst:

- schema,
- main-SHA,
- server-SHA,
- campaign type,
- scenario versions,
- mode,
- sends,
- replies,
- approvals,
- auto actions,
- writes per integration,
- customer card outcomes,
- failures,
- safety violations,
- cleanup,
- redaction,
- overall status.

## Failure triage

Varje failure ska klassificeras som transport, classification, extraction, routing, policy, approval, execution, adapter, customer-card, UI/visibility, cleanup, safety eller infrastructure.

Varje produktfix ska:

1. få ett reproducerbart scenario,
2. få ett regressionstest,
3. passera 2E–2G,
4. passera relevant livekampanj,
5. mergas separat.

## Slutbeslut

Tillåtna statusar:

```text
TESTBOT_CORE_PASS
SEMI_AUTO_PASS
AUTO_SAFE_ACTIONS_PASS
CUSTOMER_CARD_PASS
FULL_IMPLEMENTED_MATRIX_PASS
NEEDS_PRODUCT_FIXES
STOPPED_FOR_SAFETY
```

---

# Stop-villkor

Stoppa omedelbart vid:

- cross-tenant finding,
- send/reply utanför allowlist,
- write till produktionsresurs,
- approval bypass,
- dubbel execution,
- outcome unknown som behandlas som success,
- budgetöverskridning,
- cleanup mot osäkert objekt,
- verklig PII i testdata/artifacts,
- otydlig serverversion,
- krav på ny migration utan separat plan,
- funktion som kräver större produktimplementation.

---

# Definition of done

Planen är klar när:

1. testboten själv kan skapa och skicka syntetiska scenarios,
2. observe-kampanjen passerar,
3. semi-auto-kampanjen passerar,
4. allowlistad auto-kampanj passerar,
5. kundkort är testat eller sanningsenligt klassat som saknat,
6. samtliga implementerade funktioner har status,
7. externa testwrites är isolerade,
8. inga säkerhetsbrott finns,
9. 2E–2G förblir gröna,
10. kampanjer kan återköras,
11. failure triage och regression loop fungerar,
12. nästa produktprioritering bygger på faktisk kampanjevidens.

---

## Startinstruktion

> Läs `docs/plans/full-system-testbot-plan.md` i sin helhet. Behandla tekniskt innehåll som auktoritativt och read-only; endast todo-status får uppdateras. Genomför audit A och bygg den isolerade testmiljön B. Testboten ska själv generera och skicka syntetiska Gmail-scenarier, inte kräva manuellt skapade testmejl. Stoppa för uttryckligt operatörsgodkännande före deployment, första Gmail-send, första semi-automatiska outbound action och första automatiska externa testwrite. Därefter genomförs observe-, semi-auto-, auto-, kundkorts- och fullfunktionskampanjerna stegvis med exakta budgets och endast dedikerade test- eller sandboxresurser. Uppdatera `storage/status/full-system-testbot-execution-report.md` och `storage/status/full-system-testbot-campaign-report.md`.
