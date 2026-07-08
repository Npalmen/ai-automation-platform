# Runbooks Index

> Operational procedures for the Krowolf AI Automation Platform.
> For product decisions: `docs/00-master-plan.md`.
> For current system state: `docs/01-current-truth.md`.

---

## Pilot readiness

| Document | Purpose |
|----------|---------|
| [`docs/PILOT_READINESS_CHECKLIST.md`](../PILOT_READINESS_CHECKLIST.md) | Full checklist before first customer pilot (BLOCKER / REQUIRED / RECOMMENDED / POST-PILOT) |
| [`docs/PHASE_O_CLOSURE_CHECKLIST.md`](../PHASE_O_CLOSURE_CHECKLIST.md) | Phase O conditional items (support email, pending approval, DB rotation, auto_actions) |

---

## Operational runbooks

| Runbook | When to use |
|---------|------------|
| [`monitoring-and-alerting.md`](monitoring-and-alerting.md) | Daily operator health check, cron setup, alert wiring, and failure response |
| [`pending-approvals.md`](pending-approvals.md) | Pending approval queue is building up, or an email_send approval must be handled |
| [`failed-jobs.md`](failed-jobs.md) | Jobs in `failed` or `manual_review` status that need recovery |
| [`oauth-errors.md`](oauth-errors.md) | Gmail `invalid_grant`, `unauthorized_client`, or token refresh failure |
| [`integration-errors.md`](integration-errors.md) | Monday 400/503, Gmail send failure, Fortnox error |
| [`incident-response.md`](incident-response.md) | Unexpected external write, repeated failures, approval queue flood |
| [`backup-and-restore.md`](backup-and-restore.md) | Taking backups before destructive operations; restoring from backup |
| [`customer-onboarding.md`](customer-onboarding.md) | Provisioning a new customer tenant |
| [`customer-offboarding.md`](customer-offboarding.md) | Deactivating a customer tenant safely |

---

## Quick reference — kill switches

```bash
# Pause a tenant's automation (blocks inbox sync and automated sends)
curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/pause-automation \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"reason"}'

# Pause a tenant's scheduler
curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/disable-scheduler \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"reason"}'

# Resume automation
curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/resume-automation \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"reason"}'

# Resume scheduler
curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/enable-scheduler \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"reason"}'
```

No global kill switch exists — each tenant is paused individually.

---

## Quick reference — health checks

```bash
# Production health
curl -sS https://api.krowolf.se/health

# Tenant integration health
curl -sS https://api.krowolf.se/integrations/health -H "X-API-Key: TENANT_KEY"

# Triage queue (all tenants, admin)
curl -sS https://api.krowolf.se/admin/operations/needs-help \
  -H "X-Admin-API-Key: ADMIN_API_KEY"

# Pending approvals (tenant)
curl -sS https://api.krowolf.se/approvals/pending -H "X-API-Key: TENANT_KEY"

# Scheduler status (tenant)
curl -sS https://api.krowolf.se/scheduler/status -H "X-API-Key: TENANT_KEY"

# Pilot readiness (tenant)
curl -sS https://api.krowolf.se/pilot/readiness -H "X-API-Key: TENANT_KEY"
```
