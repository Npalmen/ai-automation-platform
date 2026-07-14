# AI Receptionist — Test Customer Onboarding

> **Purpose:** Repeatable setup checklist for creating an internal or friend-level test tenant.
> Designed to be followed step-by-step without improvising.
>
> **When to use:** Before any internal test, friend test, or pre-demo rehearsal.
> Do not skip steps. Do not improvise settings in production.
>
> **Audience:** Internal operator. Not shown to test customers.

---

## Prerequisites

Before starting:

- [ ] Local server running: `uvicorn app.main:app --reload` (or production deploy is live)
- [ ] `ADMIN_API_KEY` available in env/secure note — never paste in chat/logs
- [ ] Google OAuth tokens configured in `.env` (`GOOGLE_MAIL_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`)
- [ ] Gmail account connected (tokens valid — check `/integrations/health`)
- [ ] If testing Google Sheets: spreadsheet created with tabs **Leads**, **Support**, **Logg**; Sheet ID available (not committed to repo)
- [ ] Chosen Gmail label for this tenant already created in Gmail (e.g. `krowolf-demo-test01`)

---

## Tenant naming

| Setting | Example |
|---------|---------|
| Slug | `test-customer-01` |
| Tenant ID | `T_TEST_CUSTOMER_01` (auto-derived from slug) |
| Display name | `Test Customer 01` |
| Gmail label | `krowolf-demo-test01` |
| Gmail query | `label:krowolf-demo-test01` |

Use a distinct slug per test tenant. Never reuse slugs between real and test tenants.

---

## Step 1 — Create tenant

```powershell
$AdminKey = "YOUR_ADMIN_KEY"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/admin/tenants" `
  -Method POST `
  -Headers @{ "X-Admin-API-Key" = $AdminKey; "Content-Type" = "application/json" } `
  -Body '{
    "name": "Test Customer 01",
    "slug": "test-customer-01",
    "enabled_job_types": ["lead", "customer_inquiry"],
    "allowed_integrations": ["google_mail"]
  }' | ConvertTo-Json -Depth 10
```

**Save the returned API key immediately.** It is shown only once. Store in a password manager or secure note. Never share in chat or logs.

If testing Google Sheets, re-create or patch `allowed_integrations` to include `"google_sheets"`:

```json
"allowed_integrations": ["google_mail", "google_sheets"]
```

---

## Step 2 — Store API key

```powershell
$ApiKey = "kw_PASTE_KEY_HERE"
```

Rotate immediately if accidentally exposed:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/admin/tenants/T_TEST_CUSTOMER_01/rotate-key" `
  -Method POST `
  -Headers @{ "X-Admin-API-Key" = $AdminKey } | ConvertTo-Json
```

---

## Step 3 — Configure settings

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/dashboard/control" `
  -Method PUT `
  -Headers @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" } `
  -Body '{
    "support_email": "your-internal-email@example.com",
    "automation": {
      "followups_enabled": true,
      "leads_enabled": true
    },
    "scheduler": {
      "run_mode": "manual"
    },
    "google_sheets": {
      "spreadsheet_id": "PASTE_SPREADSHEET_ID_HERE"
    }
  }' | ConvertTo-Json -Depth 10
```

**Required settings explained:**

| Setting | Value | Reason |
|---------|-------|--------|
| `support_email` | Your internal email | Internal handoff destination |
| `automation.followups_enabled` | `true` | Enables pending customer reply flow |
| `automation.leads_enabled` | `true` | Enables lead processing |
| `scheduler.run_mode` | `manual` | No auto-scan; you trigger inbox manually |
| `google_sheets.spreadsheet_id` | Your sheet ID | Required only if testing Sheets export |

---

## Step 4 — Verify auto_actions are OFF

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/tenant" `
  -Headers @{ "X-API-Key" = $ApiKey } | ConvertTo-Json -Depth 10
```

Confirm in the response:

```json
"auto_actions": {
  "lead": false,
  "customer_inquiry": false,
  "invoice": false
}
```

**If any `auto_actions` value is `true` or `"full_auto"` — stop and fix before proceeding.**
All email sends must go through approval-first for first tests.

---

## Step 5 — Gmail setup

1. In Gmail: create a label exactly matching your query (e.g. `krowolf-demo-test01`)
2. Apply the label to the test emails you want processed — do NOT apply to real inbox emails
3. Test emails should be **unread** (or omit `is:unread` from your query to re-process)

Recommended Gmail query format:
```
label:krowolf-demo-test01
```

---

## Step 6 — Dry-run inbox scan

Always dry-run first:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/gmail/process-inbox" `
  -Method POST `
  -Headers @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" } `
  -Body '{
    "dry_run": true,
    "query": "label:krowolf-demo-test01",
    "max_emails": 10
  }' | ConvertTo-Json -Depth 10
```

**Expected:** `dry_run: true`, `jobs_created: 0`. Verify only the correct emails appear in scope.

---

## Step 7 — Live inbox scan

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/gmail/process-inbox" `
  -Method POST `
  -Headers @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" } `
  -Body '{
    "dry_run": false,
    "query": "label:krowolf-demo-test01",
    "max_emails": 10
  }' | ConvertTo-Json -Depth 10
```

---

## Step 8 — Verify jobs created

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/jobs?limit=20" `
  -Headers @{ "X-API-Key" = $ApiKey } | ConvertTo-Json -Depth 20
```

Check:
- [ ] Jobs created with correct `job_type`
- [ ] No unexpected `auto_actions` fired (check `external_actions_count` = 0)
- [ ] Complaint/safety emails → `status: manual_review`
- [ ] Lead/inquiry emails → `status: awaiting_approval` or `completed` depending on playbook

---

## Step 9 — Review pending approvals

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/approvals/pending" `
  -Headers @{ "X-API-Key" = $ApiKey } | ConvertTo-Json -Depth 20
```

Check:
- [ ] Customer reply drafts are pending (not auto-sent)
- [ ] Bodies look correct (correct customer name, relevant questions, no hallucinated content)
- [ ] Complaint/urgent emails have NO pending customer reply (manual_review only)

---

## Step 10 — If testing Google Sheets export

For each job you want to export:

```powershell
$JobId = "paste-job-id-here"
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/integrations/google-sheets/export-job" `
  -Method POST `
  -Headers @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" } `
  -Body "{`"job_id`": `"$JobId`", `"target`": `"auto`"}" | ConvertTo-Json -Depth 10
```

Check response: `"status": "exported"`, correct `tab` and `spreadsheet_id`.
Verify row appeared in the Google Sheet.

---

## Safety checklist before approving any email send

- [ ] `auto_actions.lead = false` confirmed
- [ ] `auto_actions.customer_inquiry = false` confirmed
- [ ] Reply body reviewed — no hallucinations, no wrong customer name, no legal/financial commitments
- [ ] Complaint/urgent email in `manual_review` (no auto-reply)
- [ ] If this is a friend test: confirm with the friend that test emails will arrive

Only approve an email send after reviewing the reply body carefully.

---

## What NOT to enable for test tenants

| Setting | Why |
|---------|-----|
| `auto_actions.lead = true` | Auto-sends customer emails without review |
| `auto_actions.customer_inquiry = true` | Same |
| `allowed_integrations: monday` | Risk of Monday production board writes |
| `allowed_integrations: visma` | No Visma writes in MVP |
| `scheduler.run_mode = scheduled` | Would auto-scan inbox without manual trigger |
| `followups_enabled = false` | Breaks pending customer reply flow |

---

## Rollback / stop procedure

To stop all processing immediately:

```powershell
# Set scheduler to manual (stops auto-scan)
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/dashboard/control" `
  -Method PUT `
  -Headers @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" } `
  -Body '{"scheduler": {"run_mode": "manual"}}' | ConvertTo-Json

# Reject all pending approvals (no emails sent)
# Do this per approval ID from /approvals/pending
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/approvals/APPROVAL_ID/reject" `
  -Method POST `
  -Headers @{ "X-API-Key" = $ApiKey; "Content-Type" = "application/json" } `
  -Body '{"note": "Stopped — test rollback"}' | ConvertTo-Json
```

To remove the test tenant entirely (admin only):
```powershell
# Deactivate tenant (all keys stop working)
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/admin/tenants/T_TEST_CUSTOMER_01/status" `
  -Method PATCH `
  -Headers @{ "X-Admin-API-Key" = $AdminKey; "Content-Type" = "application/json" } `
  -Body '{"status": "inactive"}' | ConvertTo-Json
```

---

## Reference: tenant verification commands

```powershell
# Health check
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health"

# Tenant info
Invoke-RestMethod -Uri "http://127.0.0.1:8000/tenant" -Headers @{ "X-API-Key" = $ApiKey }

# Integration health
Invoke-RestMethod -Uri "http://127.0.0.1:8000/integrations/health" -Headers @{ "X-API-Key" = $ApiKey }

# Readiness
Invoke-RestMethod -Uri "http://127.0.0.1:8000/pilot/readiness" -Headers @{ "X-API-Key" = $ApiKey }

# Audit trail
Invoke-RestMethod -Uri "http://127.0.0.1:8000/audit-events" -Headers @{ "X-API-Key" = $ApiKey } | ConvertTo-Json -Depth 10
```
