# Runbook: Gmail onboarding verification (manual)

Gmail integration in the onboarding wizard is **honestly classified**:

| Aspect | Wizard status |
|--------|----------------|
| Label scope / query format | `locally_verified` via `POST …/integrations/gmail/verify` |
| Platform Gmail token | `platform_level` — env `GOOGLE_MAIL_ACCESS_TOKEN` |
| Tenant mailbox / live intake | `not_verifiable` in wizard |

## Operator steps (after wizard config)

1. Complete onboarding wizard integrations step with a valid `label_scope_slug` (e.g. tenant slug).
2. Run **Verifiera** in the panel — confirms server-built query `label:krowolf-{slug} is:unread`.
3. In Gmail (platform account), create label `krowolf-{slug}` if it does not exist.
4. Send a test mail to the intake mailbox and confirm it receives the label (manual).
5. Confirm scheduler / live scan remains **paused** after tenant activation (`intake.gmail.scheduler: paused`).

## What the wizard does not prove

- That the platform OAuth token can access the tenant mailbox
- That live intake routing works end-to-end

Document manual evidence (tenant id, label name, test message id) in the customer handoff notes.
