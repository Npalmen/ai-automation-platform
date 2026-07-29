---
name: Produktionspilot P1 observe-only
overview: Aktivera verklig inkommande trafik för exakt en pilottenant i observe-only-läge med klassificering, extraction, manual review och shadow customer observations, men utan Gmail-svar eller andra externa writes.
todos:
  - id: p1-a-runtime-baseline
    content: Verifiera release-SHA, pilottenant, backup, rollback, kill switches och P0-evidens
    status: completed
  - id: p1-b-activation
    content: Aktivera Gmail intake och observe/manual-review för exakt en pilottenant
    status: completed
  - id: p1-c-observability
    content: Verifiera operatörsvy, metrics, daglig rapport och incidentunderlag
    status: completed
  - id: p1-d-live-observe
    content: Kör P1 observe-only med verklig pilottrafik och noll externa writes
    status: completed
  - id: p1-e-evaluation
    content: Utvärdera kvalitet, köer, fel, shadow observations, tenant isolation och rollbackberedskap
    status: completed
  - id: p1-f-decision
    content: Registrera P1-resultat och stoppa före P2 approval-baserade Gmail-svar
    status: completed
isProject: true
---

# Produktionspilot P1 — Observe-only pilottrafik

## 1. Operatörsbeslut

P0 är godkänd och releasebaselinen är:

- implementation: PR #108
- release SHA: `af99856`
- post-merge Release Gate: `30483315068` PASS
- Regression Main: `30483309218` PASS
- P0 qualification: `30484065150` PASS
- release status: `PRODUCTION_PILOT_RELEASE_READY`
- pilottenant: `TENANT_PRODUCTION_PILOT_01`

P1 är härmed auktoriserad för exakt en pilottenant.

P1 omfattar endast:

```text
verklig Gmail intake
→ normalisering
→ extraction
→ classification
→ observe/manual review
→ shadow customer observations
→ operatörsövervakning
```

P1 får inte skapa Gmail-svar eller andra externa writes.

## 2. Scope

### Tillåtet

- exakt en pilottenant
- exakt en pilotmailbox
- verklig inkommande pilottrafik
- Gmail intake
- message/thread correlation
- classification och extraction
- observe, hold, manual review och needs-help
- incidents, audit, usage och metrics
- customer shadow observations
- shadow match proposals
- paus och återställning

### Förbjudet

- Gmail replies
- approvals som kan leda till extern write
- automatic Gmail
- Sheets, Monday och Visma
- bokningar, priser, offerter, avtal eller tekniska garantier
- automatic verify, customer link, merge eller duplicate resolution
- fler tenants
- P2- eller P3-aktivering

## 3. Aktiv P1-konfiguration

```text
Gmail intake: ON
Observe: ON
Classification/extraction: ON
Manual review: ON
Needs-help/incidents: ON
Customer shadow intake: ON
Customer shadow matching: ON
Customer shadow promotion: OFF
Approvals for external write: OFF
Gmail reply: OFF
Automatic Gmail: OFF
Sheets: OFF
Monday: OFF
Visma: OFF
Automatic verify: OFF
Automatic link: OFF
Automatic merge: OFF
```

Scheduler får endast aktiveras i den omfattning som krävs för intake och observe-processing. Alla action workers som kan skriva externt ska vara blockerade av policy och kill switch.

## 4. Aktiveringsordning

```text
verify baseline
→ snapshot config
→ verify kill switches
→ verify write budget 0
→ enable Gmail intake
→ enable observe/manual review
→ enable shadow intake/matching
→ verify active config
→ process synthetic preflight
→ open pilot mailbox for real inbound
```

Ingen faktisk pilottrafik får släppas igenom innan synthetic preflight i P1-konfiguration PASS.

## 5. Pre-activation gates

Samtliga ska vara PASS:

- runtime SHA matchar release manifest
- P0 qualification finns
- senaste Regression Main och Release Gate PASS
- pilottenant är exakt `TENANT_PRODUCTION_PILOT_01`
- endast en pilottenant är aktiv
- pilotmailbox OAuth är giltig
- backup reference och rollback target finns
- config snapshot och hash finns
- scheduler state är känd
- Gmail reply kill switch är verifierad
- external write budget = 0
- shadow promotion = OFF
- automatic verify/link/merge = OFF
- Sheets/Monday/Visma = OFF
- operator login fungerar
- daily report fungerar
- incident runbook är tillgänglig
- redaction är verifierad

Failure i någon gate stoppar P1-aktivering.

## 6. Syntetisk P1-preflight

Kör före verklig pilottrafik:

- högst 2 syntetiska inbound messages
- 0 Gmail replies
- 0 external writes
- minst ett tydligt lead/inquiry
- minst ett unknown eller hold-fall
- classification och extraction observeras
- manual review/hold observeras
- shadow observation skapas
- inga verified facts, customer links eller merges skapas
- audit och metrics uppdateras
- tenant isolation verifieras

Preflight-data ska vara tydligt syntetisk och får inte blandas med verkliga pilotärenden.

## 7. Pilotperiod

P1 ska köras tills båda följande är uppfyllda:

1. minst 3 hela driftdagar, och
2. minst 25 verkliga inbound messages.

Om mailboxvolymen är för låg får perioden förlängas uttryckligen. Ingen automatisk tidsbaserad övergång till P2 får finnas.

## 8. Daglig operatörskontroll

Operatören ska minst en gång per arbetsdag kontrollera:

- inbound, processed och unprocessed messages
- duplicate suppressions
- classification distribution
- manual review och needs-help
- extraction failures och low-confidence cases
- shadow observations, ambiguous matches och conflicts
- customer promotions
- automatic verified facts, links och merges
- external writes och cross-tenant findings
- scheduler state, active flags och deploy SHA
- incidents

Skapa lokal eller intern rapport:

```text
storage/status/production-pilot-p1-daily-YYYY-MM-DD.md
```

Rapporterna får inte committas.

## 9. Ground-truth review

För varje pilotmessage ska operatören kunna märka:

- classification correct / incorrect
- extraction acceptable / needs correction
- routing correct / incorrect
- shadow observation acceptable / incorrect
- match proposal acceptable / ambiguous / incorrect
- incident required / not required

Ground truth får lagras som operator audit eller separat pilot review-record enligt befintlig arkitektur. Den får inte automatiskt ändra produktregler under pågående P1.

## 10. P1 acceptance criteria

P1 kan godkännas endast om:

- message loss = 0 enligt tillgänglig korrelation
- duplicate jobs = 0
- Gmail replies = 0
- external writes = 0
- unauthorized adapter invocations = 0
- cross-tenant findings = 0
- automatic verified facts = 0
- automatic customer links = 0
- automatic merges = 0
- shadow provenance är komplett
- manual review fungerar
- operatorn kan förstå routingbesluten
- incidents är spårbara
- config och release SHA är spårbara
- kill switches och pause/restore fungerar
- continuous regression förblir grön
- inga säkerhetskritiska fel är öppna

Kvalitetsmått ska redovisas som faktisk baseline. Trösklar får inte hittas på efter körningen.

## 11. Omedelbara stoppvillkor

Pausa pilottenanten omedelbart vid:

- någon Gmail reply
- någon Sheets-, Monday- eller Visma-write
- cross-tenant finding
- fel tenant eller mailbox
- automatic verified fact, customer link eller merge
- secret/OAuth-läcka
- message loss
- okontrollerad duplicate creation
- runtime SHA avviker från release manifest
- kill switch fungerar inte

Efter stopp:

```text
pause scheduler/tenant
→ disable intake
→ verify no pending external actions
→ snapshot incident state
→ restore baseline if required
→ verify config hash
→ create incident report
```

Ingen automatisk återstart.

## 12. Tillåtna korrigeringar under P1

Tillåtet efter tydligt felbevis:

- observability- eller redaction-fix
- operatörsrapport-fix
- fail-closed bugfix
- classification/extraction-fix som inte breddar actions
- tenant isolation-fix
- idempotency-fix
- queue/state-fix

Nytt operatörsbeslut krävs för:

- nya actions
- Gmail reply eller approvals
- automatic Gmail
- ändrade write budgets
- fler tenants
- nya integrationer
- automatic verify/link/merge

Varje produktfix kräver PR, regression och ny deploy.

## 13. Evidens

Skapa lokala rapporter:

```text
storage/status/production-pilot-p1-activation-<run-id>.md
storage/status/production-pilot-p1-result-<run-id>.md
```

Rapportera:

- release SHA
- tenant och mailbox som redigerade hashes
- activation timestamp
- config hashes före/aktiv/efter
- active flags
- inbound counts
- classifications och operator corrections
- queues och incidents
- shadow metrics
- external writes
- cross-tenant findings
- pause/restore
- daily summaries
- acceptance result

Rapporter får inte innehålla hela mejl, OAuth-token, fullständiga adresser eller onödiga personuppgifter.

## 14. Leverans

Arbeta på branch:

```text
ops/production-pilot-p1-observe
```

Genomför:

1. skapa och lås denna planfil
2. verifiera P0-baseline
3. implementera saknade P1 readiness-gates och daily metrics
4. kör riktade tester och full Release Gate
5. öppna PR om kod eller docs behöver ändras
6. squash-merga och verifiera post-merge Release Gate
7. deploya godkänd release efter environment approval
8. kör syntetisk P1-preflight
9. aktivera exakt en pilotmailbox
10. kör P1 enligt pilotperioden
11. sammanställ P1-resultat
12. stoppa före P2

Ingen P2-funktion får aktiveras.

## 15. Status efter P1

Vid full P1 PASS, registrera:

```text
PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED
PRODUCTION_PILOT_ACTIVE
```

`PRODUCTION_PILOT_ACTIVE` betyder endast:

- exakt en pilottenant
- observe-only
- 0 Gmail replies
- 0 non-Gmail external writes

Behåll:

```text
pilot-g-decision = pending
```

## 16. Failure

Vid failure:

- registrera inte P1 qualification
- disable intake
- pause pilottenant
- verifiera external writes
- återställ baseline vid behov
- skapa incidentunderlag
- ingen automatisk retry
- rapportera första felande gate eller event
- rapportera rollbackstatus

## 17. Stopp

Efter P1 PASS:

```text
OPERATOR ACTION REQUIRED — Auktorisera P2 approval-baserade Gmail-svar
```

Efter P1 failure:

```text
OPERATOR ACTION REQUIRED — Godkänn incidentfix eller avsluta pilot
```
