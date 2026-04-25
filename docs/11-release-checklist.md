# Release Checklist

## Code
- [x] Relevant code committed
- [x] No obvious dead paths in MVP flow
- [x] Env variables documented (`env.example`)
- [x] DB setup verified (`docker-compose.yml` + `scripts/create_tables.py`)

## Test
- [x] Automated tests pass — 1267/1267 (`python -m pytest`)
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
- [x] Control Panel — GET/PUT /dashboard/control; automation toggles, support email, scheduler run_mode; Kontrollpanel tab in UI
- [x] Inbox sync trigger — POST /dashboard/inbox-sync wired to _run_gmail_inbox_sync; 503 if not configured
- [x] Case View — GET /cases (list) + GET /cases/{job_id} (detail); Ärenden tab in operator UI
- [x] Setup / Onboarding Wizard — GET /setup/status (readiness score) + PUT /setup/modules + POST /setup/verify; Onboarding tab in operator UI
- [x] Customer Notifications — GET/PUT /notifications/settings + POST /notifications/daily-digest/send; Notifieringar tab in operator UI
- [x] Scheduler — POST /scheduler/run-once (multi-tenant inbox sync + digest with dedup/send_hour gate) + GET /scheduler/status; scheduler_state persisted in tenant_configs.settings; Scheduler-status section in Kontrollpanel UI
- [x] Runtime schema safeguard — ensure_runtime_schema() adds missing tenant_configs.settings column at startup; idempotent; fails loudly if blocked
- [x] Customer Auto-Reply + Internal Handoff — send_customer_auto_reply + send_internal_handoff injected for lead + inquiry; gated by followups_enabled + customer email; skipped actions persisted with reason; UI labels updated
- [x] Classification v2 — 9-type taxonomy (lead/inquiry/invoice/partnership/supplier/newsletter/internal/spam/unknown); deterministic keyword rules; visibility-only types produce skipped sentinels only; 52 new tests; Swedish UI labels
- [x] Cases UX Upgrade — search (q ILIKE), filter (type/status), sort (received_at/created_at/status/type + asc/desc), pagination (limit/offset); received_at + processed_at in list + detail; customer_email in list; Gmail inbox stores received_at; UI: search/filter/sort/pagination controls; 33 new tests
- [x] Tenant Memory Foundation — GET/PUT /tenant/memory; business_profile, system_map, routing_hints stored in settings.memory; does not clobber other settings; Kundminne tab in UI; 23 tests
- [x] Workflow Scan Status — GET /workflow-scan/status; default shape never_run; tenant-scoped; returns persisted state after scan
- [x] Gmail Workflow Scanner v1 — POST /workflow-scan/gmail; DB-only (no live API calls); known_senders/subject_patterns/detected_mail_types; no-clobber on failure; 25 tests; Skanna Gmail button in UI
- [x] Generic Workflow Scanner Engine — WorkflowScannerEngine + BaseWorkflowScannerAdapter + ADAPTER_REGISTRY; POST /workflow-scan/{system}; 404 for unknown system; multi-system summary merge; 32 tests; future adapters added with one class + one registry line
- [x] Monday Workflow Scanner v1 — MondayWorkflowScannerAdapter reads board structure via get_boards() read-only GraphQL; detect_board_purpose() deterministic keyword classification (lead/invoice/support/partnership/supplier/internal/unknown); persists system_map.monday; no-clobber; 46 tests; Skanna Monday button + summary card in UI
- [x] Routing Hint Drafts — GET /tenant/routing-hint-drafts (read-only draft generation from system_map); POST /tenant/routing-hints/apply (operator-explicit save, validates shape, no-clobber, no external writes); review-first — no auto-routing; 34 tests; Föreslå routing + Spara routing-hints UI in Kundminne tab

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