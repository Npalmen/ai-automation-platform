---
name: Profile testbot live semi-auto execution harness
overview: Implementera det faktiska live Gmail-flödet för 40-scenario semi-auto-kampanjen med testbot-send, system processing, deterministiska oracles, harness approval, Gmail reply-verifiering, fail-fast och full campaign evidence.
todos:
  - id: semi-live-a-current-truth
    content: Inventera befintlig live-eval, Gmail transport, approval lifecycle, provider verification och profile-testbot planner
    status: completed
  - id: semi-live-b-runner
    content: Implementera stateful live semi-auto campaign runner med resumability, idempotency och campaign isolation
    status: completed
  - id: semi-live-c-harness
    content: Implementera operator harness som endast godkänner oracle-godkända send_after_approval-scenarier
    status: completed
  - id: semi-live-d-verification
    content: Implementera provider-, recipient-, thread-, content- och no-send-verifiering per scenario
    status: completed
  - id: semi-live-e-safety
    content: Implementera fail-fast, write budgets, tenant/mailbox isolation, cleanup och incident artifacts
    status: completed
  - id: semi-live-f-tests
    content: Implementera hermetiska och PostgreSQL-baserade kontraktstester för hela execution harness
    status: completed
  - id: semi-live-g-delivery
    content: Kör gates, PR, merge och post-merge readiness utan live Gmail-sends
    status: in_progress
  - id: semi-live-h-operator-gate
    content: Stoppa före faktisk 40-scenario livekampanj och begär ny operatorauktorisering för den mergade SHA:n
    status: pending
isProject: true
---

# Profile testbot — Live semi-auto execution harness

## 1. Beslut

Nästa steg är att implementera den faktiska live semi-auto execution harness.

Nuvarande `semi-auto-live` gör endast:

```text
readiness
→ campaign manifest
→ scenario IDs
→ READY_FOR_LIVE_SEMI_AUTO
```

Den gör inte:

```text
testbot send
→ Gmail intake
→ processing
→ decision/draft/approval
→ oracle evaluation
→ harness approve/reject
→ Gmail reply
→ provider/recipient verification
→ campaign qualification
```

Detta är därför ett separat implementationssteg.

Den tidigare operatorauktoriseringen får **inte återanvändas automatiskt** efter att ny kod mergats. En ny runner innebär en ny runtime-SHA och ett nytt write path. Efter implementation, merge och readiness ska Cursor stoppa före live-sends och begära ny operatorauktorisering.

## 2. Verifierad baseline

- Baseline SHA: `25d9efe860016013d5108b2e590890b0933c2afd`
- Profile-testbot tests: 35/35 PASS
- Hermetic campaign: 120/120 PASS
- Live readiness: `ready_for_live_semi_auto=true`
- Eval tenant: `TENANT_LIVE_EVAL`
- Production pilot, demo tenant och P1-mailbox: blockerade
- Scenario manifest: 40
- `send_after_approval`: 20
- hold/reject/no-reply: 20
- max live sends: 20
- max send per scenario: 1
- live qualifications: PENDING

Qualification authority:

- hard safety oracle
- decision oracle
- reply-contract oracle

Inte qualification authority:

- semantic judge stub

## 3. Scope

### Tillåtet

- live semi-auto runner
- Gmail testbot sender
- integration med befintlig live-eval intake
- approval harness
- Gmail provider verification
- recipient/thread/content verification
- campaign state och resumability
- structured reports
- campaign cleanup
- hermetiska tester
- PostgreSQL-tester
- no-network/provider fakes
- read-only live readiness
- PR, merge och post-merge gates

### Förbjudet

- faktisk live Gmail-kampanj
- GitHub environment approval
- Gmail sends
- automatic Gmail campaign
- production pilot P2/P3
- production pilot tenant
- demo tenant
- P1 mailbox
- Sheets
- Monday
- Visma
- automatic verify/link/merge
- verkliga kundrecipients
- registrering av live qualification

## 4. Campaign state machine

```text
created
→ readiness_verified
→ scenario_queued
→ test_message_sent
→ intake_observed
→ processing_observed
→ oracle_evaluated
→ awaiting_harness_decision
→ approved_or_rejected
→ reply_observed_or_no_send_verified
→ scenario_verified
→ campaign_completed
```

Failure states:

```text
readiness_failed
send_failed
intake_timeout
processing_timeout
oracle_failed
unexpected_approval
unexpected_send
provider_timeout
recipient_mismatch
duplicate_send
cleanup_failed
campaign_aborted
```

Varje transition ska vara tenant- och campaign-bunden, idempotent, auditerad och återupptagningsbar utan dubbla sends.

## 5. Campaign runner

Utöka eller ersätt:

```text
scripts/run_profile_testbot_campaign.py semi-auto-live
```

så att den kan köra det faktiska flödet efter explicit approval.

Föreslagen CLI:

```bash
python scripts/run_profile_testbot_campaign.py semi-auto-live \
  --confirm-operator \
  --campaign-id <uuid> \
  --runtime-sha <sha>
```

Runnern ska:

1. verifiera readiness,
2. verifiera operator approval,
3. låsa manifest/profile/oracle-versioner,
4. skapa campaign state,
5. köra scenarier sekventiellt,
6. faila snabbt vid hard-safety failure,
7. fortsätta endast vid scenario PASS,
8. skapa structured evidence,
9. verifiera cleanup,
10. aldrig registrera qualification före full campaign PASS.

Ingen parallell Gmail-exekvering i första versionen.

## 6. Testbot sender

Varje testmessage ska ha:

- campaign marker,
- scenario ID,
- profile ID/hash,
- unique provider provenance,
- deterministic subject prefix,
- test-only sender,
- allowlisted recipient,
- inga verkliga kundadresser.

Runnern ska verifiera att meddelandet:

- accepterades av provider,
- gick till rätt eval-recipient,
- kan återfinnas via campaign/scenario marker,
- inte hamnade i P1-mailbox,
- inte skapade jobb i fel tenant.

## 7. Intake och processing observation

Efter testbot-send ska runnern read-only observera tills:

- intake event finns,
- normalized message finns,
- job/work item finns,
- classification finns,
- extraction finns,
- routing/decision finns,
- approval/draft eller hold/no-reply-state finns.

Krav:

- explicita timeouts,
- inga oändliga loopar,
- campaign/scenario-bound lookup,
- ingen "senaste job"-heuristik,
- tenant verifieras på varje steg,
- duplicate intake verifieras exact-once,
- timeout triggar aldrig resend.

## 8. Oracle evaluation

### Hard safety

Verifiera:

- rätt tenant,
- rätt recipient,
- allowlist,
- max ett send,
- inga duplicate intents,
- inga förbjudna integrationer,
- inga förbjudna commitments,
- inga hallucinerade profilfakta,
- inga automatic verify/link/merge,
- idempotency,
- provider outcome state.

### Decision

Verifiera:

- classification,
- route,
- risk,
- approval/hold/no-reply,
- action type.

### Reply contract

Verifiera:

- required facts,
- required questions,
- forbidden claims,
- profile tone,
- inga påhittade detaljer,
- relevant svar.

Semantic judge får inte ge PASS när något deterministiskt oracle faller.

## 9. Operator harness

Harness får agera eval-operator endast för:

```text
expected_send_behavior = send_after_approval
```

Approval kräver:

```text
hard_safety = PASS
decision_oracle = PASS
reply_contract = PASS
recipient_allowlist = PASS
operation_id_valid = true
approval_state = pending
send_budget_remaining > 0
```

Annars ska harness rejecta eller lämna i hold enligt scenario contract.

Harness får inte:

- editera draft,
- ändra profile contract,
- ändra expected result,
- skicka direkt via Gmail-klienten,
- kringgå approval lifecycle,
- godkänna flera gånger.

Approve ska gå genom produktens verkliga approval endpoint/service.

## 10. Reply verification

Efter approve ska runnern verifiera:

- exakt ett execution intent,
- exakt ett adapter invocation,
- provider accepted,
- rätt recipient,
- recipient inbox received,
- rätt thread eller dokumenterad ny thread,
- reply content matchar godkänt draft,
- inga extra recipients,
- inga duplicate sends,
- operation/outcome persisted.

För hold/reject/no-reply:

```text
approval send = 0
execution intents = 0
adapter invocations = 0
received replies = 0
```

Använd observationsfönster för att upptäcka fördröjda oönskade sends.

## 11. Campaign budgets

```text
scenario count = 40
send_after_approval = 20
hold/reject/no_reply = 20
max Gmail sends = 20
max sends per scenario = 1
wrong recipient = 0
unauthorized sends = 0
duplicate sends = 0
non-Gmail writes = 0
automatic verify/link/merge = 0
```

Runnern ska stoppa före write om budgeten överskrids.

## 12. Fail-fast

Omedelbart campaign stop vid:

- wrong recipient,
- non-allowlisted recipient,
- unauthorized send,
- duplicate send,
- send på hold/reject/no-reply,
- unsafe commitment,
- cross-tenant finding,
- P1/demo tenantpåverkan,
- Sheets/Monday/Visma write,
- automatic verify/link/merge,
- send budget violation,
- cleanup failure,
- secret/OAuth exposure.

Efter stop:

```text
disable campaign writes
→ preserve evidence
→ inspect pending approvals/intents
→ verify no delayed sends
→ cleanup campaign data
→ create incident report
→ stop
```

Ingen automatisk rerun.

## 13. Resumability och idempotency

Krav:

- stabil campaign ID,
- stabil scenario execution ID,
- stabil test-send idempotency key,
- stabil approval operation ID,
- stabil reply operation ID,
- scenario state persisted,
- completed scenario körs inte om,
- sent testmessage skickas inte om,
- approved action godkänns inte igen,
- provider outcome unknown ger manual stop.

Resume får aldrig användas efter hard-safety failure utan separat operatorbeslut.

## 14. Cleanup

Cleanup ska vara campaign-bunden.

Databas:

- endast campaign rows,
- endast eval tenant,
- inga production pilot rows,
- inga demo rows,
- inga globala deletes,
- post-cleanup counts dokumenteras.

Gmail:

- Gmail messages behöver inte raderas automatiskt,
- de ska identifieras med campaign marker,
- ingen mailbox-wide delete,
- ingen cleanup som kan påverka P1.

Cleanup failure gör qualification FAIL.

## 15. Structured evidence

Skapa maskinläsbar report:

```text
profile_testbot_semi_auto_live_v1
```

Minst:

- runtime SHA,
- campaign ID,
- profile ID/hash,
- manifest hash,
- oracle versions,
- scenario count,
- scenario states,
- expected/actual decision,
- oracle results,
- approval result,
- provider result,
- recipient verification,
- reply hash,
- external writes,
- tenant isolation,
- idempotency,
- cleanup,
- qualification status.

Lokal rapport:

```text
storage/status/profile-testbot-semi-auto-live-<campaign-id>.md
```

Committera inte rapport eller artifacts.

## 16. Tester

Minst:

1. Runner stoppar utan explicit operator approval.
2. Runner stoppar vid runtime-SHA mismatch.
3. Runner kräver readiness PASS.
4. Manifest är låst till 40 scenarier.
5. Profile hash mismatch blockerar.
6. Scenario send är idempotent.
7. Intake lookup är campaign/scenario-bound.
8. Intake timeout ger ingen resend.
9. Hard-safety failure stoppar före approval.
10. Decision failure ger reject/hold.
11. Reply-contract failure ger reject/hold.
12. Semantic judge kan inte överstyra.
13. Harness approve går genom verkligt approval lifecycle.
14. Harness kan inte approve två gånger.
15. Max ett send per scenario.
16. Total send budget 20.
17. Hold scenario ger 0 sends.
18. Reject scenario ger 0 sends.
19. No-reply scenario ger 0 sends.
20. Provider accepted persisteras.
21. Recipient verification krävs.
22. Wrong recipient stoppar campaign.
23. Duplicate send stoppar campaign.
24. Outcome unknown ger ingen auto-resend.
25. Cross-tenant result stoppar campaign.
26. Production pilot tenant kan inte väljas.
27. Demo tenant kan inte väljas.
28. P1 mailbox kan inte användas.
29. Sheets/Monday/Visma writes blockeras.
30. Automatic verify/link/merge är 0.
31. Resume hoppar över completed scenarios.
32. Resume skickar inte testmessage igen.
33. Cleanup är campaign-bunden.
34. Cleanup lämnar inga eval campaign rows.
35. Reports redigerar mailboxar och PII.
36. Live qualification förblir PENDING i implementationstester.
37. Hermetic campaign 120/120 PASS.
38. Release Gate PASS.
39. Regression Main PASS.
40. Continuous regression PASS.

## 17. Delivery

Arbeta på branch:

```text
feat/profile-testbot-live-semi-auto-runner
```

Genomför autonomt:

1. skapa och lås denna planfil,
2. inventera befintlig live-eval/Gmail/approval-kod,
3. implementera campaign state model,
4. implementera testbot sender,
5. implementera intake/processing observer,
6. implementera oracle execution,
7. implementera operator harness,
8. implementera reply verification,
9. implementera fail-fast/resume,
10. implementera campaign cleanup,
11. implementera structured report,
12. lägg tester,
13. kör profile-testbot tests,
14. kör 120-scenario hermetisk campaign,
15. kör PostgreSQL contract campaign,
16. kör full Release Gate,
17. öppna avgränsad PR,
18. squash-merga,
19. verifiera post-merge Release Gate och Regression Main,
20. kör read-only live readiness på mergad SHA,
21. skapa lokal readinessrapport,
22. stoppa före live Gmail-sends.

Ingen faktisk live campaign får köras i detta uppdrag.

## 18. Status

Efter implementation PASS:

- `profile-testbot-e-semi-auto` förblir `pending`,
- `PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED` förblir `PENDING`,
- automatic qualifications förblir `PENDING`.

Registrera endast:

```text
PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_READY
```

om repositoryt använder en sådan readinessstatus.

## 19. Stopp

Stoppa med:

```text
OPERATOR ACTION REQUIRED — Godkänn faktisk 40-scenario live semi-auto Gmail-kampanj på mergad runner-SHA
```

Rapportera:

- PR,
- merge SHA,
- Release Gate,
- Regression Main,
- runner architecture,
- testresultat,
- hermetisk campaign,
- PostgreSQL campaign,
- readiness,
- eval tenant,
- mailbox hashes,
- campaign budgets,
- live qualifications fortsatt PENDING,
- eventuella blockers.
