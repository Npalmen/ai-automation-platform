# Runbook: Incident Response

> **Safety principle:** Pause first, investigate second. It is always safe to pause automation. It is never safe to approve an unknown action during an incident.
> **No global kill switch exists** — each tenant must be paused individually.

---

## Incident severity levels

| Level | Definition | Response time |
|-------|-----------|---------------|
| **P1 Critical** | Unexpected external write (email sent without approval, Monday item created without approval) | Immediate — pause tenant, escalate to platform team |
| **P2 High** | Repeated job failures, OAuth token failure, integration unreachable | Within 1 hour |
| **P3 Medium** | Stale approval queue (> 10 items), slow job processing | Within 4 hours |
| **P4 Info** | Single job failure, UI not loading, minor misclassification | Within 24 hours |

---

## P1: Unexpected external write

An email was sent or a Monday item was created without an operator approving it.

### Immediate actions

1. **Pause automation for the affected tenant immediately:**
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/pause-automation \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"P1 incident — unexpected external write"}'

   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/disable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"P1 incident — unexpected external write"}'
   ```

2. **Capture logs immediately:**
   ```bash
   ssh ubuntu@api.krowolf.se \
     "sudo docker compose -f /opt/krowolf/docker-compose.prod.yml logs --tail=1000 app \
      > /tmp/incident-$(date +%Y%m%d-%H%M%S).log && echo saved"
   ```

3. **Inspect integration events:**
   ```bash
   curl -sS https://api.krowolf.se/integration-events \
     -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
   # Find the event that triggered the unexpected write
   # Record: job_id, action, created_at
   ```

4. **Inspect audit events:**
   ```bash
   curl -sS https://api.krowolf.se/audit-events \
     -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
   # Look for: approval events that should not have occurred
   ```

5. **Notify platform team immediately.** Include:
   - Affected tenant ID
   - Action that occurred (email to whom, Monday item)
   - Job ID and approval ID (if applicable)
   - Timestamp
   - Log file path

### Do NOT do during P1

- Do not approve any further approvals.
- Do not retry any jobs.
- Do not disable auth or loosen tenant isolation.
- Do not attempt to undo the external write inside the platform — contact the external service directly (Gmail: check Sent folder; Monday: delete the item manually).

---

## P2: Repeated job failures

Multiple jobs failing in a short period. Usually OAuth expiry or integration credential issue.

1. **Check triage queue:**
   ```bash
   curl -sS https://api.krowolf.se/admin/operations/needs-help \
     -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool
   ```

2. **Check integration health:**
   ```bash
   curl -sS https://api.krowolf.se/integrations/health \
     -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
   ```

3. **Pause scheduler while investigating** (prevents more failures accumulating):
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/disable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"P2 — pausing while investigating repeated failures"}'
   ```

4. **Fix root cause:**
   - OAuth error → `docs/runbooks/oauth-errors.md`
   - Integration error → `docs/runbooks/integration-errors.md`
   - Pipeline bug → inspect logs, contact platform team

5. **Resume after fix:**
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/enable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"P2 resolved — root cause fixed"}'
   ```

6. **Retry failed jobs individually** (see `docs/runbooks/failed-jobs.md`).

---

## P3: Stale approval queue

```bash
# Inspect all pending approvals
curl -sS https://api.krowolf.se/approvals/pending \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# For each stale approval with no operator available — reject with note
curl -sS -X POST https://api.krowolf.se/approvals/APPROVAL_ID/reject \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin","note":"P3 incident — stale queue cleanup; no active operator"}'
```

---

## P4: Single job failure

See `docs/runbooks/failed-jobs.md` for step-by-step job recovery.

---

## Post-incident

After resolving any P1 or P2 incident:

1. **Document in `docs/07-decisions.md`** if a process or configuration decision was made.
2. **Update `docs/01-current-truth.md`** if the incident revealed a new verified state.
3. **Resume automation** only after root cause is confirmed fixed:
   ```bash
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/resume-automation \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"P1/P2 resolved — root cause confirmed fixed"}'
   curl -sS -X POST https://api.krowolf.se/admin/support/TENANT_ID/enable-scheduler \
     -H "X-Admin-API-Key: ADMIN_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"actor":"admin","note":"P1/P2 resolved — root cause confirmed fixed"}'
   ```
4. **Verify health:**
   ```bash
   curl -sS https://api.krowolf.se/health
   curl -sS https://api.krowolf.se/integrations/health -H "X-API-Key: TENANT_KEY"
   curl -sS https://api.krowolf.se/approvals/pending -H "X-API-Key: TENANT_KEY"
   ```

---

## Escalation contacts

- Platform team: responsible for DB recovery, container restart, and code fixes.
- Operator on call: responsible for approval decisions and tenant pause/resume.
- Customer contact: only if an external write affected a real customer (P1 only).
