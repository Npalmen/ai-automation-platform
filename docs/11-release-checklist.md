# Release Checklist

## Code
- [x] Relevant code committed
- [x] No obvious dead paths in MVP flow
- [x] Env variables documented (`env.example`)
- [x] DB setup verified (`docker-compose.yml` + `scripts/create_tables.py`)

## Test
- [x] Automated tests pass — 702/702 (`python -m pytest`)
- [x] Official MVP smoke test documented in README (curl commands, step by step)
- [x] Gmail send_email verified live (real Gmail delivery confirmed)
- [x] Gmail list_messages verified live (real inbox messages returned)
- [x] Gmail get_message verified live (full message including body_text returned)
- [x] Gmail inbox trigger implemented (`POST /gmail/process-inbox` — reads unread, creates jobs)
- [x] Monday create_item verified live (real board item confirmed)
- [x] Monday create_monday_item via workflow verified live (action_dispatch → real board item)
- [x] Multi-action dispatch tested live (Monday + Gmail in single job)
- [x] Real lead ingestion flow verified (manual): list_messages → get_message → /jobs → Monday item
- [x] Automated ingestion flow implemented: POST /gmail/process-inbox → lead jobs → Monday
- [x] Follow-up question engine — completeness evaluation + follow-up email for incomplete lead/inquiry; invoice incomplete info in internal task
- [x] Thread continuation — inbox replies in same Gmail thread update existing job, no duplicate created
- [x] Activity Dashboard — GET /dashboard/summary + GET /dashboard/activity; Dashboard tab in operator UI
- [x] ROI Dashboard — GET /dashboard/roi; estimated time/value savings; ROI section in Dashboard tab

## Docs
- [x] current-state updated
- [x] backlog updated
- [x] handoff updated
- [x] decisions updated (DEC-001 revised, DEC-004 added)

## Deployment / operability
- [x] Local start from clean environment documented in README
- [x] Docker path documented and verified (`docker-compose up -d` starts Postgres)
- [x] Health endpoint verified (`GET /` returns `{"status":"ok"}`)
- [x] Demo instructions verified (README smoke test + operator UI at `/ui`)
- [x] All 6 DB tables register with `database.Base` and are created by `create_all` on startup

## Completed before full release
- [x] UI auth — operator UI sends X-API-Key; key stored in localStorage
- [x] UI rendering stable — HTML escaping + layout height fix applied
- [x] DB-driven tenant config — `tenant_configs` table + repository + fallback logic
- [x] Gmail OAuth token refresh — refresh on 401, retry once, fail cleanly
- [x] Integration event persistence — real DB row on every `POST /integrations/{type}/execute`
- [x] MVP hardening — removed unauthenticated `/tenant/test` debug route; fixed Pydantic v2 deprecation warnings
- [x] Gmail list_messages + get_message — read actions implemented, tested, and verified live
- [x] Monday workflow wiring — `create_monday_item` action type wired into action_executor; `is_integration_configured` extended for api_key+board_id configs
- [x] Full Gmail → lead → Monday flow verified end-to-end (manual trigger)
- [x] Gmail inbox trigger — `POST /gmail/process-inbox` implemented with full hardening (dedup, mark-as-read, type-gating, phone extraction, Slack notify, dry_run, query override)
- [x] Deterministic classification — invoice > lead > customer_inquiry keyword fallback; no `"unknown"` result
- [x] Customer inquiry flow — `create_monday_item` + `send_email` to support; HIGH/NORMAL priority
- [x] Invoice flow — `create_monday_item` + `create_internal_task`; deterministic extraction of amount, invoice_number, due_date, supplier_name
- [x] Inbox type inference — `/gmail/process-inbox` infers correct `job_type` before job creation
- [x] 702/702 tests pass (now 725/725 after follow-up engine)