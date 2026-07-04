# Backlog

> Governed by `docs/00-master-plan.md`.
> Backlog items must be compatible with the master plan. No side tracks without a decision in `docs/07-decisions.md`.
> Historical done-items live in `docs/archive/legacy-06-backlog.md`.

---

## Now (Fas 1 — Current Truth Audit)

- [ ] Run `py -3.10 -m pytest` and record actual test count in `docs/01-current-truth.md`.
- [ ] Run `python -m scripts.run_release_gate_r1` and record result.
- [ ] Verify all endpoints listed in `docs/01-current-truth.md` against a running instance.
- [ ] Verify Gmail integration health (token valid, inbox sync working).
- [ ] Verify Monday integration (board connected, create_item works).
- [ ] Verify Fortnox integration (read works, preview works).
- [ ] Confirm `GET /pilot/readiness` returns `ready` for at least one tenant.
- [ ] Confirm approval queue works end-to-end (create → approve → dispatch).
- [ ] Update `docs/01-current-truth.md` with all verified results.
- [ ] Fix any bugs found during truth audit that block first customer.

---

## Next (Fas 2 — First Customer Pilot)

- [ ] Provision first internal test tenant.
- [ ] Connect Gmail inbox to test tenant.
- [ ] Verify inbox sync reads real mail and creates cases.
- [ ] Verify customer-facing UI shows correct dashboard for test tenant.
- [ ] Verify approval-gated email flow works for test tenant.
- [ ] Document any config steps needed for onboarding a pilot customer.
- [ ] Complete go/no-go checklist in `docs/02-first-customer-plan.md`.

---

## Later (Fas 3–4)

- [ ] Stabilize daily operations routine (scheduler, alerts, failed job triage).
- [ ] Package standard onboarding steps for next customer.
- [ ] Improve UI where pilot feedback shows clear need.
- [ ] Define pricing and document in `docs/07-decisions.md`.
- [ ] Plan Outlook/Microsoft Mail intake.

---

## Explicitly Not Now

These items are forbidden before first customer unless `docs/00-master-plan.md` is explicitly updated:

- React or any other frontend framework.
- New frontend-stack.
- SSO or enterprise RBAC.
- Self-serve billing or subscription management.
- Full integration marketplace.
- Körjournal, resejournal, tidsstämpling.
- New large integrations not required for first customer.
- Free bookkeeping automation (Fortnox must remain read/preview/approval-gated).
- Generell chatbot without operational control.
- Any branschspecifik module not needed for first customer.

---

## Known risks (carried from archived backlog)

- `app/api/routes/jobs.py` is dead code (not mounted) — remove or wire up when safe.
- No DB migration tooling — schema changes via `create_all` + runtime safeguard.
- Gmail token is short-lived; onboarding OAuth refresh not self-service for customer.
- `create_internal_task` is stubbed — no persistence beyond job result payload.
