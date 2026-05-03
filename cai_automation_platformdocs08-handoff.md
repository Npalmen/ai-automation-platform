
## Completed slice (2026-04-26 — Slice 14: Integration Health Center)

### Problem solved
Operators had no way to see whether Gmail and Monday integrations were actually working without making external API calls or reading raw environment variables.

### What was built

**`app/health/integration_health.py`** — new module

`get_integration_health(db, tenant_id, *, app_settings)` returns:
```json
{
  "tenant_id": "...",
  "overall_status": "healthy|warning|error",
  "systems": {
    "gmail": { "status": "...", "configured": bool, "last_success_at": "...", "last_error_at": "...", "last_error_message": "...", "checks": [...], "recommended_action": "..." },
    "monday": { "...same shape..." }
  },
  "recent_errors": [{"action": "...", "category": "...", "created_at": "..."}]
}
```

Per-system checks (all read-only, no external API calls):

| Check key | Gmail | Monday |
|-----------|-------|--------|
| `config_present` | `GOOGLE_MAIL_ACCESS_TOKEN` set | `MONDAY_API_KEY` set |
| `scanner_ran` | `workflow_scan.summary.gmail.status == "success"` | `workflow_scan.summary.monday.status == "success"` |
| `inbox_sync` / `dispatch_success` | Latest `AuditEventRecord` with `action="gmail_inbox_sync"` | Latest `IntegrationEvent` with `integration_type="controlled_dispatch"` |

Overall status aggregation: `error` if any system is error, `warning` if any system is warning or not_configured, else `healthy`.

**`app/main.py`** — `GET /integrations/health` endpoint (tenant-authenticated)

**`app/ui/index.html`** — "Integrationshälsa" card added to Dashboard tab (between ROI Rapport and Senaste aktivitet); `loadIntegrationHealth()` called on dashboard load; shows overall badge + per-system status + recommended_action + recent_errors list.

### Constraints respected
- No external API calls from health endpoint
- No secrets in response (config_present is boolean, not the token value)
- Tenant-scoped (wrong-tenant data never returned)
- read-only — no writes, no side effects

### Tests
47 new tests in `tests/test_integration_health.py`:
- `TestCheckGmail` (12) — not_configured, warning/warning/healthy/warning paths, checks shape, no secrets, recommended_action, last_success_at None
- `TestCheckMonday` (10) — not_configured, warning/healthy/warning paths, no secrets, checks shape, recommended_action, last_error_message
- `TestOverallStatus` (6) — healthy, warning (one warning), warning (not_configured), error, error-over-warning, both not_configured
- `TestRecentErrors` (5) — empty list, dict shape, no secrets/details, created_at isoformat, None created_at
- `TestGetIntegrationHealth` (14) — response shape, systems present, default not_configured, overall_status, tenant_id, no secrets, gmail/monday configured, overall_healthy, no external calls, tenant isolation, recent_errors list, system health fields, overall_error

**1589/1589 total tests pass.**
