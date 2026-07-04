> Archived document. Historical reference only. Current governing source is docs/00-master-plan.md.

# 5-Customer Launch Checklist

This checklist is the final go/no-go gate for selling the MVP to 5 controlled customers.

## Required product state

- Customer UI shows: overview, ROI/results, cases, activity log, settings, account and team metadata.
- Krowolf admin UI shows: all customers, customer health, needs-help queue, integrations, readiness and logs.
- All tenant writes remain approval-gated where required; no customer-facing flow exposes raw payloads, job IDs, routing hints or environment details.
- Tenant auth is configured through DB-backed keys or `TENANT_API_KEYS`; production must fail closed if neither exists.
- `ADMIN_API_KEY` is configured and treated as pilot-only browser auth, protected by network controls.

## Per-customer onboarding checklist

1. Provision tenant in Super Admin and store the one-time API key securely.
2. Add customer account metadata: company, contact, support email and team contacts.
3. Configure modules, integrations and automation levels.
4. Run setup verification and Redo för drift.
5. Create or seed a demo/test lead if needed.
6. Verify customer dashboard shows health, ROI and recent activity.
7. Confirm email approvals and controlled dispatch remain approval-gated.
8. Set notification recipient and daily digest hour.

## Technical release gate

Run before pilot launch and before each production deploy:

```bash
python scripts/run_release_gate_r1.py --verbose
python -m pytest
docker build -t ai-automation-platform:release .
docker compose -f docker-compose.prod.yml config
python scripts/smoke_check.py --base-url https://api.krowolf.se --expect-production
```

If admin and tenant keys are available in the deployment environment, also run:

```bash
# Admin surface smoke check (admin overview + needs-help)
python scripts/smoke_check.py --base-url https://api.krowolf.se --expect-production --admin-api-key <ADMIN_API_KEY>

# Tenant surface smoke check (integration health + scheduler status + pilot readiness)
python scripts/smoke_check.py --base-url https://api.krowolf.se --tenant-api-key <TENANT_API_KEY>
```

## Backup and operational readiness gate

Before going live with any customer, confirm:

- [ ] A daily backup cron job is configured and has produced at least one successful backup.
- [ ] A restore rehearsal has been completed within the past 30 days (see `docs/12-production-guide.md#restore-rehearsal`).
- [ ] The backup file is stored on a separate volume or object storage account from the application server.
- [ ] The super admin needs-help queue (`GET /admin/operations/needs-help`) shows 0 critical rows for each pilot tenant.
- [ ] The failed-job triage runbook (`docs/runbook-pilot-support.md#misslyckade-jobb--triage`) is accessible to all support owners.
- [ ] At least one support owner has read and understood the failed-job triage procedure.

## Sellability gate

The product is ready for 5 controlled customers when:

- All release-gate tests pass.
- Production smoke check passes after deploy.
- Each pilot tenant has Redo för drift at green or only documented yellow warnings.
- Super Admin shows no critical errors in the needs-help queue (`GET /admin/operations/needs-help`).
- Backup and operational readiness gate above is fully checked.
- Krowolf has a named support owner for each customer.
- Known non-MVP limitations are documented before the sale: no SSO, no self-serve billing, no rate limiting inside the app, no enterprise RBAC, no automated backup (must be wired externally), and no job replay queue (failed jobs must be re-triggered via the API or case detail UI).
