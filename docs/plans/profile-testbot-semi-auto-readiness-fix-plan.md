---
name: Profile testbot semi-auto readiness fix
overview: Korrigera single-active-consumer-readiness, verifiera verkligt levererbara testmailboxar och återkör read-only readiness innan någon live Gmail-kampanj godkänns.
todos:
  - id: readiness-fix-a-current-truth
    content: Inventera readinessflödet, blockeringssemantik och mailboxkonfiguration
    status: completed
  - id: readiness-fix-b-consumer-semantics
    content: Korrigera single-active-consumer-kontrollen så avsiktligt blockerade tenants inte blir falska readiness-blockers
    status: completed
  - id: readiness-fix-c-mailbox-deliverability
    content: Verifiera att sender och recipient är verkligt levererbara, dedikerade och separerade från P1
    status: completed
  - id: readiness-fix-d-tests
    content: Lägg regressionstester för consumer isolation, blockerade tenants och mailbox-readiness
    status: completed
  - id: readiness-fix-e-delivery
    content: Kör gates, PR, merge och post-merge read-only readiness
    status: in_progress
  - id: readiness-fix-f-operator-gate
    content: Stoppa före livekampanj och begär nytt operatörsgodkännande
    status: pending
isProject: true
---

# Profile testbot — Semi-auto live readiness-fix

## 1. Beslut

40-scenario live semi-auto Gmail-kampanjen är **inte godkänd ännu**.

Två readinessfrågor måste stängas först:

1. `ready_for_live_semi_auto` är felaktigt `False` eftersom `_validate_single_active_consumer()` räknar avsiktliga blockeringsmeddelanden för pilot- och demo-tenants som readiness-blockers.
2. Sender- och recipientallowlist måste verifieras som verkligt levererbara, dedikerade testmailboxar. Om `sender@eval.test` och `recipient@eval.test` är bokstavliga adresser är de inte giltiga för en verklig Gmail-kampanj. Om de är redigerade placeholders ska readinessrapporten uttryckligen ange detta och verifiera de verkliga mailboxarna utan att exponera dem.

Ingen live Gmail-send är auktoriserad i detta uppdrag.

## 2. Önskad readinesssemantik

`ready_for_live_semi_auto` ska vara `True` endast när samtliga följande är uppfyllda:

- eval tenant är exakt `TENANT_LIVE_EVAL`,
- production pilot tenant är uttryckligen blockerad,
- demo tenant är uttryckligen blockerad,
- ingen blockerad tenant kan konsumera eval-mailboxen,
- exakt en aktiv consumer finns för varje testmailbox,
- sender och recipient är separata, levererbara testmailboxar,
- P1-mailboxen är blockerad,
- OAuth är giltig utan tokenexponering,
- scenario manifest = 40,
- `send_after_approval` = 20,
- hold/reject/no_reply = 20,
- total send budget = 20,
- max send per scenario = 1,
- Sheets/Monday/Visma writes = 0,
- automatic verify/link/merge = 0,
- profile ID/hash matchar,
- hard safety, decision och reply-contract är qualification authority,
- semantic judge är inte qualification authority,
- cleanup readiness PASS,
- live qualifications är fortsatt PENDING.

Avsiktligt blockerade resurser ska redovisas som positiva safety assertions, inte som readinessfel.

Exempel:

```text
production_pilot_blocked = true
demo_tenant_blocked = true
single_active_consumer = true
ready_for_live_semi_auto = true
```

## 3. Current-truth

Inventera:

- `_validate_single_active_consumer()`,
- `validate_no_production_resources()`,
- readiness-resultatets datastruktur,
- hur blockers, warnings och safety assertions representeras,
- mailbox/OAuth registry,
- tenant-to-mailbox binding,
- scheduler/intake state per tenant,
- sender/recipient allowlists,
- hur rapporten redigerar mailboxadresser.

Identifiera exakt varför positiva blockeringsresultat läggs i blocker-listan.

Ändra inte bredare gate- eller tenantlogik.

## 4. Minimal fix

Separera minst:

```text
blocking_failures
safety_assertions
warnings
```

Följande ska vara `safety_assertions`:

- production pilot tenant blocked,
- demo tenant blocked,
- P1 mailbox blocked,
- forbidden integrations blocked.

Följande ska vara `blocking_failures`:

- fler än en aktiv consumer,
- eval tenant saknas,
- production/demo tenant kan konsumera samma mailbox,
- sender eller recipient saknas,
- sender = recipient när kontraktet kräver två mailboxar,
- mailbox inte levererbar eller inte providerverifierad,
- P1-mailbox används,
- OAuth saknas/ogiltig,
- write budget saknas eller överskrids,
- cleanup readiness fail,
- profile/manifest mismatch.

`ready_for_live_semi_auto` ska baseras endast på verkliga blocking failures.

## 5. Mailboxkrav

Verifiera i readiness utan att exponera adresser:

- sender är en verklig provideransluten testmailbox,
- recipient är en verklig levererbar testmailbox,
- de är dedikerade till eval,
- de används inte av P1,
- de används inte av demo-tenant,
- exakt en aktiv consumer per mailbox,
- recipient kan verifieras efter send,
- campaign messages kan korreleras,
- mailboxarna kan städas eller filtreras via campaign marker.

Rapportera:

```text
sender_mailbox_hash
recipient_mailbox_hash
sender_provider_verified
recipient_deliverability_verified
single_active_consumer
```

Exponera inte fullständiga mailboxadresser i artifacts eller docs.

## 6. Tester

Minst:

1. Blockerad production pilot tenant är safety assertion, inte blocker.
2. Blockerad demo tenant är safety assertion, inte blocker.
3. P1 mailbox blocked är safety assertion.
4. En aktiv eval consumer ger PASS.
5. Två aktiva consumers ger FAIL.
6. Pausad men manuellt triggbart konkurrerande tenant bedöms enligt faktiskt consumerkontrakt.
7. Eval tenant saknas ger FAIL.
8. Sender saknas ger FAIL.
9. Recipient saknas ger FAIL.
10. Bokstavlig `.test`-adress eller annan icke-levererbar placeholder ger FAIL för live readiness.
11. Redigerad rapport kan representera verklig mailbox utan att exponera den.
12. Sender/recipient som överlappar P1 ger FAIL.
13. OAuth saknas ger FAIL.
14. Write budget mismatch ger FAIL.
15. Production/demo blocking förblir aktiv efter fix.
16. `ready_for_live_semi_auto=True` endast vid full readiness.
17. Live qualifications förblir PENDING.
18. Ingen Gmail-send sker i tester eller readiness.
19. Profile-testbot regressioner PASS.
20. Full Release Gate och Regression Main PASS.

## 7. Delivery

Arbeta på branch:

```text
fix/profile-testbot-semi-auto-readiness
```

Genomför:

1. skapa och lås denna planfil,
2. inventera readinesssemantiken,
3. implementera minsta fix,
4. implementera mailbox-deliverability/readiness,
5. lägg regressionstester,
6. kör profile-testbot tests,
7. kör hermetisk 120-scenario campaign,
8. kör full Release Gate,
9. öppna avgränsad PR,
10. squash-merga,
11. verifiera post-merge Release Gate och Regression Main,
12. kör read-only readiness på mergad SHA,
13. skapa lokal readinessrapport,
14. stoppa före livekampanj.

Ingen GitHub environment approval och ingen live Gmail-send får ske.

## 8. Stopp

Stoppa endast när readiness visar:

```text
ready_for_live_semi_auto = true
blocking_failures = []
```

och rapportera:

- PR,
- merge-SHA,
- post-merge gates,
- hermetisk campaign,
- eval tenant,
- single-active-consumer-resultat,
- redigerade mailbox-hashar,
- provider/deliverability checks,
- scenariofördelning,
- send budget,
- qualification authority,
- qualifications fortsatt PENDING.

Stoppa med:

```text
OPERATOR ACTION REQUIRED — Godkänn 40-scenario live semi-auto Gmail-kampanj
```
