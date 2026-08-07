# Reply quality — known limitations

Verified after R5 closure (`PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED=VALID`).

## Qualification scope

- Qualification covers **profile-driven digital coworker reply quality** on `TENANT_LIVE_EVAL` only.
- It does **not** enable automatic Gmail, production activation, or full testbot PASS.
- `PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED` and `PROFILE_DRIVEN_TESTBOT_PASS` remain **PENDING**.

## Live evidence boundaries

- R4 PASS is bound exclusively to **Attempt 12** (`b4dcd6a8-9bda-4ce4-8b63-4e7a54176605`).
- R4 Attempts 1–11 are permanently quarantined and must never contribute to qualification counts.
- R3 PASS remains the frozen-body canary (`5e9b1839…`); R4 uses reviewed live candidate bodies (`b7fd95e…`).

## Human review

- R2 PASS is based on the locked scored review artifact (`7dced592…`), not regenerated candidates.
- Human review cannot override hard-safety failures.

## Operational

- Replies still require approval before Gmail send in production paths.
- Feature flag `DIGITAL_COWORKER_REPLY_ENABLED` remains eval-scoped per DEC-050.
- Registry provenance references qualifying executor `4ad74d4…` and Release Gate `31220948265`, not ad-hoc closure merge SHAs.

## Non-goals (unchanged)

See parent plan §20: no production Gmail activation, no automatic send, no external business writes beyond qualified eval campaigns.
