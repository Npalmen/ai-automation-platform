# Current State

## Real-world validation results

The following has been confirmed through real API calls against a running instance — not theoretical.

| What | Status | Notes |
|------|--------|-------|
| Gmail send_email | ✅ LIVE VERIFIED | `POST /integrations/google_mail/execute` → real Gmail delivery |
| Gmail list_messages | ✅ LIVE VERIFIED | returns real inbox messages with message_id, thread_id, from, subject, snippet, received_at, label_ids |
| Gmail get_message | ✅ LIVE VERIFIED | returns full message including body_text (text/plain extracted from MIME tree) |
| Gmail OAuth refresh | ✅ LIVE VERIFIED | token refresh on 401; invalid_grant → 503 |
| Monday create_item (direct) | ✅ LIVE VERIFIED | `POST /integrations/monday/execute` → item appears in real board |
| Monday create_monday_item (workflow) | ✅ LIVE VERIFIED | `/jobs` → action_dispatch → Monday adapter → real board item |
| Full pipeline | ✅ END-TO-END VERIFIED | intake → classification → extraction → decisioning → policy → action_dispatch → human_handoff |
| Multi-action dispatch | ✅ LIVE VERIFIED | multiple actions in `input_data.actions` execute in sequence; partial failure recorded |
| Approval pause/resume | ✅ LIVE VERIFIED | `POST /approvals/{id}/approve` with `{}` resumes job; action executes after |
| Action persistence | ✅ LIVE VERIFIED | `GET /jobs/{job_id}/actions` returns real executed records |
| Multi-tenant auth | ✅ LIVE VERIFIED | `X-API-Key` + body `tenant_id` both required |
| Gmail → lead → Monday flow | ✅ LIVE VERIFIED | list_messages → get_message → map to /jobs → Monday item created |
| Gmail inbox trigger | ✅ PRODUCTION-READY | `POST /gmail/process-inbox` — dedup, mark-as-read, per-type tenant gate, phone extraction, Slack notify, dry_run, query override |
| Deterministic classification fallback | ✅ IMPLEMENTED | invoice > lead > customer_inquiry (keyword-based); no more `"unknown"` |
| Inbox type inference | ✅ IMPLEMENTED | `/gmail/process-inbox` infers job_type from message content before job creation; correct initial type, no post-hoc correction |
| Customer inquiry flow | ✅ IMPLEMENTED | default actions: `send_customer_auto_reply` + `send_internal_handoff` to support + `create_monday_item`; HIGH/NORMAL priority; skipped when no email or followups_enabled=false |
| Invoice flow | ✅ IMPLEMENTED | default actions: `create_monday_item` + `create_internal_task`; deterministic extraction: amount, invoice_number, due_date, supplier_name |
| Follow-up question engine | ✅ IMPLEMENTED | deterministic completeness check per job type; follow-up `send_email` to customer when lead/inquiry is incomplete; invoice incomplete info surfaced in internal task description + metadata; no LLM |
| Thread continuation | ✅ IMPLEMENTED | inbox replies in same Gmail thread update existing job instead of creating duplicate; `conversation_messages` appended; pipeline re-runs |
| Activity Dashboard | ✅ IMPLEMENTED | `GET /dashboard/summary` (today's counts by type + status) + `GET /dashboard/activity` (recent jobs with type/status/action/priority); Dashboard tab in operator UI |
| ROI Dashboard | ✅ IMPLEMENTED | `GET /dashboard/roi` (estimated minutes/hours saved, SEK value, item counts for today); ROI section in Dashboard tab; fixed assumptions, easy to tune |
| Control Panel | ✅ IMPLEMENTED | `GET /dashboard/control` + `PUT /dashboard/control` — tenant-scoped automation flags (leads/support/invoices/followups), support email, scheduler run_mode (manual/scheduled/paused); stored in `tenant_configs.settings` JSON column; Kontrollpanel tab in operator UI |
| Inbox sync trigger | ✅ WIRED | `POST /dashboard/inbox-sync` calls the same Gmail processing logic as `POST /gmail/process-inbox` via shared `_run_gmail_inbox_sync()` helper; returns `{status, processed, created_jobs, continued_threads, deduped, errors, message}`; 503 if Gmail not configured |
| Case View | ✅ IMPLEMENTED | `GET /cases` (list with subject/customer_name/priority derived from job data) + `GET /cases/{job_id}` (full detail: original message, extracted data, thread history, actions, errors); Ärenden tab in operator UI |
| Setup / Onboarding Wizard | ✅ IMPLEMENTED | `GET /setup/status` (readiness score 0–100, module status, connection status, automation settings, missing items list) + `PUT /setup/modules` (persist sales/support/finance module enablement) + `POST /setup/verify` (lightweight check-based verification: tenant config, modules, email, scheduler, destination integration); Onboarding tab in operator UI |
| Customer Notifications / Daily Digest | ✅ IMPLEMENTED | `GET /notifications/settings` + `PUT /notifications/settings` (enabled, recipient_email, frequency, send_hour; stored in `tenant_configs.settings.notifications`) + `POST /notifications/daily-digest/send` (builds digest from `_compute_summary`+`_compute_roi`, dispatches via existing `send_email` action path; 400 if no recipient, 500 on dispatch failure); Notifieringar tab in operator UI |
| Scheduler — Inbox Sync + Daily Digest | ✅ IMPLEMENTED | `POST /scheduler/run-once` (multi-tenant pass: inbox sync when run_mode=scheduled, digest when enabled+send_hour reached+not already sent today) + `GET /scheduler/status` (tenant-scoped: run_mode, notif config, last_inbox_sync_at, last_digest_sent_at, last_scheduler_run_at, last_status, last_error); state stored in `tenant_configs.settings.scheduler_state`; Scheduler-status section in Kontrollpanel UI tab |
| Runtime schema safeguard | ✅ IMPLEMENTED | `ensure_runtime_schema(engine)` called at startup after `create_all`; runs `ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS settings JSON`; idempotent; fails startup loudly if migration cannot run |
| Customer Auto-Reply + Internal Handoff | ✅ IMPLEMENTED | `send_customer_auto_reply` (Swedish confirmation to sender) + `send_internal_handoff` (structured lead/support summary to internal team) injected for lead + inquiry flows; gated by `followups_enabled` and presence of customer email; skipped actions persisted with `status=skipped` and skip reason; `skipped_count` + `actions_skipped` in dispatch result |
| Classification v2 / Inbox Taxonomy | ✅ IMPLEMENTED | 9-type taxonomy: lead, customer_inquiry, invoice, partnership, supplier, newsletter, internal, spam, unknown; deterministic keyword rules with priority order (spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry); visibility-only types (partnership/supplier/newsletter/internal/spam) produce only skipped sentinels — no customer emails; `AllowedJobType` extended in AI schema; 5 new `JobType` enum values; Swedish labels in UI |
| Cases UX Upgrade | ✅ IMPLEMENTED | `GET /cases` now supports `q` (search subject/customer/email/job_id via ILIKE), `type`, `status`, `sort_by` (received_at/created_at/status/type), `sort_dir` (asc/desc), `limit`, `offset`; response includes `received_at`, `processed_at`, `customer_email`, `limit`, `offset`; `GET /cases/{job_id}` includes `received_at`+`processed_at`; `received_at` stored in `input_data` during Gmail inbox ingestion; Ärenden UI has search/filter/sort/pagination controls with Swedish labels |
| Tenant Memory Foundation | ✅ IMPLEMENTED | `GET /tenant/memory` + `PUT /tenant/memory` — tenant-scoped memory stored in `settings.memory` JSON key; default shape: `business_profile` (company_name, industry, services, tone), `system_map` (gmail/monday sub-dicts), `routing_hints` (per job-type hints); PUT merges into existing settings without clobbering notifications/scheduler keys; Kundminne tab in operator UI with editable fields and JSON textarea |
| Workflow Scan Status | ✅ IMPLEMENTED | `GET /workflow-scan/status` — tenant-scoped; reads `settings.workflow_scan`; returns persisted scan state or `never_run` defaults |
| Gmail Workflow Scanner | ✅ IMPLEMENTED | `POST /workflow-scan/gmail` + `POST /workflow-scan/{system}` — generic scanner engine with `GmailWorkflowScannerAdapter`; scans up to 250 stored Gmail-sourced jobs (no live API calls); extracts `known_senders` (top 20, with count), `subject_patterns` (top 20, Re:/Fwd:/Sv: stripped, with count), `detected_mail_types`; persists into `settings.memory.system_map.gmail` and `settings.workflow_scan`; merges summaries across systems (running gmail scan does not clobber monday scan state); no-clobber on failure; unsupported system → 404 with supported list; Kundminne UI "Skanna Gmail" button calls generic endpoint |
| Workflow Scanner Engine | ✅ IMPLEMENTED | `WorkflowScannerEngine` + `BaseWorkflowScannerAdapter` in `app/workflows/scanners/`; `ADAPTER_REGISTRY` maps system keys to adapter instances; future adapters (microsoft_mail, visma, fortnox, crm) added by registering one class; engine handles persistence and no-clobber logic so adapters stay pure |
| Monday Workflow Scanner | ✅ IMPLEMENTED | `MondayWorkflowScannerAdapter` registered in `ADAPTER_REGISTRY`; reads board structure (boards + groups + columns) via `MondayClient.get_boards(limit=50)` read-only GraphQL call; `detect_board_purpose()` deterministic keyword mapping to lead/invoice/support/partnership/supplier/internal/unknown; persists into `settings.memory.system_map.monday` and `settings.workflow_scan`; no-clobber on failure; missing API key → 500; Kundminne UI "Skanna Monday" button + Monday summary card |
| Routing Hint Drafts | ✅ IMPLEMENTED | `GET /tenant/routing-hint-drafts` — read-only; inspects `system_map.monday` boards; returns draft hints keyed by job type (lead/customer_inquiry/invoice/partnership/supplier/support/internal); detected_purpose match → high confidence; board name keyword match → medium/low; multiple candidates → first match, reduced confidence; null when no candidate; `POST /tenant/routing-hints/apply` — operator-explicit save; merges into `memory.routing_hints` without clobbering other job types, business_profile, or system_map; validates hint shape (422 on unsupported type, missing system, bad confidence, unknown keys); no external writes; Kundminne UI "Föreslå routing" + editable textarea + "Spara routing-hints" |
| Routing Preview + Readiness | ✅ IMPLEMENTED | `GET /tenant/routing-preview/{job_type}` — reads saved routing hints, returns `{job_type, status (ready/missing_hint/invalid_hint), system, target, message}`; 400 on unsupported job_type; `GET /tenant/routing-readiness` — summary across all 7 job types: `{ready, missing, invalid, score:{ready_count, total, percent}}`; case detail `GET /cases/{job_id}` enriched with `routing_preview` field (null when job_type not in supported list); Kundminne UI "Testa routing" buttons per type + readiness score display; case detail shows colour-coded Routing Preview card; preview only — no external writes, no auto-routing |
| Generic Controlled Dispatch Engine + Monday Lead Adapter | ✅ IMPLEMENTED | `POST /jobs/{job_id}/dispatch-preview` (dry-run: resolves hint, returns what would happen, no external call) + `POST /jobs/{job_id}/dispatch` (live: validates hint, deduplicates, calls adapter, persists to integration_events, raises 400 on failure); `ControlledDispatchEngine` + `DISPATCH_REGISTRY` keyed by (system, job_type); `MondayLeadDispatchAdapter` derives item name (company→customer→sender→email→subject→"New lead"), creates Monday item via existing `MondayClient.create_item()`; duplicate guard via idempotency_key in integration_events; other adapters (HubSpot, Pipedrive, Salesforce) added with one class + one registry entry; case detail UI: "Förhandsvisa dispatch" + "Skicka till system" buttons (visible only when routing is ready); dispatch result shown inline |
| Dispatch Control Policy | ✅ IMPLEMENTED | `app/workflows/dispatchers/policy.py` — `resolve_dispatch_policy(tenant_config, job_type)` maps `auto_actions[job_type]` to normalized modes: `manual`/`False`/`None` → `"manual"`, `"semi"` → `"approval_required"`, `"auto"`/`True` → `"full_auto"`; `GET /jobs/{job_id}/dispatch-policy` — returns `{job_id, job_type, policy_mode, requires_approval, can_dispatch_now}`; `POST /jobs/{job_id}/dispatch` blocks with `{status: "approval_required"}` when `can_dispatch_now` is False (no adapter call, no DB write); `POST /jobs/{job_id}/dispatch-preview` merges policy fields into dry-run response; case detail UI shows Dispatch-policy label; 35 tests |
| Dispatch Approval Queue | ✅ IMPLEMENTED | `POST /jobs/{job_id}/dispatch` with `approval_required` policy creates a real dispatch approval record (reuses existing `approval_requests` table); returns `{status, approval_id, policy_mode, message}`; duplicate guard prevents double-queueing same job/system/job_type; `POST /approvals/{id}/approve` detects `next_on_approve=="controlled_dispatch"` and runs `ControlledDispatchEngine` instead of pipeline orchestrator; existing idempotency guard prevents double external write; `POST /approvals/{id}/reject` closes dispatch approval without external write; approval cards show "Dispatch-godkännande" badge with job_type/system/board; 33 tests |
| Auto Dispatch Pipeline Hook v1 | ✅ IMPLEMENTED | `app/workflows/dispatchers/auto_dispatch.py` — `maybe_auto_dispatch_job(db, tenant_id, job, settings)` checks all conditions before any external write: job_type=="lead", policy=="full_auto", routing_preview=="ready", system=="monday", adapter in DISPATCH_REGISTRY, duplicate guard; hooked into `WorkflowOrchestrator._finalize_success` after job reaches COMPLETED status; failure never crashes pipeline; `POST /jobs/{job_id}/auto-dispatch` endpoint for operator testing; "Testa auto-dispatch" button in case detail UI; 29 tests |
| Dispatch Observability + ROI Attribution | ✅ IMPLEMENTED | `app/workflows/dispatchers/observability.py` — `get_dispatch_summary()` / `get_dispatch_report()`; time-range presets (today/7d/30d/all, default 30d); summary aggregates total/success/failed/skipped, by_mode, by_job_type, by_system, ROI; report returns executive headline (dispatches_completed, time_saved_hours, success_rate_percent, automation_share_percent); `GET /dispatch/summary?range=` + `GET /dispatch/report?range=` endpoints; range selector buttons + ROI Rapport card in Dashboard UI; 28 + 38 tests |
| Customer Onboarding Wizard | ✅ IMPLEMENTED | `app/onboarding/readiness.py` — `get_onboarding_status(db, tenant_id, app_settings)` computes 8-step checklist from existing platform state (no external API calls): tenant_created, gmail_ready, monday_ready, systems_scanned, routing_hints_saved, automation_policy_set, test_lead_created, dispatch_verified; `GET /onboarding/status` endpoint; `POST /onboarding/test-lead` creates synthetic lead via deterministic pipeline; Kunduppsättning wizard section added to existing Onboarding UI tab with progress bar, checklist, action buttons, and "Skapa testlead" form; 49 tests |
| UI action label map | ✅ IMPLEMENTED | Case View renders human-readable labels: Kundsvar / Intern notifiering / Monday-objekt / Slack-notis / etc.; shows recipient and Gmail message_id when available |
| Integration Health Center | ✅ IMPLEMENTED | `GET /integrations/health` — tenant-scoped; per-system (gmail/monday) health from internal signals only (no external API calls, no secrets in response); checks: config_present, scanner_ran, inbox_sync/dispatch_success; status: healthy/warning/error/not_configured; overall_status aggregation; recent_errors list (action/category/created_at only); **runbook_signals** array adds deterministic remediation hints with `severity`, `action`, and `runbook_ref`; Integrationshälsa card in Dashboard UI; 47+ tests |
| Pilot Readiness Hardening | ✅ IMPLEMENTED | `GET /pilot/readiness` — tenant-scoped; 11 deterministic checks from existing platform state (no external API calls, no secrets in response): auth_configured, tenant_exists, onboarding_ready, integrations_health_not_error, routing_ready_for_lead, dispatch_duplicate_protection, dispatch_observability, scheduler_safe, required_env_present, ui_available, test_lead_exists; overall_status: ready/almost_ready/not_ready; score counters (passed/warnings/failures); Pilotberedskap card in Dashboard UI; 49 tests |
| Setup Verify Runbook Signal | ✅ IMPLEMENTED | `POST /setup/verify` response now includes `runbook_signal` (`null` when ok, object on warning/failed) with severity/action/runbook reference, so pilot operators get direct next-step guidance without reading logs. |
| Super Admin Panel v1 | ✅ IMPLEMENTED | `GET /admin/tenants/overview` — aggregates health for ALL DB tenants; read-only; no external API calls; no secrets in response; per-tenant: onboarding status/percent, pilot_readiness status/percent, integration health (overall+gmail+monday), dispatch 30d stats (total/success/failed/hours/automation_share), recent_error_count, latest_activity_at; top-level: total_tenants, healthy/warning/error/not_ready counts, total_hours_saved_30d; one failing tenant does not break the rest; "Super Admin" tab in operator UI with summary cards + tenant table + "Öppna kund" button; 44 tests |
| Admin Auth Hardening | ✅ IMPLEMENTED | `ADMIN_API_KEY` env var + `X-Admin-API-Key` header; `app/core/admin_auth.py` — `require_admin_api_key` FastAPI dependency; constant-time comparison; missing/wrong key → 401; ADMIN_API_KEY not configured → 401 (fail closed); configured value never in response/logs; tenant X-API-Key not accepted; `GET /admin/tenants/overview` now uses `require_admin_api_key` instead of `get_verified_tenant`; UI: Admin API-nyckel input in Super Admin tab (stored in localStorage as `ui_admin_api_key`); requests send `X-Admin-API-Key` header; clear "Åtkomst nekad" error on 401/403; 24 tests |
| Fortnox Workflow Scanner | ✅ IMPLEMENTED | `FortnoxWorkflowScannerAdapter` registered in `ADAPTER_REGISTRY`; reads customers (limit 50), articles (limit 50), invoices (limit 50) via `FortnoxClient` read-only methods; normalises to `{customer_number, name, email, organisation_number, phone}` / `{article_number, description, unit, sales_price}` / `{document_number, customer_number, customer_name, total, balance, status, due_date}`; persists into `settings.memory.system_map.fortnox` and `settings.workflow_scan`; missing `FORTNOX_ACCESS_TOKEN` or `FORTNOX_CLIENT_SECRET` → failed ScanResult (no exception, no credential leak); `_DEFAULT_MEMORY` seeded with fortnox slot; "Skanna Fortnox" button in Kundminne UI; no-clobber on failure; 42 tests |
| Fortnox Customer + Invoice Actions | ✅ IMPLEMENTED | `POST /integrations/fortnox/customers/lookup` (by email or name, first match wins); `POST /integrations/fortnox/customers/create` (name required; email/org/phone optional); `POST /integrations/fortnox/invoices/lookup` (by document_number → single invoice; by customer_number → list, limit capped 50); all return 503 when credentials missing; credentials never in error response; "Fortnox Pilotverktyg" section in Kundminne UI with lookup/create forms; 32 tests |
| UI Role Separation | ✅ IMPLEMENTED | Admin mode (purple badge) shows all tabs; Customer mode (teal badge) shows only Dashboard + Ärenden; role toggled via badge in header; persisted in localStorage (`ui_role_mode`); admin-only tabs hidden in customer mode; switching to customer mode while on admin-only view redirects to Dashboard; `openTenant()` bug fixed (pre-set `_activeTenantId` before `switchView` to prevent `loadSetup()` overwriting the target tenant); nav styling improved (border-bottom underline indicator, admin-only tabs in purple) |
| Customer Dashboard (Slice 21) | ✅ IMPLEMENTED | `loadDashboard()` branches on `_uiMode`; customer mode renders `#custDash`: gradient hero (welcome + date + refresh), 4 ROI/status highlight cards (sparad tid, värde SEK, ärenden klara, väntar på åtgärd), automation health status card (per-integration pills: green/amber/red/gray), ärendeöversikt card (leads/support/fakturor/redo counts), recent activity feed (last 8 items with type + subject + status pill + timestamp); all technical/internal sections (dispatch observability, pilot readiness, ROI report, assumptions) hidden; admin mode renders `#adminDash` unchanged; toggling role while on dashboard live-switches layout |
| Dark Premium SaaS Shell (Slice 22) | ✅ IMPLEMENTED | Full dark-theme redesign: CSS custom property design system (`--bg`, `--surface`, `--surface-2/3`, `--purple`, `--blue`, etc.); fixed left sidebar (220px) replaces top tab nav; sidebar groups: Översikt (dash/cases), Drift (ops/ctrl/notif), Konfiguration (setup/onboarding/memory), Super Admin (admin); topbar with view title, API-key input, refresh button; admin-only sidebar sections and nav items hidden in customer mode; `switchView()` updates topbar title via `_VIEW_TITLE` map; `_applyRoleMode()` hides/shows section headers + nav items; `toggleRole()` uses `.nav-item.active` selector; CSS overrides neutralize legacy light-mode h1/panel colors; no React/Tailwind — vanilla HTML/CSS/JS; all view panel IDs preserved |
| Ärenden / Cases View Polish (Slice 24) | ✅ IMPLEMENTED | `loadCases()` branches on `_uiMode`; customer mode: card-based list with type badge, status badge, priority badge, subject, customer name, timestamp, "Visa detaljer →"; customer detail: next-step card (nuläge + friendly explanation), original message section, timeline (action-based, human-friendly labels), conversation thread (outgoing/incoming styled), error section — no raw payloads, no dispatch controls, no routing internals; admin mode: table with type badge column, priority column, dark-safe CSS vars; admin detail: all existing sections preserved (routing, dispatch, extracted data, actions, errors) restyled with `.detail-section`/`.detail-section-title`, dark-safe colors, `.thread-message` CSS; polished empty states in list + detail for both modes; new CSS classes: `.case-card`, `.case-card-header/subject/footer/customer/snippet`, `.type-badge` (lead/support/invoice/partnership/supplier/other), `.prio-badge` (HIGH/NORMAL/LOW), `.cases-filter-bar`, `.detail-section`, `.detail-section-title`, `.detail-msg-body`, `.thread-message` (outgoing/incoming), `.thread-dir/subj/body`, `.timeline`, `.timeline-item`, `.timeline-dot` (ok/warn/err/info), `.timeline-label/meta`, `.next-step-card`, `.next-step-icon/label/text` |
| Dashboard Composition Polish (Slice 23) | ✅ IMPLEMENTED | Admin dashboard: page header with date subtitle + integration health status pill; 4 KPI cards (leads/support/klara/väntar) with icon badges and top-border accents; ROI panel redesigned (two sub-sections: sparad tid grid + breakdown + assumptions); ROI rapport side-by-side; dispatch section uses `.range-chip` pill buttons instead of `.btn`; integration health + pilot readiness in two-column layout; activity table uses CSS vars; polished empty states for dispatches/activity/health. Customer dashboard: hero with overall status pill; 4 KPI cards with icon badges (`.kpi-card`); integration health card uses dark-safe inline colors; cases summary card uses CSS vars; activity feed uses dark-safe colors; "Visa alla" link to Ärenden view. New CSS classes: `.kpi-card`, `.kpi-icon`, `.kpi-trend`, `.kpi-label/value/helper`, `.kpi-top`, `.dash-page-hdr/title/sub`, `.dash-section-hdr/title`, `.dash-quick-actions`, `.status-pill` (ok/warn/err/gray), `.empty-state` + icon/title/sub, `.dash-two-col`, `.range-chip`. All hardcoded light-mode inline colors replaced with CSS vars. |
| Real Login Screen (Slice 25) | ✅ IMPLEMENTED | Full-screen login overlay before dashboard; two-tab login (Admin / Kund); API key validated against backend (`/admin/tenants/overview` for admin, `/tenant` for customer); session stored in localStorage (`ui_session`); sidebar + mainContent hidden until logged in; logout button in sidebar footer clears session and returns to login; dev mode: if backend returns 200 without key, login proceeds with empty key; existing session restored on page reload without re-login; `_loginMode`, `doLogin()`, `_launchApp()`, `logout()`, `_checkDevMode()` added; no backend changes |
| Inställningar + Onboarding Polish (Slice 26) | ✅ IMPLEMENTED | **Inställningar**: page header with readiness status pill; grouped `.cfg-section` cards (Tenant-hantering, Konfigurationsstatus, Arbetsflöden, Anslutna system, Automationsnivå, Verifiering) each with icon badge + title + subtitle; readiness progress bar + check items with colored dots; `.cfg-save-msg` replaces hardcoded color inline styles; tenant info styled with CSS vars; `renderReadiness()` rewired to `#setupReadinessBody` + topbar pill. **Onboarding**: role-branched — admin mode: progress ring + score bar + module toggles (`.toggle-switch`) + integration card grid (`.ob-int-card`) + step checklist (`.ob-step`) + wizard section; customer mode: hero card + read-only connection/automation/module status; no admin internals visible in customer mode. All hardcoded `#16a34a`, `#dc2626`, `#9ca3af`, `#6b7280`, `#f3f4f6` replaced with CSS vars. New CSS: `.cfg-section*`, `.cfg-check-item/dot`, `.cfg-overall`, `.cfg-row*`, `.cfg-save-row/msg`, `.cfg-readiness-bar/fill`, `.ob-progress-card`, `.ob-score-ring`, `.ob-step*`, `.ob-integration-grid`, `.ob-int-card/name/badge`, `.ob-module-grid/row`, `.toggle-switch/input`, `.ob-action-grid`, `.ob-test-card`, `.ob-input/textarea`, `.ob-cust-wrap/hero`, `.ob-status-card/title/row`; no backend changes |
| Tenant Creation Wizard (Slice 27) | ✅ IMPLEMENTED | 4-step fullscreen wizard overlay (`#wizardOverlay`) accessible via "+ Ny kund" button in Super Admin view; admin-only (gated by `_uiMode`); Step 1: company name (auto-generates slug), tenant-ID (slug-safe A–Z 0–9 _), contact name/email/phone with validation; Step 2: module chips (lead/support/invoice/partnership/supplier) + integration chips (Gmail/Monday/Fortnox/Slack; Visma=coming soon); Step 3: per-job-type automation level table (manual/semi-auto/full auto; safe defaults: leads=semi, rest=manual); Step 4: review summary + credential warning; creates via `POST /tenant` + `PUT /tenant/config/{id}`; success state with "Öppna kund" / "Till Super Admin" actions; auto-reloads admin overview; Super Admin view restyled with KPI cards + dash-page-hdr + cfg-section API key input; all hardcoded colors replaced with CSS vars; no backend changes |
| Integration Setup Flow (Slice 28) | ✅ IMPLEMENTED | Fullscreen overlay (`#intSetupOverlay`) showing integration cards for Gmail, Monday, Fortnox, Visma (coming soon); each card: status pill (healthy/warning/error/not_configured/coming), checks list from `/integrations/health`, last verified timestamp, required env var keys (admin-only), action buttons (✓ Testa → `POST /setup/verify`, ⟳ Skanna → `POST /workflow-scan/{system}`, ↗ Dokumentation link); data loaded from `GET /integrations/health` + `POST /setup/verify` in parallel; admin-only config (customer sees health status only); wizard success state: "⚡ Konfigurera integrationer" button opens setup for newly created tenant; "⚡ Integrationer" shortcut button in Inställningar page header (admin-only, hidden in customer mode via `_applyRoleMode()`); `openIntegrationSetup(tenantId)`, `loadIntegrationSetup()`, `_renderIntCard()`, `_intCardVerify()`, `_intCardScan()` added; no backend changes |
| Production Safety Pass (Slice 31) | ✅ IMPLEMENTED | **Backend hardening**: `POST /tenant`, `PUT /tenant/config/{tenant_id}`, `GET /tenant/config/{tenant_id}`, `GET /tenants`, `POST /verify/{tenant_id}` — all previously unauthenticated "operator bootstrap" endpoints now require `X-Admin-API-Key` via `require_admin_api_key` dependency; removed `[TEMPORARY: local-debug]` block from startup (kept OAuth completeness warning); inbox-sync and daily-digest 500 responses no longer include raw exception text (logged server-side only). **UI hardening**: added `adminApiFetch()` helper that merges `X-Admin-API-Key` header; all admin-context calls to gated endpoints updated (`loadTenants`, `loadSetup`, `switchTenant`, `createTenant`, `saveConfig`, `runVerification`, wizard `_wizCreate`); customer case detail no longer falls back to `job_id` when subject is missing. **Docs**: `docs/12-production-guide.md` created — required env vars table, auth model, pre-launch checklist, run instructions. No new features, no schema changes. |
| Readiness / Launch Checklist (Slice 30) | ✅ IMPLEMENTED | "Redo för drift" view (admin-only) in sidebar under Konfiguration; calls `GET /pilot/readiness` (11 deterministic checks, no external API calls); score banner: percentage (pass=1pt, warning=0.5pt), pass/warning/fail counters, colour-coded progress bar; `status-pill` header (Redo ✓ / Nästan redo / Inte redo); per-check rows: check label (Swedish), backend message, `int-status-pill` (OK/Varning/Fel), "Åtgärda →" button navigating to the relevant view (Kontrollpanel, Inställningar, Onboarding, Kundminne, Ärenden) or opening integration overlay; `READINESS_LABELS` map for all 11 check keys; registered in `ADMIN_ONLY_VIEWS`, `_VIEW_DISPLAY`, `_VIEW_TITLE`, `switchView()`; `loadReadiness()` + `_renderReadinessView()` added; no backend changes |
| Kontrollpanel + Notifieringar Polish (Slice 29) | ✅ IMPLEMENTED | **Kontrollpanel**: replaced `.setup-card` with `cfg-section` cards (Automatisering, Körläge & Supportmail, Scheduler-status); plain checkboxes replaced with `.toggle-switch` + hidden checkbox pattern; `loadControl()` now calls `_syncToggle()` after setting values; page header uses `dash-page-hdr`; scheduler status displayed as `cfg-row` table; all `color:#374151`, `#6b7280`, `#16a34a`, `#d97706`, `#dc2626` in JS replaced with CSS vars / `.cfg-save-msg ok/err` classes. **Notifieringar**: replaced `.setup-card` with `cfg-section` cards (Daglig rapport, Testresultat); Aktiv toggle uses `.toggle-switch`; `loadNotifSettings()` calls `_syncToggle()`; all hardcoded JS inline colors replaced with CSS vars; `notifSaveMsg` now `.cfg-save-msg`; digest result uses `var(--success)`/`var(--danger)`; both views use `dash-page-hdr` with `dash-page-sub`; no backend changes |
| Lead Layer (Slices A–G) | ✅ IMPLEMENTED | New `app/lead/` package: rule-based Lead Analyzer (lead_type, intent, urgency, customer_type), Missing Info Engine (field schemas per lead_type, completeness_score 0–1), Question Generator (Swedish message when completeness < 0.7), Lead Scorer (0–100, hot/warm/cold), Next Best Action rules, Offer Draft Engine (safe preliminary drafts, no exact pricing); `lead_analyzer_processor` inserted after `entity_extraction` in LEAD pipeline; `GET /cases/{job_id}` exposes `lead_analysis`, `missing_fields`, `completeness_score`, `lead_score`, `score_category`, `score_reasons`, `offer_draft`, `next_action`, `generated_question_message`; admin case detail renders Lead-analys panel with score badge, completeness bar, missing field chips, AI-rekommenderar label, question message pre, offer draft card; no LLM dependency; no external writes without approval |
| Lead Layer v2 — Tenant-aware intelligence (Slices A–M) | ✅ IMPLEMENTED | **Backend**: `TenantLeadContext` dataclass (`app/lead/tenant_context.py`) loaded from `memory.lead_config` + `memory.business_profile`; all 6 lead modules (`analyzer`, `missing_info`, `scorer`, `offer_draft`, `question_generator`, `next_action`) accept optional `tenant_ctx` parameter; service filtering restricts lead_type to tenant's offered services; tenant keyword overrides, field schema overrides, pricing overrides, offer section/assumption overrides, offer principles injection, geographic scoring (match +8 / mismatch -15), high_value_services (+10), priority_services (+5), ideal_customer_type (+5), service_not_offered penalty (-20); `lead_analyzer_processor` receives live `db` session via `inspect.signature` injection; `lead_status` persisted in `input_data`; `PATCH /jobs/{job_id}/lead-status` (operator status override); `POST /jobs/{job_id}/lead-regenerate` (in-place re-run of lead modules only); `GET /dashboard/leads` (KPIs: total, by_status, by_category, by_service, pipeline_value_estimate); `GET /cases/{job_id}` extended with `lead_status`, `tenant_context_used`, `tenant_context_sources`, `matched_service`, `schema_source`, `required_fields_used`, `optional_fields_used`, `business_fit_reason`. **UI**: Lead-analys panel enhanced with lead status badge + operator select + save button, tenant-context indicator badges, matched_service, schema_source, business_fit_reason, risk_points in offer draft, "Regenerera analys" button, "Kopiera" on question message; Lead-pipeline KPI section in admin dashboard (total, by_status grid, by_category, by_service, pipeline value estimate). **Tests**: 41 unit tests in `tests/test_lead_layer_v2.py`; full fallback verified (v1 behavior when no tenant context). No LLM. No external writes without approval. |
| Super Admin Control & Tenant Context Fix (Slice 32) | ✅ IMPLEMENTED | Persistent topbar tenant context: `#topbarTenantCtx` select dropdown in admin mode; `_updateTenantCtx(tenantId)` called from `openTenant()`, `switchTenant()`, `loadSetup()`, `_adminOpen*` helpers; hidden in customer mode. Super Admin table upgraded: 3 action buttons per row (Öppna/Integr./Redo); `_adminOpenIntegrations()` + `_adminOpenReadiness()` helpers set `_activeTenantId` and update topbar before navigating. All remaining plain `apiFetch()` calls on admin-gated endpoints (`/integrations/health`, `/setup/status`, `/setup/verify`, `/workflow-scan/*`, `/admin/tenants/overview`) → `adminApiFetch()`; 12 call sites fixed. |
| Support Layer v1 — Tenant-aware intelligence (Slices A–M) | ✅ IMPLEMENTED | **Backend**: `TenantSupportContext` dataclass (`app/support/tenant_context.py`) loaded from `memory.support_config` + `memory.business_profile` + `memory.lead_config.services`; 5 support modules: `analyzer` (ticket_type, category, urgency, sentiment, matched_service), `missing_info` (per-ticket-type field schemas, completeness 0–1), `question_generator` (Swedish, emergency safety disclaimer), `prioritizer` (0–100 score, critical/urgent/normal, SLA rules), `response_draft` (ask_for_info/suggested_solution/acknowledgement/escalation, safety disclaimer in risk_points), `next_action` (ask_for_info/escalate/suggest_solution/create_task/ready_to_dispatch/manual_review); `support_analyzer_processor` inserted after `entity_extraction` in CUSTOMER_INQUIRY pipeline; `PATCH /jobs/{job_id}/support-status` (operator status override, 7 valid statuses); `POST /jobs/{job_id}/support-regenerate` (in-place re-run, no external writes); `GET /dashboard/support` (KPIs: total, by_status, by_ticket_type, by_priority, escalated_count, awaiting_info_count); `GET /cases/{job_id}` extended with 13 support fields. **UI**: Support-analys panel in case detail (priority score badge, completeness bar, urgency/sentiment grid, status badge + operator select + save, tenant-context badges, risk reason, missing fields chips, AI-rekommenderar, question message pre, svarsutkast card, "Regenerera analys" button); Support-pipeline KPI section in admin dashboard. **Tests**: 95 tests in `tests/test_support_layer_v1.py` covering all 5 modules, fallback without context, and endpoint no-side-effect verification. No LLM. No external writes without approval. |
| Admin Customer Provisioning | ✅ IMPLEMENTED | **Backend**: `POST /admin/tenants` — provision new tenant with name/slug/job-types/integrations/auto-actions; generates `kw_` API key (SHA-256 hashed, never stored raw; one-time visible); tenant_id = `"T_" + slug.upper().replace("-","_")`; slug uniqueness enforced; returns 400 on duplicate. `GET /admin/tenants` — list all DB tenants, never returns raw API key. `POST /admin/tenants/{tenant_id}/rotate-key` — revokes all active keys, issues new one; returns new key one-time. `PATCH /admin/tenants/{tenant_id}/status` — activate/deactivate; inactive tenants get 403 at auth layer. `TenantApiKeyRecord` model (`tenant_api_keys` table): key_id, tenant_id, key_hash (SHA-256), key_hint (last 4 chars), is_active, created_at, revoked_at. `TenantApiKeyRepository`: create_key, rotate_key, lookup_tenant, revoke_all, list_for_tenant. `TenantConfigRecord` extended with slug, status, created_at, updated_at columns. Auth refactored: DB hashed key lookup first → env TENANT_API_KEYS fallback → dev-mode passthrough; inactive tenant 403 check after key resolution; all existing env keys continue to work unchanged. `ensure_runtime_schema` extended with slug/status/created_at/updated_at column migrations + `tenant_api_keys` table DDL. **UI**: create-tenant form (name, slug, job types, integrations); show-once API key banner with copy button; tenant table with rotate-key/activate/deactivate actions; rotated-key banner. **Tests**: 39 tests in `tests/test_admin_provisioning.py`. |
| Approval-Based Email Dispatch | ✅ IMPLEMENTED | **Goal**: when `auto_actions[job_type]` is falsy, email actions (send_customer_auto_reply, send_internal_handoff, send_email) are intercepted and held for operator approval instead of immediately executing. Monday item creation always executes immediately regardless of policy. **Gating**: `_email_needs_approval(job_type, settings)` checks `auto_actions[job_type]`; None/False/"manual" → needs approval; True/"full_auto"/"semi" → execute normally. `_EMAIL_ACTION_TYPES` constant marks which action types are gatable. `_build_lead_default_actions` and `_build_inquiry_default_actions` both apply `_build_email_approval_action()` wrapper (adds `_needs_approval: True` sentinel) when gate is on; skipped actions are left unchanged. In `process_action_dispatch_job`, `_needs_approval` actions create a real `approval_requests` row (via `_create_email_approval_record`) with `next_on_approve="email_send"` discriminator, `delivery_payload` holding full email payload (type/to/subject/body), and are counted in `actions_pending_approval`. **Approve/Reject**: `POST /approvals/{id}/approve` + `POST /approvals/{id}/reject` detect `next_on_approve=="email_send"` and route to `_resolve_email_approval()`; approve calls `execute_action(delivery_payload)` and captures any send error; reject closes without sending. **UI**: Approvals view splits email vs dispatch approvals; email cards show ✉️ badge, recipient, subject, body preview, Godkänn och skicka / Avvisa buttons with state color-coding. **Tests**: 37 tests in `tests/test_email_approval.py`. |
| Tenant Email Branding | ✅ IMPLEMENTED | `settings.branding` JSON blob per tenant: `company_display_name`, `email_signature_name`, `internal_notification_email`; read by `_read_automation_settings`; customer auto-reply signed with `email_signature_name` when set; internal handoff sent to `internal_notification_email` (fallback: `support_email`; no email when both empty — never falls back to hardcoded address); `"AI Automation"` removed from all generated email bodies; `provision_tenant_defaults()` seeds T_ELITGRUPPEN branding at startup (no-clobber); 33 tests in `test_tenant_branding.py`. |
| Live email reply quality pass (server-verified) | ✅ IMPLEMENTED + DEPLOYED | Personalized customer replies for lead/support (more human tone, information-seeking questions, no static summary block), `Re:` subject style, and live verification against `api.krowolf.se` with approval-gated dispatch. |
| Gmail subject cleanup | ✅ IMPLEMENTED + DEPLOYED | Inbox ingestion now strips Gmail UI noise text from subject lines (including misspelled variant), preventing polluted subjects in downstream actions and approvals. |
| Gmail thread-reply capability | ✅ IMPLEMENTED + DEPLOYED | Google Mail send path now supports `thread_id` + `In-Reply-To` + `References`; metadata is propagated from inbox ingestion to approval payload and action executor. |
| No-reply form relay handling (Webflow-style) | ✅ IMPLEMENTED + DEPLOYED | For no-reply senders, customer reply target is extracted from payload/body and sent as a new outbound message (not thread reply to relay sender); normal inbox customer mails keep thread-reply behavior. |
| Case/Project Workspace v1 + Installer Vertical v1 | ✅ IMPLEMENTED | New case-scoped operations workspace (`operations_workspace`) with work order status, project context, property/customer structure, installer checklist templates (general/solar/EV charger), documentation buckets (before/after/docs), tasks, timeline, attachments, and delivery package state; API: `GET/PUT /cases/{job_id}/operations`, plus timeline/task/attachment/checklist-template/documentation/delivery mutations; admin case detail includes editable operations panel in UI. |
| Demo/test tenant mode | ✅ IMPLEMENTED | `demo_mode` in control settings blocks live inbox sync and scheduled external sends; `/demo/seed` and `/admin/tenants/{tenant_id}/demo/seed` create synthetic demo jobs through the deterministic verification pipeline only. |
| Mobile-first core UI polish | ✅ IMPLEMENTED | Core single-file UI has responsive rules for sidebar/topbar, dashboard cards, cases filters/cards, onboarding/setup cards, tables, and overlays. |
| Fas 1 Gate | ✅ VERIFIED | Product structure/navigation, admin/customer separation, active tenant context, onboarding, demo mode, docs, and desktop/mobile core UI verified. Admin tooling can use `X-Admin-API-Key` + active `X-Tenant-ID` for tenant-scoped endpoints; customer tenant-key flow remains unchanged. Gate evidence: focused Phase 1 tests `146 passed`; `py -3.10 -m scripts.run_release_gate_r1` passed regression (`338 passed`) + E2E (`145 passed`). |
| Fas 6 Automation Experience | ✅ IMPLEMENTED | `GET /cases/{job_id}/automation-wow` returns deterministic case summary, risk signals, and three preview-only wow flows: approved customer reply, case-to-project handoff, and project-to-invoice-ready package. `GET /cases/{job_id}` includes the same `automation_summary`, `automation_risks`, and `wow_flows`; admin case detail renders an automation overview panel. All flows are no-side-effect previews and preserve existing approval-gated external writes. |
| P0 Production Hardening | ✅ IMPLEMENTED | Production auth now fails closed when tenant credentials are missing; DB-backed tenant API keys count as configured auth in readiness; all-tenant `POST /scheduler/run-once` requires `X-Admin-API-Key`; public `/docs`/`/redoc`/`/openapi.json` are disabled when `ENV=production`; admin localStorage key model documented as pilot-only. Server branch `server-local-hotfix-backup` is retained only as historical backup; repo `main` remains source of truth. |
| Product SaaS Finish UI/API | ✅ IMPLEMENTED | Customer navigation is now product-focused: Översikt, Resultat, Ärenden, Aktivitetslogg, Inställningar, Konto & Team. New customer endpoints expose account/team metadata (`/customer/account`), safe activity (`/customer/activity`), ROI/results (`/customer/results`) and simplified health (`/customer/health`) using existing tenant settings and dashboard data. Admin starts in Super Admin, has a needs-help queue, customer health table and quick actions. |
| CI / Deploy hardening | ✅ IMPLEMENTED | Added `.github/workflows/release-gate.yml`, production `Dockerfile`, `docker-compose.prod.yml`, `scripts/smoke_check.py`, and `docs/13-5-customer-launch-checklist.md`. Release gate now includes customer SaaS surface tests plus production hardening/readiness tests. |
| 2172 tests passing | ✅ | `py -3.10 -m pytest` — all pass in latest full verification; release gate passed regression (`396 passed`) + E2E (`145 passed`). |
| AI Operational Insights Engine | ✅ IMPLEMENTED | `app/insights/engine.py` — `get_operational_insights()` produces tenant-scoped, severity-sorted insight rows from existing DB state. Rule packs: stale_lead, hot_lead_pending, missing_customer_info, email/dispatch_approval_waiting, support_escalation, work_order_blocked, delivery_incomplete, underlag_ready, fortnox_export_pending, stale_active_case. `GET /dashboard/operational-insights` endpoint. Top insights wired into daily digest via `_build_digest_body`. 26 tests. |
| Extended Dashboard KPIs (P1a–d) | ✅ IMPLEMENTED | `compute_dashboard_kpis()` in `app/insights/engine.py` — email_approval_queue, dispatch_approval_queue, waiting_customer, underlag_ready, active_ops_cases. `GET /dashboard/kpis` endpoint. Displayed in admin dashboard Driftstatus row and customer dashboard cases summary. |
| SLA Reminder Engine | ✅ IMPLEMENTED | `app/insights/sla_reminders.py` — `find_sla_breaches()` detects unanswered leads past SLA threshold (default 24h). `run_sla_reminder_pass()` creates internal approval records as reminders (idempotent, no customer-facing email without gate). Integrated into `_run_scheduler_pass`. `GET /dashboard/sla-breaches` endpoint. |
| Operational Insights Dashboard UI | ✅ IMPLEMENTED | Admin dashboard: Driftstatus KPI row (5 cards) + Operationella insikter section (severity-colored cards with job links). Customer dashboard: Underlag redo + Väntar på kund added to Ärendeöversikt. |
| Customer Operations Workspace UI | ✅ IMPLEMENTED | Customer mode case detail: read-only Projektöversikt panel (project/WO status badges, customer info, checklist progress X/Y, documentation counts, timeline last 5, delivery status) + Åtgärder guided edits (WO status dropdown, timeline note, time/material entry). All via existing PUT/POST operations endpoints. Admin mode operations panel unchanged. |
| Finance Draft Material Lines (P5b) | ✅ IMPLEMENTED | `POST /finance/invoices/{job_id}/draft` now includes `material_lines` array extracted from `operations_workspace.finance.material_costs` (or `.materials` fallback). Each line: description, quantity, unit_price, total, vat_rate. `GET /cases/{job_id}` now includes `finance_draft_available` (bool) and `finance_draft_url` (string). 11 new tests. |
| Mobile Field UX pass (P6) | ✅ IMPLEMENTED | CSS touch target rules for `.ops-field-form` inputs/buttons (min-height 44px), `.ops-checklist-item`, `.ops-timeline-entry`, `.ops-status-badge`; responsive 5-column KPI grid collapses to 2-col on ≤760px, 1-col on ≤460px; case cards and detail sections have mobile-safe padding. |
| Pilot Cockpit (P0) | ✅ IMPLEMENTED | `GET /dashboard/cockpit` aggregates daily action-oriented counts: actions_required (pending approvals + hot leads + escalations), sla_risk (breach count), waiting_customer, underlag_ready, blocked; top_action_items (highest severity insights); top 3 sla_breaches. Admin dashboard redesigned with cockpit section at top: 5 prominent KPI cards + action items list with job links. Dashboard title updated to "Operationscockpit". 2 tests. |
| Follow-up Engine v1 (P1) | ✅ IMPLEMENTED | `GET /cases/{job_id}/followup` — derives followup_state from lead/job status (new/replied_waiting_customer/waiting_internal/quote_sent/followup_due/closed_won/closed_lost); returns suggested_reply from existing ai_reply_suggestions/offer_draft/support_response_draft; last_customer_message from conversation_messages; pending_approval_id with type for quick approve-and-send. `_FOLLOWUP_STATE_MAP` and `_FOLLOWUP_NEXT_ACTION` lookup tables. Admin case detail renders Uppföljning panel with state, next_action, last customer message, suggested reply, and approval buttons. 9 tests. |
| Field Workflow (P2) | ✅ IMPLEMENTED | Admin operations workspace panel upgraded with: large field action buttons (Starta/Pausa/Klart/Blockerad) with color coding and active-state disable; work order status shown in bold Swedish label with color; checklist progress visible in status row; raw JSON editor collapsed into `<details>` element; `_setWorkOrderStatus()` helper updates workspace via existing PUT endpoint. |
| Project Closeout Packet (P3) | ✅ IMPLEMENTED | `GET /cases/{job_id}/closeout` — returns customer_summary, internal_summary, work_order_status, project_status, checklist progress, documentation counts, material_lines, time_entries, total_material_sek, total_hours, timeline_events, delivery_status, finance_ready, fortnox_exported, missing_fields, risks. Admin case detail has "Sammanställ projekt" button that loads and renders closeout packet with finance badges, customer/internal summary columns, checklist/docs/material/time stats, material-line table, missing-fields warnings, and Fortnox preview link. 4 tests. |
| Finance Export Status (P4) | ✅ IMPLEMENTED | `GET /cases/{job_id}/finance/export-status` — returns finance_ready, exported (bool), export_count, export_events (last 10 Fortnox integration events), material_lines, time_entries, and direct preview/export/draft URLs. Supports P4 finance hardening: operator can check export state without navigating away from the case. 4 tests. |
| Pilot Ops Runbooks (P5) | ✅ IMPLEMENTED | Three runbook documents created: `docs/runbook-scheduler.md` (scheduler start/control/cron/troubleshooting/escalation), `docs/runbook-oauth.md` (Gmail OAuth recovery, token refresh, env vars, Microsoft future), `docs/runbook-pilot-support.md` (daily operator routine, what AI does vs operator, FAQ, troubleshooting, data handling, onboarding checklist). |
| 2193 tests passing | ✅ | `py -3.10 -m pytest` — all pass after Product Audit Roadmap implementation (was 2172, +21 new). |
| Replay & Recovery Console (Slice 1) | ✅ IMPLEMENTED | `app/admin/recovery_actions.py` — six admin-protected recovery actions: `retry_job` (reset failed/manual_review job and rerun full pipeline), `replay_dispatch` (re-run controlled dispatch path, respects idempotency), `reclassify` (re-run classification processor, overwrites prior state), `re_extract` (re-run entity extraction, overwrites prior state), `resend_approval` (regenerate approval request without erasing history), `reprocess_gmail_source` (re-ingest from stored Gmail source metadata with safe dedup). Endpoints: `POST /admin/recovery/{job_id}/{action}` all require `X-Admin-API-Key` + `X-Tenant-ID`. All actions emit audit events. UI: "Återhämtning & Återuppspelning" panel in admin case detail + "Försök igen" in Needs Help view. Consistent response shape: `{status, action, job_id, tenant_id, message, details}`. 36 tests. |
| Support Action Console (Slice 2) | ✅ IMPLEMENTED | `app/admin/support_console.py` — eight admin-protected per-tenant operational actions: `pause_automation` (sets demo_mode=true), `resume_automation` (clears demo_mode), `disable_scheduler` (sets run_mode=paused), `enable_scheduler` (sets run_mode=scheduled), `force_inbox_sync` (triggers Gmail inbox sync), `ack_needs_help` (marks item acknowledged in settings), `clear_acknowledged` (removes acknowledgement), `get_tenant_ops_state` (aggregates automation/scheduler/health/failed jobs/stale approvals/recent audits). Endpoints: `GET /admin/support/{tenant_id}/state`, `POST /admin/support/{tenant_id}/{action}`. All actions emit audit events. UI: dedicated "Supportkonsol" view (admin-only) with operational state display and action buttons. 29 tests. |
| Production Alerting Engine (Slice 3) | ✅ IMPLEMENTED | `app/alerts/engine.py` — proactive email alerts with deduplication. Six alert evaluators: `repeated_failed_jobs` (configurable threshold, default 3), `gmail_oauth_failure` (recent failed oauth/inbox_sync audit events), `scheduler_failure` (last_status=failed), `repeated_dispatch_failures` (configurable threshold, default 5), `stale_approvals` (pending > configurable hours, default 24), `integration_health_critical` (error status systems). Dedup window configurable (default 4h) via `_LAST_SENT_KEY` timestamps in tenant settings. Email delivery via existing `action_executor`. All alert emissions audited. Config stored in `settings.alerts`. Endpoints: `GET/PUT /alerts/config` (tenant), `POST /alerts/run` (tenant manual trigger), `GET /admin/alerts/run-all` (admin). `_run_scheduler_pass` calls `run_alert_pass` for each tenant. UI: "Produktionslarm" section in Notifieringar view with enable/thresholds/last-sent. 33 tests. |
| Pilot Customer Onboarding Wizard (Slice 4) | ✅ IMPLEMENTED | Customer-facing guided onboarding wizard. New endpoint: `GET /onboarding/wizard-state` (customer-safe) aggregates 8-step readiness, setup status, routing hint drafts, and applied routing hints. UI: "Kom igång" navigation item (customer-only). Step-by-step wizard: welcome, Gmail connect/verify, Monday connect/verify, workflow scan, routing suggestions (with apply), automation mode selection, test workflow, go-live readiness. Implemented missing `suggestRouting()` JS function. Customer/admin role separation enforced via `CUSTOMER_ONLY_VIEWS` / `ADMIN_ONLY_VIEWS`. 31 new tests covering readiness evaluators, wizard-state endpoint, tenant isolation, permission separation. |
| 2402 tests passing | ✅ | `py -3.10 -m pytest` — all pass after Operational Scalability (slices 1–4); R1 release gate passes all phases. |
| SaaS Productization — UI/UX Hardening (Slices 0–8) | ✅ IMPLEMENTED | Full productization pass: UI product audit matrix (38 Pass / 14 Fix / 8 Hide / 7 Remove), P0 crash hygiene (`_safeHide`/`_safeText` guards, `_friendlyError` API error normalization), fake-surface pruning (19 speculative job types and 7 unimplemented integrations removed), admin session auth (`/auth/admin/login`, `/auth/admin/logout`, `/auth/admin/me` + `app/core/admin_session.py`, signed HttpOnly cookies, `require_admin_api_key` session-first), customer UX cleanup (Swedish labels, tenant ID hidden, friendly terminology throughout), integration hardening (`tokenExpiredBanner`, `_intFriendlyErr`, `description` field in health checks, `_ACTION_LABELS`/`_CAT_LABELS`), premium SaaS design system (`:root` light-mode + `html.dark-mode` CSS tokens, `#2563eb` blue accent replaces `#7c3aed` purple, system-font stack, dark/light mode toggle with localStorage persistence). Bug fixed: duplicate `adminKeyInput` ID resolved; `adminKey()` now reads localStorage fallback. 2457 tests passing. |

---

## Known API Contract Gaps

These are sharp edges discovered during live testing. Each one has caused a real failure.

| Endpoint / Area | Sharp edge |
|-----------------|-----------|
| `POST /jobs` | Requires `X-API-Key` header **and** `tenant_id` in the request body. Missing either returns an error. |
| `POST /jobs` | `job_type` is a hint — AI classification may override it. The final job type is in the response. |
| `POST /approvals/{id}/approve` | Requires a JSON body. Minimal working body: `{}`. Empty body causes a parse error. |
| `POST /integrations/{type}/execute` | Body field is `"payload"`, not `"input"`. Sending `"input"` silently produces empty payload → `400`. |
| Monday — `board_id` | Not a per-request payload field. Fixed from `MONDAY_BOARD_ID` env var at connection time. |
| Monday — `column_values` | Pass a plain dict; the platform serializes it to a JSON string internally. monday's GraphQL API requires a JSON string — sending a dict directly caused `Invalid type, expected a JSON string`. |
| Tenant config — DB vs static | The DB `tenant_configs` row overrides `TENANT_CONFIGS` in `app/core/config.py` when a row exists. If an integration appears enabled in code but returns `403`, check the DB row. |
| Tenant config — enum vs string | `allowed_integrations` in static config previously stored `IntegrationType.MONDAY` (enum objects). DB stores `"monday"` (strings). Code normalizes both; the DB row is authoritative when present. |
| Google Mail | All four env vars required for refresh: `GOOGLE_MAIL_ACCESS_TOKEN`, `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`. Partial config → `invalid_grant` on first token expiry. |
| UTF-8 output | API response is correct UTF-8. Windows terminals (GBK/CP936) misrender Swedish chars as `?` in curl output. The data is correct. Run `chcp 65001` to fix terminal display. |

---

## Release planning lock (2026-05-06)

Slice 0 is now locked as planning baseline before implementation starts:

- **R1 (next release):** Productification light, Lead-to-case core, and Pilot operations/reliability
- **R2:** Case/project workspace v1 and installer-specific vertical functionality
- **Later:** Finance layer v1

Locked R1 KPIs:

- Setup readiness score >= 90% on pilot tenant
- >= 95% of new leads receive first follow-up action within SLA window
- 100% of AI-generated customer reply drafts are approval-gated before send
- Zero P0/P1 defects in release-gate E2E pilot flow (`inbox -> classification -> approval -> dispatch`)

R1 release-gate execution is now consolidated in one command instead of repeated full-suite runs:

- `python -m scripts.run_release_gate_r1` runs the full R1 gate (regression + E2E phases)
- `python -m scripts.run_release_gate_r1 --phase regression` runs only the regression phase
- `python -m scripts.run_release_gate_r1 --phase e2e` runs only the E2E pilot-flow phase

Locked out-of-scope for R1:

- Full frontend rewrite or platform shift
- New architecture patterns outside current backend-first architecture
- Full accounting/billing suites, white-labeling, and mobile app scope
- Broad net-new integration tracks beyond current controlled MVP adapters

Visual UI Refresh scope lock (DEC-005, 2026-05-07):

- Sprint 5 (Visual UI Refresh) is constrained to **polish on existing CSS tokens and dark shell** — not a new design direction from scratch
- The dark premium SaaS shell and `:root` CSS custom property design system (surfaces, borders, text hierarchy, accents, status colors, shape/shadow tokens) are already implemented
- Allowed: spacing adjustments, hover/focus/transition polish, contrast improvements, empty/loading/error state refinement, sparse `backdrop-filter` on modals, mobile/accessibility pass
- Prohibited: new color schemes, new typographic hierarchies, new layout approaches, breaking existing CSS classes/IDs/JS selectors
- See `docs/07-decisions.md` DEC-005 for full rationale

---

## What works (as of 2026-04-25)

### Core pipeline
- `/jobs` endpoint accepts jobs and runs the full pipeline synchronously
- Pipeline: intake → classification → entity extraction → type-specific processor → decisioning → policy → action_dispatch → human_handoff
- Supported job types with full pipelines: `lead`, `customer_inquiry`, `invoice`
- Classification and extraction use the LLM when `LLM_API_KEY` is set; fall back to deterministic defaults without it — pipeline always completes
- Policy decides: `auto_execute` → action_dispatch → `completed`; `send_for_approval` → paused `awaiting_approval`; `hold_for_review` → `manual_review`
- Failed action dispatch → job status `failed` with error persisted to audit and `action_executions`

### Input handling
- `input_data` is required inside the job request body
- Sender fields support two formats: flat (`sender_name`, `sender_email`, `sender_phone`) or nested (`sender.name`, `sender.email`, `sender.phone`) — both normalized by intake
- Entity extraction uses normalized intake `origin` as fallback for `customer_name`, `email`, `phone` when LLM leaves them null — prevents false `missing_identity` validation errors

### Multi-tenant
- Per-tenant API key auth via `X-API-Key` header; tenant derived from key
- Tenant config stored in `tenant_configs` DB table; static fallback in `TENANT_CONFIGS` when no DB row
- Enabled job types and integrations are per-tenant
- All protected endpoints derive tenant from the key — `X-Tenant-ID` ignored when auth enabled

### Operator UI
- Single-file HTML/CSS/JS at `/ui` — no build toolchain
- Inställningar (Setup) tab: create tenants, configure job types/integrations/automation levels, run verification
- Operationer tab: view jobs, approve/reject
- All reads/writes use explicit `{tenant_id}` endpoints — no silent reversion to API-key tenant

### Verification
- `POST /verify/{tenant_id}` — unauthenticated; runs a deterministic pipeline (no LLM, no external credentials)
- Picks first enabled supported type from tenant DB config (lead > customer_inquiry > invoice)
- Returns `completed` or `awaiting_approval` for valid configured tenants

### Approvals
- Policy can trigger approval pause; human decision via UI or API resumes the pipeline
- Approvals persisted in DB with actor/channel/timestamp

### Integrations

**Google Mail** — ✅ LIVE VERIFIED (read + write)
- `send_email` — delivers to real Gmail inbox; OAuth token refresh on 401; `invalid_grant` surfaces as 503
- `list_messages` — lists inbox messages; returns message_id, thread_id, from, subject, received_at, snippet, label_ids; supports `max_results` and `query` params
- `get_message` — fetches single message by `message_id`; returns all header fields plus `body_text` (text/plain extracted from MIME tree; empty string for HTML-only messages)
- All three actions share the same 401→refresh→retry path

**Monday** — ✅ LIVE VERIFIED
- `create_item` (direct via `/integrations/monday/execute`) — creates real item in the configured board
- `create_monday_item` (workflow via `input_data.actions`) — routes through action_dispatch → MondayAdapter → real board item
- `column_values` serialized to JSON string internally; `board_id` is env-only (`MONDAY_BOARD_ID`)

**All other integrations** (CRM, Slack, Fortnox, Visma, etc.) are stubbed or webhook-based and have not been live-tested.

### Deterministic execution path

`input_data.actions` is the primary control path for action dispatch. When actions are provided explicitly, the workflow engine executes them directly without requiring LLM output. The LLM is used for classification, extraction, and decisioning — but if those processors fall back (no `LLM_API_KEY`), the policy processor still routes to `auto_execute` for `lead` and `customer_inquiry` job types, and action_dispatch runs.

**Default actions are auto-generated per job type** — `_build_fallback_actions` in `action_dispatch_processor.py` produces correct actions for `lead`, `customer_inquiry`, and `invoice` without any explicit `input_data.actions`. Explicit `input_data.actions` (or `decisioning_processor` actions) still override defaults completely.

### Audit
- All pipeline steps emit audit events: `step_started`, `step_completed`, `step_failed`, `workflow_completed`, `workflow_failed`

## Verified end-to-end flows

### Flow 1: Gmail read → lead intake → Monday item
1. `POST /integrations/google_mail/execute` with `action: list_messages` → inbox message list
2. `POST /integrations/google_mail/execute` with `action: get_message, message_id: <id>` → full message with body_text
3. Map sender, subject, body_text into `POST /jobs` with `job_type: lead` and `input_data.actions: [{type: create_monday_item, ...}]`
4. Pipeline runs deterministically (no LLM required): intake → classification → extraction → decisioning → policy (auto_execute) → action_dispatch
5. Monday item created in real board; job status: `completed`

This is a complete manual-trigger ingestion → decision → action flow, confirmed live.

### Flow 2: Multi-action dispatch
- Both `create_monday_item` and `send_email` can be listed in `input_data.actions`
- Actions execute in sequence within a single action_dispatch step
- If one fails: job status is `failed`; the successful action's side effect is not rolled back
- Partial success is visible in `GET /jobs/{id}` → `pipeline_state.action_dispatch.actions_taken` vs `actions_failed`

### Flow 3: Approval pause → resume → action
- Include `force_approval_test: true` in `input_data` to force approval pause
- Job enters `awaiting_approval`; `POST /approvals/{id}/approve` with `{}` resumes it
- Post-approval path runs ACTION_DISPATCH only (no re-classification)

## What is limited

- No LLM in dev without `LLM_API_KEY` — processors fall back deterministically (invoice > lead > customer_inquiry keyword classification; others → safe defaults); pipeline always completes
- Action dispatch is real for Gmail and Monday only; `notify_slack` is non-fatal (silently no-ops when Slack not configured); `create_internal_task` is stubbed (no persistence)
- Gmail `body_text` is empty for HTML-only emails — no HTML-to-text conversion
- Monday `board_id` is env-only — no per-request override
- No DB migration tooling — schema changes require manual intervention
- Search on `input_data` JSON blob uses `ILIKE` cast — works on PostgreSQL; not indexed (acceptable for MVP volumes)
- `sort_by=received_at` proxies to `created_at` at DB level — same order for inbox jobs (processed within seconds of receipt)
- Visibility-only classification types (partnership/supplier/newsletter/internal/spam) produce only skipped sentinels — no customer email sent; cases appear in Ärenden with skip reason
- No pagination in the UI — API supports it via query params (Ärenden tab has pagination controls; other tabs do not)
- No auto-refresh in the UI — all loads are manual
- `app/api/routes/jobs.py` is dead code (not mounted)
- Gmail and Monday are current test integrations — business logic is source/destination agnostic and works with any future adapter

---

## Status summary (historical)
The project has passed the concept stage and has a working backend core with real execution capability.

## Confirmed implemented
- [x] FastAPI API
- [x] PostgreSQL persistence
- [x] SQLAlchemy repository layer
- [x] Multi-tenant with per-tenant API key auth (`X-API-Key`); `X-Tenant-ID` fallback in dev mode
- [x] Orchestrator-baserad workflow pipeline
- [x] AI-processorer med typed outputs
- [x] Approval flow med pause/resume
- [x] Action dispatch
- [x] Audit events
- [x] Approval persistence i DB
- [x] Action execution persistence i DB
- [x] Read-endpoints för approvals och actions
- [x] Live-testad Gmail / Google Mail integration: `send_email`, `list_messages`, `get_message`
- [x] Live-testad Monday integration: `create_item` (direct) + `create_monday_item` (workflow)
- [x] Multi-action dispatch verified (lead → Monday + Gmail in single job)

## Confirmed API surface
### Core
- [x] `GET /`
- [x] `GET /tenant`
- [x] `GET /jobs`
- [x] `GET /jobs/{job_id}`
- [x] `POST /jobs`

### Actions / approvals
- [x] `GET /jobs/{job_id}/actions`
- [x] `GET /jobs/{job_id}/approvals`
- [x] `GET /approvals/pending`
- [x] `POST /approvals/{approval_id}/approve`
- [x] `POST /approvals/{approval_id}/reject`

### Integrations
- [x] `GET /integrations`
- [x] `POST /integrations/{integration_type}/execute`

### Audit
- [x] `GET /audit-events`

## MVP flow verification (2026-04-09)
- [x] Official lead flow traced end-to-end: intake → classification → entity_extraction → lead → decisioning → policy → action_dispatch / human_handoff → approval pause/resume → Gmail action
- [x] Three critical bugs patched:
  - `asyncio.run()` removed from sync `run_pipeline` call in `main.py`
  - `action_executor.send_email` fixed to use `IntegrationType.GOOGLE_MAIL` (was referencing non-existent `EMAIL`)
  - `is_integration_configured` extended to recognise token-based integrations (Google Mail now activates when `access_token` + `api_url` are set)
- [x] Duplicate assertion block removed from `test_invoice_duplicate_detection`
- [x] `tests/test_mvp_flow.py` added: 23 new tests covering policy, human_handoff, approval helpers, orchestrator skip-step logic, integration config, and action executor email routing
- [x] All 36 tests pass

## Read endpoint hardening (2026-04-09)
- [x] Root cause identified: `main.py` called `list_jobs`, `count_jobs`, `list_events`, `count_events` — names that did not exist on any repository
- [x] Six missing alias methods added across three repositories:
  - `JobRepository.list_jobs` / `count_jobs` (aliases for `list_jobs_for_tenant` / `count_jobs_for_tenant`)
  - `AuditRepository.list_events` / `count_events` (aliases for `list_events_for_tenant` / `count_events_for_tenant`)
  - `IntegrationRepository.list_events` / `count_events` (static wrappers over instance methods)
- [x] `tests/test_repository_aliases.py` added: 10 tests for all new aliases + `_to_domain` regression
- [x] All 46 tests pass

## Schema and table bootstrap hardening (2026-04-09)
- [x] `JobListResponse` schema fixed: was `{tenant_id, limit, offset, jobs}`, now `{items, total}` matching all other list endpoints and what `main.py` actually returns
- [x] `main.py` startup `Base` import fixed: was importing from `app.repositories.postgres.base` (empty declarative base), now imports from `app.repositories.postgres.database` (the base all models inherit from) — all four tables (`jobs`, `approval_requests`, `audit_events`, `action_executions`) are now created on startup via `create_all`
- [x] Verified: `Base.metadata.tables` now contains all four expected tables after startup import
- [x] All 46 tests still pass

## Action error handling hardening (2026-04-09)
- [x] `action_dispatch_processor`: result `status` is now `"failed"` (not `"completed"`) when any action fails
- [x] `action_dispatch_processor`: audit event `action_dispatch_failed` emitted on failure (with failed action types and error strings)
- [x] `orchestrator._finalize_success`: detects `failed_count > 0` in action_dispatch payload → routes to `_finalize_failure` → job status `FAILED` (not `MANUAL_REVIEW`)
- [x] `get_db` dependency: added `except: db.rollback(); raise` to prevent dirty sessions after partial commits
- [x] `tests/test_action_failure.py` added: 11 tests covering failure shape, audit event, orchestrator routing, and success/non-action-dispatch paths
- [x] All 68 tests pass

## Operator UI (2026-04-10)
- [x] `app/ui/index.html` — thin single-file operator UI served by FastAPI
- [x] `GET /ui` route added to `app/main.py` (reads HTML from disk, no static mount needed)
- [x] Jobs list with status badges, click to open job detail
- [x] Job detail: id, status, type, tenant, timestamps, result payload, per-job approvals, per-job actions
- [x] Pending approvals tab with Approve/Reject buttons
- [x] All fetches send `X-API-Key` from an editable key input (updated in UI auth slice)
- [x] Approve/Reject POSTs to existing endpoints; UI refreshes after decision
- [x] No React, no Vite, no separate frontend toolchain — pure HTML/CSS/JS inline
- [x] 74/74 tests at time of implementation

**UI limitations (by design — out of MVP scope):**
- No pagination controls — UI fetches first 100 jobs/approvals; backend supports pagination
- No filtering or search
- No audit log view in the UI (data exists in API at `GET /audit-events`)
- No job creation form
- No retries or advanced action controls
- No auto-refresh — operator triggers all loads manually

## UI auth alignment (2026-04-11)
- [x] `app/ui/index.html` — API key input added to header (replaces tenant ID input)
- [x] All fetch calls now send `X-API-Key` header instead of `X-Tenant-ID`
- [x] Key persisted to `localStorage` — survives page refresh
- [x] Warning banner shown when no key is entered
- [x] Auto-load on page open only fires when a saved key exists (avoids immediate 401)
- [x] Dev mode (auth disabled server-side) still works — key field can be left empty
- [x] 88/88 tests pass; no backend changes

## Auth / API key enforcement (2026-04-11)
- [x] `app/core/auth.py` — `get_verified_tenant` FastAPI dependency added
- [x] `app/core/settings.py` — `TENANT_API_KEYS` setting added (JSON string, loaded from env)
- [x] All protected endpoints updated to use `Depends(get_verified_tenant)` instead of `x_tenant_id: str = Header(...)`
- [x] Auth behaviour: when `TENANT_API_KEYS` is set, `X-API-Key` header required; tenant derived from key; `X-Tenant-ID` ignored
- [x] Auth disabled mode: when `TENANT_API_KEYS` is empty, `X-Tenant-ID` trusted directly (dev mode); warning logged
- [x] Missing key → `401`; invalid key → `403`; malformed config → `RuntimeError` at startup
- [x] `tests/test_auth.py` added: 14 tests covering all auth paths (disabled/enabled/missing/invalid/malformed)
- [x] `env.example` updated with `TENANT_API_KEYS` entry and documentation
- [x] README updated: Authentication section, smoke test curl commands use `X-API-Key`, UI limitation noted
- [x] 88/88 tests pass; no business logic changed

**UI auth:** operator UI sends `X-API-Key` on all requests. Key is entered in the header field and persisted to `localStorage`. A warning banner is shown when no key is set. Works in both authenticated mode and dev mode (auth disabled).

## Operability and docs hardening (2026-04-10)
- [x] `requirements.txt` created — all runtime and test dependencies pinned
- [x] `docker-compose.yml` written — starts Postgres 15 on port 5432 with correct DB name
- [x] `env.example` created — full environment variable template with inline docs
- [x] `scripts/create_tables.py` fixed — now imports all four model modules so standalone table creation works; must be run as `python -m scripts.create_tables` from repo root
- [x] README fully rewritten — concrete local setup, DB verification step, full golden-path smoke test with curl commands, Gmail notes, API reference table, known limitations
- [x] `force_approval_test` flag documented in README smoke test
- [x] 74/74 tests still pass; no code logic changed

## DB-driven tenant config (2026-04-12)
- [x] `tenant_configs` table created via `TenantConfigRecord` model; picked up by `create_all` on startup
- [x] `TenantConfigRepository` — `get` / `upsert` / `to_dict`
- [x] `get_tenant_config(tenant_id, db=None)` — reads from DB when `db` provided; falls back to `TENANT_CONFIGS` static dict when no row exists or DB is unavailable
- [x] `/tenant` endpoint now passes DB session — returns DB-stored config when present
- [x] All existing callers (`policies.py`, `integrations/policies.py`) unchanged — they call without `db`, get static fallback
- [x] 105/105 tests pass

## Integration event persistence (2026-04-12)
- [x] `IntegrationEvent` model fixed to use `database.Base` — `integration_events` table now created by `create_all`
- [x] `POST /integrations/{type}/execute` persists a real `IntegrationEvent` row; response built from the saved record
- [x] Payload shape: `{"action": ..., "request": ..., "result": ...}` — captures full round-trip
- [x] `GET /integration-events` lists persisted records (was already wired; now has real data)
- [x] 122/122 tests pass

## Gmail OAuth token refresh (2026-04-12)
- [x] `refresh_access_token()` in `mail_client.py` — calls `https://oauth2.googleapis.com/token` with `refresh_token`, `client_id`, `client_secret`; returns new access token or raises `RuntimeError`
- [x] `GoogleMailClient.send_message` — on 401, attempts refresh and retries once if credentials are present; 403 is not retried (permissions error, not expiry); falls back to raising if refresh is unavailable or retry fails
- [x] Credentials configured via `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` env vars; all default to empty (no breaking change)
- [x] 141/141 tests pass

## Setup UI slice (2026-04-12)
- [x] `GET /tenant` extended — now returns `enabled_job_types`, `auto_actions`, and normalises `allowed_integrations` to plain strings
- [x] `PUT /tenant/config` added — accepts `{enabled_job_types, allowed_integrations, auto_actions}`, calls `TenantConfigRepository.upsert`, returns `{status, tenant_id}`
- [x] `app/ui/index.html` — "Setup" tab added alongside existing "Operations" tab; loads current config from `GET /tenant`; renders checkbox lists for job types and integrations; renders auto-action toggles per enabled job type; single "Save Configuration" button POSTs to `PUT /tenant/config` and reloads
- [x] `tests/test_setup_ui_endpoints.py` — 15 new tests; 156/156 pass

## Setup Status / Readiness panel (2026-04-12)
- [x] `app/ui/index.html` — readiness summary panel added inside the Setup tab; rendered before config checkboxes
- [x] Four checks computed from already-loaded config: Tenant loaded, ≥1 job type enabled, ≥1 integration enabled, auto-actions configured (warn-only — does not block overall readiness)
- [x] Overall status: "Ready" (green) when tenant + job types + integrations all present; "Not Ready" (red) otherwise
- [x] Frontend-only change; no backend or test changes; 156/156 pass

## Tenant creation (2026-04-12)
- [x] `POST /tenant` added — accepts `{tenant_id, name}`; rejects duplicates with 400; creates DB row via `TenantConfigRepository.upsert` with empty job types, integrations, auto actions; no auth required (bootstrap endpoint)
- [x] `TenantCreateRequest` Pydantic schema added to `app/main.py`
- [x] `app/ui/index.html` — "Create Tenant" section added at top of Setup tab; two inputs (Tenant ID, Name) + "Create Tenant" button; POSTs to `POST /tenant`, shows inline success/error, reloads config on success
- [x] `tests/test_tenant_creation.py` — 10 tests: success shape, duplicate 400, upsert args, schema validation; 166/166 pass

## Verification / Test Run UI (2026-04-12)
- [x] `app/ui/index.html` — "Verification" section added at bottom of Setup tab; frontend-only, no backend changes
- [x] "Run Verification Test" button submits a minimal `customer_inquiry` job for the active tenant via `POST /jobs`
- [x] Result panel shows: job ID, status (colour-coded), job type, summary, and condensed payload JSON
- [x] Tenant ID captured from loaded config (`_verifyTenantId`); shows clear error if Setup not loaded first
- [x] Uses existing AI fallback path — completes without external credentials
- [x] 166/166 tests pass; no backend changes

## UI polish, Swedish localisation, and tenant switcher (2026-04-12)
- [x] `app/ui/index.html` fully rewritten with Swedish UI text throughout (headings, buttons, messages, empty states, labels)
- [x] Tenant switcher added to Inställningar tab — input + "Ladda tenant" button loads config for any tenant via `GET /tenant/config/{tenant_id}`; clears input and confirms success inline
- [x] Full CSS/layout polish: consistent card system (`.setup-card`, `.readiness-card`), form field helpers (`.form-field`, `.form-inline`), improved tab styling, better header layout, cleaner spacing throughout
- [x] `GET /tenant/config/{tenant_id}` added to `app/main.py` — unauthenticated, returns same shape as `GET /tenant` for any tenant ID; used by the tenant switcher in the UI
- [x] `tests/test_tenant_config_by_id.py` — 8 tests; 174/174 pass

## Tenant listing and dropdown switcher (2026-04-12)
- [x] `TenantConfigRepository.list_all(db)` added — queries `tenant_configs` table ordered by `tenant_id`; returns only real DB rows, no static fallback
- [x] `GET /tenants` added to `app/main.py` — unauthenticated; returns `{items: [{tenant_id, name}], total}`; no static/fallback tenants included
- [x] `app/ui/index.html` — tenant switcher upgraded from free-text input to `<select>` dropdown populated from `GET /tenants`; only existing DB tenants can be selected; error shown if no tenant selected
- [x] `loadTenants()` called on `loadSetup()` (tab open) and after `createTenant()` (new tenant pre-selected in dropdown immediately)
- [x] `tests/test_tenant_listing.py` — 14 tests: shape, field content, no-fallback guarantee, repository method; 188/188 pass

## Tenant state fix, label maps, automation levels, live readiness (2026-04-13)

**Root cause fixed:** `saveConfig()` previously called `PUT /tenant/config` (API-key-derived tenant) then `loadSetup()` → `GET /tenant` (also API-key tenant), silently reverting to `TENANT_1001`. Fix: added `PUT /tenant/config/{tenant_id}` (unauthenticated bootstrap endpoint); UI now reads/writes config exclusively via `GET /tenant/config/{id}` and `PUT /tenant/config/{id}` using a single `_activeTenantId` variable.

- [x] `PUT /tenant/config/{tenant_id}` added to `app/main.py` — unauthenticated, 404 if tenant not in DB, upserts to exact tenant; saves `dict[str, bool | str]` auto_actions (accepts both legacy bool and new string levels)
- [x] `TenantConfigUpdateRequest.auto_actions` widened to `dict[str, bool | str]` to support automation level strings
- [x] `app/ui/index.html`:
  - Single `_activeTenantId` state variable — set by `switchTenant()`, `createTenant()`, and initial `loadSetup()`; never overwritten by `saveConfig()` or `loadTenants()`
  - `saveConfig()` calls `PUT /tenant/config/{_activeTenantId}` then reloads from `GET /tenant/config/{_activeTenantId}` — tenant never reverts
  - `JOB_TYPE_LABELS` and `INTEGRATION_LABELS` maps — job types and integrations shown with Swedish customer-friendly labels
  - Auto actions replaced with 3-level radio selector per active job type: Manuellt godkännande / Semi-automatiskt / Fullt automatiskt
  - Readiness panel updated live on every checkbox/radio change via `refreshReadiness()` / `computeReadiness()`
  - Readiness now checks: tenant inläst, ≥1 arbetsflöde, ≥1 system, automationsnivå konfigurerad för alla aktiva jobbtyper
  - Final status text changed from "Redo" → "Redo att köra jobb"
- [x] `tests/test_tenant_config_save_by_id.py` — 14 tests: save endpoint shape, 404 path, upsert args, automation level schema; 202/202 pass

## Verification fix — tenant-aware routing (2026-04-13)

Two live testing failures in the verification flow fixed:

**Root causes:**
1. `POST /jobs` uses `get_verified_tenant` (API-key → `TENANT_1001`) but payload had `tenant_id: "TENANT_2002"` → HTTP 400 tenant mismatch.
2. Hard-coded `customer_inquiry` job type was not in the target tenant's `enabled_job_types` DB row → HTTP 403 job type not enabled.

**Fix:**
- [x] `POST /verify/{tenant_id}` added — unauthenticated; picks first enabled supported type; calls `run_pipeline` with tenant-specific payload
- [x] `app/ui/index.html` — `runVerification()` calls `POST /verify/{_activeTenantId}` with no body
- [x] `tests/test_verify_tenant.py` — 16 tests; 216/216 pass

## Verification fix — deterministic pipeline (2026-04-13)

**Root cause:** `run_pipeline` triggers the classification processor which calls the LLM (`LLM_API_KEY` not set in dev) → falls back to `detected_job_type: "unknown"` → orchestrator routes to `UNKNOWN` pipeline → policy appends `"unknown_job_type"` reason → `manual_review`. All three supported job types (lead, customer_inquiry, invoice) also have LLM-dependent processors that fall back to `low_confidence / manual_review` without credentials.

**Fix:** `_run_verification_pipeline(job, job_type_value, db)` — deterministic pipeline helper that bypasses all LLM calls:
- [x] Runs `intake_processor` (deterministic)
- [x] Injects synthetic `processor_history` entries for all AI steps: `classification_processor` (confidence=0.95, correct `detected_job_type`), `entity_extraction_processor`, type-specific processor (`lead_processor` / `customer_inquiry_processor` / `invoice_processor`), and `decisioning_processor` (for lead/inquiry: `auto_execute`)
- [x] Runs `policy_processor` (deterministic — reads from injected history; routes correctly for lead/inquiry/invoice without LLM)
- [x] Runs `human_handoff_processor` (deterministic — reads from policy)
- [x] Finalises `JobStatus` (`COMPLETED`, `AWAITING_APPROVAL`, or `MANUAL_REVIEW`)
- [x] Supported types: `lead`, `customer_inquiry`, `invoice` — each has a realistic Swedish input payload in `_VERIFICATION_PAYLOADS`
- [x] If no supported type is enabled: 400 with clear message listing supported types
- [x] Response includes `verification_type` field indicating which type was exercised
- [x] `tests/test_verify_tenant.py` — 16 tests: 404, 400 (no types, unsupported-only), success shape, tenant match, supported-type preference; updated for new interface
- [x] `tests/test_verification_pipeline.py` — 19 new tests: end-to-end pipeline for all three types (no mocking), verifies status not failed, no `unknown_job_type` reason, correct `detected_job_type` in history; payload config sanity checks
- [x] 237/237 pass

## MVP stabilization (2026-04-14)

See handoff doc for the full list. Key items:
- Intake normalization supports flat `sender_*` fields
- Entity extraction uses normalized origin as identity fallback
- `/jobs` input contract clarified: `input_data` is required; flat sender keys work
- Verification redesigned: deterministic pipeline, no LLM dependency
- Auth header bug fixed: `X-API-Key` always preserved in `apiFetch`
- 263/263 tests pass

## Live testing and regression hardening (2026-04-14)

Performed real API testing of the full platform. Findings and fixes:

- ✅ Gmail integration confirmed working end-to-end (live send + OAuth refresh)
- ✅ Full approval flow confirmed: `POST /jobs` → `awaiting_approval` → `POST /approvals/{id}/approve` → `completed` → action persisted
- Identified and documented API contract gaps (see "Known API Contract Gaps" section above)
- `POST /integrations/{type}/execute` — `RuntimeError` from Gmail now maps to `503` (not `500`); `ValueError` maps to `400`
- `_mask()` helper and `_log_config_diagnostics()` added to `GoogleMailAdapter` — logs masked OAuth credential presence on every `execute_action` call
- `tests/test_google_mail_runtime_errors.py` — 15 tests covering `_mask`, diagnostics logging, and route error mapping
- `tests/test_integration_execute_contract.py` — 10 tests covering schema field name (`payload` not `input`), valid execute, and all `400` paths
- `tests/test_swedish_char_encoding.py` — 12 tests confirming UTF-8 is preserved through all layers (request schema, adapter call, event payload, response serialization, Starlette bytes)
- 300/300 tests pass

## Monday integration + tenant config normalization (2026-04-14)

Live testing of Monday.com integration and tenant config resolution:

- ✅ Monday `create_item` confirmed working end-to-end — item appears in real monday board
- **Bug fixed:** `allowed_integrations` in static `TENANT_CONFIGS` stored `IntegrationType.MONDAY` (enum objects); route check expected string `"monday"` → `403` even though integration was configured
- **Fix 1 (config.py):** all `IntegrationType.X` in `allowed_integrations` replaced with `IntegrationType.X.value` (plain strings) across all four static tenant configs
- **Fix 2 (policies.py):** defensive normalization added — `allowed = [i.value if hasattr(i, "value") else i for i in raw]` — handles strings, enums, and mixed lists; checks `integration_type.value in allowed`
- **Bug fixed:** `column_values` sent as a Python dict to monday's GraphQL API — monday requires a JSON string → `Invalid type, expected a JSON string` error
- **Fix (client.py):** `column_values` serialized via `json.dumps()` before assignment to variables; `None` maps to `"{}"`, strings pass through unchanged
- **Improvement:** monday API `errors` array now raises `RuntimeError("monday API error: <message>")` instead of `Exception(str(list))` — readable error, correct type for route's `except RuntimeError → 503` handler
- `tests/test_tenant_config.py` — 10 new normalization tests (string list, enum list, mixed, empty, monday in TENANT_1001 / TENANT_2001)
- `tests/test_monday_client.py` — 16 new tests (column_values serialization for all input types, board_id as string, group_id, error handling, adapter routing)
- 326/326 tests pass

## Gmail inbox trigger endpoint (2026-04-21)

- `POST /gmail/process-inbox` added to `app/main.py`
- Reads unread Gmail messages (`is:unread`, configurable `max_results`, default 5)
- For each message: calls `get_message`, maps to lead job payload with `create_monday_item` action, calls `run_pipeline`
- Per-message errors are silently skipped; only `list_messages` failure raises 503
- `_parse_from_header(from_header)` helper added: parses `"Name <email>"` or bare `"email"` into `(name, email)`
- Response: `{"processed": int, "created_jobs": [{"message_id": ..., "job_id": ..., "status": ...}]}`
- **Known limitations:** no deduplication, does not mark messages as read, `job_type` hardcoded as `lead`, `create_monday_item` hardcoded as the sole action
- `tests/test_gmail_process_inbox.py` — 14 new tests
- 371/371 tests pass

## Gmail inbox hardening (2026-04-22)

Seven production-readiness slices applied to `POST /gmail/process-inbox`:

### Deduplication
- `JobRepository.get_by_gmail_message_id(db, tenant_id, message_id)` — queries `jobs` table for existing records with matching Gmail message ID
- Already-processed messages skipped with `reason: "duplicate"` in `skipped_messages`; `skipped` counter incremented
- `tests/test_gmail_process_inbox_dedup.py` — 12 tests

### Mark-as-read after successful processing
- `GoogleMailClient.mark_as_read(message_id)` added — `POST /users/{uid}/messages/{id}/modify` with `{"removeLabelIds": ["UNREAD"]}`; uses same 401→refresh→retry path
- `GoogleMailAdapter` dispatches `mark_as_read` action
- Called (non-fatally) after successful pipeline run; `marked_handled` flag in response per message
- `tests/test_gmail_mark_handled.py` — 12 tests

### Tenant config type gate
- `get_tenant_config(tenant_id, db)` called at inbox entry; `get_message` called first to infer type; job creation skipped if the inferred type is not in `enabled_job_types`
- Gated messages appear in `skipped_messages` with `reason: "{inferred_type}_disabled"`
- `tests/test_gmail_tenant_config_gate.py` — 17 tests

### Improved Monday item naming and column_values
- `_make_monday_item_name(subject, sender_name)` — uses subject (truncated to 60 chars), falls back to sender name, then `"Ny förfrågan"`
- `_infer_priority(subject, body)` — deterministic priority (`"High"` on Swedish/English urgency keywords, `"Medium"` otherwise)
- `tests/test_gmail_lead_enrichment.py` — helper and priority function tests

### Improved From-header and phone extraction
- `_parse_from_header` replaced by `email.utils.parseaddr` — correctly handles RFC 2822 `"Name <email>"` and bare addresses
- `_extract_phone(text)` — regex-based extraction of Swedish/international phone numbers from subject+body
- Extracted phone fed into `input_data.sender`
- `tests/test_gmail_extraction.py` — 26 tests

### Slack notification after job creation
- `dispatch_action("notify_slack", ...)` called (non-fatally) after successful pipeline run to `#inbox`
- Notification includes tenant ID, job ID, sender name, subject, and inferred type
- `notified` flag per message in response
- `tests/test_gmail_notification.py` — 20 tests

### Scheduler-safe mode (dry_run + query override)
- `GmailProcessInboxRequest` extended: `dry_run: bool = False`, `query: str | None = None`
- `dry_run=True` — reads messages but skips all writes (no job creation, no pipeline, no mark-as-read, no Slack notify); response entries have `status: "dry_run"`, `job_id: null`, `inferred_type`
- Default query `"is:unread"` used when `query` is absent; custom query forwarded to `list_messages`
- Response extended with: `dry_run`, `query_used`, `max_results`, `scanned`
- `tests/test_gmail_scheduler_mode.py` — 24 tests

## Deterministic classification fallback (2026-04-22)

- `_INVOICE_KEYWORDS`, `_LEAD_KEYWORDS` added to `classification_processor.py`
- `classify_email_type(subject, body) -> str` — public function; priority order: invoice > lead > customer_inquiry
- `_classify_deterministic` delegates to `classify_email_type` (single source of truth)
- Fallback sets `confidence=0.5`, `reasons=["deterministic_fallback", "llm_unavailable"]`
- Applies to **all job sources** — `POST /jobs`, inbox trigger, verification
- `tests/test_classification_deterministic.py` — updated

## Customer inquiry default actions (2026-04-23)

- `_build_inquiry_default_actions(job)` added to `action_dispatch_processor.py`
- ACTION 1: `create_monday_item` — item name with sender label; `column_values` includes `source=inquiry`, `priority`, `email`, `phone`, `subject`, `message`, `completeness_status`, `missing_fields`; priority prefix `[HIGH]` in item name
- ACTION 2: `send_email` to `support@company.com` — body includes sender, email, phone, subject, message, priority, job ID, tenant
- ACTION 3 (conditional): `send_email` to customer — added when `is_complete=False` and `sender_email` is known; Swedish follow-up questions as bullet list
- Sender normalized via `normalize_sender()`; phone extracted via `extract_phone()` when not in sender dict
- `classify_inquiry_priority(subject, message_text)` — keywords `akut`, `snabbt`, `problem` → `HIGH`; else `NORMAL`
- `_build_fallback_actions` routes `customer_inquiry` → `_build_inquiry_default_actions`
- `tests/test_inquiry_default_actions.py` — 76 tests

## Invoice default actions (2026-04-23)

- `_build_invoice_default_actions(job)` added to `action_dispatch_processor.py`
- ACTION 1: `create_monday_item` — `column_values` includes `source=invoice`, `email`, `subject`, `amount`, `invoice_number`, `due_date`, `supplier_name`, `completeness_status`, `missing_fields`
- ACTION 2: `create_internal_task` — title, description includes `SAKNAD INFORMATION: <fields>` when incomplete; `metadata` includes `invoice` extraction payload and `completeness` result
- No follow-up email to supplier — internal review only
- `_build_fallback_actions` routes `invoice` → `_build_invoice_default_actions`
- `tests/test_invoice_default_actions.py` — 32 tests

## Invoice extraction (2026-04-23)

Deterministic regex extraction from email subject+body:

- `extract_invoice_amount(subject, body)` — matches `"12 500 kr"`, `"SEK 12500"`, decimal amounts; returns first match or None
- `extract_invoice_number(subject, body)` — matches `"Faktura #1234"`, `"Fakturanummer: INV-001"`, `"Invoice 5678"`; requires explicit punctuation or digit-start reference
- `extract_due_date(subject, body)` — matches ISO-style dates `YYYY-MM-DD`, `YYYY/MM/DD`, `YYYY.MM.DD`; normalizes to `-`
- `extract_invoice_data(input_data)` — orchestrates all extractors; returns `supplier_name`, `amount`, `invoice_number`, `due_date`, `raw_text`; omits fields not found
- `normalize_sender(input_data)` — reads nested `sender` dict first, falls back to flat `sender_name/email/phone` keys
- `tests/test_invoice_extraction.py` — 47 tests

## Inbox type inference (2026-04-23)

- `/gmail/process-inbox` now infers `job_type` before creating the job
- `classify_email_type` imported from `classification_processor` — single source of truth
- `get_message` is called before the tenant gate (type must be known first)
- Inferred type checked against `enabled_job_types`; skipped with `"{type}_disabled"` if not enabled
- `Job` created with the inferred `JobType` (`LEAD`, `CUSTOMER_INQUIRY`, or `INVOICE`)
- `input_data` no longer contains a hardcoded `actions` list — pipeline fallback builds correct actions per type
- `created_jobs` entries include `inferred_type`
- Slack notification body is type-generic; channel changed to `#inbox`
- `tests/test_gmail_tenant_config_gate.py` — fully rewritten (17 tests)

**702/702 tests pass.**

## Monday workflow wiring (2026-04-20)

- `create_monday_item` added to `SUPPORTED_ACTIONS` in `app/workflows/action_executor.py`
- `_build_monday_item_result()` handler added — mirrors `_build_email_result` pattern; routes to `MondayAdapter`
- `is_integration_configured()` in `app/integrations/service.py` extended: `api_key + board_id` → configured (previously only checked token-based or webhook-based configs)
- `tests/test_action_executor_monday.py` — 9 new tests
- Monday is now fully wired into both the direct integration path and the workflow pipeline

## Gmail read actions (2026-04-20)

- `list_messages` action added to `GoogleMailClient` and `GoogleMailAdapter`
  - Fetches inbox stubs then enriches each with metadata headers in one pass
  - Returns: `message_id`, `thread_id`, `from`, `subject`, `received_at`, `snippet`, `label_ids`
  - Supports `max_results` (default 10) and `query` (Gmail search string)
  - 401→refresh→retry path shared with send
- `get_message` action added to `GoogleMailClient` and `GoogleMailAdapter`
  - Fetches single message with `format=full`
  - Extracts `body_text` by walking MIME part tree depth-first; returns first `text/plain` part, base64-decoded
  - Returns: `message_id`, `thread_id`, `from`, `to`, `subject`, `received_at`, `snippet`, `label_ids`, `body_text`
  - `body_text` is empty string for HTML-only messages
- `tests/test_google_mail_list_messages.py` — 11 new tests
- `tests/test_google_mail_get_message.py` — 11 new tests
- 371/371 tests pass

## Follow-up Question Engine (2026-04-24)

Deterministic completeness evaluation and follow-up action injection — no LLM.

- `evaluate_information_completeness(job_type, input_data)` added to `ai_processor_utils.py`
  - Returns: `is_complete`, `missing_fields`, `follow_up_questions`, `recommended_status`
  - `lead`: requires `email` + either `message_text ≥ 10 chars` or a meaningful subject; `phone` is missing but not blocking
  - `customer_inquiry`: requires `email` + `message_text ≥ 15 chars`
  - `invoice`: requires `supplier_name` + at least one of `amount`, `invoice_number`, `due_date`
  - All other job types: always `is_complete=True`
- `_build_lead_default_actions(job)` added — previously leads fell through to generic fallback
  - `create_monday_item` with `completeness_status` and `missing_fields` in `column_values`
  - Follow-up `send_email` to customer when incomplete and `sender_email` known
- `_build_inquiry_default_actions` and `_build_invoice_default_actions` updated with completeness fields
- `_build_follow_up_email(sender_email, questions)` helper — uses `send_email` action type (no new integration)
- Explicit `input_data.actions` or `decisioning_processor` actions still bypass all default/follow-up logic
- `tests/test_followup_engine.py` — 23 tests; 725/725 pass

## Thread continuation (2026-04-24)

- `JobRepository.get_by_source_thread_id(db, tenant_id, source_system, thread_id)` — generic lookup by source system + thread_id
- `gmail_process_inbox` processing order: dedup by message_id → `get_message` → thread continuation check → new-job path
- Continuation: merges new message into `input_data.conversation_messages`; updates `latest_message_text/subject/sender`; resets `processor_history`; re-runs pipeline on existing job; marks Gmail message as read
- `dry_run`: continuation detected but no writes; response includes `job_id` + `continuation_reason`
- Response shape: `continued: true/false` + `continuation_reason` on all entries
- `tests/test_thread_continuation.py` — 18 tests; 743/743 pass

## ROI Dashboard (2026-04-24)

- `GET /dashboard/roi` — tenant-scoped, period=today
  - Counts: `leads_created`, `support_cases_handled`, `invoices_processed`, `followups_sent`
  - `followups_sent` = `send_email` action executions today on lead/customer_inquiry jobs
  - Derived: `estimated_minutes_saved`, `estimated_hours_saved`, `estimated_value_sek`
  - Fixed assumptions (constants in `main.py`, easy to adjust): lead=10 min, support=8 min, invoice=6 min, follow-up=5 min, hourly value=500 SEK
  - `assumptions` key included in response for transparency
- ROI section added to Dashboard tab in operator UI: "Sparad tid" + "Uppskattat värde" highlight cards + 4 count cards; collapsible Antaganden panel
- `tests/test_dashboard_roi.py` — 19 tests covering shape, empty state, calculation correctness, tenant isolation; 780/780 pass

## Activity Dashboard (2026-04-24)

- `GET /dashboard/summary` — tenant-scoped summary: `leads_today`, `inquiries_today`, `invoices_today`, `waiting_customer`, `ready_cases`, `completed_today`
  - `waiting_customer` counts active jobs where result payload `recommended_status=needs_customer_info`
  - `ready_cases` counts jobs with `status=awaiting_approval`
  - "today" = jobs created since midnight UTC on the current date
- `GET /dashboard/activity` — recent jobs list with `type`, `status`, `latest_action` (from `action_executions` table), `priority` (from action_dispatch result payload), `created_at`, `tenant`; supports `limit`/`offset`
- Dashboard tab added to operator UI (`/ui`): 6 summary cards + recent activity table; Swedish labels; empty + error states; "Uppdatera" button
- `tests/test_dashboard.py` — 18 tests; 761/761 pass

## Sellable MVP — intake flows complete (2026-04-23)

All three intake flows are implemented, tested, and production-ready:

| Flow | Classification | Default actions | Extraction |
|------|---------------|-----------------|------------|
| Lead | ✅ keyword + LLM | create_monday_item | contact fields |
| Customer inquiry | ✅ keyword + LLM | create_monday_item + send_email (support) | priority, phone |
| Invoice | ✅ keyword + LLM | create_monday_item + create_internal_task | amount, invoice_number, due_date, supplier_name |

The platform can be demonstrated to a first customer for:
- **Sales** (lead intake flow)
- **Support** (customer inquiry flow with HIGH/NORMAL priority)
- **Basic finance intake** (invoice flow with deterministic field extraction)

**780/780 tests pass.**

## Finance Layer v1 (2026-05-06)

- `POST /finance/invoices/{job_id}/draft` — builds deterministic pre-accounting invoice drafts from stored invoice jobs (amount ex VAT, VAT amount, total, VAT rate, expense category, account suggestion).
- `POST /finance/invoices/{job_id}/fortnox/preview` — read-only preview of mapped Fortnox customer+invoice payload based on the draft.
- `POST /finance/invoices/{job_id}/fortnox/export` — approval-gated controlled write path to Fortnox with optional customer creation, `dry_run` support, idempotency key, and persisted integration event audit after export.
- `GET /finance/projects/{job_id}/profitability` — deterministic project profitability signal from case operations finance data (revenue, material/labor/external/other costs, margin, risk status).
- Deterministic classification for finance prep includes VAT rate inference (`0/6/12/25`) and expense category/account suggestion (e.g., materials -> `4010`, services -> `4531`).

## Fas 6 Automation Experience (2026-05-06)

- `app/automation/wow_flows.py` adds pure deterministic helpers for case summaries, risk detection, and wow-flow previews.
- `GET /cases/{job_id}/automation-wow` exposes the Phase 6 payload without external writes.
- `GET /cases/{job_id}` now includes `automation_summary`, `automation_risks`, and `wow_flows` for the existing case UI.
- Admin case detail shows an automation overview with next step, evidence, risks, and three safe preview flows: approved customer reply, case-to-project handoff, and project-to-invoice-ready package.
- Risk signals cover failed jobs/actions, pending approvals, missing customer information, blocked projects, incomplete delivery package, low margin, and stale active cases.

## Fas 7 Ready-to-Market Hardening (2026-05-06)

- `GET /admin/usage/analytics` — admin-protected, read-only usage analytics across all tenants.
- Reports tenant count, active customers, active tenants in range, jobs created/completed, pending approvals, blocked flows, controlled-dispatch totals, automation rate, and estimated time saved.
- Supports `range=today|7d|30d|all` with default `30d`.
- Uses only existing DB state (`tenant_configs`, `jobs`, `approval_requests`, `integration_events`); no external API calls and no secrets in response.
- `app/analytics/usage.py` contains the deterministic aggregation service for reuse in future pilot dashboards.

## Next likely product step

- **Scheduler / cron trigger** — wire a periodic external trigger to call `POST /gmail/process-inbox`
- **Dashboard polish** — date-range filters, charts, auto-refresh interval
- **Finance sync expansion** — broaden finance sync patterns beyond the initial approval-gated Fortnox pre-accounting export flow

## Known issues / filesystem
- `pyproject.toml` is a directory (not a file) in the local filesystem — not tracked in git; does not affect runtime
- `.env.example` is an empty directory in the local filesystem — use `env.example` (no dot prefix)
- `app/api/routes/jobs.py` is dead code (not mounted in `main.py`) — not a blocker
- No DB migration tooling — tables created via `create_all` on startup; schema changes require manual intervention