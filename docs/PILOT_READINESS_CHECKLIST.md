# Pilot Readiness Checklist

> **Governing document:** `docs/00-master-plan.md`
> **Current verified state:** `docs/01-current-truth.md`
> **Phase O decision:** CONDITIONAL GO (2026-07-08)
>
> This checklist must be completed before the first real customer pilot run.
> A single operator must be able to read this document and understand exactly
> what must be done, in what order, and why.

---

## Classification

| Class | Meaning |
|-------|---------|
| **BLOCKER** | Pilot cannot start. Fix before any customer data enters the system. |
| **REQUIRED** | Must be done before pilot. Not a hard blocker but skipping creates serious operational risk. |
| **RECOMMENDED** | Strongly recommended. Acceptable to carry 24–72h into pilot with documented acknowledgement. |
| **POST-PILOT** | Defer until after a stable pilot period. Document and track. |

---

## Safety Prerequisites (BLOCKER)

- [ ] **BLOCKER** — `auto_actions` is `false` for all job types for all pilot tenants.
  ```bash
  # Verify
  curl -sS https://api.krowolf.se/tenant \
    -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
  # Expect: "auto_actions": {"lead": false, "customer_inquiry": false, "invoice": false}

  # Disable if not already false
  curl -sS -X PUT https://api.krowolf.se/tenant/config \
    -H "X-API-Key: TENANT_KEY" \
    -H "Content-Type: application/json" \
    -d '{"enabled_job_types":["lead","customer_inquiry"],"allowed_integrations":["google_mail","monday"],"auto_actions":{"lead":false,"customer_inquiry":false,"invoice":false}}'
  ```

- [ ] **BLOCKER** — All pending `email_send` approvals have been reviewed and handled (rejected or deliberately approved) before pilot starts.
  ```bash
  # List pending approvals and inspect next_on_approve field
  curl -sS https://api.krowolf.se/approvals/pending \
    -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
  # For any pending email_send approval that is NOT intentional:
  curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/reject \
    -H "X-API-Key: TENANT_KEY" \
    -H "Content-Type: application/json" \
    -d '{"actor":"operator","note":"rejected before pilot — not intentional"}'
  ```

- [ ] **BLOCKER** — Gmail send is approval-gated. Verify `auto_actions.customer_inquiry = false` and no approval has been pre-approved that would dispatch an outbound email.

- [ ] **BLOCKER** — No mass-send mechanism is enabled. There is no batch-send route. Confirm no integration events show `gmail_send` that was not manually approved.
  ```bash
  curl -sS https://api.krowolf.se/integration-events \
    -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
  # Expect: empty list or only controlled events — no unexpected gmail_send
  ```

- [ ] **BLOCKER** — Tenant isolation confirmed. A second tenant's key must not expose the pilot tenant's data.
  Reference: `docs/01-current-truth.md` — Phase E/O cross-tenant checks PASSED.

---

## Infrastructure (BLOCKER / REQUIRED)

- [ ] **BLOCKER** — Production app health check returns 200 with `env: production`.
  ```bash
  curl -sS https://api.krowolf.se/health
  # Expect: {"status":"ok","app_name":"Krowolf","env":"production"}
  ```

- [ ] **BLOCKER** — Database is reachable and healthy (app startup confirms DB tables created).
  ```bash
  # On server
  sudo docker exec krowolf-db-1 psql -U postgres -d ai_platform -c "SELECT 1;"
  # Expect: (1 row)
  ```

- [ ] **BLOCKER** — Local PostgreSQL backup exists, is recent (< 25h old), and passes integrity check.
  Local backups alone are **not sufficient** — a server failure destroys both data and local backups.
  ```bash
  # Check local backup exists and is recent
  sudo BACKUP_DIR=/opt/krowolf/backups POSTGRES_DB=ai_platform \
    bash /opt/krowolf/scripts/check_backup_freshness.sh
  # Expect: all lines "OK", exit 0
  ```

- [ ] **BLOCKER** — Offsite backup is configured, and at least one copy has been verified in remote storage.
  Local-only backups are not acceptable for first real customer pilot.
  `OFFSITE_BACKUP_COMMAND` must be set and a test upload must be confirmed before pilot.
  ```bash
  # Confirm OFFSITE_BACKUP_COMMAND is set in /opt/krowolf/.env.production
  sudo grep 'OFFSITE_BACKUP_COMMAND' /opt/krowolf/.env.production
  # Must be non-empty

  # Run a manual backup and verify the offsite copy was created
  sudo DOCKER_DB_CONTAINER=krowolf-db-1 POSTGRES_DB=ai_platform \
    BACKUP_DIR=/opt/krowolf/backups \
    bash /opt/krowolf/scripts/backup_postgres.sh
  # Expect: "[backup] Offsite upload completed." — NOT the warning line

  # Verify the file appears in remote storage (command depends on provider):
  # rclone ls remote:krowolf-backups/ | tail -3
  # aws s3 ls s3://your-bucket/krowolf-backups/ | tail -3
  ```

- [ ] **BLOCKER** — Restore rehearsal completed using a real production backup.
  A restore rehearsal is **required** before first real customer pilot — not optional.
  ```bash
  # Run the restore rehearsal script (verifies 6 core tables)
  sudo DOCKER_DB_CONTAINER=krowolf-db-1 \
    RESTORE_SOURCE_FILE=/opt/krowolf/backups/ai_platform_YYYY-MM-DD-HHMMSS.sql.gz \
    RESTORE_TARGET_DB=ai_platform_restore_test \
    bash /opt/krowolf/scripts/restore_postgres_rehearsal.sh
  # Expect: all tables verified with row counts matching production, exit 0
  # See docs/runbooks/backup-and-restore.md for full procedure
  ```

- [ ] **REQUIRED** — Container status: app, db, and caddy all running without restart loops.
  ```bash
  sudo docker compose -f /opt/krowolf/docker-compose.prod.yml ps
  # Expect: app Up, db Up, caddy Up — no "Restarting" status
  ```

- [ ] **REQUIRED** — Production healthcheck script deployed and passing.
  One command covers app HTTP, containers, disk, and backup freshness:
  ```bash
  sudo \
    APP_BASE_URL=https://api.krowolf.se \
    DOCKER_APP_CONTAINER=krowolf-app-1 \
    DOCKER_DB_CONTAINER=krowolf-db-1 \
    DISK_CHECK_PATH=/opt/krowolf \
    BACKUP_DIR=/opt/krowolf/backups \
    bash /opt/krowolf/scripts/check_production_health.sh
  # Expect: all [PASS], exit 0, summary line "HEALTHY"
  # See docs/runbooks/monitoring-and-alerting.md for setup
  ```

- [ ] **REQUIRED** — Healthcheck cron job scheduled (every 5 minutes during pilot).
  See `docs/runbooks/monitoring-and-alerting.md` — Cron setup section.

- [ ] **RECOMMENDED** — `ALERT_COMMAND` configured so failures trigger an email or webhook.
  Set in `/opt/krowolf/.env.production` — do not commit real addresses.
  See `docs/runbooks/monitoring-and-alerting.md` — Alert setup section.

- [ ] **RECOMMENDED** — Disk monitoring alerts when usage ≥ 80% (covered by health script above).

- [ ] **RECOMMENDED** — Container restart monitoring enabled (covered by health script above).

---

## Tenant Configuration (REQUIRED)

- [ ] **REQUIRED** — Support email is configured for the pilot tenant.
  ```bash
  # Check current value
  curl -sS https://api.krowolf.se/dashboard/control \
    -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
  # Expect: "support_email": "support@krowolf.se" (non-empty)

  # Set if missing
  curl -sS -X PUT https://api.krowolf.se/dashboard/control \
    -H "X-API-Key: TENANT_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "support_email": "SUPPORT_EMAIL",
      "automation": {"leads_enabled":true,"support_enabled":true,"invoices_enabled":true,"followups_enabled":true,"demo_mode":false},
      "scheduler": {"run_mode":"manual"}
    }'
  ```

- [ ] **REQUIRED** — Scheduler `run_mode` is `manual` or `paused` (not `scheduled`) until operator explicitly enables it.
  ```bash
  curl -sS https://api.krowolf.se/scheduler/status \
    -H "X-API-Key: TENANT_KEY"
  # Expect: "run_mode": "manual" or "paused"
  ```

- [ ] **REQUIRED** — `demo_mode` is `false` (allows inbox sync and live send when approved).
  ```bash
  curl -sS https://api.krowolf.se/dashboard/control \
    -H "X-API-Key: TENANT_KEY"
  # Expect: "automation": {"demo_mode": false, ...}
  ```

- [ ] **REQUIRED** — Pilot readiness check passes or only shows expected warnings.
  ```bash
  curl -sS https://api.krowolf.se/pilot/readiness \
    -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
  # Expect: overall_status "almost_ready" or "ready"
  # Acceptable warnings: onboarding steps, routing hints
  # Not acceptable: 0 failures with unexpected auth/isolation fails
  ```

- [ ] **REQUIRED** — Integration health shows expected state (no `error` status).
  ```bash
  curl -sS https://api.krowolf.se/integrations/health \
    -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
  # Expect: overall_status "warning" (configured but not dispatched yet) or "healthy"
  # NOT acceptable: overall_status "error"
  ```

---

## Approval Flow (REQUIRED)

- [ ] **REQUIRED** — Approval flow is functional: pending approvals are visible, reject works without side effects.
  Reference: `docs/01-current-truth.md` — Phase G PASSED.

- [ ] **REQUIRED** — Operator knows which approval `next_on_approve` values exist and what each triggers:
  - `action_dispatch` — resumes pipeline, may dispatch internal task
  - `email_send` — sends an email to the customer; requires explicit operator approval
  - `finance_fortnox_export` — exports invoice to Fortnox (not active in pilot)
  - `controlled_dispatch` — resumes a controlled external dispatch

- [ ] **REQUIRED** — At least one operator can access and action the approval queue before pilot starts.

- [ ] **REQUIRED** — There is no automated approval flow (no route that auto-approves). Confirm in logs.

---

## Kill Switches (REQUIRED)

- [ ] **REQUIRED** — Per-tenant automation pause verified. Operator knows the pause command.
  ```bash
  # Emergency pause — blocks inbox sync and demo mode sends
  curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/pause-automation \
    -H "X-Admin-API-Key: ADMIN_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"actor":"operator","note":"pilot precautionary pause"}'

  # Pause scheduler separately
  curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/disable-scheduler \
    -H "X-Admin-API-Key: ADMIN_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"actor":"operator","note":"pilot precautionary pause"}'
  ```

- [ ] **REQUIRED** — Scheduler disable verified. Operator knows the disable command (above).

- [ ] **REQUIRED** — Operator knows that `PUT /dashboard/control` with `scheduler.run_mode: "paused"` is the tenant-scoped equivalent.
  ```bash
  curl -sS -X PUT https://api.krowolf.se/dashboard/control \
    -H "X-API-Key: TENANT_KEY" \
    -H "Content-Type: application/json" \
    -d '{"automation":{"leads_enabled":true,"support_enabled":true,"invoices_enabled":true,"followups_enabled":true,"demo_mode":false},"scheduler":{"run_mode":"paused"}}'
  ```

- [ ] **REQUIRED** — Note: there is no global kill switch for all tenants. Each tenant must be paused individually via `pause-automation` + `disable-scheduler`.

---

## Operational Routines (REQUIRED)

- [ ] **REQUIRED** — OAuth error routine exists and is documented. See `docs/runbooks/oauth-errors.md`.

- [ ] **REQUIRED** — Failed job routine exists and is documented. See `docs/runbooks/failed-jobs.md`.

- [ ] **REQUIRED** — Integration error routine exists and is documented. See `docs/runbooks/integration-errors.md`.

- [ ] **REQUIRED** — Pending approvals routine exists and is documented. See `docs/runbooks/pending-approvals.md`.

- [ ] **REQUIRED** — Customer onboarding runbook exists. See `docs/runbooks/customer-onboarding.md`.

- [ ] **REQUIRED** — Customer offboarding runbook exists. See `docs/runbooks/customer-offboarding.md`.

- [ ] **REQUIRED** — Incident response procedure exists. See `docs/runbooks/incident-response.md`.

- [ ] **REQUIRED** — Backup and restore procedure exists. See `docs/runbooks/backup-and-restore.md`.

---

## Drift Checks (RECOMMENDED)

- [ ] **RECOMMENDED** — Confirm live code commit matches expected `git log --oneline -1` on server.
  ```bash
  ssh ubuntu@api.krowolf.se "cd /opt/krowolf && git log --oneline -1"
  # Expect: ad9b059 or latest known-good commit
  ```

- [ ] **RECOMMENDED** — Confirm no untracked environment variable changes since last review.
  ```bash
  ssh ubuntu@api.krowolf.se "sudo grep -c '=' /opt/krowolf/.env.production"
  ```

- [ ] **RECOMMENDED** — Alerts are configured for the pilot tenant.
  ```bash
  curl -sS https://api.krowolf.se/alerts/config \
    -H "X-API-Key: TENANT_KEY"
  # Check: enabled=true, recipient_email set
  ```

- [ ] **RECOMMENDED** — Needs-help triage queue is empty or understood before pilot.
  ```bash
  curl -sS https://api.krowolf.se/admin/operations/needs-help \
    -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool
  # Acceptable: total=0 or known acknowledged items
  ```

---

## Security (RECOMMENDED)

- [ ] **RECOMMENDED** — DB password is not the default value. Rotation plan exists (see `docs/01-current-truth.md`).

- [ ] **RECOMMENDED** — `ADMIN_API_KEY` is a strong random value (not a dev-mode default).

- [ ] **RECOMMENDED** — No secrets appear in application logs.
  ```bash
  ssh ubuntu@api.krowolf.se "sudo docker compose -f /opt/krowolf/docker-compose.prod.yml logs --tail=200 app | grep -Ei 'access_token=|refresh_token=|client_secret=|password=' || echo CLEAN"
  ```

- [ ] **RECOMMENDED** — Production docs endpoints return 404.
  ```bash
  curl -o /dev/null -w '%{http_code}' https://api.krowolf.se/docs      # expect 404
  curl -o /dev/null -w '%{http_code}' https://api.krowolf.se/openapi.json # expect 404
  ```

---

## Monday Integration (REQUIRED — before enabling `auto_actions.lead`)

- [ ] **REQUIRED** — Monday live write tested in isolation before enabling `auto_actions.lead = true` for any tenant.
  - Keep `auto_actions.lead = false` during the first pilot period.
  - Test Monday item creation manually via `POST /integrations/monday/execute` before enabling.
  - See `docs/runbooks/integration-errors.md` for Monday troubleshooting.

---

## Post-Pilot Items (POST-PILOT)

- [ ] **POST-PILOT** — DB migration tooling (currently uses `create_all` + runtime safeguards).
- [ ] **POST-PILOT** — Pagination controls in the operator UI jobs list.
- [ ] **POST-PILOT** — Fortnox access token verified and live invoice export tested end-to-end.
- [ ] **POST-PILOT** — Visma OAuth flow tested end-to-end.
- [ ] **POST-PILOT** — Microsoft Mail intake configured and tested.
- [ ] **POST-PILOT** — Self-serve customer onboarding flow.
- [ ] **POST-PILOT** — Automated restore rehearsal on a schedule.

---

## Sign-off

Before first pilot run, an operator must confirm:

```text
Date: ___________
Operator: ___________

All BLOCKER items: ⬜ Complete
All REQUIRED items: ⬜ Complete / ⬜ Acknowledged with documented risk
Support email set: ⬜ Yes
Pending email_send approvals reviewed: ⬜ Yes
auto_actions = false: ⬜ Confirmed
Kill switch commands known: ⬜ Confirmed
Runbooks read: ⬜ Confirmed
```

> **Safety principle:** If in doubt, pause first. It is always safe to set `demo_mode = true` or `run_mode = "paused"`. It is never safe to approve an unknown pending approval.
