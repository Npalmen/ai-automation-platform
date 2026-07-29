---
name: Testbot H continuous regression
overview: Gör de kvalificerade Testbot A–G-kontrakten till kontinuerliga, deterministiska och fail-closed regressionsgrindar utan automatiska live-writes eller produktionsaktivering.
todos:
  - id: testbot-h-a-current-truth
    content: Inventera befintliga CI-workflows, testsviter, kvalificeringar, artifacts och driftgränser
    status: completed
  - id: testbot-h-b-regression-registry
    content: Inför en versionsstyrd registry för regressionssviter, kvalificeringar och evidensberoenden
    status: completed
  - id: testbot-h-c-ci-tiers
    content: Implementera PR-, main-, nightly- och manual-canary-nivåer med tydliga budgetar
    status: completed
  - id: testbot-h-d-drift-determinism
    content: Implementera determinism-, schema-, migration-, capability- och qualification-driftkontroller
    status: completed
  - id: testbot-h-e-failure-operations
    content: Implementera fail-fast, flakinesspolicy, incidentunderlag, artifacts, retention och återställning
    status: completed
  - id: testbot-h-f-delivery
    content: Kör regressioner, PR, squash-merge och post-merge validering
    status: in_progress
  - id: testbot-h-g-closure
    content: Kör formell continuous-regression-kvalificering och registrera TESTBOT_SYSTEM_CLOSED vid full PASS
    status: pending
isProject: true
---

# Testbot H — Continuous regression

## 1. Operatörsbeslut

Testbot H ska nu genomföras.

Målet är att omvandla verifieringen från Testbot A–G till ett kontinuerligt kvalitetssystem som upptäcker regressioner före merge och efter förändringar på `main`.

Cursor ska utföra denna plan. Planens tekniska innehåll är låst efter att filen lagts i repot. Endast todo-status får ändras:

```text
pending → in_progress → completed
```

Testbot H får inte:

- aktivera produkten för verkliga kunder,
- skapa återkommande live Gmail-writes,
- skapa live Sheets-, Monday- eller Visma-writes,
- ändra kvalificeringsscope för A–G,
- dölja fel genom blind retry,
- göra breda produktrefaktoreringar utan bevisad regressionsorsak.

---

## 2. Verifierad baseline

### Testbotstatus

| Kapitel | Status |
|---|---|
| Testbot A — current truth | completed |
| Testbot B — isolated environment | completed |
| Testbot C — observe | completed |
| Testbot D — semi-automatic | completed |
| Testbot E — automatic Gmail | completed |
| Testbot F — customer-card stateful | completed |
| Testbot G — full-function matrix | completed |
| Testbot H — continuous regression | pending |

### Testbot G

- implementation: PR #104
- merge SHA: `9963660`
- post-merge Release Gate: `30474014405` PASS
- formal qualification: `30474812807`
- TBG01–TBG25: 25/25 PASS
- qualification: `FULL_FUNCTION_MATRIX_PASS`
- closure docs: PR #105
- new live external writes: 0

### Registrerade kvalificeringar

Minst:

- observe qualification från Testbot C
- semi-automatic qualification från Testbot D
- `AUTOMATIC_GMAIL_CANARY_QUALIFIED`
- `AUTOMATIC_GMAIL_CORE_QUALIFIED`
- `CUSTOMER_CARD_STATEFUL_DIRECT_QUALIFIED`
- `CUSTOMER_CARD_HTTP_CONTRACT_QUALIFIED`
- `CUSTOMER_CARD_SHADOW_DOMAIN_QUALIFIED`
- `CUSTOMER_CARD_SHADOW_PIPELINE_QUALIFIED`
- `CUSTOMER_CARD_PASS`
- `FULL_FUNCTION_MATRIX_PASS`

Testbot H ska läsa den faktiska kvalificeringslistan från aktuell `main` och inte anta att denna lista är fullständig.

---

## 3. Syfte

Testbot H ska säkerställa att följande alltid gäller när kod förändras:

1. Kvalificerade kontrakt fortsätter fungera.
2. Blockerade funktioner förblir blockerade.
3. Feature flags förblir fail-closed.
4. Tenant isolation förblir intakt.
5. Idempotency och exact-once förblir intakta.
6. Provider timeout orsakar inte automatisk resend.
7. Pre-write safety kan inte kringgås.
8. Customer-card shadowdata kan inte bli verifierad automatiskt.
9. Capability registry och full-function matrix förblir synkroniserade med koden.
10. Migrationskedjan fungerar från tom databas.
11. Rapporter är deterministiska och redigerade.
12. Ingen schemalagd regressionskörning skapar live external writes.

Testbot H är ett kvalitetssystem, inte en ny produktfunktion.

---

## 4. Continuous-regression-arkitektur

Inför fyra exekveringsnivåer.

### H1 — PR Fast Gate

Körs på varje relevant pull request.

Innehåll:

- manifest- och registryvalidering,
- capability/matrix consistency,
- hermetiska kontraktstester,
- säkerhetsregler,
- idempotency-unit tests,
- feature flag defaults,
- redaction tests,
- import/schema checks,
- migration static checks,
- changed-path impact analysis.

Krav:

- inga nätverksanrop,
- inga externa writes,
- snabb feedback,
- path-baserad testselektion,
- konservativ fallback för okända eller gemensamma kodytor.

### H2 — PR/Main PostgreSQL Gate

Körs på:

- PR när berörd kod påverkar persistence, workflows, actions, policy, customer domain eller migrations,
- varje merge till `main`.

Innehåll:

- full migration chain på tom PostgreSQL,
- customer-domain F1/F1b/F2a/F2b,
- approval/action lifecycle,
- idempotency och concurrency,
- tenant isolation,
- Testbot G PostgreSQL-kampanj,
- campaign cleanup,
- deterministic repeat-run för kritiska kampanjer.

Inga live externa writes.

### H3 — Nightly Full Regression

Körs en gång per natt eller enligt repoets etablerade schema.

Innehåll:

- hela hermetiska testsviten,
- hela PostgreSQL eval-sviten,
- full-function matrix,
- Docker build/start/health,
- migrationskedja,
- semantic hash repeat-run,
- stale qualification audit,
- capability drift,
- artifact schema validation,
- redaction scan,
- dependency/config driftkontroller som kan köras utan externa writes.

Nightly får inte automatiskt:

- godkänna GitHub environment för live Gmail,
- aktivera tenantautomation,
- seed:a live OAuth,
- skicka Gmail,
- skriva till Sheets, Monday eller Visma.

### H4 — Manual qualification/canary

Endast `workflow_dispatch` med exakt confirmation och explicit operatörsbeslut.

Används för:

- framtida live Gmail-canaries,
- provider-/recipientverifiering,
- nya sandbox- eller externa integrationskvalificeringar.

H4 är inte schemalagd. Befintliga live qualifications får bindas som evidens men ska inte återköras automatiskt.

---

## 5. Regression registry

Skapa:

`app/evaluation/regression/regression_registry.yaml`

Varje svit ska minst innehålla:

```yaml
id: testbot-g-full-function-pg
chapter: G
description: Full-function matrix against isolated PostgreSQL
tier:
  - main_pg
  - nightly
command:
  - python
  - -m
  - app.evaluation.full_function.runner
required_paths:
  - app/evaluation/full_function/**
  - app/workflows/**
database: postgres_eval
network: forbidden
external_write_budget: 0
expected_qualification:
  - FULL_FUNCTION_MATRIX_PASS
artifact_schema: full_function_matrix_v1
timeout_class: long
repeat_run: true
cleanup_required: true
owners:
  - platform
```

Fält:

- `id`
- `chapter`
- `description`
- `tier`
- `command`
- `required_paths`
- `always_run_paths`
- `database`
- `network`
- `external_write_budget`
- `required_flags`
- `required_services`
- `expected_qualification`
- `artifact_schema`
- `timeout_class`
- `repeat_run`
- `cleanup_required`
- `owners`
- `known_limitations`

Registry ska vara auktoritativ för vilka regressionssviter som finns och på vilka nivåer de körs.

Okända, duplicerade eller brutna kommandon ska faila CI.

---

## 6. Qualification registry och evidensdrift

Skapa eller utöka en maskinläsbar qualification registry.

Varje qualification ska minst innehålla:

- qualification ID,
- kapitel,
- scope,
- source workflow/run,
- source SHA,
- contract version,
- evidence schema,
- allowed reuse,
- incompatible changes,
- expiry policy,
- default production activation,
- live external write type,
- current status.

Testbot H ska upptäcka:

- qualification refererar till borttagen capability,
- contract version har ändrats utan ny kvalificering,
- evidensschema kan inte längre läsas,
- säkerhetskontrakt har ändrats,
- actionnamn eller campaign type har ändrats,
- feature flag defaults har ändrats,
- live-evidens återanvänds för bredare scope än den bevisar.

Driftstatus:

- `VALID`
- `STALE`
- `INCOMPATIBLE`
- `MISSING_EVIDENCE`
- `SCOPE_EXPANSION_BLOCKED`

En stale qualification får inte automatiskt raderas, men ska blockera påståenden som kräver aktuell evidens.

---

## 7. Path-based impact selection

Inför en deterministisk impact map.

| Ändrad kodyta | Obligatoriska regressioner |
|---|---|
| `app/decisioning/**` | decision contract, approvals, automatic Gmail, full-function |
| `app/workflows/**` | intake, semi-auto, automatic, shadow pipeline, full-function |
| `app/integrations/google/**` | Gmail provider, recipient verify, Sheets contract |
| `app/domain/customer/**` | F1/F1b/F2a/F2b, full-function |
| `app/api/routes/end_customer*` | customer HTTP, tenant isolation |
| `migrations/**` | full migration chain + berörda PG suites |
| `.github/workflows/**` | workflow contract + readiness + no-live-write guards |
| `app/evaluation/**` | berörda eval contract tests + self-tests |
| feature flag/settings | fail-closed, qualification drift, relevanta kampanjer |

Krav:

- impact map får endast minska redundans när säkerheten bevaras,
- `main` och nightly ska fortfarande ha bred täckning,
- ändringar i gemensamma kärnfiler ska utlösa bred regression,
- okända paths ska använda konservativ fallback,
- obligatoriska sviter får inte kringgås med filnamn eller label.

---

## 8. Determinism

Kritiska kampanjer ska kunna köras två gånger mot ren eval-state och ge samma normaliserade resultat.

Normalisering får exkludera:

- timestamps,
- slumpmässiga DB-ID:n,
- workflow run-ID,
- campaign run-ID där de inte är semantiskt relevanta,
- ordning som inte är kontrakterad.

Normalisering får inte exkludera:

- classification,
- decision,
- authorization,
- action operation ID-semantik,
- status,
- counts,
- external writes,
- provider outcome type,
- customer current/pending/conflict/historical state,
- cross-tenant findings,
- cleanupresultat,
- safety violations.

Krav:

- semantic hash versioneras,
- repeat-run körs på kritiska PG-kampanjer,
- hashändring utan kontraktsversionering ger driftfel,
- fixtures och seeds är deterministiska,
- scenarioordning är explicit.

---

## 9. Flakinesspolicy

Blind rerun är förbjuden.

När en testkörning faller:

1. Bevara första failure-artifact.
2. Klassificera:
   - deterministic product regression,
   - deterministic test regression,
   - environment failure,
   - infrastructure failure,
   - suspected flaky.
3. Kör högst en diagnostisk reproduktion endast när inga externa writes kan ske.
4. Automatisk rerun får aldrig omvandla en failure till PASS utan att ursprungligt fel redovisas.

Quarantine är endast tillåtet när:

- issue/incident finns,
- ägare är utsedd,
- expiry-datum finns,
- säkerhetskritiska tester inte berörs,
- testet fortsatt körs och rapporteras separat,
- merge gate uttryckligen visar `QUARANTINED`.

Följande får aldrig quarantinas:

- tenant isolation,
- unauthorized writes,
- pre-write safety,
- idempotency/exact-once,
- automatic verify/merge blocks,
- cleanup av campaign-data,
- feature flag fail-closed,
- credential/redactionkontroller.

---

## 10. Nätverks- och write-säkerhet

Alla automatiska H1–H3-sviter ska ha:

```text
network = forbidden
external_write_budget = 0
```

Inför guards som blockerar:

- okända outbound hosts,
- Gmail/Sheets/Monday/Visma-provideranrop,
- environment approval för live workflows,
- live OAuth-secrets i regression jobs,
- verkliga recipient-domäner,
- produktions-DB-signaler.

Verifiera att mock/sandbox adapters används.

Oväntat nätverksanrop ska:

- stoppa sviten,
- ge security failure,
- trigga cleanup,
- rapportera host och call-site redigerat,
- hindra fortsatta scenarios som kan skriva externt.

---

## 11. PostgreSQL och migrationsdrift

H2/H3 ska verifiera:

1. Tom databas → samtliga migrations i ordning.
2. Senast stödda tidigare schema → framåt.
3. Inga dubbletter i migration numbering.
4. Inga saknade migration files.
5. SQLAlchemy-modeller och PostgreSQL-schema är kompatibla.
6. SQLite-hermetiska modeller använder korrekta dialect variants där stödet är avsett.
7. Index och constraints för tenant isolation/idempotency finns.
8. Evaluation cleanup lämnar inga campaign rows.
9. Produktionsliknande tabeller utanför eval-scope förändras inte.

---

## 12. Feature flag drift

Skapa fail-closed kontroll för samtliga riskflags.

Minst:

- end-customer read/write,
- shadow intake/matching/promotion,
- automatic Gmail actions,
- integrations,
- scheduler,
- operator actions,
- live-eval/transportflaggor.

Kontrollera:

- defaultvärde,
- settings/schema,
- dokumenterad ägare,
- tenant scope,
- readiness,
- audit,
- restoration,
- kvalificering som krävs.

En riskflagga som ändras från `false` till `true` som default ska faila Testbot H utan explicit beslutsdokument och ny qualification.

---

## 13. Security regression

H1–H3 ska minst täcka:

- cross-tenant access,
- cross-tenant action,
- cross-tenant customer link,
- cross-tenant duplicate decision,
- spoofad sender,
- Reply-To mismatch,
- prompt injection,
- malicious attachment metadata,
- no-reply handling,
- redaction,
- secret scanning i artifacts,
- provider metadata utan OAuth,
- operation ID exact-once,
- stale approval/CAS,
- outcome unknown no-resend,
- unsafe reply blocked pre-write,
- AI fact cannot become verified,
- automatic merge forbidden.

---

## 14. Observability och artifacts

Varje tier ska skapa ett maskinläsbart summary artifact.

Schema:

`continuous_regression_report_v1`

Minst:

- `run_id`
- `runtime_sha`
- `tier`
- `trigger`
- `registry_version`
- `qualification_registry_version`
- `selected_suites`
- `skipped_suites`
- `skip_reasons`
- `test_counts`
- `scenario_counts`
- `qualification_drift`
- `capability_drift`
- `migration_result`
- `determinism_result`
- `external_writes`
- `network_attempts`
- `cross_tenant_findings`
- `security_failures`
- `quarantined_tests`
- `cleanup_status`
- `redaction_status`
- `duration_seconds`
- `status`

Artifacts ska:

- ha redigerade identifiers,
- inte innehålla OAuth,
- inte innehålla hela mejl,
- inte innehålla verklig PII,
- ha retention enligt CI-policy,
- vara jämförbara mellan runs.

Skapa lokal sammanfattning vid formell qualification:

`storage/status/testbot-h-continuous-regression-<run-id>.md`

Committera inte `storage/status/*`.

---

## 15. Failure- och incidentunderlag

Vid failure ska rapporten ge:

- första felande tier/svit/scenario,
- berörd capability,
- berörd qualification,
- första felande assertion,
- runtime SHA,
- migration/schema version,
- möjliga writes,
- nätverksförsök,
- tenant scope,
- cleanupresultat,
- artifactreferens,
- föreslagen klassificering,
- minsta reproduktionskommando.

Testbot H ska inte automatiskt skapa extern incident eller notifiering om sådan integration inte redan finns och är auktoriserad.

---

## 16. Performance budgets

Mät baseline för:

- H1 total tid,
- H2 total tid,
- H3 total tid,
- långsammaste sviter,
- DB setup/migration,
- Docker build,
- artifact generation.

Inför versionerade budgetar först efter uppmätt baseline.

Cursor får inte optimera bort säkerhetstester för att nå en godtycklig tidsgräns.

---

## 17. Workflow architecture

Föreslagen struktur:

### `.github/workflows/regression-pr.yml`

- diff/impact selection,
- H1,
- villkorad H2,
- summary artifact,
- inga live provider-secrets.

### `.github/workflows/regression-main.yml`

- full H1,
- full H2,
- Docker,
- migration chain,
- qualification drift,
- capability drift.

### `.github/workflows/regression-nightly.yml`

- H3,
- repeat-run determinism,
- full matrix,
- stale evidence audit,
- artifact retention,
- inga live writes.

### Befintlig `live-eval.yml`

- fortsatt manual,
- ingen schedule,
- exakta confirmations,
- separerad från H1–H3.

Återanvänd befintliga workflows när det minskar duplicering utan att göra ansvar och säkerhetsgränser otydliga.

---

## 18. TBR-scenarier

Implementera exakt TBR01–TBR20.

### TBR01 — Clean PR fast gate

Korrekt selection, hermetic PASS och inga onödiga PG/live-jobs.

### TBR02 — Shared decisioning change

Utlöser C–E- och G-relevanta sviter.

### TBR03 — Customer-domain change

Utlöser F1/F1b/F2a/F2b och G.

### TBR04 — Migration added

Utlöser migration chain och berörda PG-tests.

### TBR05 — Workflow change

Utlöser workflow contracts, readiness och no-live-write guards.

### TBR06 — Unknown path

Använder konservativ fallback.

### TBR07 — Qualification contract drift

Qualification blir `STALE` eller `INCOMPATIBLE`; bredare scope blockeras.

### TBR08 — Capability drift

Borttagen eller ändrad action/flag upptäcks.

### TBR09 — Determinism drift

Semantic hashändring utan versionering blockeras.

### TBR10 — Flaky failure

Blind rerun förbjuds och första failure bevaras.

### TBR11 — Quarantine expiry

Utgången quarantine blockerar.

### TBR12 — Unauthorized network attempt

Outbound call blockeras och rapporteras.

### TBR13 — External write attempt

Write-budget 0 stoppar före adapter.

### TBR14 — Tenant isolation regression

Kan inte quarantinas och merge blockeras.

### TBR15 — Cleanup regression

Kvarvarande campaign rows blockerar.

### TBR16 — Feature flag default drift

Riskflag default true blockeras.

### TBR17 — Broken artifact schema

Report/artifact validation failar.

### TBR18 — Missing evidence reference

PASS/PASS_LIVE kan inte rapporteras utan evidens.

### TBR19 — Nightly full pass

Samtliga H3-sviter PASS och 0 external writes.

### TBR20 — Manual live workflow isolation

Nightly kan inte trigga live-eval; live workflow kräver explicit confirmation.

---

## 19. Obligatoriska tester

Minst:

1. Regression suite IDs är unika.
2. Commands i registry existerar.
3. Required paths är giltiga.
4. Okänd tier avvisas.
5. External write budget för H1–H3 är 0.
6. Network policy för H1–H3 är forbidden.
7. Qualification IDs är unika.
8. Qualification source evidence är parsebar.
9. Scope expansion utan ny qualification blockeras.
10. Capability drift upptäcks.
11. Flag drift upptäcks.
12. Migration drift upptäcks.
13. TBR01–TBR20 finns.
14. Path impact selection är deterministisk.
15. Unknown path använder fallback.
16. Shared core changes utlöser bred regression.
17. Customer-domain changes utlöser F/G.
18. Workflow changes utlöser C–G-kontrakt.
19. Blind rerun är förbjuden.
20. Första failure-artifact bevaras.
21. Security tests kan inte quarantinas.
22. Quarantine kräver ägare och expiry.
23. Utgången quarantine blockerar.
24. Unauthorized network blockeras.
25. External write attempt blockeras före adapter.
26. Live provider secrets saknas i H1–H3.
27. Tenant isolation regression blockerar.
28. Cleanup regression blockerar.
29. Feature flag default true blockerar utan beslut.
30. Determinism repeat-run PASS.
31. Semantic hash versionering krävs vid kontraktsändring.
32. Artifact schema valideras.
33. Redaction scan PASS.
34. Migration chain PASS.
35. Customer F1/F1b/F2a/F2b regressioner PASS.
36. Approval/action lifecycle regressioner PASS.
37. Automatic Gmail safety regressioner PASS.
38. Full-function matrix regression PASS.
39. Docker PASS.
40. Main regression workflow PASS.
41. Nightly dry-run eller workflow-contract PASS.
42. Manual live workflow saknar schedule.
43. Ingen automatisk environment approval.
44. Nya live external writes = 0.
45. Full Release Gate PASS.

---

## 20. Leverans

Branch:

```text
feat/testbot-h-continuous-regression
```

Genomför autonomt:

1. skapa och lås planfilen,
2. inventera befintliga workflows och sviter,
3. implementera regression registry,
4. implementera qualification registry och drift,
5. implementera impact selection,
6. implementera H1,
7. implementera H2,
8. implementera H3,
9. implementera manual H4-isolation guards,
10. implementera determinismkontroller,
11. implementera nätverks- och write-guards,
12. implementera flakiness/quarantine-policy,
13. implementera artifact/report schema,
14. implementera TBR01–TBR20,
15. kör riktade tester,
16. kör full hermetisk regression,
17. kör full PostgreSQL regression,
18. kör migration chain,
19. kör Docker,
20. kör full Release Gate,
21. öppna avgränsad PR,
22. squash-merga,
23. verifiera post-merge Release Gate,
24. kör exakt en formell H-kvalificeringsrun på post-merge SHA,
25. registrera closure vid full PASS,
26. stoppa.

Ingen automatisk live-kampanj får köras.

---

## 21. PR-beskrivning

PR ska ange:

- A–G är completed,
- G source qualification och SHA,
- H1/H2/H3/H4-separation,
- regression registry,
- qualification drift,
- path impact selection,
- determinism,
- flakinesspolicy,
- nätverks- och write-budget 0,
- tenant isolation,
- cleanup,
- artifacts och retention,
- att `live-eval.yml` fortsatt är manual,
- att inga nya live writes har gjorts,
- att produktionsaktivering inte följer av Testbot H.

Committera inte:

- `storage/status/*`,
- CI artifacts,
- DB dumps,
- OAuth-data,
- provider payloads,
- verklig PII,
- live mailboxadresser.

---

## 22. Closure

Testbot H får markeras `completed` endast om:

- H1 PR fast gate PASS,
- H2 PostgreSQL/main gate PASS,
- H3 nightly full regression PASS eller fullständig formell motsvarande run PASS,
- H4 manual-live-isolation PASS,
- regression registry är komplett,
- qualification registry är komplett,
- capability och qualification driftkontroller PASS,
- TBR01–TBR20 PASS,
- repeat-run determinism PASS,
- migration chain PASS,
- Docker PASS,
- full-function matrix regression PASS,
- customer-card regression PASS,
- approval/automatic safety regression PASS,
- unauthorized network attempts = 0,
- external writes = 0,
- cross-tenant findings = 0,
- cleanup PASS,
- redaction clean,
- post-merge Release Gate PASS,
- formell H-kvalificeringsrun PASS.

Registrera:

```text
CONTINUOUS_REGRESSION_QUALIFIED
TESTBOT_SYSTEM_CLOSED
```

Uppdatera:

- `docs/01-current-truth.md`,
- `docs/06-backlog.md`,
- `docs/07-decisions.md`,
- `docs/plans/full-system-testbot-plan.md`,
- denna planfil, endast todo-status.

Testbotsystemets closure betyder inte:

- produktions-GA,
- automatisk tenantaktivering,
- live Sheets/Monday/Visma,
- automatisk verify/link/merge,
- att framtida ändringar inte behöver ny kvalificering.

---

## 23. Failure

Vid failure:

- testbot H förblir `in_progress`,
- `TESTBOT_SYSTEM_CLOSED` registreras inte,
- ingen automatisk livekörning,
- ingen blind retry,
- rapportera första felande tier/svit/TBR,
- rapportera qualification/capability drift,
- rapportera möjliga writes och network attempts,
- rapportera cleanup,
- föreslå minsta avgränsade fix eller forensics.

---

## 24. Stopp

Efter full PASS och closure:

```text
OPERATOR ACTION REQUIRED — Besluta om produktionspilotens release- och aktiveringsplan
```
