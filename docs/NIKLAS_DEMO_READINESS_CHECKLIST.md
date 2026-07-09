# Niklas Demo — Readiness Checklist (Rehearsal)

> This is the rehearsal checklist. Complete ALL BLOCKER and REQUIRED items
> before marking Niklas Demo as GO.
>
> **Only proceed to Mårtens Demo after Niklas Demo is fully GREEN.**
>
> Classification: **BLOCKER** | **REQUIRED** | **NICE_TO_HAVE** | **DO_NOT_DO**

---

## Infrastructure

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | App is running and `/health` returns `{"status": "ok"}` | `curl -sS https://api.krowolf.se/health` |
| [ ] | BLOCKER | Database is reachable | `curl -sS https://api.krowolf.se/health \| grep db` |
| [ ] | REQUIRED | Latest backup is fresh (< 24 h old) if using production | `sudo bash /opt/krowolf/scripts/check_backup_freshness.sh` |

---

## Demo tenant

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | Tenant `T_NIKLAS_DEMO_001` exists | `curl -sS https://api.krowolf.se/admin/tenants -H "X-Admin-API-Key: ADMIN_API_KEY" \| python3 -m json.tool \| grep -A3 "Niklas"` |
| [ ] | BLOCKER | `support_email` is configured (e.g. `niklas.palm@sol-f.se`) | `curl -sS https://api.krowolf.se/tenant -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY" \| python3 -m json.tool` |
| [ ] | BLOCKER | `auto_actions=false` for ALL job types (lead, customer_inquiry, invoice) | Same as above — check `auto_actions` field |
| [ ] | BLOCKER | `scheduler.run_mode` is `manual` — no automatic inbox sync | Same as above — check `scheduler` field |
| [ ] | REQUIRED | Niklas Demo API key is stored securely and not committed to repo | `git grep NIKLAS_DEMO_TENANT_KEY` → no match |
| [ ] | REQUIRED | `enabled_job_types` includes `lead` and `customer_inquiry` | Same tenant check |
| [ ] | REQUIRED | `allowed_integrations` includes `google_mail` | Same tenant check |

---

## Approval flow

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | Gmail send requires approval — not auto-dispatched | `auto_actions.customer_inquiry=false` AND `auto_actions.lead=false` |
| [ ] | BLOCKER | Old unrelated pending `email_send` approvals from previous sessions handled | `curl -sS https://api.krowolf.se/approvals/pending -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY"` → drain or reject |

---

## Gmail setup

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | `niklas.palm@sol-f.se` is connected OR a fallback demo Gmail is available | `curl -sS https://api.krowolf.se/integrations/health -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY"` |
| [ ] | BLOCKER | Gmail label `krowolf-demo-niklas` has been created | Confirm in Gmail settings |
| [ ] | BLOCKER | At least 5 realistic Swedish demo emails are under the `krowolf-demo-niklas` label | Check Gmail label — count unread messages |
| [ ] | BLOCKER | Demo emails are marked as unread | Check in Gmail |
| [ ] | BLOCKER | Dry_run with `label:krowolf-demo-niklas is:unread` returns only demo emails | `curl -sS -X POST .../gmail/process-inbox -d '{"dry_run":true,"query":"label:krowolf-demo-niklas is:unread"}'` |
| [ ] | BLOCKER | Gmail query `label:krowolf-demo-niklas is:unread` is used for all syncs | Confirmed in all curl commands |
| [ ] | REQUIRED | No sensitive or private `niklas.palm@sol-f.se` email content is used in demo | Visual inspection of each demo email |
| [ ] | REQUIRED | `GOOGLE_MAIL_USER_ID` is set to `niklas.palm@sol-f.se` in `.env.production` | `grep GOOGLE_MAIL_USER_ID .env.production` (do not print tokens) |
| [ ] | NICE_TO_HAVE | 10+ demo emails covering all scenario types | See `docs/demo/martens-gmail-demo-scenarios.md` |

---

## Visma

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | REQUIRED | Visma status checked — read-only framing confirmed | `curl -sS https://api.krowolf.se/integrations/visma/status -H "X-API-Key: NIKLAS_DEMO_TENANT_KEY"` |
| [ ] | DO_NOT_DO | **DO NOT** create real Visma invoices, customers, or orders during rehearsal | — |
| [ ] | DO_NOT_DO | **DO NOT** perform Visma production writes of any kind | — |
| [ ] | DO_NOT_DO | **DO NOT** call `POST /integrations/visma/execute` with write actions | — |

---

## Google Sheets

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | REQUIRED | Google Sheet "Krowolf - Niklas Demo" is created (separate from "Krowolf - Mårtens Demo") | Open in browser |
| [ ] | REQUIRED | Sheet has Leads, Support, and Logg tabs per structure doc | See `docs/demo/google-sheets-leads-support-structure.md` |
| [ ] | REQUIRED | Google Sheet ID is stored in env/config only — NOT committed to repo | `git grep SHEET_ID` → no match |
| [ ] | REQUIRED | Sheet is shared only with `niklas.palm@sol-f.se` and operator account | Google Sheet sharing settings |
| [ ] | DO_NOT_DO | **DO NOT** write to "Krowolf - Mårtens Demo" during the Niklas rehearsal | — |
| [ ] | DO_NOT_DO | **DO NOT** commit the Google Sheet ID or share link to the repo | — |

---

## Monday

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | DO_NOT_DO | **DO NOT** enable Monday integration for Niklas Demo tenant | `allowed_integrations` must not include `monday` |
| [ ] | DO_NOT_DO | **DO NOT** perform Monday production writes | — |

---

## Data safety

| Status | Level | Item | Verification |
|--------|-------|------|--------------|
| [ ] | BLOCKER | No real customer data is used in any demo email | Visual review of all demo email content |
| [ ] | BLOCKER | No real OAuth tokens, API keys, or secrets are committed to repo | `git status` — no `.env.*` files staged |
| [ ] | REQUIRED | Demo emails use only fictional sender placeholders (`@example.com`) | Visual check |
| [ ] | REQUIRED | No private mailbox content from `niklas.palm@sol-f.se` is used | Confirm each email is a manually prepared scenario |

---

## Rehearsal result documentation

| Status | Level | Item |
|--------|-------|------|
| [ ] | REQUIRED | Rehearsal results documented in writing before Mårtens Demo (see Step 11 in `NIKLAS_DEMO_SETUP.md`) |
| [ ] | REQUIRED | All BLOCKER items are PASS before Mårtens Demo |
| [ ] | REQUIRED | Any issues found are fixed or explicitly accepted before Mårtens Demo |
| [ ] | NICE_TO_HAVE | Rehearsal run is tested twice (catch config drift between runs) |

---

## Post-rehearsal cleanup

| Status | Level | Item |
|--------|-------|------|
| [ ] | REQUIRED | Pending demo approvals rejected after rehearsal |
| [ ] | REQUIRED | Niklas Demo tenant scheduler paused after rehearsal |
| [ ] | REQUIRED | `krowolf-demo-niklas` label cleared or demo emails marked processed |
| [ ] | REQUIRED | Token decision made: keep for Mårtens Demo or switch to Mårten's OAuth |
| [ ] | NICE_TO_HAVE | "Krowolf - Niklas Demo" sheet archived after rehearsal |

---

## Sign-off

| | |
|--|--|
| Operator | ________________________________ |
| Date | ________________________________ |
| Rehearsal session | Niklas Demo — pre-Mårten rehearsal |
| Status | ☐ GO (proceed to Mårtens Demo) ☐ NOT GO (fix issues first) |
