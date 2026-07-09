# Mårtens Demo — Readiness Checklist

> Check every item before running the demo.
> Classification: **BLOCKER** | **REQUIRED** | **NICE_TO_HAVE** | **DO_NOT_DO**

---

## Infrastructure

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | App is running and `/health` returns `{"status": "ok"}` | `curl -sS https://api.krowolf.se/health` |
| [ ] | BLOCKER | Database is reachable (healthcheck passes) | `curl -sS https://api.krowolf.se/health \| grep db` |
| [ ] | REQUIRED | Latest backup is fresh (< 24 h old) if using production | `sudo bash /opt/krowolf/scripts/check_backup_freshness.sh` |
| [ ] | REQUIRED | Disk usage < 80 % | `df -h /opt/krowolf` |

---

## Demo tenant

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | Tenant `T_MARTENS_DEMO_001` (or equivalent slug) exists | `curl -sS https://api.krowolf.se/admin/tenants -H "X-Admin-API-Key: ADMIN_API_KEY"` |
| [ ] | BLOCKER | `support_email` is configured for the demo tenant | `curl -sS https://api.krowolf.se/tenant -H "X-API-Key: DEMO_TENANT_KEY" \| python3 -m json.tool` |
| [ ] | BLOCKER | `auto_actions` is `false` for ALL job types (lead, customer_inquiry, invoice) | Same as above — check `auto_actions` field |
| [ ] | BLOCKER | `scheduler.run_mode` is `manual` — no automatic inbox sync | Same as above — check `scheduler` field |
| [ ] | REQUIRED | Demo API key is stored securely and not committed to the repo | `git grep DEMO_TENANT_KEY` → no match |
| [ ] | REQUIRED | `enabled_job_types` includes at least `lead` and `customer_inquiry` | Same tenant check |
| [ ] | REQUIRED | `allowed_integrations` includes `google_mail` | Same tenant check |

---

## Approval flow

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | Gmail send requires approval (not auto-dispatched) | Check: `auto_actions.customer_inquiry = false` AND `auto_actions.lead = false` |
| [ ] | BLOCKER | Any old pending `email_send` approvals from previous sessions are handled | `curl -sS https://api.krowolf.se/approvals/pending -H "X-API-Key: DEMO_TENANT_KEY"` → drain or reject |
| [ ] | REQUIRED | Operator has reviewed and understands the approval flow before demo | See `docs/runbooks/pending-approvals.md` |

---

## Gmail setup

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | Mårten's Gmail is connected OR a demo Gmail fallback is available | `curl -sS https://api.krowolf.se/integrations/health -H "X-API-Key: DEMO_TENANT_KEY"` |
| [ ] | BLOCKER | At least 5 realistic Swedish demo emails are prepared in Gmail with label `krowolf-demo` | Check Gmail label — count unread messages |
| [ ] | BLOCKER | Demo emails are marked as unread | Check in Gmail |
| [ ] | BLOCKER | Dry run returns only demo emails (no real customer emails in scope) | `curl -sS -X POST .../gmail/process-inbox -d '{"dry_run":true,"query":"label:krowolf-demo is:unread"}'` |
| [ ] | REQUIRED | Gmail demo label/search scope is documented | See `docs/MARTENS_DEMO_SETUP.md` Step 4 |
| [ ] | REQUIRED | No sensitive or private Gmail content is included in demo | Visual inspection of each demo email |
| [ ] | REQUIRED | No real customer Gmail accounts are connected for this demo | `GOOGLE_MAIL_USER_ID` should be Mårten's demo address |
| [ ] | NICE_TO_HAVE | 10 demo emails covering all scenario types | See `docs/demo/martens-gmail-demo-scenarios.md` |

---

## Visma

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | REQUIRED | Visma framing is clearly sandbox/status-only in all demo materials | See `docs/demo/martens-sales-talk-track.md` |
| [ ] | REQUIRED | No Visma `create_customer` or `create_invoice` calls are made during demo | Do not call `POST /integrations/visma/execute` with write actions |
| [ ] | REQUIRED | Visma status shows connected (or disconnected with clear messaging) | `curl -sS https://api.krowolf.se/integrations/visma/status -H "X-API-Key: DEMO_TENANT_KEY"` |
| [ ] | DO_NOT_DO | **DO NOT** create real Visma invoices, customers, or orders during demo | — |
| [ ] | DO_NOT_DO | **DO NOT** perform Visma production writes of any kind | — |

---

## Google Sheets

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | REQUIRED | Demo Google Sheet "Krowolf - Mårtens Demo" is created with correct structure | See `docs/demo/google-sheets-leads-support-structure.md` |
| [ ] | REQUIRED | Google Sheet ID is stored in env/config only — NOT committed to the repo | `git grep SHEET_ID` → no match |
| [ ] | REQUIRED | Demo sheet is isolated to `T_MARTENS_DEMO_001` only | Manual verification — no other tenant config references this sheet |
| [ ] | REQUIRED | Salesperson knows this is a manual step (no auto-write yet) | Confirmed in talk track |
| [ ] | DO_NOT_DO | **DO NOT** write to any customer-owned Google Sheet during the demo | — |
| [ ] | DO_NOT_DO | **DO NOT** commit the Google Sheet ID or share link to the repo | — |

---

## Data safety

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | No real customer data is used in any demo email | Visual review of all 10 demo email templates |
| [ ] | BLOCKER | No real OAuth tokens, API keys, or secrets are shown or committed | `git status` — no `.env.*` files staged |
| [ ] | REQUIRED | Demo emails use only fictional sender placeholders | See `docs/demo/martens-gmail-demo-scenarios.md` |

---

## Monday

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | DO_NOT_DO | **DO NOT** enable Monday integration for demo tenant | `allowed_integrations` must not include `monday` for demo tenant |
| [ ] | DO_NOT_DO | **DO NOT** perform Monday production writes | — |

---

## Salesperson readiness

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | REQUIRED | Salesperson (Mårten) has clear test instructions before demo | See `docs/MARTENS_DEMO_SETUP.md` and `docs/demo/martens-sales-talk-track.md` |
| [ ] | REQUIRED | Talk track is reviewed — especially Visma and Google Sheets framing | See `docs/demo/martens-sales-talk-track.md` |
| [ ] | NICE_TO_HAVE | Mårten has done a dry run of the demo flow himself | Completed in internal rehearsal |

---

## Post-demo cleanup plan

| Status | Level | Item |
|--------|-------|------|
| [ ] | REQUIRED | Pending demo approvals rejected after demo |
| [ ] | REQUIRED | Demo tenant scheduler paused after demo |
| [ ] | REQUIRED | `krowolf-demo` Gmail label cleared (demo emails re-processed risk) |
| [ ] | REQUIRED | Gmail tokens revoked if connected to production |
| [ ] | REQUIRED | Demo API key rotated if it was shared or shown |
| [ ] | NICE_TO_HAVE | Demo Google Sheet archived after demo |

---

## Sign-off

| | |
|--|--|
| Operator | ________________________________ |
| Date | ________________________________ |
| Demo session | Mårtens Demo — internal sales |
| Status | ☐ GO ☐ NOT GO |
