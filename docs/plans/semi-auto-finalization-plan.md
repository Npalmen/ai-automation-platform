---
name: Semi-auto finalisering
overview: Bevisa Gmail-svarens verkliga destination, korrigera reject-approval-kontraktet och slutföra semi-auto genom en begränsad canary följd av full kampanj
todos:
  - id: finalize-a-evidence-freeze
    content: Frys och korrelera runtimeevidens från run 30228379236
    status: completed
  - id: finalize-b-gmail-forensics
    content: Fastställ faktisk Gmail-destination, providerobjekt, headers, OAuth-scope och recipient-verifiering
    status: completed
  - id: finalize-c-reject-approval-truth
    content: Identifiera exakt vilka approval rows förblir pending efter reject och varför
    status: completed
  - id: finalize-d-bounded-fixes
    content: Implementera minsta bevisade Gmail-, approval-, harness- eller rapporteringsfix
    status: completed
  - id: finalize-e-regression-delivery
    content: Kör tester, PR, CI, merge och post-merge Release Gate
    status: in_progress
  - id: finalize-f-two-scenario-canary
    content: Kör en approve- och en reject-canary med strikt budget
    status: pending
  - id: finalize-g-full-semi-auto
    content: Kör full TBSM01-TBSM08-kampanj endast efter godkänd canary
    status: pending
  - id: finalize-h-closure
    content: Stäng todo D eller rapportera verifierat kvarstående block
    status: pending
isProject: true
---

# Semi-auto finalisering

**Failed run:** `30231548426` @ `a25ccc738` — canary 1/2 PASS (TBSM04), TBSM01 recipient verify FAIL, budget harness `1 != 4`  
**Prior failed full run:** `30228379236` @ `3837c739` — 1/8 PASS (TBSM08)  
**Branch:** `fix/semi-auto-recipient-verification-canary-budget`  
**Prior fixes:** PR #69–#73 (operator-gate, newsletter marker, Re: parser, recipient Sent fallback, API pending)

## Blockerare (run 30228379236)

| Scenario | Result | failure_category |
|----------|--------|------------------|
| TBSM01–03 | FAIL | outcome_unknown (`provider_accepted`, `recipient_verified=0`) |
| TBSM04–05 | FAIL | unexpected pending approval |
| TBSM06 | FAIL | outcome_unknown |
| TBSM07 | FAIL | unexpected pending approval |
| TBSM08 | PASS | — |

**Budget:** sends 8/8, provider_accepted 4, recipient_verified 0, unauthorized 0, external writes 0.

## A. Evidence freeze

Korrelera run `30228379236` mot `origin/main` @ `3837c739`. Lokal rapport (ej committad): `storage/status/semi-auto-finalization-evidence.md`.

## B. Gmail forensics (read-only, inga nya sends)

1. Hämta provider message-ID från adapter/integration/decision/DB.
2. `messages.get` mot sändande appkonto.
3. Jämför faktisk `To` mot allowlistad testbotsändare vs fixture-avsändare.
4. Verifiera Sent/All Mail på app- och mottagarkonto.
5. Sök med RFC Message-ID, run-ID, scenario-ID — inte enbart subject.
6. Slutklassificera per svar (tillåtna statusar enligt mandat).

## C. Reject approval truth

För TBSM04/05/07: DB + `/jobs/{id}/approvals` efter operatorfas. Rapportera approval-ID, delivery type, action type, state, version, target/non-target. Hypotes: legacy `next_on_approve=action_dispatch` rad kvar pending efter per-action reject.

## D. Minsta bevisade fix

Tillåtet scope:

- Gmail reply recipient derivation / allowlist
- Provider message-ID persistence
- Recipient verification (`in:anywhere`, RFC Message-ID, provider-ID)
- Legacy job-level approval suppression vid per-action materialisering
- Target-scopade pending assertions
- Riktade tester

## E. Regression och leverans

Hermetic + live-eval + PostgreSQL + Release Gate → PR → squash-merge → post-merge Release Gate. Högst två fixcykler före canary.

## F. Tvåscenariocanary

TBSM01 (approve + 1 verified reply) + TBSM04 (reject + 0 replies). Budget: 2 sends, 1 reply. Ingen full kampanj före PASS.

## G. Full semi-auto-kampanj

Endast efter canary PASS: TBSM01–08, 8 sends, 4 verified replies, 7/7 target approvals korrekta, 0 oväntade pending.

## H. Closure

Vid 8/8: markera `testbot-d-semi-automatic-campaign = completed`, uppdatera lokala rapporter (ej commit), stoppa med operatorauth för todo E.
