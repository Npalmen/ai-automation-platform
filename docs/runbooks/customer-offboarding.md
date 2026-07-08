# Runbook: Customer Offboarding

> **Safety:** Pause automation before deactivating a tenant. Never delete production data without a backup.
> **Isolation:** Deactivating a tenant makes their API key return 403. Existing data is retained in the DB.

---

## Overview

This runbook covers safely removing a customer from active use. Data is not deleted — the tenant is deactivated and the API key is invalidated. Data retention and deletion follow your data handling policy.

---

## Pre-offboarding checklist

Before deactivating a tenant:

- [ ] Take a DB backup: `docs/runbooks/backup-and-restore.md`
- [ ] Confirm all pending approvals have been handled (approved or rejected)
- [ ] Confirm no active Gmail inbox sync is in progress
- [ ] Notify the customer that access will be revoked
- [ ] Confirm data retention requirements (export if needed before deactivation)

---

## Step 1: Pause automation and scheduler

```bash
curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/pause-automation \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"offboarding — pausing automation"}'

curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/disable-scheduler \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"offboarding — disabling scheduler"}'
```

---

## Step 2: Drain the approval queue

```bash
# List pending approvals
curl -sS https://api.krowolf.se/approvals/pending \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# Reject all pending approvals with offboarding note
# (repeat for each approval_id)
curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/reject \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"offboarding — rejecting pending approval"}'
```

---

## Step 3: Take a final DB backup

```bash
ssh ubuntu@api.krowolf.se \
  "sudo docker exec krowolf-db-1 pg_dump -U postgres ai_platform \
   > /opt/krowolf/backups/offboarding-TENANT_ID-$(date +%Y%m%d-%H%M%S).sql"
```

---

## Step 4: Export tenant data (if required by data retention policy)

Currently no automated export endpoint exists. Export the tenant's data manually from the backup if needed before deactivation.

---

## Step 5: Deactivate the tenant

```bash
curl -sS -X PATCH https://api.krowolf.se/admin/tenants/TENANT_ID/status \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status":"inactive"}'
```

**Expected:** tenant status changes to `inactive`. All API calls with the tenant's key will now return `403`.

---

## Step 6: Verify deactivation

```bash
# Tenant key must now return 403
curl -o /dev/null -w '%{http_code}' https://api.krowolf.se/tenant \
  -H "X-API-Key: TENANT_KEY"
# Expect: 403

# Tenant still appears in admin list (data retained)
curl -sS https://api.krowolf.se/admin/tenants \
  -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool
# Confirm: TENANT_ID listed with status "inactive"
```

---

## Step 7: Revoke Gmail OAuth tokens (if applicable)

If the customer's Gmail account was connected:
1. Go to Google Account → Security → Third-party apps with account access.
2. Find the platform's OAuth application.
3. Revoke access.
4. Remove the Gmail env vars from `.env.production` on the server.
5. Recreate the container: `sudo docker compose -f docker-compose.prod.yml up -d app`

---

## Data retention

- Tenant data (jobs, approvals, audit events) is retained in the DB after deactivation.
- Data deletion requires a manual SQL operation against the production DB.
- Always take a backup before any data deletion.
- Follow your data handling and GDPR/privacy policy for retention periods.

---

## Reactivation

If a tenant needs to be reactivated:

```bash
curl -sS -X PATCH https://api.krowolf.se/admin/tenants/TENANT_ID/status \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"status":"active"}'

# Issue a new API key (old key is not restored)
curl -sS -X POST https://api.krowolf.se/admin/tenants/TENANT_ID/rotate-key \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
# Save the new api_key immediately
```

---

## Related runbooks

- `docs/runbooks/customer-onboarding.md`
- `docs/runbooks/backup-and-restore.md`
- `docs/runbooks/incident-response.md`
