# Niklas Demo — Setup Guide (Rehearsal)

> **Purpose:** Internal rehearsal before Mårtens Demo. Niklas verifies the
> full setup flow with his own Gmail account so that Mårten's demo runs
> smoothly and predictably.
>
> **Relationship to Mårtens Demo:** Run Niklas Demo first. Fix any issues here.
> Only proceed to Mårtens Demo when Niklas Demo is fully GREEN.
>
> **Audience:** Internal operator only. Not shown to customers or salespeople.
>
> **Safety:** `auto_actions=false`. Gmail send is approval-gated. No production writes
> to Visma. No real customer data. No Monday production writes.
> All external writes are disabled except an isolated demo Google Sheet (if explicitly configured).
> Google Sheet ID must not be committed — store in env/config only.

---

## Demo tenant

| Setting | Value |
|---------|-------|
| Tenant display name | Niklas Demo |
| Tenant ID | `T_NIKLAS_DEMO_001` |
| Gmail account | `niklas.palm@sol-f.se` |
| Gmail label | `krowolf-demo-niklas` |
| Gmail query | `label:krowolf-demo-niklas is:unread` |
| Visma | Status/read-only — no production writes |
| Google Sheets | Manual output step — sheet name: "Krowolf - Niklas Demo" |
| Monday | Disabled — no production writes |
| `auto_actions` | `false` for all job types |
| Gmail send | Approval-first — operator must approve before any email is sent |

---

## Rehearsal flow (high level)

```
1. Create / verify Niklas Demo tenant T_NIKLAS_DEMO_001
        ↓
2. Set support_email, confirm auto_actions=false, scheduler=manual
        ↓
3. Connect niklas.palm@sol-f.se via OAuth env vars
        ↓
4. Create Gmail label krowolf-demo-niklas; add 5-10 demo emails; mark unread
        ↓
5. POST /gmail/process-inbox  dry_run=true  query="label:krowolf-demo-niklas is:unread"
   → preview only, confirm only demo emails are in scope, no jobs created
        ↓
6. POST /gmail/process-inbox  dry_run=false
   → jobs created, AI classifies each as lead / customer_inquiry
        ↓
7. GET /jobs → verify classifications, extracted fields, priorities
        ↓
8. GET /approvals/pending → verify approval queue, review draft responses
        ↓
9. Manually copy key job fields to "Krowolf - Niklas Demo" Google Sheet
        ↓
10. GET /integrations/visma/status → confirm read-only connection or disconnected
        ↓
11. Document results → confirm Mårtens Demo is safe to run
```

---

## Step 1: Create (or verify) the Niklas Demo tenant

**Option A — Provision new tenant:**
```bash
curl -sS -X POST https://api.krowolf.se/admin/tenants \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Niklas Demo",
    "slug": "niklas-demo-001",
    "enabled_job_types": ["lead", "customer_inquiry"],
    "allowed_integrations": ["google_mail", "visma"],
    "auto_actions": {"lead": false, "customer_inquiry": false, "invoice": false}
  }'
# Save the api_key from the response — shown exactly once
```

**Verify the tenant exists:**
```bash
curl -sS https://api.krowolf.se/admin/tenants \
  -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool | grep -A3 "Niklas"
```

---

## Step 2: Set support_email and verify safety settings

```bash
curl -sS -X PUT https://api.krowolf.se/dashboard/control \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "support_email": "niklas.palm@sol-f.se",
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
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" | python3 -m json.tool
# Confirm:
#   auto_actions = {"lead": false, "customer_inquiry": false, "invoice": false}
#   scheduler.run_mode = "manual"
```

---

## Step 3: Connect niklas.palm@sol-f.se Gmail

Set the four OAuth env vars in `.env.production` for Niklas' Gmail account:

```bash
# In .env.production (never committed to repo)
GOOGLE_MAIL_ACCESS_TOKEN=<niklas_access_token>
GOOGLE_MAIL_USER_ID=niklas.palm@sol-f.se
GOOGLE_OAUTH_REFRESH_TOKEN=<niklas_refresh_token>
GOOGLE_OAUTH_CLIENT_ID=<oauth_client_id>
GOOGLE_OAUTH_CLIENT_SECRET=<oauth_client_secret>
```

After updating `.env.production`, recreate the app container:
```bash
sudo docker compose -f docker-compose.prod.yml up -d app
```

**Verify Gmail connection:**
```bash
curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" | python3 -m json.tool
# Expect: systems.gmail.status = "healthy" or "warning" (not "error")
```

**Quick token test (dry_run, 1 result):**
```bash
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox" \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 1, "dry_run": true, "query": "label:krowolf-demo-niklas is:unread"}'
# Expect: HTTP 200, dry_run: true — no jobs created
```

See `docs/runbooks/oauth-errors.md` for token setup and `invalid_grant` troubleshooting.

---

## Step 4: Create Gmail label and add demo emails

In the Gmail inbox at `niklas.palm@sol-f.se`:

1. Create a label called **`krowolf-demo-niklas`**.
2. Send or draft 5–10 demo emails from different fictitious senders and apply the label.
   Use the Swedish scenario templates from `docs/demo/martens-gmail-demo-scenarios.md`.
3. Mark each email as **unread**.
4. Confirm no real customer emails have this label.

> **Label name:** `krowolf-demo-niklas` — separate from Mårten's `krowolf-demo` label.
> The different label ensures Niklas Demo and Mårtens Demo never interfere with each other.

---

## Step 5: Run Gmail dry_run — verify scope

```bash
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox" \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 15, "dry_run": true, "query": "label:krowolf-demo-niklas is:unread"}'
```

**Expected response:**
```json
{
  "processed": 0,
  "scanned": 5,
  "dry_run": true,
  "query_used": "label:krowolf-demo-niklas is:unread",
  "created_jobs": [],
  "skipped_messages": [],
  "failed_messages": []
}
```

Verify:
- `scanned` matches the number of demo emails you prepared
- `failed_messages` is empty
- No unexpected real emails appear in the response subjects

---

## Step 6: Run real Gmail processing

Once the dry_run shows only demo emails:

```bash
curl -sS -X POST "https://api.krowolf.se/gmail/process-inbox" \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 15, "dry_run": false, "query": "label:krowolf-demo-niklas is:unread"}'
```

**Expected response:**
```json
{
  "processed": 5,
  "skipped": 0,
  "failed": 0,
  "dry_run": false,
  "query_used": "label:krowolf-demo-niklas is:unread",
  "created_jobs": ["job-uuid-1", "..."],
  "skipped_messages": [],
  "failed_messages": []
}
```

---

## Step 7: Verify created jobs

```bash
curl -sS "https://api.krowolf.se/jobs?limit=20" \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" | python3 -m json.tool
```

Check for each job:
- `job_type` is `lead` or `customer_inquiry` (matches scenario intent)
- `status` is `awaiting_approval` (correct — approval-first)
- Extracted fields are present (sender name, phone, location, service type)
- Priority is set (kritisk / hög / medel / låg)

---

## Step 8: Verify pending approvals

```bash
curl -sS https://api.krowolf.se/approvals/pending \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" | python3 -m json.tool
```

Check:
- Each job has a pending approval
- `next_on_approve` = `"email_send"` for most approvals
- Draft response content is visible and reasonable

**Do not approve** unless recipient is `niklas.palm@sol-f.se` itself:
```bash
# Only if testing real send to Niklas' own inbox
curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/approve \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"niklas-demo","note":"rehearsal approval to own inbox"}'
```

---

## Step 9: Create "Krowolf - Niklas Demo" Google Sheet and copy output

**Google Sheets integration is not yet implemented.** This is a manual step.

1. Create a Google Sheet named: `Krowolf - Niklas Demo`
2. Use the same tab structure as Mårtens Demo:
   - **Leads** — for `lead` job type
   - **Support** — for `customer_inquiry` job type
   - **Logg** — demo run log
3. Use the column headers from `docs/demo/google-sheets-leads-support-structure.md`.
4. For each job in the response, copy the key extracted fields into the sheet manually.
5. Share the sheet only with `niklas.palm@sol-f.se` and operator account.

**Do not use the same sheet as Mårtens Demo** — keep them separate.

---

## Step 10: Verify Visma status (read-only)

```bash
curl -sS https://api.krowolf.se/integrations/visma/status \
  -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" | python3 -m json.tool
```

Expected outcomes:
- `"status": "connected"` with token details → connection ready, no write actions taken
- `"status": "disconnected"` → acceptable for rehearsal; note for Mårtens Demo setup

**Do not call** `POST /integrations/visma/execute` with `create_customer` or `create_invoice`.

---

## Step 11: Document results before Mårtens Demo

After completing the rehearsal, record the following:

| Check | Result | Notes |
|-------|--------|-------|
| Tenant created | ☐ pass / ☐ fail | |
| Gmail connected | ☐ pass / ☐ fail | |
| Dry_run scope correct | ☐ pass / ☐ fail | scanned N = expected N |
| Jobs created with correct classification | ☐ pass / ☐ fail | |
| Pending approvals visible | ☐ pass / ☐ fail | |
| Draft responses reasonable | ☐ pass / ☐ fail | |
| Google Sheet populated (manual) | ☐ pass / ☐ fail | |
| Visma status checked | ☐ pass / ☐ fail | |
| Overall rehearsal status | ☐ GO / ☐ NOT GO | |

**Only proceed to Mårtens Demo when all items are PASS or GO.**

---

## Rollback / cleanup after rehearsal

After the rehearsal session:

1. **Reject all pending demo approvals:**
   ```bash
   # For each approval_id from GET /approvals/pending:
   curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/reject \
     -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"niklas-operator","note":"rehearsal cleanup"}'
   ```

2. **Pause the Niklas Demo tenant:**
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/T_NIKLAS_DEMO_001/disable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"post-rehearsal cleanup"}'
   ```

3. **Remove or clear the `krowolf-demo-niklas` label** from processed demo emails
   to prevent re-processing on the next rehearsal run.

4. **Decide on Gmail token:**
   - If Niklas Demo and Mårtens Demo share the same Gmail OAuth app, the token
     stays in place for Mårtens Demo. No action needed.
   - If using separate OAuth credentials, revoke Niklas' token and set Mårten's
     credentials before the sales demo.

5. **Archive the "Krowolf - Niklas Demo" sheet** — move rows to a Rehearsal tab.

6. **Rotate Niklas Demo API key** if it was shared or logged anywhere:
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/tenants/T_NIKLAS_DEMO_001/rotate-key \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{}'
   # Save the new api_key
   ```

---

## Relationship to Mårtens Demo

| Aspect | Niklas Demo | Mårtens Demo |
|--------|-------------|--------------|
| Purpose | Rehearsal / operator test | Internal sales demo |
| Audience | Niklas (operator) | Mårten (salesperson) |
| Tenant ID | `T_NIKLAS_DEMO_001` | `T_MARTENS_DEMO_001` |
| Gmail account | `niklas.palm@sol-f.se` | Mårten's demo Gmail |
| Gmail label | `krowolf-demo-niklas` | `krowolf-demo` |
| Google Sheet | "Krowolf - Niklas Demo" | "Krowolf - Mårtens Demo" |
| Run order | **First** | Second (after Niklas GO) |
| Approval behavior | Test only — approve to own inbox | Show queue only |
| Scenario content | Same templates reused | Same templates reused |

---

## Related documents

- `docs/MARTENS_DEMO_SETUP.md` — the sales demo this rehearsal prepares for
- `docs/MARTENS_DEMO_READINESS_CHECKLIST.md` — Mårten's readiness checklist
- `docs/NIKLAS_DEMO_READINESS_CHECKLIST.md` — this rehearsal's readiness checklist
- `docs/demo/martens-gmail-demo-scenarios.md` — Swedish demo email templates
- `docs/demo/google-sheets-leads-support-structure.md` — Sheet structure
- `docs/runbooks/oauth-errors.md` — Gmail token troubleshooting
- `docs/runbooks/pending-approvals.md` — Approval queue handling
