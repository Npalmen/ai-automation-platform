# Runbook: Failed Jobs

> **Safety:** Pause the tenant before retrying jobs if the failure is systemic.
> **Isolation:** Recovery actions require both `X-Admin-API-Key` and `X-Tenant-ID`.

---

## Overview

Jobs can end in `failed` or `manual_review` status. Failed jobs are surfaced in the admin triage queue. This runbook covers how to find, diagnose, and recover failed jobs without triggering unintended external actions.

---

## Status reference

| Status | Meaning |
|--------|---------|
| `completed` | Pipeline ran fully; all dispatches succeeded or were intentionally skipped. |
| `awaiting_approval` | Paused for operator approval. See `docs/runbooks/pending-approvals.md`. |
| `manual_review` | Routed to manual review by policy (low confidence, high-risk, or rejection). |
| `failed` | An action dispatch step failed. Error is persisted to audit and `action_executions`. |

---

## Step 1: Find failed jobs

```bash
# Admin triage queue — shows failed/stale jobs across all tenants
curl -sS "https://api.krowolf.se/admin/operations/needs-help" \
  -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool

# Per-tenant job list (filter manually by status)
curl -sS "https://api.krowolf.se/jobs?limit=100" \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
```

---

## Step 2: Inspect the failed job

```bash
# Full job detail including result and error
curl -sS https://api.krowolf.se/jobs/JOB_ID \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# Actions executed for this job
curl -sS https://api.krowolf.se/jobs/JOB_ID/actions \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# Audit trail
curl -sS https://api.krowolf.se/audit-events \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
```

Look for:
- `result.error` or `result.error_detail` — the root cause
- Integration errors (Gmail 503, Monday 400) vs pipeline errors

---

## Step 3: Decide recovery action

**Do not retry blindly.** Check whether the failure was:

| Failure type | Recovery action |
|-------------|-----------------|
| Gmail `invalid_grant` (OAuth expired) | Fix tokens first (see `docs/runbooks/oauth-errors.md`), then retry |
| Gmail `503` (transient) | Retry the job after a short wait |
| Monday `400 board_id missing` | Check env vars, then retry |
| Pipeline classification error | Reclassify and reprocess |
| Extraction error | Re-extract and retry |
| Action dispatch error (non-OAuth) | Replay dispatch only |
| Unknown/systemic | Pause tenant, investigate logs, then retry |

---

## Step 4: Recovery commands

All recovery actions require admin key + tenant ID header.

```bash
# Full pipeline retry (for failed or manual_review jobs)
curl -sS -X POST https://api.krowolf.se/admin/recovery/JOB_ID/retry \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'

# Replay dispatch only (skip re-classification and extraction)
curl -sS -X POST https://api.krowolf.se/admin/recovery/JOB_ID/replay-dispatch \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'

# Force reclassification and full pipeline
curl -sS -X POST https://api.krowolf.se/admin/recovery/JOB_ID/reclassify \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'

# Re-run extraction only
curl -sS -X POST https://api.krowolf.se/admin/recovery/JOB_ID/re-extract \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'

# Reprocess Gmail source (re-fetch email and reprocess)
curl -sS -X POST "https://api.krowolf.se/admin/recovery/JOB_ID/reprocess-gmail?force=false" \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'
```

**Expected response:**
```json
{"status":"success","action":"retry","job_id":"...","tenant_id":"...","message":"...","details":{}}
```

---

## Step 5: Verify recovery

```bash
# Check job status after retry
curl -sS https://api.krowolf.se/jobs/JOB_ID \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Expect: status "completed" or "awaiting_approval"

# Check audit events for the action
curl -sS https://api.krowolf.se/audit-events \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
```

---

## Systemic failure (multiple jobs failing)

1. Pause the scheduler immediately:
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/disable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"systemic failure — pausing to investigate"}'
   ```
2. Pause automation (blocks demo mode sends):
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/pause-automation \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"systemic failure — pausing to investigate"}'
   ```
3. Inspect logs on server:
   ```bash
   ssh ubuntu@api.krowolf.se "sudo docker compose -f /opt/krowolf/docker-compose.prod.yml logs --tail=300 app"
   ```
4. Fix root cause, then resume:
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/resume-automation \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"root cause fixed"}'
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/enable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"root cause fixed"}'
   ```

---

## Related runbooks

- `docs/runbooks/oauth-errors.md` — Gmail/OAuth failures
- `docs/runbooks/integration-errors.md` — Monday/Fortnox integration errors
- `docs/runbooks/incident-response.md` — unexpected external writes
