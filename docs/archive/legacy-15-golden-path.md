> Archived document. Historical reference only. Current governing source is docs/00-master-plan.md.

# Golden Path — Lead to Invoice Preparation

This guide walks through the complete end-to-end flow that the platform supports: from an incoming lead to prepared invoice/bookkeeping documents. It can be followed manually against a running instance with a test tenant.

## Prerequisites

- Running instance (local or deployed)
- A provisioned tenant with API key (use Super Admin or `POST /admin/tenants`)
- Gmail integration configured (or use demo mode for synthetic jobs)
- Monday integration configured (optional, for dispatch testing)
- Fortnox integration configured (optional, for finance preview)

## Step 1: Lead Intake

**Option A — Real Gmail inbox:**
```
POST /gmail/process-inbox
X-API-Key: <tenant-key>
```

**Option B — Synthetic demo lead:**
```
POST /demo/seed
X-API-Key: <tenant-key>
{"count": 1}
```

**Option C — Direct job creation:**
```
POST /jobs
X-API-Key: <tenant-key>
{
  "tenant_id": "<TENANT_ID>",
  "job_type": "lead",
  "input_data": {
    "subject": "Offertförfrågan solceller",
    "sender": {"name": "Test Kund", "email": "test@example.com", "phone": "070-1234567"},
    "message_text": "Hej, vi är intresserade av solceller på vårt tak. Kan ni ge en offert?"
  }
}
```

**Result:** Job created, pipeline runs (classification → extraction → lead analysis → policy → action dispatch). Job appears in `GET /cases`.

## Step 2: Case Review and Communication

```
GET /cases/<job_id>
X-API-Key: <tenant-key>
```

Check the response for:
- `lead_analysis` — lead type, score, completeness
- `automation_summary` — next step recommendation
- `automation_risks` — any blocking issues

If email approval is pending (policy = manual/semi):
```
GET /approvals/pending
X-API-Key: <tenant-key>
```

Approve customer reply:
```
POST /approvals/<approval_id>/approve
X-API-Key: <tenant-key>
{}
```

## Step 3: Operations Workspace

Initialize or update the operations workspace:
```
PUT /cases/<job_id>/operations
X-API-Key: <tenant-key>
{
  "project": {"name": "Solceller Kund AB", "status": "in_progress", "installation_type": "solar"},
  "work_order": {"status": "scheduled", "technician": "Erik"},
  "customer": {"name": "Test Kund", "phone": "070-1234567", "email": "test@example.com"},
  "property": {"address": "Storgatan 1, Stockholm"}
}
```

Add timeline entry:
```
POST /cases/<job_id>/operations/timeline
X-API-Key: <tenant-key>
{"entry": "Installation planerad för nästa vecka", "author": "admin"}
```

Apply checklist template:
```
POST /cases/<job_id>/operations/checklists/template
X-API-Key: <tenant-key>
{"template": "solar"}
```

Mark work as completed:
```
PUT /cases/<job_id>/operations
X-API-Key: <tenant-key>
{
  "work_order": {"status": "completed"},
  "delivery_package": {"status": "ready"}
}
```

## Step 4: Finance Draft (Invoice Preparation)

Generate a pre-accounting invoice draft:
```
POST /finance/invoices/<job_id>/draft
X-API-Key: <tenant-key>
```

**Result:** Returns `amount_ex_vat`, `vat_amount`, `total`, `vat_rate`, `expense_category`, `account_suggestion`.

## Step 5: Fortnox Preview (dry run — no bookkeeping performed)

Preview the Fortnox export without writing:
```
POST /finance/invoices/<job_id>/fortnox/preview
X-API-Key: <tenant-key>
```

**Result:** Returns mapped customer + invoice payload that would be sent to Fortnox. No external write occurs.

For actual export (approval-gated):
```
POST /finance/invoices/<job_id>/fortnox/export
X-API-Key: <tenant-key>
{"dry_run": true}
```

## Step 6: Verify via Dashboard

Check the dashboard for updated KPIs:
```
GET /dashboard/summary
GET /dashboard/roi
GET /dashboard/leads
GET /dashboard/operational-insights
X-API-Key: <tenant-key>
```

## What this proves

1. A lead enters the system and is classified/analyzed automatically
2. Customer communication is approval-gated
3. Operations workspace tracks lightweight project data
4. Finance draft prepares invoice documents
5. Fortnox preview shows what would be exported (no bookkeeping performed)
6. Dashboard reflects the state across all stages

## Boundary

This golden path covers **preparation** of invoice/bookkeeping documents. The platform does **not** perform bookkeeping — that remains with the accounting system (Fortnox) and the bookkeeper.
