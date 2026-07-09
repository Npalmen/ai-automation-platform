# Mårtens Demo — Setup Guide

> **Purpose:** Internal sales demo. Mårten can demonstrate customer value through
> a realistic workflow: Gmail inbound email → AI classification → approval-first
> response draft → leads/support output.
>
> **Audience:** Internal. Not shown to external customers as a customer portal.
>
> **Safety:** `auto_actions=false`. Gmail send is approval-gated. No production writes
> to Visma. No real customer data. No Monday production writes.
> All external writes are disabled except an isolated demo Google Sheet (if explicitly configured).
> Google Sheet ID must not be committed — store in env/config only.

---

## Demo tenant

| Setting | Value |
|---------|-------|
| Tenant display name | Mårtens Demo |
| Tenant ID | `T_MARTENS_DEMO_001` |
| Gmail account | Mårten's demo Gmail (not a real customer account) |
| Visma | Status/read-only — no production writes |
| Google Sheets | Manual output step (see `docs/demo/google-sheets-leads-support-structure.md`) |
| Monday | Disabled — no production writes |
| `auto_actions` | `false` for all job types |
| Gmail send | Approval-first — operator must approve before any email is sent |

---

## Demo flow (high level)

```
1. Prepare demo emails in Mårten's Gmail (label: krowolf-demo)
        ↓
2. Run inbox sync (dry_run first to preview)
        ↓
3. Jobs appear: classified as lead / customer_inquiry
        ↓
4. AI extracts sender, urgency, request type, contact details
        ↓
5. Policy routes to approval queue (email_send approval required)
        ↓
6. Operator reviews draft response in approval queue
        ↓
7. Operator approves → email response sent (OR rejects → nothing sent)
        ↓
8. Lead/support data → Google Sheets (manual copy for demo, or future integration)
        ↓
9. Visma status check shown as "ready" — no production write performed
```

---

## Step 1: Create (or verify) the demo tenant

**Option A — Provision new tenant:**
```bash
curl -sS -X POST https://api.krowolf.se/admin/tenants \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mårtens Demo",
    "slug": "martens-demo",
    "enabled_job_types": ["lead", "customer_inquiry"],
    "allowed_integrations": ["google_mail", "visma"],
    "auto_actions": {"lead": false, "customer_inquiry": false, "invoice": false}
  }'
# Save the api_key from the response — shown exactly once
```

Tenant ID will be: `T_MARTENS_DEMO_001` (matches slug `martens-demo` → `T_MARTENS_DEMO` — adjust slug to `martens-demo-001` if you need the exact ID).

> If the tenant already exists, skip to Step 2.

**Verify the tenant exists:**
```bash
curl -sS https://api.krowolf.se/admin/tenants \
  -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool | grep -A3 "Mårtens"
```

---

## Step 2: Configure the demo tenant

```bash
# Set support email and keep scheduler in manual mode
curl -sS -X PUT https://api.krowolf.se/dashboard/control \
  -H "X-API-Key: DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "support_email": "DEMO_SUPPORT_EMAIL",
    "automation": {
      "leads_enabled": true,
      "support_enabled": true,
      "invoices_enabled": false,
      "followups_enabled": false,
      "demo_mode": false
    },
    "scheduler": {"run_mode": "manual"}
  }'
```

**Verify auto_actions are off:**
```bash
curl -sS https://api.krowolf.se/tenant \
  -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool
# Confirm: auto_actions = {"lead": false, "customer_inquiry": false, "invoice": false}
```

---

## Step 3: Connect Mårten's Gmail

**Prerequisites:**
- Mårten's Gmail account must be authorized via the platform's OAuth app.
- All four env vars must be set in `.env.production` before running the demo:
  - `GOOGLE_MAIL_ACCESS_TOKEN`
  - `GOOGLE_OAUTH_REFRESH_TOKEN`
  - `GOOGLE_OAUTH_CLIENT_ID`
  - `GOOGLE_OAUTH_CLIENT_SECRET`
- See `docs/runbooks/oauth-errors.md` for token setup.

**After setting tokens, verify Gmail connection:**
```bash
curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool
# Expect: systems.gmail.status = "healthy" or "warning" (not "error")
```

**Verify token refresh works without a dry_run:**
```bash
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox" \
  -H "X-API-Key: DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 1, "dry_run": true, "query": "label:krowolf-demo is:unread"}'
# Expect: HTTP 200, dry_run: true — no jobs created
```

---

## Step 4: Prepare demo emails in Gmail

In Mårten's Gmail:

1. Create a label called **`krowolf-demo`** in Gmail.
2. Send 5–10 demo emails from different senders to the inbox and apply the `krowolf-demo` label.
   - Use the scenario templates from `docs/demo/martens-gmail-demo-scenarios.md`.
   - Mark them as **unread** after applying the label.
3. Make sure no real customer emails have this label.

**Why use a label?** The inbox sync supports a `query` parameter. By using
`"label:krowolf-demo is:unread"` you scope the demo to exactly the prepared
emails and never touch real inbox traffic.

**Verify label scope before running real sync:**
```bash
# Dry run scoped to demo label — shows what would be processed
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox" \
  -H "X-API-Key: DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 10, "dry_run": true, "query": "label:krowolf-demo is:unread"}'
# Review scanned count and message subjects in the response
```

---

## Step 5: Run the demo inbox sync

Once you have confirmed the dry run shows only demo emails:

```bash
# Real sync — creates jobs for demo emails
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox" \
  -H "X-API-Key: DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 10, "dry_run": false, "query": "label:krowolf-demo is:unread"}'
```

**Expected response:**
```json
{
  "processed": 5,
  "skipped": 0,
  "failed": 0,
  "dry_run": false,
  "query_used": "label:krowolf-demo is:unread",
  "created_jobs": ["job-uuid-1", "job-uuid-2", "..."],
  "skipped_messages": [],
  "failed_messages": []
}
```

---

## Step 6: Verify created jobs

```bash
# List jobs for demo tenant
curl -sS "https://api.krowolf.se/jobs?limit=20" \
  -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool

# Check pending approvals (email send approvals)
curl -sS https://api.krowolf.se/approvals/pending \
  -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool
# Expect: items with next_on_approve = "email_send" for each processed job
```

During the demo, show Mårten:
- Job list with AI-classified types (lead / customer_inquiry)
- The extracted fields (sender, urgency, request type)
- The pending approval queue with draft response

---

## Step 7: Show the approval flow (demo highlight)

```bash
# Inspect a specific approval
curl -sS https://api.krowolf.se/approvals/APPROVAL_ID \
  -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool
```

For the demo, **do NOT approve email sends** unless Mårten has confirmed the
recipient is himself or a test address. Instead:
- Show the approval queue
- Show the draft response content
- Explain that approval → send, rejection → nothing happens

If you want to demonstrate an actual send, approve only to Mårten's own email:
```bash
# Only if recipient is Mårten's own demo address
curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/approve \
  -H "X-API-Key: DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"marten-demo","note":"demo approval to own inbox"}'
```

---

## Step 8: Show Google Sheets output (manual demo step)

**Google Sheets integration does not exist yet in the platform.**
For the demo, this is a manual step:

1. Open the prepared demo Google Sheet: "Krowolf - Mårtens Demo"
   (see `docs/demo/google-sheets-leads-support-structure.md` for structure)
2. Copy the key extracted fields from the job result into the sheet manually.
3. Show the customer: "This will be written automatically when the integration is live."

This is an honest, safe framing — the AI has already classified and extracted
the data; writing it to Sheets is a config step we're completing next.

---

## Step 9: Show Visma status (read-only framing)

```bash
# Check Visma connection status — read-only, no writes
curl -sS https://api.krowolf.se/integrations/visma/status \
  -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool
# Shows: connected/disconnected, token expiry, scopes
```

**Demo framing:** "We've connected to the Visma API — when a lead converts to a
customer, we can automatically create the customer and invoice record in Visma.
For today's demo we're showing the connection status only — no production entries
will be created."

See `docs/demo/martens-sales-talk-track.md` for the exact script.

---

## Step 10: Verify pilot readiness before demo

```bash
# Full healthcheck (if running on production)
sudo APP_BASE_URL=https://api.krowolf.se \
  DOCKER_APP_CONTAINER=krowolf-app-1 \
  DOCKER_DB_CONTAINER=krowolf-db-1 \
  DISK_CHECK_PATH=/opt/krowolf \
  BACKUP_DIR=/opt/krowolf/backups \
  bash /opt/krowolf/scripts/check_production_health.sh
# Expect: HEALTHY — all checks passed
```

---

## Rollback / cleanup after demo

After the demo session:

1. **Clear demo jobs and approvals** — reject all pending demo approvals:
   ```bash
   # Reject all pending email_send approvals from demo
   curl -sS https://api.krowolf.se/approvals/pending \
     -H "X-API-Key: DEMO_TENANT_KEY" | python3 -m json.tool
   # For each approval_id:
   curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/reject \
     -H "X-API-Key: DEMO_TENANT_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"operator","note":"demo cleanup"}'
   ```

2. **Pause the demo tenant** (stops further inbox sync):
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/T_MARTENS_DEMO_001/disable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"post-demo cleanup"}'
   ```

3. **Remove the `krowolf-demo` label** from demo emails in Gmail to avoid re-processing.

4. **Revoke Gmail tokens** if Mårten's personal Gmail was connected to production:
   - Go to Google Account → Security → Third-party apps → revoke the platform's access.
   - Remove `GOOGLE_MAIL_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN` from `.env.production`.
   - Recreate container: `sudo docker compose -f docker-compose.prod.yml up -d app`

5. **Rotate demo API key** if it was shown or shared:
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/tenants/T_MARTENS_DEMO_001/rotate-key \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{}'
   # Save the new api_key — old key is immediately invalidated
   ```

6. **Archive or clear the demo Google Sheet** — move demo rows to an archive tab.

---

## Related documents

- `docs/MARTENS_DEMO_READINESS_CHECKLIST.md` — pre-demo checklist
- `docs/demo/martens-gmail-demo-scenarios.md` — 10 realistic Swedish demo emails
- `docs/demo/google-sheets-leads-support-structure.md` — Sheet structure
- `docs/demo/martens-sales-talk-track.md` — Swedish sales script
- `docs/runbooks/oauth-errors.md` — Gmail token issues
- `docs/runbooks/pending-approvals.md` — Approval queue handling
