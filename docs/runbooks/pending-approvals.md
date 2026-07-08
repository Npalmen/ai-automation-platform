# Runbook: Pending Approvals

> **Safety:** Fail-closed. Never approve an unknown action. When in doubt, reject.
> **Isolation:** All approval operations are tenant-scoped. One tenant cannot see or action another tenant's approvals.

---

## Overview

The platform pauses jobs that require human review before dispatching an external action. Pending approvals sit in a queue until an operator explicitly approves or rejects them.

**Key principle:** Approving is irreversible. Rejection is always safe.

---

## Approval types (`next_on_approve`)

| Value | What happens on approve |
|-------|------------------------|
| `email_send` | Sends an email to a customer. **Cannot be undone.** Review recipient and body before approving. |
| `action_dispatch` | Resumes pipeline; may dispatch an internal task (`create_internal_task`). Low risk — no external write in current pilot config. |
| `controlled_dispatch` | Resumes a controlled external dispatch step. Review before approving. |
| `finance_fortnox_export` | Exports invoice to Fortnox. **Not active in pilot.** |

---

## Routine: Check pending approvals

```bash
# List pending approvals for pilot tenant
curl -sS https://api.krowolf.se/approvals/pending \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# Key fields to inspect per approval:
# - approval_id: used for approve/reject
# - next_on_approve: what will execute on approval (see table above)
# - title / summary: human-readable description
# - job_id: the job this approval belongs to
# - created_at: how long it has been waiting
```

---

## Routine: Reject an approval (always safe)

```bash
curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/reject \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"operator","note":"reason for rejection"}'
```

**Expected response:** `{"status":"rejected","approval_id":"...","message":"..."}`

Rejection never sends email, never writes to Monday/Fortnox/Visma.

---

## Routine: Approve an approval (irreversible for email_send)

Only approve after reviewing `next_on_approve`, title, and summary.

```bash
curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/approve \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"operator","note":"approved after review"}'
```

> **Body `{}` is required.** Sending no body causes a parse error.

---

## Routine: Inspect the job behind an approval

```bash
# Get the job to understand what generated this approval
curl -sS https://api.krowolf.se/jobs/JOB_ID \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# See approval history for the job
curl -sS https://api.krowolf.se/jobs/JOB_ID/approvals \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
```

---

## Routine: Stale approval (> 24h old)

If an approval has been pending for more than 24h:

1. Check `GET /admin/operations/needs-help` — it surfaces stale approvals.
2. Inspect the approval (job type, next_on_approve, summary).
3. If not actionable: reject with a note explaining why.
4. If actionable: escalate to the responsible operator.

```bash
# Admin triage — shows stale approvals across all tenants
curl -sS https://api.krowolf.se/admin/operations/needs-help \
  -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool

# Resend approval notification to responsible party
curl -sS -X POST https://api.krowolf.se/admin/recovery/JOB_ID/resend-approval \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'
```

---

## Escalation

- **email_send approval pending > 1h:** notify the operator responsible for the tenant immediately.
- **Unknown approval with no context:** reject. Do not approve without understanding what will be sent.
- **Approval queue growing (> 10 pending):** pause the scheduler to stop new jobs from entering while queue is cleared.

```bash
# Pause scheduler to stop new approvals accumulating
curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/disable-scheduler \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"operator","note":"pausing while approval queue is cleared"}'
```

---

## Related runbooks

- `docs/runbooks/failed-jobs.md` — for jobs that failed during pipeline
- `docs/runbooks/incident-response.md` — for unexpected external writes
