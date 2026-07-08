# Phase O Closure Checklist

> **Phase O decision:** CONDITIONAL GO (2026-07-08, commit `ad9b059`)
> **All live verification phases A–O:** PASSED
> **29/29 Phase O checks:** PASSED, 0 FAIL, 0 WARN
>
> This checklist records the explicit conditions from Phase O that must be
> satisfied before the first real customer pilot run. Each item is traceable
> to the Phase O evidence log in `docs/10-live-verification-plan.md`.

---

## CONDITION 1 — Set support email

**Status:** ⬜ Not done  
**Priority:** REQUIRED before pilot

Support email was confirmed empty (`""`) during Phase N/O inspection.
It must be set before any customer-facing communication is generated.

```bash
# Set support email for T_LIVE_TEST_001 (or the active pilot tenant)
curl -sS -X PUT https://api.krowolf.se/dashboard/control \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "support_email": "SUPPORT_EMAIL",
    "automation": {
      "leads_enabled": true,
      "support_enabled": true,
      "invoices_enabled": true,
      "followups_enabled": true,
      "demo_mode": false
    },
    "scheduler": {"run_mode": "manual"}
  }'

# Verify
curl -sS https://api.krowolf.se/dashboard/control \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Expect: "support_email": "SUPPORT_EMAIL"
```

**Done when:** `GET /dashboard/control` returns non-empty `support_email`.

---

## CONDITION 2 — Review and handle pending email_send approval

**Status:** ⬜ Not done  
**Priority:** BLOCKER — must be handled before pilot

During Phase O, 1 pending approval was found:
- `approval_id`: `eml_5d69...`
- `type`: `action_dispatch`
- `next_on_approve`: `email_send`
- `state`: `pending`

This approval, if approved, would trigger an outbound email. It must be explicitly reviewed by an operator.

```bash
# List current pending approvals
curl -sS https://api.krowolf.se/approvals/pending \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# If the approval is no longer intentional — reject it
curl -sS -X POST https://api.krowolf.se/approvals/eml_5d69.../reject \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"operator","note":"Phase O closure — reject unintentional email_send approval"}'

# If the approval IS intentional — approve only after confirming recipient,
# subject, and body are correct. Approving will send an email immediately.
curl -sS -X POST https://api.krowolf.se/approvals/eml_5d69.../approve \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"operator","note":"Phase O closure — approved with explicit operator review"}'
```

**Done when:** `GET /approvals/pending` returns `total: 0` or all remaining approvals are acknowledged and understood.

> **Warning:** Never approve an email_send approval without knowing exactly what email will be sent, to whom, and why. Approving cannot be undone.

---

## CONDITION 3 — Plan and schedule DB password rotation

**Status:** ⬜ Not done  
**Priority:** REQUIRED before pilot month 2 / RECOMMENDED for day 1

`POSTGRES_PASSWORD` is currently hardcoded directly in `docker-compose.prod.yml`.
A safe rotation plan exists in `docs/01-current-truth.md` (Phase N section).

**Rotation steps (requires maintenance window — do not execute during active pilot):**

1. Take a fresh DB backup:
   ```bash
   sudo docker exec krowolf-db-1 pg_dump -U postgres ai_platform \
     > /opt/krowolf/backups/pre-rotation-$(date +%Y%m%d-%H%M%S).sql
   ```
2. Generate a strong new password:
   ```bash
   openssl rand -base64 32
   ```
3. Add `POSTGRES_PASSWORD=<new>` to `/opt/krowolf/.env.production`.
4. Edit `docker-compose.prod.yml`: change `POSTGRES_PASSWORD: <hardcoded>` to `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`.
5. Update `DATABASE_URL` in `.env.production` to use the new password.
6. Alter the Postgres user:
   ```bash
   sudo docker exec krowolf-db-1 psql -U postgres \
     -c "ALTER USER postgres WITH PASSWORD '<new>';"
   ```
7. Recreate the app container:
   ```bash
   cd /opt/krowolf && sudo docker compose -f docker-compose.prod.yml up -d
   ```
8. Verify health:
   ```bash
   curl -sS https://api.krowolf.se/health
   curl -sS https://api.krowolf.se/tenant -H "X-API-Key: TENANT_KEY"
   ```
9. Keep old password in a secure location until rollback window passes (48h).

**Done when:** `POSTGRES_PASSWORD` is no longer hardcoded in compose; `/health` and a DB-backed endpoint return 200.

---

## CONDITION 4 — Keep auto_actions disabled until each external write is tested separately

**Status:** ⬜ Active constraint — must remain disabled  
**Priority:** BLOCKER

`auto_actions` must remain `false` for all job types during the pilot period.

```bash
# Verify auto_actions are disabled
curl -sS https://api.krowolf.se/tenant \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Expect: "auto_actions": {"lead": false, "customer_inquiry": false, "invoice": false}
```

**Enabling `auto_actions` must go through a separate, explicit decision for each job type:**
- `lead` → only after Monday write has been tested in isolation (see Condition 5)
- `customer_inquiry` → only after email send has been tested via the approval flow with a real recipient
- `invoice` → only after Fortnox export flow has been reviewed and tested

**Done when:** An explicit decision is made per job type, after isolated testing, and documented in `docs/07-decisions.md`.

---

## CONDITION 5 — Test Monday write in isolation before enabling auto_actions.lead

**Status:** ⬜ Not done  
**Priority:** REQUIRED before enabling `auto_actions.lead = true`

Monday item creation code is verified locally but has not been live-tested with a real write during verification (Phase L was read-only only).

```bash
# Controlled Monday write test — verify MONDAY_API_KEY and MONDAY_BOARD_ID are set first
curl -sS -X POST https://api.krowolf.se/integrations/monday/execute \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "create_item",
    "payload": {
      "item_name": "PILOT TEST — safe to delete"
    }
  }'
# Expect: HTTP 200 with created item details
# Then manually verify the item appears on the Monday board
# Then delete the test item from Monday manually
```

**Done when:** Monday item creation returns 200, item appears on board, and item is cleaned up.

---

## CONDITION 6 — Prepare drift and incident routines

**Status:** ⬜ Not done  
**Priority:** REQUIRED before pilot

Operators must know what to do when something goes wrong.

| Routine | Document |
|---------|----------|
| OAuth token expired | `docs/runbooks/oauth-errors.md` |
| Failed jobs in queue | `docs/runbooks/failed-jobs.md` |
| Integration write error | `docs/runbooks/integration-errors.md` |
| Pending approval backlog | `docs/runbooks/pending-approvals.md` |
| Customer onboarding | `docs/runbooks/customer-onboarding.md` |
| Customer offboarding | `docs/runbooks/customer-offboarding.md` |
| Incident response | `docs/runbooks/incident-response.md` |
| Backup and restore | `docs/runbooks/backup-and-restore.md` |

**Done when:** At least one operator has read all runbooks above and confirmed readiness.

---

## Closure Sign-off

```text
Phase O closure completed by: ___________
Date: ___________

Condition 1 — Support email set:          ⬜ Done / ⬜ Deferred (reason: ___)
Condition 2 — Pending approval handled:   ⬜ Done
Condition 3 — DB rotation scheduled:      ⬜ Done / ⬜ Deferred (reason: ___)
Condition 4 — auto_actions confirmed off: ⬜ Confirmed
Condition 5 — Monday write tested:        ⬜ Done / ⬜ Deferred (reason: ___)
Condition 6 — Runbooks read:              ⬜ Done

Pilot is GO with all BLOCKER conditions met: ⬜ Yes / ⬜ No (blockers: ___)
```

---

## Reference

- Full Phase O evidence: `docs/10-live-verification-plan.md` — Phase O section
- Current system state: `docs/01-current-truth.md`
- Pilot readiness checklist: `docs/PILOT_READINESS_CHECKLIST.md`
- Backlog status: `docs/06-backlog.md`
