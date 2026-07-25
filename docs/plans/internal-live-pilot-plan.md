---
name: Intern aktivering av AI-receptionisten
overview: "Aktivera AI-receptionisten i en kontrollerad intern pilotmiljö för verklig daglig användning, samla strukturerad kvalitets- och driftfeedback och förbättra produkten utifrån faktiska inkommande mejl — med approval-first, strikt tenantisolering, begränsad mailbox-scope, inga automatiska externa writes och obligatoriskt operatörsstopp före liveaktivering."
todos:
  - id: pilot-a-readiness-audit
    content: Verifiera aktuell main-baseline, intern pilottenant, Gmail-konfiguration, approval-flöde, scheduler, integrationsstatus, backup/restore och operatörssynlighet
    status: completed
  - id: pilot-b-controlled-activation
    content: Förbered och aktivera boten i intern pilottenant med begränsad mailbox-scope, approval-first, no-auto-send och tydliga stopp- och rollbackregler
    status: in_progress
  - id: pilot-c-daily-soak
    content: Kör kontrollerad daglig användning, samla fel, kvalitetsmått, operatörsfriktion och användarfeedback utan att ändra gold dataset automatiskt
    status: pending
  - id: pilot-d-improvement-loop
    content: Gruppera verkliga fel, prioritera produktfixar, implementera säkra förbättringar och verifiera dem mot 2E–2G samt pilotregressioner
    status: pending
  - id: pilot-e-pilot-closure
    content: Sammanställ pilotresultat, dokumentera kvarvarande risker och fatta beslut om fortsatt intern drift, första kundpilot eller ytterligare förbättringscykel
    status: pending
isProject: true
---

# Intern aktivering av AI-receptionisten

**Planstatus:** Auktoritativ exekveringsplan  
**Planversion:** `internal-live-pilot-v1`  
**Syfte:** Aktivera boten internt för verklig användning och produktförbättring  
**Normalläge:** Approval-first, no-auto-send, no-auto-write, strikt tenantisolering  
**Särskilt stopp:** All liveaktivering kräver uttryckligt operatörsgodkännande

---

## Agentregler

Läs hela planen innan någon ändring görs.

Planens tekniska krav, scope, säkerhetsregler, kvalitetsgates och stop-villkor är read-only. Endast todo-status får ändras:

```text
pending → in_progress → completed
```

Agenten får arbeta autonomt genom audit, implementation, riktade tester, commit, PR, CI, squash-merge och post-merge-verifiering när samtliga gates passerar.

Agenten måste stoppa före:

- riktiga Gmail reads/sends/mutations,
- OAuth- eller secretändring,
- scheduleraktivering mot verklig mailbox,
- externa integration writes,
- Live LLM-körning,
- deployment eller produktionsaktivering,
- användning av verklig kunddata.

Lokal exekveringsrapport:

```text
storage/status/internal-live-pilot-execution-report.md
```

Lokal pilotlogg:

```text
storage/status/internal-live-pilot-soak-report.md
```

Dessa ska inte committas.

---

# 1. Mål

Planen ska göra det möjligt att använda AI-receptionisten i den egna verksamheten eller en annan uttryckligen godkänd intern testmiljö.

Boten ska:

1. läsa endast godkända inkommande mejl,
2. klassificera och extrahera information,
3. föreslå routing och nästa steg,
4. skapa svars- eller åtgärdsutkast,
5. kräva mänskligt godkännande före extern åtgärd,
6. visa vad som behöver operatörens hjälp,
7. samla strukturerad feedback,
8. förbättras genom vanliga produktfixar och nya regressionstester.

Det primära målet är inte att bevisa att testharnessen fungerar. Det är att upptäcka:

- felaktiga klassificeringar,
- dåliga sammanfattningar,
- irrelevanta följdfrågor,
- missad information,
- otydlig routing,
- svaga svarsutkast,
- operatörsfriktion,
- integrationsproblem,
- driftproblem,
- funktioner som saknas i verklig användning.

---

# 2. Avgränsning

## Ingår

- intern pilottenant,
- en godkänd Gmail-mailbox eller label,
- verkliga eller manuellt inskickade interna testmejl,
- approval-first,
- operatörsgranskning,
- klassificering,
- entity extraction,
- lead/support/invoice/unknown,
- service profiles,
- svarsutkast,
- routing,
- needs-help,
- incidenter,
- audit och telemetri,
- daglig soak,
- feedback- och förbättringscykel.

## Ingår inte

- automatisk extern kundkommunikation,
- automatiska Gmail-svar,
- automatiska Visma-, Sheets- eller Monday-writes,
- nya kundfunktioner,
- full kundportal,
- Fas 2 Lead/Support/Ekonomi,
- kundminne eller RAG,
- masskörning via Live LLM,
- automatisk ändring av gold dataset,
- produktion hos extern betalande kund.

---

# 3. Säkerhetsmodell

## 3.1 Tillåten autonomi

Under intern pilot:

| Nivå | Tillåten |
|---|---|
| Informera | Ja |
| Föreslå | Ja |
| Utföra efter godkännande | Endast där befintligt säkert kontrakt redan finns |
| Utföra automatiskt | Nej |

## 3.2 Externa writes

Standard:

```text
external_action_writes = 0
automatic_gmail_replies = 0
automatic_approval_resolution = 0
```

Boten får förbereda:

- svar,
- routing,
- underlag,
- approval.

Den får inte själv skicka eller skriva externt utan separat, uttryckligt operatörsgodkännande.

## 3.3 Mailbox-scope

Piloten ska begränsas med minst ett av följande:

- dedikerad intern testmailbox,
- dedikerad Gmail-label,
- explicit sender-allowlist,
- explicit recipient-allowlist,
- fast pilottenant,
- begränsat tidsfönster.

Full inbox-scan utan scope är förbjuden i första aktiveringen.

## 3.4 Rollback

Det ska alltid vara möjligt att:

- pausa scheduler,
- inaktivera tenantautomation,
- stoppa Gmail-sync,
- återkalla approval,
- markera incident,
- återgå till manuellt läge,
- bevara auditdata.

---

# 4. Låsta kvalitetsbaselines

Följande ska förbli gröna under hela piloten:

- 2E canonical gold dataset,
- 2F Live Gmail/LLM evidence,
- 2G generator, mutation och batch quality gates,
- approval-first,
- tenantisolering,
- external-write violations = 0,
- canonical regressions = 0,
- injection bypasses = 0.

Ingen produktfix får mergas om den bryter dessa baselines.

---

# A. Readiness-audit

**Todo:** `pilot-a-readiness-audit`

## Mål

Fastställ exakt vilken intern tenant, mailbox, scheduler- och approvalkonfiguration som ska användas.

## Audit

Verifiera minst:

- aktuell `origin/main`,
- senaste gröna Release Gate,
- intern pilottenant,
- tenantstatus,
- Gmail OAuth/status,
- mailbox/label-scope,
- service profiles,
- automationflags,
- schedulerstatus,
- approval endpoints,
- operatörsroller,
- cockpit/overview/needs-help,
- incidentflöde,
- backup freshness,
- restore rehearsal,
- build/deploy metadata,
- audit/telemetri,
- befintliga runbooks.

## Output

Skapa:

```text
storage/status/internal-live-pilot-readiness.md
```

Rapporten ska ange:

- vald pilottenant,
- vald mailbox/label,
- vilka jobbtyper som ingår,
- vilka integrationer som är read-only,
- vilka externa writes som är blockerade,
- vilka manuella steg som krävs,
- readiness PASS/FAIL per kontroll,
- blockerare,
- rollbackkommandon,
- rekommenderad pilotperiod.

## Gate

Fortsätt endast om:

- pilottenant är isolerad,
- mailbox-scope är begränsat,
- Gmail readiness är grön,
- scheduler kan pausas,
- approval-first är aktiv,
- external writes är avstängda,
- operatören kan se och hantera fel,
- backup/restore-status är godtagbar,
- ingen migration krävs.

Ingen tom commit eller PR.

---

# B. Kontrollerad aktivering

**Todo:** `pilot-b-controlled-activation`

Todo B har två faser.

## B1. Autonom förberedelse

Agenten får:

- skapa eller förbättra readiness-CLI,
- skapa pilotconfigvalidering,
- lägga till no-auto-send/no-auto-write-gates,
- skapa rollback- och pause-script,
- förbättra operatörssynlighet,
- skapa hermetiska tester,
- uppdatera runbook,
- skapa PR och mergea när CI är grön.

## Obligatoriska aktiveringsgates

Kräv:

- exakt en pilottenant,
- exakt mailbox/label-scope,
- max antal processade mejl per körning,
- scheduler initialt manual/paused,
- automatic replies = false,
- external writes = false,
- approval-first = true,
- unknown/manual review fail-closed,
- no active Live Eval-runs,
- logging och audit aktivt,
- rollback testad.

## B1-tester

Minst:

- fel tenant nekas,
- fel label/scope nekas,
- auto-send flagga nekas,
- external write flagga nekas,
- max-email-budget verifieras,
- scheduler pause/resume fungerar,
- rollback lämnar systemet paused,
- no-network där testet är hermetiskt,
- redaction.

## B1-gate

- riktade tester PASS,
- PR Release Gate PASS,
- post-merge Release Gate PASS,
- ingen extern aktivitet,
- readinessrapport PASS.

## B2. Obligatoriskt operatörsstopp

Agenten ska stoppa och rapportera:

```text
OPERATOR ACTION REQUIRED — Aktivera intern AI-receptionist
```

Rapporten ska innehålla:

- aktuell main-SHA,
- pilottenant,
- mailbox/label,
- schedulerläge,
- maximalt antal tillåtna mejl,
- vilka jobbtyper som ingår,
- vilka externa writes som är blockerade,
- exakt aktiveringskommando,
- exakt pauskommando,
- exakt rollbackkommando,
- vad operatören ska kontrollera i UI,
- vilken evidens som ska sparas.

Ingen liveaktivering före uttryckligt godkännande.

## B3. Operatörsauktoriserad aktivering

Efter uttryckligt godkännande:

1. verifiera readiness igen,
2. aktivera endast valt scope,
3. processa en liten första batch,
4. verifiera cockpit/jobs/approvals,
5. kontrollera external writes = 0,
6. pausa vid avvikelse,
7. registrera resultat i pilotloggen.

Rekommenderad första batch:

```text
3–5 mejl
```

Första batchen ska representera:

- ett tydligt lead,
- en kundfråga/support,
- ett oklart eller unsupported ärende,
- eventuellt ett fakturarelaterat mejl om det ingår i pilotens scope.

---

# C. Daglig soak och feedback

**Todo:** `pilot-c-daily-soak`

## Mål

Köra boten tillräckligt länge för att hitta verkliga produktfel och operatörsfriktion.

## Rekommenderad pilotperiod

```text
5–10 arbetsdagar
```

eller tills minsta evidensmängd nåtts.

## Rekommenderad volym

- minst 30 behandlade mejl,
- mål 50–100 mejl,
- flera jobbtyper,
- både enkla och otydliga ärenden.

Ingen massgenerering. Volymen ska komma från verklig intern användning eller uttryckligt godkända testmejl.

## Daglig rutin

Operatören ska varje dag:

1. kontrollera scheduler och integrationsstatus,
2. granska nya jobs,
3. kontrollera klassificering,
4. kontrollera extraherade fält,
5. granska svarsutkast,
6. godkänna/avslå endast enligt pilotscope,
7. markera fel och friktion,
8. kontrollera needs-help/incidents,
9. verifiera external writes,
10. registrera kort daglig rapport.

## Feedbackklassificering

Varje finding ska klassificeras som:

- `classification_error`
- `service_profile_error`
- `entity_extraction_error`
- `summary_quality`
- `missing_question`
- `irrelevant_question`
- `routing_error`
- `decision_policy_issue`
- `approval_friction`
- `response_quality`
- `operator_ui_friction`
- `integration_issue`
- `scheduler_issue`
- `duplicate_or_idempotency`
- `unknown_handling`
- `missing_product_capability`

## Pilotmått

Minst:

- antal behandlade mejl,
- korrekt klassificering,
- korrekt service profile,
- kritiska entity-fel,
- routingfel,
- manual review-rate,
- approval-rate,
- avslag,
- externa writes,
- app replies,
- duplicate executions,
- incidenter,
- tid per operatörsgranskning,
- antal findings per kategori.

## Stop-gates

Pausa piloten direkt vid:

- cross-tenant finding,
- otillåtet app reply,
- otillåten extern write,
- dubbel execution,
- approval bypass,
- Gmail-scope utanför allowlist,
- återkommande pipelinefel,
- incident som inte kan förstås från UI/runbook,
- PII eller secrets i artifacts/loggar.

---

# D. Förbättringscykel

**Todo:** `pilot-d-improvement-loop`

## Mål

Omvandla pilotfindings till säkra och mätbara produktförbättringar.

## Triage

Gruppera findings efter:

- frekvens,
- kundpåverkan,
- säkerhetsrisk,
- operatörstid,
- om problemet redan täcks av test,
- om problemet är produktkod, config, UX eller tränings-/regeldata.

## Prioritering

Fixordning:

1. säkerhet och tenantisolering,
2. approval/idempotens,
3. felaktig klassificering/routing,
4. hallucination eller felaktigt svar,
5. kritisk entity extraction,
6. operatörsblockerande UX,
7. återkommande mindre kvalitetsproblem,
8. nya funktioner.

Nya funktioner får inte implementeras i denna plan om de tillhör Fas 2 eller kräver större arkitekturändring. De dokumenteras som framtida roadmap-item.

## Fixkontrakt

För varje fix:

1. skapa reproducerbart testfall,
2. lägg till pilotregression,
3. kör relevanta 2E–2G-tester,
4. implementera minsta produktfix,
5. verifiera inga canonical regressions,
6. skapa separat PR,
7. bevaka CI,
8. mergea först när alla gates är gröna.

Agenten måste stoppa om en fix kräver:

- sänkt quality gate,
- ändrat gold dataset utan review,
- ny beslutsmotorarkitektur,
- ny integration,
- kundminne/RAG,
- Fas 2-funktionalitet.

## Pilotregressioner

Pilotfall får läggas till som nya granskade regressionstester, men:

- får inte skriva över canonical gold,
- ska ha syntetiserad/redigerad data,
- ska ha provenance,
- ska dokumentera vilken finding de skyddar mot.

---

# E. Pilot closure

**Todo:** `pilot-e-pilot-closure`

## Mål

Bedöma om boten är stabil nog för fortsatt intern drift och nästa steg mot första betalande kund.

## Slutstatusar

```text
CONTINUE_INTERNAL
READY_FOR_CUSTOMER_PILOT
NEEDS_IMPROVEMENT
STOPPED_FOR_SAFETY
```

## READY_FOR_CUSTOMER_PILOT kräver

- minsta pilotvolym uppnådd,
- inga öppna kritiska findings,
- external writes = 0 utanför tillåten budget,
- app replies = 0 om de inte uttryckligen auktoriserats,
- approval-first = 100 %,
- duplicate executions = 0,
- inga cross-tenant findings,
- klassificering och routing håller definierad nivå,
- operatören kan förstå och hantera fel,
- rollback/pause fungerar,
- backup/restore och driftstatus är godtagbara,
- 2E–2G fortsatt gröna,
- kvarvarande problem är dokumenterade och accepterade.

## Output

Skapa lokalt:

```text
storage/status/internal-live-pilot-final-report.md
```

Rapporten ska innehålla:

- baseline,
- pilotperiod,
- tenant,
- mailbox-scope,
- antal mejl,
- jobbtypsfördelning,
- metrics,
- findings,
- fixade findings,
- öppna findings,
- incidents,
- external writes,
- app replies,
- approvalresultat,
- operatörstid,
- rollbacktest,
- säkerhetsstatus,
- rekommenderat nästa steg.

## Dokumentation

Uppdatera auktoritativa dokument först när pilotresultatet är känt.

Ingen förtida markör.

Möjliga markörer:

```text
Intern AI-receptionistpilot — PASS och fortsatt intern drift
```

eller:

```text
Intern AI-receptionistpilot — redo för första kundpilot
```

eller:

```text
Intern AI-receptionistpilot — förbättring krävs
```

---

# Branch- och PR-struktur

| Todo | Branch | Leverans |
|---|---|---|
| A | Ingen vid read-only audit | Readinessrapport |
| B1 | `feat/internal-pilot-activation` | Gating, CLI, rollback, runbook |
| B3 | Ingen kod-PR som standard | Operatörsauktoriserad aktivering |
| C | Ingen kod-PR som standard | Soakrapport |
| D | En branch per avgränsad fix | Regression + produktfix |
| E | `docs/internal-pilot-closure` vid behov | Sanningsenlig closure-docs |

Högst två CI-korrigeringscykler per fix-PR.

---

# Definition of done

Planen är avslutad när:

1. intern pilottenant är säkert aktiverad,
2. mailbox-scope är begränsat,
3. approval-first är verifierat,
4. minsta pilotvolym är uppnådd,
5. findings är strukturerat klassificerade,
6. kritiska produktfel är fixade eller blockerar closure,
7. 2E–2G är fortsatt gröna,
8. inga cross-tenant findings finns,
9. inga otillåtna externa writes finns,
10. rollback/pause är verifierat,
11. final pilotrapport är klar,
12. ett evidensbaserat slutbeslut är registrerat.

---

## Startinstruktion

> Läs `docs/plans/internal-live-pilot-plan.md` i sin helhet. Behandla planens tekniska innehåll som auktoritativt och read-only; endast todo-status får uppdateras. Genomför readiness-auditen och den autonoma förberedelsen för intern aktivering. Stoppa obligatoriskt och lämna `OPERATOR ACTION REQUIRED — Aktivera intern AI-receptionist` innan någon riktig Gmail-aktivitet, scheduleraktivering, OAuth-/secretändring eller extern write utförs. Efter uttryckligt godkännande ska piloten aktiveras med begränsat mailbox-scope, approval-first och external writes avstängda. Uppdatera `storage/status/internal-live-pilot-execution-report.md` och `storage/status/internal-live-pilot-soak-report.md`.
