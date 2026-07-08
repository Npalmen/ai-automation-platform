# Runbook: Customer Onboarding

> **Safety:** Never enable `auto_actions` during onboarding without explicit operator confirmation after isolated integration testing.
> **Isolation:** Each customer must be provisioned as a separate tenant. Tenant API keys must be stored securely and never reused.

---

## Overview

This runbook covers provisioning a new customer tenant, verifying readiness, and handing off to the customer. It does not cover product features — it is the operational checklist for adding a safe, isolated customer to the platform.

---

## Pre-onboarding checklist

Before provisioning a new tenant:

- [ ] Platform health check passes: `GET /health` → 200, `env: production`
- [ ] DB backup taken (see `docs/runbooks/backup-and-restore.md`)
- [ ] Admin API key is available and working
- [ ] Customer-specific integration credentials are ready (Gmail, Monday board ID if applicable)
- [ ] Support email agreed with customer
- [ ] Operator assigned as primary contact for this tenant

---

## Step 1: Provision the tenant

```bash
curl -sS -X POST https://api.krowolf.se/admin/tenants \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Customer Name AB",
    "slug": "customer-slug",
    "enabled_job_types": ["lead", "customer_inquiry"],
    "allowed_integrations": ["google_mail", "monday"],
    "auto_actions": {"lead": false, "customer_inquiry": false, "invoice": false}
  }'
```

**Expected response:**
```json
{
  "tenant_id": "T_CUSTOMER_SLUG",
  "name": "Customer Name AB",
  "slug": "customer-slug",
  "api_key": "kw_xxx...",
  "status": "active"
}
```

> **IMPORTANT:** Save the `api_key` immediately and securely. It is shown exactly once and cannot be retrieved again. Rotate via `POST /admin/tenants/{id}/rotate-key` if lost.

---

## Step 2: Verify tenant was created

```bash
curl -sS https://api.krowolf.se/admin/tenants \
  -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool
# Confirm: new tenant_id appears in list
# Confirm: api_key is NOT in the list response (correct — shown only on create)
```

---

## Step 3: Rotate key if needed (if key was not saved)

```bash
curl -sS -X POST https://api.krowolf.se/admin/tenants/T_CUSTOMER_SLUG/rotate-key \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
# Returns new api_key — save immediately
```

---

## Step 4: Set support email

```bash
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
```

---

## Step 5: Verify pilot readiness

```bash
curl -sS https://api.krowolf.se/pilot/readiness \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Expect: overall_status "almost_ready" or "ready"
# Acceptable warnings: onboarding steps not yet complete, no integration events yet
# Not acceptable: auth failures, isolation failures, integration health "error"

curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Expect: overall_status "warning" or "healthy" — not "error"
```

---

## Step 6: Run a verification test job (no external calls)

```bash
curl -sS -X POST https://api.krowolf.se/verify/T_CUSTOMER_SLUG \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expect: {"status":"completed"} or {"status":"awaiting_approval"}
# This uses a deterministic pipeline — no LLM, no Gmail, no Monday writes
```

---

## Step 7: Configure Gmail (if applicable)

Gmail tokens must be set in `.env.production` on the server.
See `docs/runbooks/oauth-errors.md` for token setup procedure.

After updating tokens:
```bash
# Dry-run inbox sync first
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox?dry_run=true" \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
# Expect: HTTP 200, "dry_run": true, job_count unchanged
```

Only run a real sync after the dry run confirms the connection works.

---

## Step 8: Verify tenant isolation

```bash
# Tenant key must not expose other tenants' data
curl -sS https://api.krowolf.se/jobs \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Expect: only jobs for this tenant

# Admin key must not work as a tenant key
curl -o /dev/null -w '%{http_code}' https://api.krowolf.se/jobs \
  -H "X-API-Key: ADMIN_API_KEY"
# Expect: 403
```

---

## Step 9: Hand off

- Provide the tenant API key securely (not via email).
- Confirm support email is set.
- Confirm scheduler is in `manual` mode (not `scheduled`) until operator enables it.
- Confirm `auto_actions` are all `false`.
- Confirm the approval queue is empty.
- Brief the customer on the approval flow (no email will be sent without operator approval).

---

## Related runbooks

- `docs/runbooks/customer-offboarding.md`
- `docs/runbooks/oauth-errors.md`
- `docs/PILOT_READINESS_CHECKLIST.md`
