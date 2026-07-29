---
name: Produktionspilot release och aktivering
overview: Förbered, releasa och stegvis aktivera en enda tenant-isolerad produktionspilot med fail-closed feature flags, tydliga rollbackgränser, operatörsövervakning och utan bred produktionsaktivering.
todos:
  - id: pilot-a-current-truth
    content: Inventera aktuell produktionsmiljö, feature flags, kvalificeringar, driftverktyg och kvarvarande pilotgap
    status: completed
  - id: pilot-b-release-baseline
    content: Lås release-SHA, migrationsplan, backup, rollback och produktionskonfiguration
    status: completed
  - id: pilot-c-pilot-tenant
    content: Skapa och verifiera exakt en isolerad pilottenant med tillåtna integrationer och syntetisk preflight
    status: completed
  - id: pilot-d-activation-stages
    content: Implementera stegvis aktivering P0–P3 med separata gates och kill switches
    status: completed
  - id: pilot-e-operations
    content: Implementera operatörsvy, larm, incidentflöde, usage och daglig pilotrapport
    status: completed
  - id: pilot-f-live-verification
    content: Genomför produktionslik preflight och begränsad pilotverifiering enligt write-budget
    status: completed
  - id: pilot-g-decision
    content: Sammanställ pilotresultat och stoppa före bredare tenant- eller funktionsaktivering
    status: pending
isProject: true
---

# Produktionspilot — release- och aktiveringsplan

## 1. Operatörsbeslut

Testbotsystemet är formellt stängt genom:

- `CONTINUOUS_REGRESSION_QUALIFIED`
- `TESTBOT_SYSTEM_CLOSED`

Det innebär att de verifierade kontrakten kan användas som releaseunderlag. Det innebär inte att produkten ska aktiveras brett.

Nästa steg är en strikt avgränsad produktionspilot med:

- exakt en pilottenant,
- en dedikerad pilotmailbox,
- tydliga feature flags,
- stegvis aktivering,
- operatörskontroll,
- dokumenterad rollback,
- inga Sheets-, Monday- eller Visma-writes,
- ingen automatisk verify, customer link eller merge,
- ingen bred tenantaktivering.

Cursor ska genomföra denna plan. Planens tekniska innehåll är låst efter att filen lagts i repot. Endast todo-status får ändras:

```text
pending → in_progress → completed
```

---

## 2. Pilotens mål

Piloten ska verifiera att systemet fungerar stabilt i verklig drift med verklig transport och verklig operatörsanvändning, men med begränsad affärsrisk.

Piloten ska svara på:

1. Kan intake hantera en verklig mailbox stabilt?
2. Kan systemet klassificera och strukturera inkommande arbete korrekt?
3. Kan operatören se, förstå och kontrollera besluten?
4. Fungerar approval, reject, hold och needs-help i praktiken?
5. Fungerar automatisk Gmail-bekräftelse endast för kvalificerade lågriskfall?
6. Kan automation pausas omedelbart?
7. Återställs konfiguration och state korrekt efter incident?
8. Är audit, metrics, incidents och usage tillräckliga för drift utan kodinspektion?
9. Finns inga cross-tenant-läckor eller oauktoriserade writes?
10. Är produktens faktiska värde tydligt för pilotkunden?

---

## 3. Pilotens scope

### Tillåtet

- en pilottenant,
- en dedikerad Gmail-mailbox,
- observe,
- classification/extraction,
- manual review,
- approvals,
- approve/reject,
- exact-once Gmail reply efter approval,
- begränsad automatic Gmail safe acknowledgement i senare steg,
- customer-card shadow observations,
- match proposals,
- operatorpromotion till `PROPOSED` facts där det redan är kvalificerat,
- audit, metrics, incidents och usage,
- dagliga operatörsrapporter.

### Förbjudet under första pilotrelease

- fler än en pilottenant,
- bred tenantaktivering,
- live Sheets-writes,
- live Monday-writes,
- live Visma-writes,
- ekonomiska irreversible actions,
- automatisk bokning,
- pris- eller offertbesked,
- avtalsmässiga åtaganden,
- tekniska garantier,
- automatisk verify av kundfakta,
- automatisk customer link,
- automatisk merge,
- automatisk duplicate resolution,
- full automatic multi-integration,
- nya actiontyper utanför kvalificerad registry.

---

## 4. Rekommenderad pilotkund

Första piloten ska vara intern verksamhet eller en mycket nära samarbetspartner med låg till måttlig mailvolym, tydlig informationsmailbox och låg affärsrisk vid ett felaktigt utkast eller felklassificering.

Första piloten ska inte vara en högvolymskund, jourverksamhet eller en kund som kräver pris, bokning eller ekonomiintegration från dag ett.

---

## 5. Releasebaseline

### Lås release-SHA

Skapa en explicit release candidate från aktuell gröna `main`.

Krav:

- samtliga A–H todos completed,
- `FULL_FUNCTION_MATRIX_PASS`,
- `CONTINUOUS_REGRESSION_QUALIFIED`,
- `TESTBOT_SYSTEM_CLOSED`,
- post-merge Release Gate PASS,
- Regression Main PASS,
- senaste Nightly PASS eller formell motsvarande full regression,
- Docker PASS,
- migration chain PASS,
- redaction clean,
- inga öppna säkerhetskritiska regressionsfel.

Tagga enligt repositoryts standard, exempelvis:

```text
pilot-v0.1.0
```

### Release manifest

Skapa ett maskinläsbart release manifest med minst:

- release version,
- commit SHA,
- migration head,
- Docker image digest,
- frontend build hash,
- capability registry version,
- qualification registry version,
- feature flag defaults,
- pilottenant-ID,
- tillåtna integrationer,
- aktiveringsnivå,
- rollback target,
- backup reference,
- operator approval ID,
- release timestamp.

Manifestet får inte innehålla secrets.

---

## 6. Produktionsmiljö och deployment readiness

Verifiera före deploy:

### Infrastruktur

- färsk PostgreSQL-backup och dokumenterad restore,
- tillräckligt diskutrymme,
- TLS och domän fungerar,
- reverse proxy health PASS,
- app, worker/scheduler och frontend låsta till image digest,
- logrotation fungerar,
- secrets har rätt behörigheter,
- OAuth-token finns i DB och inte i logs/artifacts,
- inga debug-flaggor är aktiva,
- scheduler startläge är explicit.

### Databas

- migrations körs på backupad miljö,
- migration head matchar release manifest,
- inga eval tenants eller campaign rows följer med,
- tenant isolation- och idempotency-constraints finns,
- shadow ledger migration är aktiv,
- rollbackstrategi är dokumenterad.

### Applikation

- operatorrollen är korrekt,
- kundportalens auth är korrekt för aktiverat scope,
- no-reply och spamfall är fail-closed,
- alla riskflags default `false`,
- testworkflows kan inte aktivera pilottenanten,
- continuous regression använder inga produktionssecrets.

---

## 7. Pilottenant

Skapa exakt en tenant, exempelvis:

```text
TENANT_PRODUCTION_PILOT_01
```

Använd repositoryts verkliga tenant-ID-standard om annan.

Tenantkonfigurationen ska innehålla:

- pilotstatus,
- pilotstart,
- pilotägare,
- mailbox,
- allowed sender/recipient scope där tillämpligt,
- aktiverade integrationer,
- feature flags,
- write budgets,
- operatorer,
- audit reason,
- rollback snapshot,
- pilot review-datum.

Tenantkrav:

- isolerad från alla andra tenants,
- kan pausas utan deploy,
- integration kan kopplas bort utan deploy,
- automation kan pausas utan deploy,
- customer shadow pipeline kan stängas separat,
- aktivering loggas,
- config snapshot och hash sparas redigerat.

---

## 8. Aktiveringsnivåer

### P0 — Production dry run

```text
Gmail intake: OFF eller testmailbox-only
Observe: ON
Approvals: OFF
Automatic Gmail: OFF
Customer shadow intake: OFF
Customer shadow matching: OFF
Customer shadow promotion: OFF
Sheets/Monday/Visma: OFF
Scheduler automatic processing: PAUSED
```

### P1 — Observe och manual review

```text
Gmail intake: ON för pilotmailbox
Observe: ON
Classification/extraction: ON
Manual review/hold: ON
Approvals: OFF
Automatic Gmail: OFF
Customer shadow intake: ON
Customer shadow matching: ON
Customer shadow promotion: OFF
Sheets/Monday/Visma: OFF
```

### P2 — Approval-baserade Gmail-svar

```text
Gmail intake: ON
Manual review: ON
Approval create: ON
Approve/reject: ON
Gmail reply efter approval: ON
Automatic Gmail: OFF
Customer shadow promotion: endast explicit operatoraction
Sheets/Monday/Visma: OFF
```

### P3 — Begränsad automatic Gmail safe acknowledgement

```text
Automatic Gmail: ON endast för kvalificerad safe acknowledgement
Pre-write safety: obligatorisk
Reply budget: låg och explicit
Pris/bokning/åtagande: alltid hold
Customer shadow pipeline: fortsatt shadow/proposed only
Automatic verify/link/merge: OFF
Sheets/Monday/Visma: OFF
```

Ingen fas får aktiveras automatiskt på grund av tid. Varje övergång kräver uttryckligt operatörsbeslut.

---

## 9. Aktiveringsgates

### P0 → P1

Kräv:

- release deployad,
- migrations PASS,
- health PASS,
- operator login PASS,
- pilottenant skapad,
- Gmail OAuth PASS,
- mailbox preflight PASS,
- inga andra tenants påverkade,
- automation pausad,
- rollback testad,
- audit synlig,
- inga externa writes.

### P1 → P2

Kräv:

- minst 3–5 driftdagar eller tillräckligt antal inbound events,
- accepterad classification/extraction-kvalitet,
- inga cross-tenant findings,
- inga tappade messages,
- inga duplicate jobs,
- manual review fungerar,
- shadow observations är korrekta,
- 0 verified facts skapade automatiskt,
- backlog inom accepterad nivå.

### P2 → P3

Kräv:

- approval-flödet stabilt,
- approve/reject exact-once,
- inga oauktoriserade replies,
- provider accepted och recipient verification fungerar,
- pre-write safety-regressioner PASS,
- hold precision för pris/bokning/åtaganden accepterad,
- operatorn kan pausa automation omedelbart,
- rollback testad på pilottenant,
- explicit operatörsauktorisering.

---

## 10. Write-budgetar

### P0

- inbound Gmail reads: 0 eller syntetisk testmailbox,
- Gmail replies: 0,
- other external writes: 0.

### P1

- inbound messages: pilotmailboxens verkliga volym,
- Gmail replies: 0,
- approvals: 0,
- non-Gmail writes: 0.

### P2

- Gmail replies: endast explicit godkända,
- max reply per job/action: 1,
- unauthorized replies: 0,
- non-Gmail writes: 0.

### P3

Sätt en låg startbudget, exempelvis:

- max automatiska replies per dag: 3,
- max reply per scenario/job: 1,
- max sammanhängande automatic failures: 1,
- unauthorized replies: 0,
- non-Gmail writes: 0.

Exakt budget ska beslutas från pilotmailboxens volym och dokumenteras i tenantkonfigurationen.

---

## 11. Kill switches

Det ska finnas minst:

1. global scheduler pause,
2. tenant automation pause,
3. Gmail reply disable,
4. customer shadow intake disable,
5. customer shadow matching disable,
6. customer shadow promotion disable,
7. integration disconnect,
8. read-only operatorläge,
9. deployment rollback,
10. database restore procedure.

Kill switches ska kunna utföras utan kodändring, vara auditerade och testas före P1 samt före P3.

---

## 12. Rollback

### Applikationsrollback

- föregående image digest dokumenterad,
- databasens backward compatibility bedömd,
- deployrollback testad i staging eller motsvarande,
- frontend och backend rullas tillbaka kompatibelt.

### Konfigurationsrollback

```text
snapshot
→ activate phase
→ verify
→ pause
→ restore
→ verify hash match
```

### Databashantering

- inga automatiska destruktiva rollbackmigrationer,
- backup före migration,
- incidentplan för schema som inte är bakåtkompatibelt,
- campaign/testdata får aldrig blandas med pilotdata,
- customer shadowdata får inte raderas brett.

---

## 13. Operatörspanel och daglig drift

Piloten får inte starta förrän operatören kan se minst:

- app health,
- scheduler state,
- automation state,
- tenant integration status,
- senaste intake,
- jobs per status,
- approvals,
- needs-help,
- incidents,
- action intents/outcomes,
- provider failures,
- duplicate/replay blocks,
- usage,
- customer shadow observations,
- match proposals awaiting review,
- feature flag state,
- senaste deploy SHA.

Om allt inte finns i UI får ett tydligt pilotdriftkommando eller en redigerad daglig rapport användas interimistiskt. Operatören ska inte behöva läsa rå kod.

---

## 14. Metrics

Mät minst:

### Intake

- inbound messages,
- processed messages,
- duplicate suppressions,
- processing failures,
- processing latency,
- no-reply/spam/unknown.

### Decisioning

- classification distribution,
- manual review rate,
- hold rate,
- approval rate,
- automatic eligibility,
- safety blocks,
- low-confidence rate.

### Actions

- approvals created,
- approves,
- rejects,
- Gmail adapter invocations,
- provider accepted,
- recipient verified,
- unauthorized writes,
- timeout/outcome unknown,
- duplicate dispatch blocks.

### Customer shadow

- observations created,
- proposals awaiting review,
- ambiguous matches,
- conflicts,
- promotions to proposed facts,
- replay suppressions,
- cross-tenant blocks,
- automatic verify/link/merge count.

### Drift

- incidents,
- operator interventions,
- queue age,
- daily processing volume,
- error rate,
- feature flag state.

---

## 15. Pilot acceptance criteria

Teknisk pilotacceptans kräver:

- inga cross-tenant findings,
- unauthorized writes = 0,
- duplicate external writes = 0,
- message loss = 0 enligt tillgänglig korrelation,
- provider outcome persistence fungerar,
- recipient verification fungerar i aktiverade svarslägen,
- unsafe replies blockeras pre-write,
- automatic verify/link/merge = 0,
- customer shadow provenance är komplett,
- operatorn kan pausa och återställa,
- incidenter är spårbara,
- continuous regression är grön,
- release SHA och config är spårbara,
- backup/rollback är verifierad,
- redaction och secret handling är godkända.

Affärsmässig pilotacceptans ska bedömas separat:

- sparad administrativ tid,
- kvalitet på sortering och förberedelse,
- antal ärenden som kräver korrigering,
- operatörens arbetsbelastning,
- pilotkundens upplevda nytta.

---

## 16. Incidentgränser

### Stoppa automation omedelbart vid

- oauktoriserat externt svar,
- fel recipient,
- cross-tenant finding,
- safety bypass,
- duplicate reply,
- automatic verified fact,
- automatic customer link eller merge,
- OAuth-/secretläcka,
- okänd extern adapterwrite,
- återkommande provider timeout med osäkert outcome.

### Pausa och utred vid

- hög klassificeringsfelgrad,
- växande manual review-kö,
- återkommande extractionfel,
- stale approvals,
- customer shadow conflicts över tröskel,
- onormal latency,
- drift mellan runtime och release manifest.

---

## 17. Preflight utan verklig kundtrafik

Före P1 ska en produktionslik preflight köras med syntetisk data.

Krav:

- pilottenant,
- riktig production deployment,
- dedikerad testadress eller intern mailbox,
- högst två syntetiska inbound messages,
- 0 automatiska replies,
- 0 non-Gmail writes,
- observe/manual routing,
- shadow observations,
- audit,
- cleanup eller tydlig retention.

Preflight får inte använda verklig kunddata.

---

## 18. Leveransarkitektur

Branch:

```text
feat/production-pilot-release-activation
```

Genomför autonomt:

1. skapa och lås denna planfil,
2. inventera produktionsmiljö och aktuella flags,
3. implementera release manifest,
4. implementera pilottenant-konfiguration,
5. implementera eller verifiera kill switches,
6. implementera readiness och preflight,
7. implementera daglig pilotrapport,
8. implementera metrics och incidentunderlag,
9. verifiera backup/rollback,
10. kör staging/production-like dry run,
11. kör full Release Gate,
12. öppna avgränsad PR,
13. squash-merga,
14. verifiera post-merge Release Gate,
15. deploya release candidate efter separat environment approval,
16. kör P0 preflight,
17. stoppa före P1 aktivering.

Ingen verklig pilottrafik får aktiveras automatiskt av denna plan.

---

## 19. Obligatoriska tester

Minst:

1. Pilottenant-ID är unikt.
2. Pilottenant kan pausas separat.
3. Riskflags default `false`.
4. P0 har 0 external writes.
5. P1 kan inte skapa Gmail reply.
6. P2 kräver approval.
7. P3 kräver pre-write safety PASS.
8. Pris/bokning/åtagande hålls.
9. Max reply per job = 1.
10. Daily auto-reply budget blockeras före write.
11. Sheets/Monday/Visma förblir blockerade.
12. Automatic verify är blockerad.
13. Automatic customer link är blockerad.
14. Automatic merge är blockerad.
15. Tenant isolation PASS.
16. Cross-tenant config access blockeras.
17. Config snapshot/restore hash match.
18. Tenant automation pause stoppar nästa intake/action.
19. Scheduler pause stoppar bakgrundskörning.
20. Gmail reply kill switch stoppar adapter.
21. Shadow intake kill switch stoppar observationer.
22. Integration disconnect failar stängt.
23. Rollback target är verifierbar.
24. Release manifest matchar runtime.
25. Runtime SHA visas i driftunderlag.
26. Backup reference krävs före migration.
27. Preflight använder syntetisk data.
28. Preflight max två inbound.
29. Preflight replies = 0.
30. Preflight non-Gmail writes = 0.
31. Audit event finns för aktivering.
32. Audit event finns för pause/restore.
33. Incidentunderlag redigeras.
34. OAuth exponeras inte.
35. Verklig PII saknas i testartifacts.
36. Continuous regression PASS.
37. Migration chain PASS.
38. Docker PASS.
39. Full Release Gate PASS.
40. Post-merge Release Gate PASS.

---

## 20. Dokumentation

Uppdatera vid leverans:

- `docs/01-current-truth.md`
- `docs/06-backlog.md`
- `docs/07-decisions.md`
- release notes
- pilot runbook
- rollback runbook
- incident runbook
- feature flag inventory
- operator checklist

Dokumentationen ska tydligt skilja:

- testkvalificering,
- release readiness,
- pilotaktivering,
- produktions-GA.

---

## 21. Status efter leverans

När implementation, gates och P0 preflight är PASS:

Registrera:

```text
PRODUCTION_PILOT_RELEASE_READY
```

Registrera inte ännu:

```text
PRODUCTION_PILOT_ACTIVE
PRODUCTION_GA
```

Stoppa med:

```text
OPERATOR ACTION REQUIRED — Auktorisera P1 observe-only pilottrafik
```

---

## 22. Failure

Vid failure:

- ingen P1-aktivering,
- automation pausad,
- Gmail replies av,
- customer shadow promotion av,
- pilottenant återställd till baseline,
- ingen bred fix,
- rapportera första felande gate,
- rapportera möjliga external writes,
- rapportera rollbackstatus,
- föreslå minsta avgränsade fix eller forensics.
