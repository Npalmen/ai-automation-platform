# Inbox quality qualification — known limitations

**Status:** Post Todo J closure (`PROFILE_DRIVEN_SEMI_AUTO_QUALITY_QUALIFIED` VALID @ `128aacee5567d4d8ed762e25192c766494e7b634`)

## Scope boundaries

- Qualification binds to isolated `TENANT_LIVE_EVAL` with dedicated eval mailboxes only.
- Semi-auto approval-gated Gmail replies only; automatic Gmail remains unqualified (`PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED` PENDING).
- Full profile testbot PASS aggregate remains open (`PROFILE_DRIVEN_TESTBOT_PASS` PENDING).
- Production pilot activation is not implied by this qualification.

## Oracle and evaluation limits

- Semantic judge oracle is stubbed and is not qualification authority.
- Live campaigns use `gpt-4o-mini` for classification/extraction; hermetic gates use deterministic contracts.
- Quality dataset v1 (96 scenarios) and locked canary/campaign manifests must be re-run after contract or dataset version bumps.

## Re-qualification triggers

Re-qualification is required after changes to:

- quality oracle contract
- quality dataset version
- thread/replay semantics
- safe-ack eligibility contract
- profile snapshot hash for `niklas-demo-live-eval-v1`

## Operational notes

- Live quality execution requires operator-approved runtime SHA, OAuth readiness, and explicit runner approval flags.
- Duplicate/hold scenarios must not materialize customer-facing drafts; hold paths rely on safe-ack eligibility blocking and decision oracles.
- Re-running live quality after registry registration requires explicit operator authorization and a new campaign id.
