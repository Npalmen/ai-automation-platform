---
name: Post-2G roadmap audit
overview: "Genomför en read-only audit av repositoryts faktiska läge efter stängt Kapitel 2G, jämför kod, dokumentation, första-kund-plan och långsiktig produktvision, prioritera nästa största värdeskapande kapitel och lämna ett beslutsunderlag för nästa kompletta Cursor-plan — utan implementation, commit, PR, externa anrop eller ändring av repositoryt."
todos:
  - id: verify-current-truth
    content: Verifiera main-baseline, auktoritativa dokument, implementerad funktionalitet och faktisk CI-/driftstatus efter 2G
    status: completed
  - id: map-product-gaps
    content: Kartlägg gap mellan nuvarande produkt, första kundens användarresa, operatörsbehov och den långsiktiga digitala medarbetarvisionen
    status: completed
  - id: prioritize-roadmap
    content: Rangordna återstående arbete med en tydlig viktad beslutsmodell och identifiera det enda rekommenderade nästa huvudkapitlet
    status: completed
  - id: produce-decision-report
    content: Skapa en fullständig lokal roadmap-auditrapport med rekommenderat nästa kapitel, avgränsning, beroenden, risker och föreslagen planstruktur
    status: completed
isProject: false
---

# Post-2G roadmap audit

**Planstatus:** Auktoritativ read-only auditplan  
**Planversion:** `post-2g-roadmap-audit-v1`  
**Låst förväntad startbaseline:** `main @ 632a15955c82b62a17b26f5b87d1c36b0d329ef4`  
**Föregående kapitel:** `Kapitel 2G — PASS och stängt`  
**Output:** `storage/status/post-2g-roadmap-audit.md`

---

## Agentregler

Läs hela planen innan auditen påbörjas.

Detta är en read-only audit. Ingen implementation eller repositoryändring får ske.

Endast todo-status i YAML-frontmatter får uppdateras lokalt:

```text
pending → in_progress → completed
```

Planens krav, prioriteringsmodell och outputstruktur är read-only.

Vid avvikelse mellan förväntad baseline och faktisk `origin/main`:

1. lista samtliga nya commits,
2. analysera om de ändrar produkt-, eval-, drift- eller roadmap-sanningen,
3. använd den faktiska senaste `origin/main` som auditbaseline endast om ändringarna är begripliga och gröna,
4. stoppa vid oklar eller riskfylld drift.

---

## Absoluta begränsningar

Utför inte:

- kodändringar,
- dokumentationsändringar,
- todoändringar utöver status,
- commit,
- push,
- PR,
- merge,
- workflow-dispatch,
- deployment,
- migration,
- databaswrite,
- Gmail-anrop,
- OpenAI- eller andra LLM-provideranrop,
- externa action writes,
- environment- eller secretändringar,
- fixtureuppdatering,
- golden dataset-ändring,
- ny planfil för implementation.

Auditen får läsa repositoryt, Git-historik, lokala dokument och befintliga CI-metadata via utvecklarverktygen. Den får inte köra externa evalflöden.

Rör inte lokal WIP eller `storage/` utöver auditrapporten.

---

# 1. Produktprinciper som auditen ska använda

Bedöm roadmapen mot följande produktvision.

## 1.1 Krowolf arbetar – användaren leder

Produkten ska inte primärt kännas som ett system där användaren loggar in för att utföra administration. Den ska kännas som en digital medarbetare som redan har:

1. observerat,
2. förstått,
3. prioriterat,
4. utfört det den har mandat att utföra,
5. förberett beslut där mänskligt godkännande behövs.

När användaren öppnar produkten ska arbetsdagen vara förberedd.

## 1.2 En digital medarbetare som får fler roller

Roadmapen ska förstås som samma digitala medarbetare som utvecklar fler kompetenser:

| Fas | Kompetens |
|---|---|
| Receptionisten | Kommunicera |
| Kontoret | Administrera |
| Projektledaren | Samordna |
| Företagschefen | Optimera |

Auditen ska bedöma vilken kompetens som faktiskt är implementerad, testad, kundsynlig och driftbar.

## 1.3 Fyra autonominivåer

Produkten ska på sikt stödja kundstyrd självständighet:

1. `informera`
2. `föreslå`
3. `utföra efter godkännande`
4. `utföra automatiskt`

Auditen ska verifiera vilka nivåer som faktiskt stöds idag per arbetsflöde och om kontrollmodellen är begriplig för kund och operatör.

---

# 2. Verifiera Git- och CI-baseline

Kör read-only:

```bash
git fetch origin
git rev-parse origin/main
git log --oneline --decorate -20 origin/main
git status --short
```

Förväntad baseline:

```text
632a15955c82b62a17b26f5b87d1c36b0d329ef4
```

Verifiera att Kapitel 2G:s slutstatus fortfarande är sann:

- closure marker finns,
- Release Gate-run `30170263775` är dokumenterad eller spårbar,
- `2g-final-evidence-632a15955c82b62a17b26f5b87d1c36b0d329ef4` är auktoritativt,
- `2g_final_report.json` ska enligt repositorysanningen ha `overall_status=passed`,
- todos A–E är completed,
- inga senare commits har brutit 2G-kontrakten.

Kör inga nya externa workflows.

---

# 3. Inventera auktoritativa dokument

Identifiera och läs minst:

```text
docs/00-master-plan.md
docs/01-current-truth.md
docs/02-first-customer-plan.md
docs/06-backlog.md
docs/07-decisions.md
docs/08-runbook.md
docs/09-testing-and-release.md
docs/10f-live-eval-testbot.md
docs/10g-generated-scenario-eval.md
docs/plans/2g-execution-plan.md
```

Om namn eller sökvägar skiljer sig:

- hitta den faktiska motsvarigheten,
- dokumentera skillnaden,
- använd inte en antagen fil som inte finns.

Sök även efter:

```text
first customer
pilot
receptionist
office
kontoret
lead
support
invoice
approval
automation
autonomy
operator
customer portal
scheduler
Gmail
Visma
Sheets
Monday
calendar
memory
usage
pricing
deployment
backup
restore
incident
onboarding
service profile
2H
3A
next phase
not started
partial
blocked
```

---

# 4. Verifiera faktisk implementation

Auditen ska inte lita enbart på dokumentation.

Inspektera relevant kod och tester för att fastställa faktisk status för minst följande områden.

## 4.1 Fas 1 – Receptionisten

- Gmail/intake
- klassificering
- entity extraction
- service profiles
- lead/support/invoice-flöden
- decisioning och policy authorization
- approval-first
- kundsvar eller svarsutkast
- routing och human handoff
- notifieringar
- Visma-, Sheets- och Monday-kontrakt
- scheduler och idempotens
- tenantisolering
- audit och telemetri

## 4.2 Operatörens arbetsyta

- overview
- customers
- needs-help
- operations/actions
- incidents
- usage
- system status
- rollmodell
- felhantering
- backup/restore-signaler
- deployment readiness
- testdatahantering

## 4.3 Kundens arbetsyta

- kundportal eller avsaknad av kundportal
- approvals
- konfiguration
- integrationsstatus
- automationnivåer
- användning och transparens
- onboarding
- kundsynlig kontroll

## 4.4 Första kundens drift

- tenant setup
- OAuth/integration onboarding
- service profile setup
- kvalitets- och acceptance-test
- backup
- restore rehearsal
- health monitoring
- incidenthantering
- support och felsökning
- releaseprocess
- data retention
- kundoffboarding
- operatörens dagliga arbetsflöde

## 4.5 Fas 2 – Kontoret

Verifiera vad som faktiskt finns, är delvis byggt eller endast planerat inom:

- Lead
- Support
- Ekonomi
- administrativ uppföljning
- påminnelser
- offert- och fakturaunderlag
- systemintegrationer
- kundminne, regler och minnespunkter
- automatiska arbetsflöden
- kundstyrd autonomi

## 4.6 Eval och kvalitet

Verifiera att 2E–2G ger:

- canonical gold dataset
- Live Gmail-bevis
- Live LLM-bevis
- offline replay
- final evidence
- deterministisk generator
- mutationsmotor
- PR/main-batcher
- blocking quality gates
- failure corpus
- closure artifacts

Bedöm vilken produkt- och driftlucka som nu är större än testluckan.

---

# 5. Klassificera varje område

Använd exakt följande statusmodell:

| Status | Definition |
|---|---|
| `verified_complete` | Implementerat, testat, dokumenterat och användbart |
| `implemented_unverified` | Kod finns men full verifiering eller driftbevis saknas |
| `partial` | Delar finns men användarresan eller kontraktet är ofullständigt |
| `planned_only` | Dokumenterat men ingen verklig implementation |
| `missing` | Varken tillräcklig plan eller implementation |
| `contradictory` | Kod, tester och dokumentation säger olika saker |
| `deferred_by_decision` | Medvetet uppskjutet genom låst beslut |
| `not_needed_now` | Ger inte tillräckligt värde i nästa produktsteg |

Varje klassificering ska stödjas med:

- filer,
- symboler/endpoints,
- tester,
- dokumentationsreferenser,
- commit eller beslut när relevant.

---

# 6. Kartlägg första kundens användarresa

Beskriv den faktiska end-to-end-resan från avtal till daglig användning.

Minst:

1. kund skapas,
2. integrationskonton ansluts,
3. tjänster och regler konfigureras,
4. historik eller profil etableras,
5. första mejl tas emot,
6. systemet klassificerar och förbereder arbete,
7. kund eller operatör granskar,
8. godkänd åtgärd utförs,
9. resultat visas och följs upp,
10. fel eller osäkerhet hanteras,
11. användning och värde mäts,
12. kunden ändrar automationnivå,
13. systemet uppdateras och supporteras.

För varje steg ska rapporten ange:

- vem gör arbetet,
- vilken UI eller CLI som används,
- om momentet är manuellt,
- om det kräver kodkunskap,
- kundens synlighet,
- operatörens synlighet,
- risk,
- nuvarande status,
- största kvarvarande friktion.

Skapa en tydlig gap-karta.

---

# 7. Kartlägg användarens morgonupplevelse

Bedöm konkret om produkten idag uppfyller:

> När användaren öppnar produkten är arbetsdagen redan förberedd.

Kartlägg vad kunden kan eller borde se:

- nytt sedan sist,
- prioriterade leads,
- kundfrågor som behöver beslut,
- fakturor eller ekonomiarbete,
- utförda automatiska uppgifter,
- väntande approvals,
- risker och avvikelser,
- rekommenderade nästa steg,
- tydligt värde och sparad tid.

Klassificera varje del som:

- synlig idag,
- tillgänglig endast för operatör,
- finns i backend men saknar kundyta,
- saknas helt,
- bör inte byggas ännu.

---

# 8. Kartlägg autonominivåer

Skapa en matris per befintligt arbetsflöde:

| Arbetsflöde | Informera | Föreslå | Efter godkännande | Automatiskt | Kundkonfigurerbart |
|---|---:|---:|---:|---:|---:|

Minst:

- lead intake
- första kundsvar
- support routing
- invoice routing
- offertutkast
- Sheets/Monday-export
- Visma-underlag
- påminnelser
- kalender-/uppföljningsförslag
- interna notifieringar

Skilj mellan:

- tekniskt möjligt,
- faktiskt implementerat,
- säkert verifierat,
- exponerat i UI,
- begripligt för kunden.

---

# 9. Identifiera roadmap-gap

Gruppera gap i följande kategorier:

## Kundvärde

Vad gör att kunden faktiskt sparar tid eller får bättre kontroll?

## Produktbarhet

Vad saknas för att en kund ska kunna använda produkten utan utvecklarhjälp?

## Driftbarhet

Vad saknas för att en operatör ska kunna hantera många kunder utan kodinspektion?

## Säkerhet och kontroll

Vad saknas för att kunden tryggt ska kunna öka autonomin?

## Onboarding

Vad saknas från avtal till fungerande tenant?

## Synlighet och UX

Vad finns i backend men märks inte för kunden?

## Integrationer

Vilka befintliga integrationer är verkligt produktklara respektive endast tekniska kontrakt?

## Affär

Vad behöver finnas för demo, försäljning, paketering, prissättning och mätbart kundvärde?

---

# 10. Prioriteringsmodell

Poängsätt varje realistiskt nästa huvudinitiativ från 1 till 5.

## Viktning

| Kriterium | Vikt |
|---|---:|
| Värde för första betalande kund | 25 % |
| Minskar manuellt operatörsarbete | 15 % |
| Gör befintlig backend synlig/användbar | 15 % |
| Säkerhet och kundkontroll | 15 % |
| Beroenden redan klara | 10 % |
| Låg genomföranderisk | 10 % |
| Undviker framtida ombyggnad | 5 % |
| Sälj- och demovärde | 5 % |

Beräkna viktad totalpoäng av 5.

## Minst följande kandidater ska bedömas

- första-kund-onboarding och konfigurationsflöde,
- kundportal med approvals och kontroll,
- kundens morgonöversikt/digital medarbetare,
- operatörspanelens kvarvarande driftåtgärder,
- Fas 2 Lead,
- Fas 2 Support,
- Fas 2 Ekonomi,
- kundminne/profil/regler/minnespunkter,
- automationnivåer och mandat per arbetsflöde,
- produktionsdeploy och första externa pilot,
- integration completion/polish,
- användnings- och värdemätning,
- backup/restore/incident closure,
- försäljnings- och onboardingverktyg.

Lägg endast till andra kandidater om repositoryt visar ett verkligt behov.

---

# 11. Välj exakt ett rekommenderat nästa huvudkapitel

Rapporten ska rekommendera ett enda nästa huvudkapitel.

Rekommendationen ska innehålla:

- namn,
- vilket konkret problem som löses,
- varför det kommer före alternativen,
- kundsynligt slutresultat,
- operatörssynligt slutresultat,
- beroenden,
- vad som uttryckligen inte ingår,
- största risk,
- förväntad storlek,
- föreslagen uppdelning i 3–6 Cursor-todos,
- förslag på branch- och PR-struktur,
- stop-gates,
- definition of done.

Ange även:

- andra plats,
- tredje plats,
- varför de väntar.

Skapa inte implementationsplanen i denna audit. Lämna endast det beslutsunderlag som krävs för att nästa plan ska kunna skrivas korrekt.

---

# 12. Kontrollera om roadmapen bör ändras

Bedöm om repositoryts nuvarande roadmap fortfarande är korrekt efter 2G.

Rapportera:

- vilka delar som ska behållas,
- vilka statusar som är inaktuella,
- vilka planerade funktioner som bör flyttas,
- vilka funktioner som bör tas bort eller skjutas upp,
- om fasgränserna Receptionisten/Kontoret/Projektledaren/Företagschefen fortfarande är praktiska,
- om nästa kapitel främst är produktisering av Fas 1 eller start av Fas 2.

Ingen dokumentation får ändras i denna audit.

---

# 13. Riskanalys

Analysera minst:

- att börja Fas 2 innan Fas 1 är produktklar,
- att bygga mer backend utan kundsynlig nytta,
- att bygga kundportal innan onboarding och kontrollmodell är tydlig,
- att produktionssätta innan operatörsdrift är tillräcklig,
- att överbygga operatörspanelen före riktiga kundsignaler,
- att lägga till fler integrationer innan befintliga flöden är produktklara,
- att kundminne införs för tidigt eller för autonomt,
- att autonomy UI inte matchar backendens säkerhetsmodell,
- att roadmapdokument och faktisk kod fortsätter divergera.

För varje risk:

- sannolikhet,
- konsekvens,
- evidens,
- mitigation,
- stop-gate.

---

# 14. Outputformat

Skapa:

```text
storage/status/post-2g-roadmap-audit.md
```

Rapporten ska ha följande struktur:

```markdown
# Post-2G roadmap audit

## Executive decision

## Verified baseline

## Authoritative sources

## Current product truth

## First-customer journey

## Morning experience gap

## Autonomy matrix

## Product and operations gaps

## Roadmap contradictions

## Prioritization matrix

## Recommended next chapter

## Second and third choices

## Proposed todo structure

## Dependencies and exclusions

## Risk register

## GO/NO-GO decisions

## Evidence index
```

## Evidencekrav

Varje viktig slutsats ska referera:

- fil och rad eller symbol,
- relevant test,
- endpoint eller modul,
- dokument och sektion,
- beslut eller commit när relevant.

Undvik lösa bedömningar utan repositoryevidens.

---

# 15. GO/NO-GO-matris

Rapportera minst:

| Beslut | Status |
|---|---|
| Fas 1 är tekniskt verifierad | GO/NO-GO |
| Fas 1 är produktklar för första betalande kund | GO/NO-GO |
| Första externa pilot kan startas nu | GO/NO-GO |
| Kundportal bör vara nästa kapitel | GO/NO-GO |
| Onboarding bör vara nästa kapitel | GO/NO-GO |
| Autonomikontroll bör vara nästa kapitel | GO/NO-GO |
| Fas 2 Lead bör startas nu | GO/NO-GO |
| Fas 2 Support bör startas nu | GO/NO-GO |
| Fas 2 Ekonomi bör startas nu | GO/NO-GO |
| Kundminne bör startas nu | GO/NO-GO |
| Mer evalarbete behövs före produktarbete | GO/NO-GO |
| Nästa kompletta Cursor-plan kan skrivas | GO/NO-GO |

---

# 16. Definition of done

Auditen är klar när:

1. baseline är verifierad,
2. kod och dokumentation är jämförda,
3. första kundens resa är kartlagd,
4. morgonupplevelsen är bedömd,
5. autonomimodellen är kartlagd,
6. roadmap-gap är evidensbaserade,
7. kandidater är viktat poängsatta,
8. exakt ett nästa huvudkapitel är rekommenderat,
9. två alternativ är rangordnade,
10. föreslagen todo-struktur finns,
11. risker och stop-gates finns,
12. GO/NO-GO-matrisen är komplett,
13. ingen repositoryändring har gjorts,
14. auditrapporten är sparad lokalt,
15. samtliga todos är `completed`.

---

## Startinstruktion

> Läs `docs/plans/post-2g-roadmap-audit.md` i sin helhet. Behandla den som auktoritativ och read-only; endast todo-status får uppdateras. Genomför hela read-only-auditen mot aktuell `origin/main`, repositoryts kod, tester och auktoritativa dokument. Gör inga kod-, dokumentations-, Git- eller externa ändringar. Skapa `storage/status/post-2g-roadmap-audit.md` med full evidens, prioriteringsmatris och exakt ett rekommenderat nästa huvudkapitel. Återkom först när auditen är komplett eller när ett uttryckligt stop-villkor aktiveras.
