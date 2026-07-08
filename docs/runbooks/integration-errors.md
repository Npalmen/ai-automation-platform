# Runbook: Integration Errors

> **Safety:** No external write should be retried blindly. Check what the action was and whether a duplicate write would be acceptable before retrying.
> **Isolation:** Integration events and errors are tenant-scoped.

---

## Overview

Integration errors occur when the platform attempts to dispatch an action to an external system (Gmail, Monday, Fortnox) and the external system returns an error or the credentials are invalid. This runbook covers diagnosis and safe recovery.

---

## Step 1: Identify the error

```bash
# Integration health — overall status per system
curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Look for: system.status, system.last_error_message, system.recommended_action

# Recent integration events (read, write, and error events)
curl -sS https://api.krowolf.se/integration-events \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool

# Admin triage — shows integration errors across all tenants
curl -sS https://api.krowolf.se/admin/operations/needs-help \
  -H "X-Admin-API-Key: ADMIN_API_KEY" | python3 -m json.tool
```

---

## Gmail errors

| Error | Cause | Fix |
|-------|-------|-----|
| `503 invalid_grant` | Refresh token expired or revoked | See `docs/runbooks/oauth-errors.md` |
| `503 unauthorized_client` | Client ID/secret mismatch | See `docs/runbooks/oauth-errors.md` |
| `503 gmail send failed` | Send failed after successful auth | Check recipient email, subject, body |
| `400 Missing to / subject / body` | Payload missing required fields | Inspect job result — re-create job with correct payload |
| `403` | Gmail scopes insufficient or account access revoked | Re-authorize in Google Cloud Console |

**Check Gmail send events:**
```bash
curl -sS https://api.krowolf.se/integration-events \
  -H "X-API-Key: TENANT_KEY" | python3 -c "
import sys,json
d=json.load(sys.stdin)
events=d if isinstance(d,list) else d.get('items',d.get('events',[]))
for e in events:
    if 'gmail' in str(e.get('action','')).lower():
        print(e.get('action'), e.get('status'), e.get('created_at'))
"
```

---

## Monday errors

| Error | Cause | Fix |
|-------|-------|-----|
| `400 Missing monday api_key` | `MONDAY_API_KEY` env var not set | Add to `.env.production`, recreate container |
| `400 Missing monday board_id` | `MONDAY_BOARD_ID` is 0 or unset | Add to `.env.production`, recreate container |
| `400 Missing item_name` | `item_name` field not in payload | Inspect job result — reclassify if needed |
| `403 Forbidden` | `monday` not in tenant `allowed_integrations` | Update tenant config (see below) |
| `503` | Monday GraphQL error (invalid token, board not found, wrong column ID) | Check `MONDAY_API_KEY` validity, verify board ID |

**Check Monday item status:**
```bash
# Monday health
curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
# Look for: systems.monday.status, systems.monday.last_error_message

# Add monday to tenant allowed integrations if missing
curl -sS -X PUT https://api.krowolf.se/tenant/config \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"enabled_job_types":["lead","customer_inquiry"],"allowed_integrations":["google_mail","monday"],"auto_actions":{"lead":false,"customer_inquiry":false}}'
```

**Test Monday write in isolation (before enabling auto_actions):**
```bash
curl -sS -X POST https://api.krowolf.se/integrations/monday/execute \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action":"create_item","payload":{"item_name":"PILOT TEST — safe to delete"}}'
# Expect: HTTP 200 with item details
# Then manually verify and delete the test item from Monday
```

---

## Fortnox errors

Fortnox is not active in the pilot (not configured). If Fortnox appears in integration events unexpectedly:
1. Pause the tenant immediately.
2. Check `auto_actions` — `invoice` should be `false`.
3. Check integration events for unexpected `fortnox_write` events.
4. Report as a potential incident (see `docs/runbooks/incident-response.md`).

---

## Env var fix + container recreate procedure

If an env var is missing or wrong:

```bash
ssh ubuntu@api.krowolf.se
sudo nano /opt/krowolf/.env.production
# Make the change (e.g. add MONDAY_API_KEY=xxx)
# Save and exit

cd /opt/krowolf
# IMPORTANT: use up -d, not restart — restart does not re-read .env.production
sudo docker compose -f docker-compose.prod.yml up -d app

# Verify
curl -sS https://api.krowolf.se/health
curl -sS https://api.krowolf.se/integrations/health \
  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool
```

---

## Retry after fixing credentials

```bash
# Replay dispatch only (does not re-classify or re-extract)
curl -sS -X POST https://api.krowolf.se/admin/recovery/JOB_ID/replay-dispatch \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'

# Full retry (if classification or extraction also needs to run again)
curl -sS -X POST https://api.krowolf.se/admin/recovery/JOB_ID/retry \
  -H "X-Admin-API-Key: ADMIN_API_KEY" \
  -H "X-Tenant-ID: TENANT_ID" \
  -H "Content-Type: application/json" \
  -d '{"actor":"admin"}'
```

> **Duplicate write risk:** If the integration action partially succeeded before the error, retrying may create a duplicate Monday item or duplicate email. Check the integration's side before retrying.

---

## Set up integration error alerts

```bash
curl -sS -X PUT https://api.krowolf.se/alerts/config \
  -H "X-API-Key: TENANT_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "recipient_email": "SUPPORT_EMAIL",
    "channel": "email",
    "dedup_window_hours": 4,
    "thresholds": {}
  }'
```

---

## Related runbooks

- `docs/runbooks/oauth-errors.md` — Gmail OAuth token errors
- `docs/runbooks/failed-jobs.md` — jobs that failed during pipeline
- `docs/runbooks/incident-response.md` — unexpected external writes
