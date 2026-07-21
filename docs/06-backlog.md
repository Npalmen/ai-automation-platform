# Backlog

> Governed by `docs/00-master-plan.md`.
> Backlog items must be compatible with the master plan. No side tracks without a decision in `docs/07-decisions.md`.
> Historical done-items live in `docs/archive/legacy-06-backlog.md`.

---

### Stabilization chapter — pilot baseline (2026-07-20)

- [x] **Del A preflight script** — `scripts/ops/stabilization_preflight.py` (health, tenant whitelist, scheduler, OAuth source, backup).
- [x] **Del D server inventory** — `scripts/ops/stabilization_server_inventory.sh` → `storage/status/stabilization_server_inventory.json`.
- [x] **Del H archive** — `scripts/ops/pre_live_niklas_archive.py` → `pre_live_niklas_archive.json`.
- [x] **Del I operational reset** — `scripts/ops/niklas_operational_reset.py` (jobs/approvals/alerts/incidents/events; preserves OAuth + tenant config).
- [x] **Del J clean baseline** — `scripts/ops/niklas_live_clean_baseline.json` via `niklas_live_clean_baseline.py`.
- [x] **Document index** — `docs/DOCUMENT_INDEX.md` (canonical vs deprecated).
- [x] **Local gates** — R1 release gate 524+157 passed; secret scan 4 passed; frontend typecheck + contracts + build PASS.
- [x] **Pilot image redeploy** — RC-bundle + `krowolf-app:rc-<sha>` from canonical commit.
- [x] **Documentation reconciliation** — PASS (`docs/DOCUMENT_INDEX.md`, DEC-031).
- [ ] **Soak Dag 1 live scan** — blocked until operator adds 3–5 new unread labeled emails (`docs/niklas-gmail-soak-log.md`).

---

### Customer settings — integration selection (2026-07-21)

- [x] **Slice A — selection resolver + health gating** — canonical keys (`app/integrations/keys.py`); `app/admin/integrations/selection_resolver.py`; platform vs tenant health split; gated triage, tenant directory, alerts; frontend customer detail filtering. No migration 015. Cherry-picked to `main` from `a99c33c` (feature branch `feature/kapitel-2d1-approval-trace` not merged). Tests: parity + health + tenant_directory + super_admin (144 passed).
- [x] **Slice B — explicit `settings.integrations.selections`** — migration **016** (structure SQL + `integration_selection_backfill_runs`); backfill service `run_integration_selection_backfill.py`; `enabled_external_writes` fail-closed; onboarding tri-state UI; `finance_destination` panel + `manual_accounting_routing` + mandatory `visma_disposition`; integration groups; Niklas + conflict/credential gate tests. **Local gates green on branch** — merge/deploy pending browser smoke + postgres dry-run in operator environment.
- [ ] **Slice C — transactional customer settings edits** — backend commits 1–2B done (`customer_settings` module, aggregate GET with `effective_readiness`, deterministic `compute_automation_runtime_projection`, invalid vs not-ready PATCH semantics, HTTP contract tests). **Commit 3 frontend (`CustomerSettingsPage`) pending.**
- [ ] **Slice D — slutgates + pilot deploy** — after B/C.

---

- [x] **Fas 1 plan godkänd** — releasebeslut RB-01–RB-04 + prestandaprofiler dokumenterade i `docs/kapitel-12-release-inventory.md`.
- [x] **RB-04** — `approval.approve` backend + React (`approveTenantApproval`, needs-help/customer detail).
- [x] **RB-02 (delvis)** — legacy `/ui` read-only; `localStorage` admin key purge; client-side write block.
- [x] **Slice 1 verify script** — `scripts/kapitel12_slice1_verify.py` → `kapitel12_slice1_report.json`.
- [x] **Golden paths A–I (pytest)** — 633 tester via slice script; 0 FAIL.
- [x] **Slice 2 infra** — offsite upload (`offsite_backup_upload.py`), checksum metadata, safe retention, restore-from-offsite script, backup alert fix.
- [x] **Slice 2 verify script** — `scripts/kapitel12_slice2_verify.py` → `kapitel12_slice2_report.json` (PARTIAL; RB-01 BLOCKED locally).
- [x] **Profil A/B baseline** — `scripts/kapitel12_perf_baseline.py` PASS (TestClient + mocked services; live via `K12_PERF_BASE_URL`).
- [x] **Slice 2 tester** — `test_kapitel12_backup_offsite.py` (6), `test_kapitel12_incident_drills.py` (6); regression bundle 156 passed.
- [x] **RB-01 offsite backup + restore (pilot server)** — S3 offsite configured; live backup `ai_platform_2026-07-18-202653`; restore from S3 + app verify `:8001`; canonical cron `krowolf-backup-canonical.sh`; RPO/RTO in `k12_slice2_del3_resume_report.json`.
- [x] **Kapitel 12 Slice 3 verify** — `scripts/kapitel12_slice3_verify.py`; browser/a11y/roles/legacy/security/regression/docs; release **CONDITIONAL GO** (`kapitel12_slice3_report.json`).
- [x] **K12 regression cleanup** — 4 failures fixed (usage period bounds, routing `invalid_hint`, schema migration count); full suite **3586/0** (2026-07-18).
- [ ] **Deploy/rollback live rehearsal** — staging/prod server with Docker.
- [ ] **Live incident drills** — app/DB/scheduler outage on pilot server.
- [x] **Slice 3 autentiserad browsermatris** — read_only + operations (+ Del 7) + admin PASS på pilot (2026-07-19); aggregat `storage/status/kapitel12_browser_report.json`; env `/opt/krowolf/.env.browser-test`; scripts `kapitel12_browser_pilot_verify.py`, `kapitel12_browser_aggregate.py`.
- [x] **K12 slutgate regression** — **3589 passed / 0 failed** (2026-07-19); scheduler digest-test stabiliserad (`send_hour=0`).
- [x] **K12 slutgate security** — **240 passed** (K11 bundle, 2026-07-19).

---

### Mellankapitel 8B — Responsivitet och testmiljösanering (2026-07-17)

- [x] **`useListLayout`** — content-width ResizeObserver; conservative `compact` initial state.
- [x] **DataTable** — `full` / `compact` / `cards`; `compactRow` → `compactColumns` → card fallback.
- [x] **Needs help + usage** — compact rows; short AI cost table text; FilterBar reset/wrap.
- [x] **Incidents + customers** — shared layout hook; compact rows.
- [x] **Reset CLI** — `scripts/reset_test_environment.py`; `inventory`, `purge-tenants`, `prune-stale-data`, `seed-baseline`.
- [x] **Guards** — positive ENV + DATABASE_URL fingerprint allowlist; `RESET_TEST_ENVIRONMENT_ALLOWED`.
- [x] **Incident purge policy** — unlink tenant links; orphan timeline/incident delete last.
- [x] **Test environment purge** — `TENANT_1001`, `TENANT_2001`, `T_KROWOLF_E2E_TEST` removed; `T_NIKLAS_DEMO_001` preserved.
- [x] **Baseline seed** — `T_LOCAL_OPS_BASELINE` created via `seed-baseline --execute`.
- [x] **`TENANT_2002` orphan** — documented; 1 job without `tenant_config`; not purged in 8B run.
- [x] **Docs** — `docs/runbooks/test-data-dependency-map.md`, `local-test-environment-reset.md`.
- [x] **Tests** — `tests/test_reset_test_environment.py`.
- [x] **Manual responsive browser verification** — 4 views × 10 breakpoint/zoom modes; PASS (no global overflow, no character-level text break).

### Low priority (8B follow-up)

- [ ] **seed-baseline CLI reports SKIP despite created/upserted resources** — presentation-only reporting bug in `OperationReport` / execute output; no data or security impact.

---

### Kapitel 9 — Standardiserad kundonboarding (2026-07-17)

- [x] **Inventory gate** — `docs/chapter-9-inventory.md`.
- [x] **Migration** — `migrations/009_onboarding_sessions.sql`; onboarding tables + partial unique open-session index.
- [x] **Backend package** — `app/admin/onboarding/` (models, repository, registries, readiness, service, routes).
- [x] **Slice 1 API** — `POST/GET/PATCH /admin/onboarding` (+ identity/modules/automation, readiness, activate, cancel, api-key, read-only step GETs).
- [x] **Registry completion (slice 1)** — `GET /admin/onboarding/registries`; `GET …/activation-plan` + `plan_hash` on activate; `runtime_evaluation.py`; startup `validate_registry_integrity()`; frontend consumes registries (no hardcoded options).
- [x] **Tests** — `tests/test_admin_onboarding.py`, `tests/test_admin_onboarding_registries.py` (25 pass); `frontend/src/features/onboarding/registrySource.test.mjs`.
- [x] **Frontend wizard** — `src/features/onboarding/`; `/ops/customers/new`, `/ops/customers/:tenantId/onboarding`.
- [x] **Docs** — `docs/01-current-truth.md`, `docs/runbooks/customer-onboarding.md` (panel-first).
- [x] **Legacy deprecation note** — `POST /admin/tenants` retained for scripts; no new React usage.
- [ ] **Manual responsive browser verification** — not executed in this environment.
- [x] **Slice 2A** — PATCH service profile + nested lead requirements, routing (`internal_routing_hints`), data start; registry extensions; `plan_hash` includes 2A fingerprints; integrations step read-only; customer detail config summary; `tests/test_admin_onboarding_slice2a.py` (13 pass).
- [ ] **Slice 2B** — Integration OAuth/editor; extern dispatch i `routing_hints`; API-key revoke on cancel.

---

### Kapitel 8 — System-, backup- och deploystatus (2026-07-17)

- [x] **Metadata scripts** — `write_operation_status.py`, `write_build_metadata.py`; atomic JSON; separate operation vs metadata exit semantics.
- [x] **Backup/restore scripts** — status files via `BACKUP_STATUS_FILE` / `RESTORE_STATUS_FILE`; `archive_integrity_verified`; verification enums.
- [x] **Docker build metadata** — Dockerfile build args; CI `release-gate.yml` quoted `--build-arg`.
- [x] **Backend system status** — `system_status_sources.py`, `system_status_schemas.py`, `system_status.py`; `GET /admin/system/status`.
- [x] **Scheduler fix** — `_derive_scheduler_signal` nested `scheduler.run_mode` + overview regression.
- [x] **Tests** — sources, system status, script metadata, build metadata writer.
- [x] **Frontend system** — `src/features/systemStatus/`; `/ops/system`; runtime/resilience/deploy readiness sections.
- [x] **Docs** — `docs/01-current-truth.md`, `frontend/README.md`, runbook, `infra/README.md`.
- [ ] **Manual responsive browser verification** — not executed in this environment.
- [ ] **Deploy manifest / last_deployed_at** — deferred until deploy pipeline writes allowlisted artifact.
- [ ] **Release gate runtime artifact** — deferred (CI does not publish to runtime today).
- [ ] **Production status dir permissions** — requires one-time server `chgrp`/`chmod` per runbook.

---

### Kapitel 7 — Användning, kostnad och kapacitet (2026-07-17)

- [x] **Usage schemas** — `app/admin/usage_schemas.py`; half-open period; `NotMeasuredValue`, `ProxyTimestampMetric`.
- [x] **Batched repository** — `app/admin/usage_repository.py`; `GROUP BY tenant_id`; Python peak-hour bucketing (SQLite-safe).
- [x] **Service + routes** — `app/admin/usage.py`; `GET /admin/usage/overview`, `GET /admin/usage/tenants`; single `require_operator_role` auth.
- [x] **Tests** — `tests/test_admin_usage.py` (period boundaries, not_measured metrics, auth, batch call counts).
- [x] **Frontend usage** — `src/features/usage/`; `/ops/usage`; tenant rows link to customer detail.
- [x] **Docs** — `docs/01-current-truth.md`, `frontend/README.md`.
- [ ] **Manual responsive browser verification** — not executed in this environment.
- [ ] **AI token instrumentation** — deferred (requires LLM client changes + persistence model).
- [ ] **Automation rate** — deferred until `audit_events.job_id` or equivalent batchable linkage exists.
- [ ] **Time-series charts** — deferred (no daily series endpoint).

---

### Kapitel 6 — Incidenthantering (2026-07-17)

- [x] **Incident models** — `app/admin/incident_models.py`; explicit startup import; `create_all()` (no Alembic).
- [x] **Repository + service** — `incident_repository.py`, `incidents.py`; atomic version updates; single-commit timeline+audit.
- [x] **Schemas + routes** — typed requests (`extra=forbid`); full `/admin/incidents` surface in `main.py`.
- [x] **Needs-help linking** — `recommended_incident_action`, `linked_incidents` on detail.
- [x] **Tests** — `tests/test_admin_incidents.py`; extended needs-help tests.
- [x] **Frontend incidents** — `src/features/incidents/`; nested `/ops/incidents/:incidentId`; create from needs-help.
- [x] **Docs** — `docs/01-current-truth.md`, `frontend/README.md`.
- [ ] **Manual responsive browser verification** — not executed in this environment.
- [ ] **Auto-incident rules** — deferred until flow validated.

---

### Kapitel 5 — Säkra operatörsåtgärder (2026-07-17)

- [x] **Action registry** — `app/admin/operator_actions.py` + schemas; five safe writes; explicit `execute_*` per action.
- [x] **Role dependency** — `require_operator_role(allowed_roles)` + `resolve_authenticated_operator` in `admin_auth.py`.
- [x] **Routes** — pause/resume automation, pause/resume scheduler, reject dispatch approval; `require_same_origin`.
- [x] **`available_actions`** — needs-help detail + tenant overview; `allowed`/`blocked_reason` for read_only.
- [x] **Tests** — `tests/test_admin_operator_actions.py`.
- [x] **Frontend operatorActions** — explicit API/mutations, `OperatorActionsSection` on customer + needs-help detail.
- [x] **Docs** — `docs/01-current-truth.md`, `frontend/README.md`.
- [ ] **`job.manual_review.resolve`** — deferred until local-only service variant exists (`blocked_external_risk`).
- [ ] **Manual responsive browser verification** — not executed in this environment.

---

### Kapitel 4 — Gemensam felkö och Behöver hjälp (2026-07-17)

- [x] **Shared triage normalization** — `dedupe_and_normalize_signals`, latest-per-source integration events, explicit retry/impact enums, runbook allowlist in `operations_triage.py`.
- [x] **New signals** — `reconciliation_required`, `tenant_config` (active non-demo only); mapping moved to shared triage module.
- [x] **Needs-help service** — `app/admin/operations_needs_help.py` + schemas; panel severity vocabulary; filtered summary; extended filters.
- [x] **Routes** — `GET /admin/operations/needs-help` (typed queue), `GET /admin/operations/needs-help/{item_id}` (detail).
- [x] **Tests** — extended triage/overview tests; `tests/test_admin_operations_needs_help.py`.
- [x] **Frontend needsHelp** — `src/features/needsHelp/` (`NeedsHelpQueuePage`, `NeedsHelpDetailPage`); nested `/ops/needs-help/:itemId`.
- [x] **Frontend gates** — typecheck, contracts, build pass.
- [x] **Docs** — `docs/01-current-truth.md`.
- [ ] **Manual responsive browser verification** — not executed in this environment.

---

### Kapitel 3 — Kundlista och kunddetalj (2026-07-17)

- [x] **Backend tenant directory** — `app/admin/tenant_directory.py`: enriched `GET /admin/tenants` (batched counts, `last_activity_at`, integration summary, health derivation); `GET /admin/tenants/{id}/overview` detail aggregation.
- [x] **Pydantic schemas** — `app/admin/tenant_directory_schemas.py`; reuses `PriorityItem` for `recent_errors`.
- [x] **Tests** — `tests/test_admin_tenant_directory.py` (health/status separation, integration sources, totals, secrets, performance smoke, auth).
- [x] **Frontend components** — `DataTable`, `FilterBar`, `TenantIdentifier`, `AuditTimeline` (`implemented: true` in contracts).
- [x] **Frontend customers** — `src/features/customers/` (`CustomersListPage`, `CustomerDetailPage`); nested `/ops/customers/:tenantId`.
- [x] **Frontend gates** — typecheck, contracts, lint, build pass.
- [x] **Docs** — `frontend/README.md`, `docs/01-current-truth.md`.
- [ ] **Manual responsive browser verification** — not executed in this environment.

---

### Kapitel 2 — Global operativ översikt (2026-07-17)

- [x] **Backend overview service** — `app/admin/operations_overview.py`: global counters, stuck-job rule, integration status (gmail health vs event-log for visma/sheets), deterministic priority sort/IDs, platform status, 503 on aggregation failure.
- [x] **Triage refactor** — `collect_all_triage_rows()` extracted in `operations_triage.py`; shared by needs-help and overview (no behavior change for needs-help).
- [x] **Pydantic schemas** — `app/admin/operations_overview_schemas.py` with `CounterValue.window_hours`, `system.api`.
- [x] **Route** — `GET /admin/operations/overview` with `require_admin_api_key`.
- [x] **Tests** — `tests/test_admin_operations_overview.py` (auth, counters, 503, sorting, IDs, integration rules, performance smoke, secrets).
- [x] **Frontend overview** — `src/features/overview/` (`OverviewPage`, MetricGrid, PriorityList, integration/system status). TanStack Query `["operations","overview"]`.
- [x] **Route swap** — `/ops` index → `OverviewPage`.
- [x] **Frontend gates** — typecheck, contracts, lint, build pass.
- [x] **Docs** — `frontend/README.md`, `docs/01-current-truth.md`.
- [ ] **Manual responsive browser verification** — checklist not executed in this environment.

---

### Kapitel 1C — Operations shell and authentication (2026-07-17)

- [x] **Backend auth extensions** — typed `operator` + `environment` on `/auth/admin/me` and session login response; `ADMIN_ROLE`/`ADMIN_DISPLAY_NAME`/`ALLOWED_ORIGINS` settings; fail-closed role validator; `require_same_origin()` on login/logout.
- [x] **Frontend auth feature** — `src/features/auth/` (AuthProvider, RequireAuth, RequireRole, LoginPage, forbidden/unauthorized).
- [x] **AppShell** — responsive sidebar/topbar/mobile drawer, environment badge from auth query, operator profile, logout.
- [x] **Protected routes** — `/ops/login` public only; placeholder pages; `/ops/foundation` + `/ops/design-reference` admin-only; `routePolicy.ts`.
- [x] **Tests** — extended `test_admin_session.py`; new `/ops/*` smoke tests; auth/tenant regressions.
- [x] **Security scan** — no admin keys or browser storage for auth in frontend source/build.
- [x] **Docs** — `frontend/README.md`, `docs/01-current-truth.md`.
- [ ] **Manual responsive browser verification** — checklist documented, not executed in this environment.
- [x] **Next step** — Kapitel 2 (global operational overview) may begin once manual verification is done.

---

### Kapitel 1B — Design contracts and visual reference (2026-07-17)

- [x] **JSON contracts** — `frontend/design/krowolf-ui-profile.json` (v1.0.0), `component-contracts.json`, `page-contracts.json`. Nordic Operations direction; 8 status tokens; forbidden patterns documented.
- [x] **Token pipeline** — `scripts/generate-design-tokens.mjs`, `tokens:generate` npm script, `predev`/`prebuild` hooks, `tailwind.config.js` via `createRequire`, `globals.css` imports generated tokens.
- [x] **Typed contracts** — `src/design/types.ts` (`keyof typeof` derived unions), `loadContracts.ts`, `resolveJsonModule` enabled.
- [x] **Contract tests** — `design/contracts.test.mjs` (node:test), `npm run test:contracts`.
- [x] **10 operator components** — PageHeader, StatusBadge, SeverityBadge, MetricCard, HealthIndicator, EmptyState, ErrorState, LoadingState, ActionDialog (native dialog), CriticalActionDialog (native dialog with reason + confirmation gating).
- [x] **Design reference** — `/ops/design-reference` with static Swedish demo data; desktop queue table + mobile cards; no API calls.
- [x] **Governance** — `.cursor/rules/frontend-ui.mdc`.
- [x] **Tests** — backend `test_ops_design_reference_serves_spa_fallback`; CI `test:contracts` step.
- [x] **No auth/real data** — intentionally not built.
- [x] **Next step** — Kapitel 1C (operations shell and authentication).

---

### Kapitel 1A — Operator panel frontend foundation (2026-07-17)

- [x] **`frontend/` scaffolded** — React/TypeScript/Vite with `base: "/ops/"`, strict TS, `@/` alias, Tailwind v3, shadcn/ui baseline (`button`, `badge`), React Router (`basename: /ops`), TanStack Query, minimal `apiClient`. No `lucide-react`; production source maps disabled.
- [x] **Foundation page** — responsive `FoundationPage` at `/ops` and `/ops/foundation`; `NotFoundPage` catch-all; minimal `FoundationLayout` shell. No auth, no dashboards, no brand design.
- [x] **FastAPI `/ops` routes** — additive end-of-file routes in `app/main.py`: SPA fallback (`index.html` only), explicit `GET /ops/assets/{path}` with `FileResponse` + traversal guard, 503 when `frontend/dist` missing. Legacy `/ui` and API routes untouched.
- [x] **Docker multi-stage build** — Node 22 build stage in `Dockerfile`; only `frontend/dist` copied to runtime image. `.dockerignore` excludes `frontend/node_modules` and `frontend/dist`.
- [x] **CI gates** — `frontend` job in `release-gate.yml` (typecheck, lint, build); `docker` job waits on `tests` + `frontend`.
- [x] **Tests** — `tests/test_operator_panel_static.py` (12 tests: SPA, assets, 503, traversal, regressions).
- [x] **`frontend/README.md`** — local dev, build, backend integration, roadmap pointers.
- [x] **Docker build verification** — not run locally (no Docker CLI in this environment). Awaiting CI `docker` job on push/PR for full PASS.
- [x] **Next step** — Kapitel 1B (design contract).

---

### Kapitel 0B — Operator panel governance lock (2026-07-17)

- [x] **DEC-024 registered** — `docs/07-decisions.md`. New internal operator panel frontend stack (React/TS/Vite/shadcn/Tailwind/React Router/TanStack) approved, scoped explicitly to the internal operator panel only; supersedes DEC-015 for that scope alone. Includes deployment principle, security principle, responsiveness principle, design-contract governance, legacy-UI policy, and a deploy readiness matrix (Kapitel-1A-blocking vs. production-deploy-blocking items).
- [x] **Contradicting docs updated** — `docs/00-master-plan.md` ("Forbidden scope now" list) and `docs/05-architecture.md` ("Frontend principle") now reference the DEC-024 exception instead of stating an unqualified prohibition on a new frontend stack.
- [x] **Legacy-UI policy documented** — inside DEC-024: `app/ui/index.html` frozen, not a design basis for the new panel, not removed/dismantled during initial frontend chapters, function-parity checklist deferred to the legacy-retirement chapter (Kapitel 5 per Kapitel 0A plan).
- [x] **Caddy investigation** — confirmed `infra/Caddyfile` (real production file) has never been committed to this repo and was not retrieved in this session (no SSH access available). Added `infra/README.md` + `infra/Caddyfile.example`, both explicitly labeled as a non-verified target config, not production truth.
- [x] **`docs/01-current-truth.md` updated** — new "Operator panel initiative — governance and deploy status" section recording DEC-024, doc updates, legacy status, and Caddy verification status.
- [x] **No code changed** — Kapitel 0B is documentation/infra-doc only. No `frontend/`, no npm install, no Dockerfile/Compose/route/auth changes, `app/ui/index.html` untouched.
- [x] **Next step defined** — Kapitel 1A (frontend foundation) may begin; production deploy of the new panel remains blocked on the real Caddy verification per the DEC-024 deploy readiness matrix.

---

### Niklas Demo — Gmail manual-review handoff + approval queue accuracy (2026-07-15)

- [x] **Gmail manual-review operator handoff** — `manual_review` Gmail jobs now get `krowolf-manual-review` label + UNREAD; state on `job.result.manual_review_handoff`; queue APIs `GET/POST /manual-review/jobs*`; daily summary `unresolved_manual_review` count; 15 tests in `tests/test_manual_review_handoff.py`.
- [x] **Internal handoff post-approval job state** — `finalize_email_approval_resolution()` syncs job status, processor pending counts, and action execution audit after `email_send` approvals; successful `send_internal_handoff` → `completed` with `customer_case_open=true` (not customer-resolved).
- [x] **Dashboard `ready_cases` source of truth** — counts live pending rows via `ApprovalRequestRepository.count_pending_for_tenant`, not `jobs.status=awaiting_approval`.
- [x] **Daily summary `internal_handoffs_sent`** — distinct successful `send_internal_handoff` executions in period; Swedish rendered line when > 0.
- [ ] **Approval via Gmail reply** — parser exists (`approval_command_parser.py`); deferred — no approval-request email with reference, Gmail intake not wired (separate slice).

---

## Completed (Fas 1 + Fas 2 prep)

### Fas 1 — Current Truth Audit (2026-07-04)
- [x] Run `python -m pytest` — 2475 passed, 1 failed. Documented in `docs/01-current-truth.md`.
- [x] Run `python -m scripts.run_release_gate_r1` — PASSED (487 regression + 152 E2E).
- [x] Endpoint audit — all actual routes in `main.py` documented.
- [x] Integration audit — all integration modules inspected and documented.
- [x] UI audit — all views in `index.html` documented.
- [x] Automation risk and approval gate audit — documented.
- [x] Tenant/auth audit — documented.
- [x] **AUDIT-BUG-01** | FIXED 2026-07-04 | `httpx` added to `requirements.txt`.
- [x] **AUDIT-BUG-02** | FIXED 2026-07-04 | Policy gate now fail-closed for unknown tenant IDs.
- [x] Local tenant/auth/customer-data isolation hardening — 42 isolation tests pass.

### Fas 2 prep — First tenant setup path (2026-07-05)

- [x] **First tenant setup path mapped and verified locally.** All provisioning endpoints verified via test suite.
- [x] **Pilot readiness verified** — 11 checks, deterministic, no external API calls. `test_production_readiness.py` passes.
- [x] **Integration health verified** — `not_configured` safely without live tokens, no secrets in response.
- [x] **Customer dashboard/status verified** — empty-state loads without crash.
- [x] **`docs/08-runbook.md`** — added "First internal pilot tenant setup" section (Steps 1–11 with curl commands).
- [x] **`docs/02-first-customer-plan.md`** — added "Local pre-live setup checklist" (11 items).
- [x] **Flaky test fixed**: `test_sla_pass_already_run_today_skips` — timezone mismatch (`date.today()` vs UTC). Fixed.

### Fas 2 local hardening — Core Intelligence Quality Pass (2026-07-06)

- [x] **Core intelligence inventory completed locally** — classification, lead/support analyzers, invoice processing, policy, handoff, action dispatch, and customer reply drafting inspected.
- [x] **Deterministic Swedish eval suite added** — `tests/test_core_intelligence_quality.py` covers installation-company scenarios for classification, qualification, missing info, risk, approval/handoff, customer replies, low-risk routing, and high-risk do-not-touch behavior.
- [x] **Classification fallback improved** — empty/unclear and wrong-recipient input now becomes `unknown`; support/risk phrases beat broad lead keywords; Swedish spam/sales outreach is detected.
- [x] **Do-not-touch/risk logic added** — legal threats, reklamation, contract disputes, inkasso/betalningskrav, safety risk, sensitive personal data, data deletion, financial changes, and mass-send intent force manual review.
- [x] **Customer replies hardened** — sensitive lead/customer-inquiry replies are approval-gated non-binding acknowledgements and hand off to a responsible human.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2510 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Swedish Extraction & Qualification Quality Pass (2026-07-06)

- [x] **Extraction/qualification inventory completed** — `ai_processor_utils.py`, `lead/analyzer.py`, `lead/missing_info.py`, `support/analyzer.py`, `ai/schemas.py`, and `lead/models.py` mapped as controlling files.
- [x] **Swedish address extraction added** — `extract_swedish_location(text)` in `ai_processor_utils.py`: extracts street address, postal code (NNN NN), city (after postal code or preposition), property type (villa/brf/lantbruk/lägenhet/lokal), and fastighetsbeteckning. No LLM required.
- [x] **Org number extraction added** — `extract_org_number(subject, body)` matches Swedish format NNNNNN-NNNN.
- [x] **OCR / payment reference extraction added** — `extract_ocr_number(subject, body)` handles "OCR-nummer:", "betalningsref (OCR):", and similar Swedish bank giro label patterns.
- [x] **Invoice risk level detection added** — `detect_invoice_risk_level(subject, body)` returns "high_risk" (inkasso/kronofogden/kravbrev), "medium_risk" (betalningspåminnelse/förfallodatum passerat), or "normal". Inkasso/debt collection never enters low-risk automation.
- [x] **Lead missing-info address detection from text** — `_field_present("address")` now runs the new location extractor over raw text when entity dict has no address/city. Addresses inline in Swedish messages now satisfy the completeness check.
- [x] **Lead analyzer: expanded work-type keywords** — `electrical_work` now detects "felsökning", "nätanslutning", "jordfelsbrytaren löser", "säkringen löser". `solar_installation` now detects "växelriktare"/"inverter".
- [x] **Lead analyzer: lantbruk customer type** — "lantbruk", "gård", "jordbruk", "lantgård" map to `private` customer type.
- [x] **Support analyzer: electrical safety urgency** — "luktar bränt", "gnistor", "gnistrar" added to `_EMERGENCY_KEYWORDS` and `_URGENCY_KEYWORDS["critical"]`. Fires both `emergency` ticket type and `safety` category.
- [x] **Support analyzer: electrical fault issue keywords** — "jordfelsbrytaren löser", "säkringen löser", "växelriktaren", "inga solceller" added to `issue` ticket type keywords.
- [x] **Support analyzer: post-installation warranty detection** — "ni installerade", "installerade hos oss", "sedan ni installerade" added to `warranty` ticket type keywords.
- [x] **Support analyzer: frustrated escalation** — `requires_human` now includes `frustrated` in addition to `angry` sentiment (repeated-contact / recurring-fault cases escalate to human review).
- [x] **Swedish extraction eval suite added** — `tests/test_swedish_extraction_quality.py`, 61 deterministic tests covering all 8 focus areas.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2571 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Service Profiles & Qualification Schemas (2026-07-06)

- [x] **Service profile module created** — `app/service_profiles/` package: `models.py` (ServiceProfile frozen dataclass), `registry.py` (10 profiles), `qualification.py` (select, compute, build_message, tenant_seam), `__init__.py`.
- [x] **10 first service profiles defined** — generic_lead, generic_support, ev_charger_installation, solar_installation, battery_storage, electrical_fault, inverter_support, electrical_panel, invoice_generic, debt_collection_risk. Each has keywords, required_fields, optional_fields, risk_flags, routing defaults, and Swedish follow-up questions.
- [x] **Profile selection implemented** — `select_profile(job_type, lead_type, support_category, text, tenant_ctx)` routes deterministically through invoice → support → lead → fallback hierarchy.
- [x] **Service-specific missing fields** — `compute_profile_missing_info()` detects 20+ field types per profile, including profile-specific fields (safety_risk, desired_location, production_status, inverter_model_or_error_code, etc.).
- [x] **Service-specific Swedish follow-up questions** — `build_profile_question_message()` uses profile intro + question labels. `generate_question_message()` patched with optional `service_profile` param (backward-compatible).
- [x] **Risk profiles always manual_review** — debt_collection_risk has default_route, complete_action, and missing_info_action all = manual_review. Electrical safety risk_flags trigger high_risk_action = manual_review via `resolve_action()`.
- [x] **Tenant override seam** — `apply_tenant_overrides()` applies routing_hint overrides when tenant context is present; schema overrides applied in `compute_profile_missing_info`. Documented as future onboarding connection point.
- [x] **Service profiles eval suite added** — `tests/test_service_profiles_qualification.py`, 82 deterministic tests covering registry, selection, required fields, missing fields, follow-up questions, risk routing, and tenant override seam.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2653 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Local Final Spurt before Live (2026-07-06)

- [x] **Service profiles wired into lead pipeline** — `lead_analyzer_processor.py` calls `select_profile()` after `analyze_lead()`; passes `service_profile` to `generate_question_message()`; `service_profile_type` added to payload.
- [x] **Service profiles wired into support pipeline** — `support_analyzer_processor.py` calls `select_profile()` after `analyze_support()`; `service_profile_type` added to payload.
- [x] **Customer auto-reply quality (lead)** — `_build_lead_default_actions` reads `generated_question_message` from lead_analyzer payload and uses it for the customer auto-reply body; falls back to generic questions if not available.
- [x] **Customer auto-reply quality (inquiry)** — `_build_inquiry_default_actions` reads `support_generated_question_message` from support_analyzer payload and uses it for the customer auto-reply body; falls back to generic questions if not available.
- [x] **Risk/high-risk reply enforcement** — Sensitive cases (inkasso, legal threat, complaint, safety risk) use `_build_sensitive_customer_ack` with `_needs_approval=True`; no legal/financial commitment in reply body.
- [x] **Tenant routing hints verified** — `apply_tenant_overrides()` applied in `select_profile()` for both lead and support; `tenant_ctx.routing_hints[service_type]` overrides `default_route` without changing other fields.
- [x] **Tenant-specific required fields verified** — `compute_profile_missing_info()` checks `tenant_ctx.schema_for(service_type)` and applies tenant schema when present; `schema_source` correctly reflects override.
- [x] **Company name in replies** — `build_profile_question_message()` personalises intro with `company_name` when available from tenant context.
- [x] **Debt collection risk detection fixed** — Added "inkassokrav", "inkassobolag", "betalningsanmärkning" to `intelligence_safety._RISK_KEYWORDS["debt_collection"]`.
- [x] **Solar plural keyword fix** — Added "solceller", "solpaneler" to `lead/analyzer.py` solar_installation keywords so standard plural forms trigger correct profile selection.
- [x] **Service profile field presence: entity fallback** — `_profile_field_present` now handles `phone` and `email` via text regex + entity dict; generic entity-based fallback added for other entity fields.
- [x] **Test suites for pipeline wiring** — `tests/test_service_profile_pipeline.py` (25 tests) covering profile selection, lead_analyzer wiring, support_analyzer wiring, missing-info computation, and question generator integration.
- [x] **Test suites for customer reply quality** — `tests/test_customer_reply_quality.py` (22 tests) covering low-risk profile-aware replies, high-risk safe acknowledgements, non-binding language, signature, followup disable.
- [x] **Test suites for tenant routing hints** — `tests/test_tenant_routing_hints.py` (15 tests) covering routing override, required field override, company name, and tenant schema seam.
- [x] **Local golden path test suite** — `tests/test_local_golden_path.py` (20 tests) covering EV charger, solar, debt collection, electrical fault, and tenant routing golden paths end-to-end locally.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2735 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Fas 2 local hardening — Local Cleanup/Consistency-Pass before Live Verification (2026-07-06)

- [x] **`docs/01-current-truth.md` test file count corrected** — repo structure table now shows "101 test files (see Test status above)" matching actual count and top-level test status.
- [x] **`docs/01-current-truth.md` customer-safe isolation wording updated** — now clearly distinguishes: customer-safe API responses (verified locally), tenant/admin/customer server-side isolation (verified locally), customer visual UI separation (partially verified code/static), live browser/session validation (deferred to live verification). Known-issues note updated accordingly.
- [x] **`profile_missing_fields` wired into lead pipeline** — `lead_analyzer_processor` now calls `compute_profile_missing_info(service_profile, ...)` and exposes `profile_missing_fields` and `profile_completeness_score` in payload. `generate_question_message` uses profile-specific missing fields for question content (fallback to generic if empty).
- [x] **Support question generator accepts `service_profile`** — `generate_support_question_message` now has optional `service_profile` parameter; uses `build_profile_question_message` for non-emergency/non-safety tickets; `support_analyzer_processor` passes `service_profile` to it.
- [x] **`_has_safety_risk` extended for `ticket_type=="safety"`** — ensures safety-typed tickets always get the safety disclaimer and bypass profile question generation, regardless of message content.
- [x] **Duplicate `_resolve_customer_reply_target` call removed** — redundant second call in `action_dispatch_processor._build_lead_default_actions` removed; behavior unchanged.
- [x] **9 new tests added to `test_service_profile_pipeline.py`** — covers `profile_missing_fields`/`profile_completeness_score` in lead payload, profile question content for EV charger, inverter support profile questions, emergency/safety bypass regression, and no-profile fallback.
- [x] **Local verification passed** — `python -m pytest --tb=no -q` passed with 2744 tests; `python -m scripts.run_release_gate_r1` passed with 505 regression + 152 E2E tests.

### Deferred — live verification phase

Full live verification plan: `docs/10-live-verification-plan.md` — production deploy completed 2026-07-07 on `/opt/krowolf` with live commit `87d9369`. Phase A-C, D, E, F, G, H, I, and J passed 2026-07-07. Phase K BLOCKED (Gmail invalid_grant). Full live verification not complete.

**Phase A — Pre-flight**
- [x] Confirm full local test suite passes immediately before live session — 2026-07-07 final pre-live UI simplification run: 2746 passed, 0 failed, 4 warnings.
- [x] Confirm R1 gate passes immediately before live session — 2026-07-07: 505 regression + 152 E2E passed.
- [x] Resolve unclear `app/ui/index.html` dirty state — previous fancy CSS/card-contrast styling replaced with minimal Internal Operator Console.
- [x] Deploy latest code before Phase A-C re-run — completed on `/opt/krowolf`; live commit `87d9369`; Docker Compose file `/opt/krowolf/docker-compose.prod.yml`; containers `krowolf-app-1`, `krowolf-db-1`, and `krowolf-caddy-1` running.
 - [x] Operator confirmation required before Phase D — DB backup taken (`pre-phase-d-20260707-190618.sql`); app/db/caddy containers running; admin key confirmed working; no real customer tenants modified.

**Phase B — Production health**
- [x] `GET https://api.krowolf.se/` → HTTP 200, `env: production`.
- [x] `GET https://api.krowolf.se/health` → HTTP 200, `env: production`.
- [x] Confirm `/docs` and `/openapi.json` return 404 in production.

**Phase C — Admin/auth**
- [x] Admin endpoint without key → 401.
- [x] Admin endpoint with wrong key → 401.
- [x] Admin endpoint with correct key → 200; existing tenants: `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1`.
- [x] Tenant key rejected on admin endpoint → 401 — verified in Phase D.

**Phase D — Tenant provisioning**
- [x] DB backup taken before Phase D — `pre-phase-d-20260707-190618.sql` (677 KB).
- [x] `T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1` confirmed untouched.
- [x] `POST /admin/tenants` creates `T_LIVE_TEST_001` — HTTP 201, `status: active`.
- [x] `GET /admin/tenants` shows `T_LIVE_TEST_001` listed correctly.
- [x] `GET /tenant` with tenant key → HTTP 200.
- [x] `GET /pilot/readiness` → `almost_ready` (6 pass, 5 warnings, 0 failures — expected pre-integration).
- [x] `GET /integrations/health` → `warning`, no secrets in response.
- [x] Tenant key on `/admin/tenants` → HTTP 401 — isolation confirmed.
- [x] `GET /jobs` with `T_LIVE_TEST_001` key → empty list; no cross-tenant data.

**Phase E — Tenant/customer endpoint isolation and readiness**
- [x] All `/tenant`, `/customer/*`, `/jobs`, `/audit-events`, `/integration-events`, `/tenant/context`, `/tenant/memory`, `/integrations/health`, `/pilot/readiness` with tenant key → HTTP 200.
- [x] All above endpoints without key → HTTP 401.
- [x] Admin key on tenant endpoint (`/jobs`) → HTTP 403.
- [x] Tenant key on admin endpoint (`/admin/tenants`) → HTTP 401.
- [x] Wrong `X-Tenant-ID` header with correct key → HTTP 200 (correct: header ignored per auth design; tenant resolved from key).
- [x] No secrets, stack traces, or 500s in any response or logs.
- [x] No cross-tenant data (`T_ELITGRUPPEN`, `TENANT_2001`, `T_TEST1`) visible via `T_LIVE_TEST_001` key.
- [x] SQL logs show only `T_LIVE_TEST_001` queries; key values stored as SHA-256 hash only.

**Phase F — Safe synthetic intake/job flow**
- [x] `auto_actions: false` for all job types confirmed before first write.
- [x] `POST /jobs` with synthetic lead payload → HTTP 200; `job_id: bea23f74-...`; `tenant_id: T_LIVE_TEST_001`.
- [x] Pipeline ran to completion: `status: completed`, `requires_human_review: False`, `summary: "Ingen manuell överlämning behövs."`, 0 external actions dispatched.
- [x] `GET /jobs/:id` → HTTP 200; scoped to `T_LIVE_TEST_001`; no secrets.
- [x] Jobs list → only `T_LIVE_TEST_001` data; no cross-tenant entries.
- [x] Audit events → no external write events; no cross-tenant data.
- [x] Integration events → no external write events.
- [x] App logs → no Gmail/Monday/Fortnox/Visma writes; no 500s or stack traces.
- [x] `GET /jobs/:id` without key → HTTP 401.
- [x] Wrong `X-Tenant-ID` + correct key on specific job → HTTP 200 scoped to `T_LIVE_TEST_001` (header ignored per auth design).
- [x] Synthetic job `bea23f74-1dbe-4424-a8cb-60262da92f9b` retained under `T_LIVE_TEST_001` as Phase F evidence.

**Phase D — Tenant provisioning**
- [ ] `POST /admin/tenants` creates T_INTERN_PILOT, returns api_key (once).
- [ ] `GET /admin/tenants` shows T_INTERN_PILOT, no api_key in response.
- [ ] `GET /tenant` with tenant key returns `current_tenant: T_INTERN_PILOT`.
- [ ] Tenant key cannot reach `/admin/tenants`.
- [ ] `GET /pilot/readiness` shows expected not_ready/almost_ready state.

**Phase E — Customer endpoints**
- [ ] All `/customer/*`, `/integration-events`, `/tenant/context`, `/tenant/memory` require API key.
- [ ] No secrets in customer endpoint responses.

**Phase F — Integration health**
- [ ] `GET /integrations/health` returns safely without live tokens (not_configured).
- [ ] No token values in integration health response.


**Phase G — Approval queue / manual review**
- [x] Approval endpoints identified: `GET /approvals/pending`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject` — all tenant-scoped; reject safe (no external writes).
- [x] Synthetic `customer_inquiry` created with `force_approval_test: true` → HTTP 200; `job_id: 8b2d53d2-cc44-4d45-a11b-5a4a60654bb0`; `status: awaiting_approval`.
- [x] `GET /jobs/:id` → HTTP 200; `status: awaiting_approval`; `result.summary: "Approval dispatched via dashboard."`.
- [x] `GET /approvals/pending` → HTTP 200; `approval_id: f5d27fc3-071c-41f0-ba65-c9f052f591b3`; `next_on_approve: action_dispatch`; no cross-tenant data.
- [x] `/approvals/pending` without key → HTTP 401.
- [x] Wrong tenant header + T_LIVE_TEST_001 key → HTTP 200 scoped only to T_LIVE_TEST_001 (header ignored per auth design).
- [x] `POST /approvals/:id/reject` → HTTP 200; job status → `manual_review`; no external writes.
- [x] Approval removed from pending queue after reject; T_ELITGRUPPEN/TENANT_2001/T_TEST1 absent.
- [x] Audit events → no cross-tenant data; no external write events.
- [x] Integration events → no external write events.
- [x] App logs → no 500s, no stack traces, no external writes.
- [x] 24/24 checks passed; 0 failures; 0 warnings.
- [x] Phase F email_send approval (eml_adeaf87...) remains pending — non-blocking; consider rejecting via dashboard before pilot.

**Phase H — Integration health/OAuth readiness**
- [x] `GET /integrations/health` → 200; `overall_status: warning`; gmail configured but not OAuth-synced; no secrets; no cross-tenant.
- [x] `GET /integrations` → 200; Monday.com and Google Mail listed as enabled; no secrets.
- [x] `GET /setup/status` → 200; `readiness.score: 90, status: ready`; `google_mail: true, monday: true, fortnox: false, visma: false`.
- [x] `GET /pilot/readiness` → 200; `almost_ready`.
- [x] `GET /integrations/visma/status` → 200; `disconnected`; no tokens.
- [x] `GET /integrations/visma/oauth/url` → 503; not configured; safe.
- [x] `/oauth/start` and `/oauth/callback` — skipped (out of scope).
- [x] `GET /integration-events` → 200; no external write events; no cross-tenant.
- [x] `GET /audit-events` → 200; no cross-tenant; no secrets.
- [x] `GET /integrations/health` without key → 401.
- [x] Wrong `X-Tenant-ID` + correct key → 200 scoped to T_LIVE_TEST_001 only.
- [x] Phase F email_send approval (eml_adeaf87...) found and safely rejected (cleanup). No external write.
- [x] App logs clean — no 500s, no secrets, no external writes.
- [x] 42/42 checks passed; 0 failures; 1 warning (expected cleanup).

**Phase I — UI / read-only dashboard verification**
- [x] `GET https://app.krowolf.se/ui` → 200; "Internal Operator Console" confirmed in HTML; all operator sections present.
- [x] `GET https://api.krowolf.se/ui` → 200; same HTML.
- [x] Cache-bust request → 200; same content.
- [x] No-key: /tenant, /jobs, /approvals/pending → all 401.
- [x] Tenant read-only: /tenant, /customer/health, /customer/results, /customer/activity, /customer/account → all 200; T_LIVE_TEST_001 scoped; no secrets.
- [x] /pilot/readiness → 200; almost_ready.
- [x] /integrations/health → 200; overall_status: warning.
- [x] /jobs → 200; total=2 (Phase F+G synthetics only); no cross-tenant.
- [x] /approvals/pending → 200; 0 pending (clean after Phase H).
- [x] /audit-events → 200; T_LIVE_TEST_001 only.
- [x] /admin/tenants without key → 401; with admin key → 200; no api_key values in list.
- [x] Browser check: "Internal Operator Console" title confirmed; login form visible; no plaintext keys; minimal internal UI; no cached fancy SaaS dashboard. Screenshot taken 2026-07-07.
- [x] App logs clean — no 500s, no stack traces, no secrets.
- [x] 58 actual pass, 0 true fail; 3 script false-positives on HTML variable names (not actual values).

**Phase J — Gmail OAuth readiness/connection planning**
- [x] Gmail config: `GOOGLE_MAIL_ACCESS_TOKEN` (len=253), `GOOGLE_OAUTH_REFRESH_TOKEN`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` — all SET. Env var names match `settings.py` exactly.
- [x] Token model: static env-var tokens — no browser OAuth consent URL flow. No consent route exists in app.
- [x] Sync routes identified but NOT called: `POST /gmail/process-inbox`, `POST /workflow-scan/gmail`, `POST /dashboard/inbox-sync`.
- [x] All Google OAuth URL/start/callback routes → 404 (not implemented — correct for static token model).
- [x] `GET /workflow-scan/status` → 200; `status: never_run` — inbox sync never executed.
- [x] `/integrations/health` → gmail.status: warning, configured: True (warning = not scanned yet).
- [x] `/setup/status` → `google_mail: True, email_connected: True, readiness.score: 90`.
- [x] `/pilot/readiness` → almost_ready; warnings: onboarding steps, routing hints, integration events.
- [x] No Gmail events in integration-events or audit-events.
- [x] Logs: no 500s, no tokens, no inbox sync, no Gmail writes.
- [x] 32/32 pass; 0 fail; 1 false-positive warn.
- [x] Phase K attempted 2026-07-07 — BLOCKED: Gmail invalid_grant (GOOGLE_OAUTH_REFRESH_TOKEN revoked/expired). Fix: regenerate OAuth tokens, update .env.production, restart app, rerun Phase K.

**Phase K — Gmail inbox sync (PASSED 2026-07-08)**
- [x] `POST /gmail/process-inbox` dry_run=true → HTTP 200; 0 new jobs (correct).
- [x] `POST /gmail/process-inbox` dry_run=false → HTTP 200; **8 real jobs created** from Gmail inbox.
- [x] `auto_actions: false` — no external dispatch triggered.
- [x] Token refresh working: new Google OAuth client `502012997563-gp9iku5erqff3u8tad923pk8mb7fsp8m` configured.
- [x] Container recreated with `docker compose up -d` (env vars require recreation, not just restart).
- [x] Phase K blocker removed. Phase O unblocked.

**Phase O — Final go/no-go pilot checklist (CONDITIONAL GO 2026-07-08)**
- [x] O1: Production health — `/` + `/health` → 200 production; `/docs` + `/openapi.json` → 404. All pass.
- [x] O2: Tenant readiness — T_LIVE_TEST_001 active; auto_actions=false; score=90; pilot/readiness=almost_ready (7p 4w 0f); no secrets.
- [x] O3: Gmail jobs — 10 total (2 synthetic + 8 Gmail); all ext_actions=0; all T_LIVE_TEST_001 scoped; no secrets.
- [x] O4: Pending approvals — 1 pending (eml_5d69..., action_dispatch, next_on_approve=email_send); not approved; cross-tenant absent.
- [x] O5: Events — 50 audit events (no external writes); 0 integration events; no secrets.
- [x] O6: Cross-tenant isolation — header ignored per design; T_ELITGRUPPEN data not exposed.
- [x] O7: Operator UI — app.krowolf.se/ui → 200; Operator Console confirmed; no secrets.
- [x] O8: Logs — no risky patterns in tail=1200; no 500s, tokens, writes.
- [x] O9: Cleanup review documented. All GO criteria met. CONDITIONAL GO issued.
- [x] 29/29 pass; 0 fail; 0 warn.
- [ ] **CONDITION**: Set support email `PUT /dashboard/control` for T_LIVE_TEST_001.
- [ ] **CONDITION**: Review pending approval `eml_5d69...` (email_send) — reject if not intentional.
- [ ] **CONDITION**: DB password rotation (maintenance window required).

**Phase N — Production hardening cleanup (PASSED 2026-07-07)**
- [x] N1: Hardening inventory confirmed — ENV=production, APP_NAME=Krowolf, all key env vars SET.
- [x] N2: SQL echo source identified — `echo=True` hardcoded in `database.py`.
- [x] N3: SQL echo fixed — `DB_ECHO: bool = False` added to `settings.py`; `database.py` now uses `echo=settings.DB_ECHO`; 2746 tests pass; committed as `01f5763`; Docker image rebuilt on server; `sql_echo_count_tail30=0` confirmed.
- [x] N4: Support email state inspected — empty `''`; set via `PUT /dashboard/control` (NOT env var); operator must confirm value before setting; suggested `support@krowolf.se` not yet applied.
- [x] N5: DB password hardening plan documented — password currently hardcoded in compose; safe rotation plan written in `docs/01-current-truth.md`; not executed (maintenance window required).
- [x] N6: Gmail token fix plan documented.
- [x] N7: Post-rebuild health: `/` + `/health` 200; `/docs`+`/openapi.json` 404; all tenant endpoints 200.
- [x] N8: Logs risk search: no risky patterns; SQL echo confirmed eliminated in production.
- [x] 2746 tests pass; commit `01f5763` live on server.
- [ ] Phase K remains BLOCKED.

**Phase M — Final pre-pilot cleanup/status consolidation (PASSED 2026-07-07)**
- [x] Server/container status: commit `87d9369`; app/db/caddy Up; no restart loop; no 500s.
- [x] Production health: `/` and `/health` → 200 `env: production`; `/docs` + `/openapi.json` → 404.
- [x] `/tenant` → 200; `T_LIVE_TEST_001` active; name: Live Test Tenant.
- [x] `/setup/status` → score 90, status ready; connections: google_mail✓ monday✓ fortnox✗ visma✗.
- [x] `/pilot/readiness` → `almost_ready`; 7 pass, 4 warn, 0 fail.
- [x] `/integrations/health` → `warning`; gmail+monday configured; fortnox not_configured.
- [x] `/jobs` → 2 synthetic jobs (Phase F+G evidence retained); no cross-tenant.
- [x] `/approvals/pending` → 0 (queue clean).
- [x] `/audit-events` + `/integration-events` → no external write events; no cross-tenant; no secrets.
- [x] Backups: pre-Phase-D backup + 16 daily automated backups; `.env.production`/compose/Caddyfile present.
- [x] Logs risk search (tail=1000): no risky patterns; no leaked tokens; no write events.
- [x] 8 known cleanup items confirmed documented.
- [x] 50/50 pass; 0 fail; 0 warn.
- [ ] Phase K remains BLOCKED — Gmail `invalid_grant` carried forward.

**Phase L — Monday readiness/no-write verification (PASSED 2026-07-07)**
- [x] `MONDAY_API_KEY` SET (len=227), `MONDAY_BOARD_ID` SET — Monday configured.
- [x] `/integrations/health` → `monday.status: warning, configured: True` — health check passes.
- [x] `/setup/status` → `connections.monday: True`, score 90 — Monday connection confirmed.
- [x] `/integrations/monday/status` → 404; `/integrations/monday/health` → 404 — controlled, no dedicated route (health bundled).
- [x] `POST /integrations/monday/execute` without key → 401 — write endpoint protected.
- [x] No Monday write events in integration-events or audit-events.
- [x] No 500s, no stack traces, no leaked tokens in logs.
- [x] Negative auth: 401 without key; cross-tenant scoping confirmed for T_LIVE_TEST_001.
- [x] Phase K Gmail blocker visible in logs (historical, expected).
- [x] 30 pass, 0 true fail, 2 false-positive script FAILs (explained).

**Phase G — Gmail OAuth and inbox sync**
- [ ] Gmail OAuth flow completed for pilot tenant.
- [ ] `GET /integrations/health` → `gmail.status: healthy`.
- [ ] Inbox sync creates case from test email.
- [ ] Outbound email requires approval (not auto-sent).

**Phase H — Monday/Fortnox/Visma safe checks**
- [ ] Monday integration health reflects correct state.
- [ ] Fortnox export confirmed approval-gated.
- [x] Visma sandbox E2E (demo tenant): OAuth connected, allowlist-gated preview/export, approval-gated single export, idempotency — production 2026-07-16 (`0c17256`).
- [x] Visma Chapter 3 cleanup: 5 stale `finance_visma_export` pending approvals rejected via normal reject path; v6 approval remains `approved`; no Visma writes during cleanup (2026-07-16).

**Phase I — Approval queue E2E**
- [ ] Test lead → awaiting_approval → approve → completed.
- [ ] Audit event created, tenant-scoped.

**Phase J — Customer UI**
- [ ] Customer dashboard loads after test jobs.
- [ ] No admin-only data in customer view.

**Phase K — Smoke check**
- [ ] `python scripts/smoke_check.py --base-url https://api.krowolf.se --expect-production` passes.

**Phase L — Go/no-go**
- [ ] All 16 gates in `docs/10-live-verification-plan.md` are green.
- [ ] Named support owner confirmed for pilot tenant.

---

### Visma sandbox Chapters 2–3 (2026-07-16)

- [x] **Chapter 2** — Approval-gated sandbox customer-invoice export on `T_NIKLAS_DEMO_001`; idempotency; ArticleId/customer lookup fix (`0c17256`).
- [x] **Chapter 3** — Rejected 5 stale `finance_visma_export` approvals (pre-ArticleId failed jobs) via `POST /approvals/{id}/reject`; v6 approval unchanged (`approved`); 1 success Visma integration event; diagnostic sandbox artifacts documented (retained).
- [x] **Release regression** — R1 gate 668 tests + focused Visma 64 + sheets/golden 125 + full suite 3265 passed locally (2026-07-16).
- [x] **Pilot transition** — Internal demo rehearsal PASS; `docs/PILOT_TRANSITION.md` published (scope, onboarding, ops, metrics, commercial).
- [ ] **Optional operator cleanup** — Remove duplicate diagnostic Visma sandbox customer/invoice manually in Visma UI if desired (not via production API).
- [ ] **Before first pilot** — Drain/reject 8 legacy demo `email_send` approvals or use fresh tenant; complete PILOT_READINESS BLOCKER items (offsite backup, restore rehearsal, incident contacts).

### Sprint 3 — Google Sheets manual export (2026-07-14)

- [x] **Google Sheets adapter created** — `app/integrations/google/sheets_client.py`: real `GoogleSheetsClient` (Sheets v4 REST API, appends rows via USER_ENTERED) and `MockGoogleSheetsClient` (in-memory, for tests). Uses existing Google OAuth access token.
- [x] **Row mapper created** — `app/integrations/google/sheets_row_mapper.py`: `choose_tab()` for auto/explicit routing; `build_leads_row()` (12 cols), `build_support_row()` (12 cols), `build_logg_row()` (6 cols). Extracts sender, processor history fields, status, source.
- [x] **Manual export endpoint added** — `POST /integrations/google-sheets/export-job` in `app/main.py`. Body: `{"job_id": "...", "target": "auto"|"leads"|"support"|"logg"}`. Auth: X-API-Key (tenant).
- [x] **Tenant config support added** — `allowed_integrations` must include `"google_sheets"`. `settings.google_sheets.spreadsheet_id` must be set. Both fail-closed.
- [x] **Audit event created on export** — `create_audit_event` called with `category="integration"`, `action="google_sheets_export"`, `status`, and `details` (job_id, tab, spreadsheet_id, error).
- [x] **Integration event created on export** — `IntegrationEvent` row added with `integration_type="google_sheets"`, idempotency key, tab, spreadsheet_id, and status for observability.
- [x] **Safety gates verified** — (1) `google_sheets` not in `allowed_integrations` → `integration_not_allowed`; (2) `spreadsheet_id` empty/missing → `configuration_missing`; (3) wrong-tenant job → 404; (4) no access token → `configuration_missing`; (5) no auto-export from Gmail processing.
- [x] **Test suite added** — `tests/test_google_sheets_export.py`: 50 tests covering row mapper (choose_tab, build_leads_row, build_support_row, build_logg_row), MockGoogleSheetsClient, all endpoint safety gates, adapter called exactly once, audit event created, row_count in response, tenant-specific spreadsheet_id used, and no-auto-export pipeline checks.
- [x] **Full test suite verified** — `python -m pytest --tb=no -q` → 3140 passed, 0 failed, 4 warnings (2026-07-14). Sprint 1, 2, 2B tests all unaffected.

### Sprint 4 — AI Receptionist test-customer onboarding package (2026-07-15)

- [x] **Onboarding checklist created** — `docs/ai-receptionist-test-customer-onboarding.md`: purpose, prerequisites, step-by-step tenant setup, API key handling, Gmail label/query setup, Google Sheet setup, approval-first settings, safety checklist, what NOT to enable, rollback/stop procedure, reference commands.
- [x] **Test mail scenarios created** — `docs/ai-receptionist-test-mail-scenarios.md`: 8 core scenarios (EV charger, laddbox fault, battery add-on, solar issue, emergency, VVS, build/carpentry, complaint) with expected job_type, playbook, context, approval behavior, and sheet tab.
- [x] **MVP Gate created** — `docs/ai-receptionist-mvp-gate.md`: chapter-level verification checklist (Sections A–H) covering Gmail ingestion, playbook quality, safety routing, approval-first, Sheets export, tenant isolation, allowlist enforcement, and observability. Clear PASS/PASS WITH NOTES/BLOCKED/FAIL status. GO/NO-GO criteria defined.
- [x] **Friend test guide created** — `docs/ai-receptionist-friend-test-guide.md`: Swedish non-technical guide for test users explaining what Krowolf does, what to send, what to expect, feedback requested, and safety expectations.
- [x] **Helper script created** — `scripts/print_ai_receptionist_test_setup.py`: prints tenant settings, Gmail setup, Sheets column/tab structure, safety checklist, and scenario table. Read-only, no dependencies. Syntax verified.
- [x] **No code changed** — Sprint 4 is documentation only. No tests run (none required).
- [x] **Deferred confirmed** — UI, Visma writes, Outlook/SMS, auto-export, and Monday remain deferred per master plan.
- [x] **Next step defined** — Run `docs/ai-receptionist-mvp-gate.md` against live environment before first friend test.

### Sprint 5 — Phase 1 value layer (2026-07-15)

- [x] **Quote draft enrichment** — `app/lead/models.py` + `app/lead/offer_draft.py`. `OfferDraft` now includes `customer_name`, `customer_email`, `customer_phone`, `address`, `missing_fields`, `human_approval_required=True`. Always approval-gated. No Visma/Fortnox writes.
- [x] **Lead status fix** — `lead_analyzer_processor._infer_lead_status`: `ask_questions` → `waiting_for_customer`; `create_offer_draft` → `quote_draft_prepared`. `LeadStatus` literal extended.
- [x] **Invoice routing classifier** — `app/invoice/routing.py`. Deterministic keyword scan. Outputs one of: `debt_collection_review`, `payment_reminder_review`, `manual_review_required`, `forward_to_accounting`, `ignore_not_invoice`. Wired into `invoice_processor` payload.
- [x] **Derived status helper** — `app/workflows/derived_status.py`. Pure `derive_job_status(job)` reads processor history; returns 7 human-readable statuses for reporting and MVP gate.
- [x] **Daily report generator** — `app/reporting/daily_report.py`. `generate_daily_report(db, tenant_id, since_hours)`. Counts leads/quotes/inquiries/invoices/risk/approvals. Renders Swedish morning summary text.
- [x] **`GET /reports/daily-summary` endpoint** — tenant-scoped, `since_hours` param, uses `generate_daily_report`.
- [x] **Approval command parser** — `app/workflows/approval_command_parser.py`. `parse_approval_command(body)`. GODKÄNN/APPROVE → approve; STOPPA/REJECT → reject; ÄNDRA/CHANGE: text → change. Fail-closed. Gmail reply webhook deferred.
- [x] **25 tests added and passing** — `tests/test_sprint5_phase1_value.py`. 25 passed, 0 failed, run 2026-07-15.
- [x] **MVP Gate updated** — Section I added to `docs/ai-receptionist-mvp-gate.md` with 6 new checks for Phase 1 value layer.
- [x] **Deferred (intentional)** — Calendar, Visma/Fortnox writes, Gmail reply webhook, customer UI, scheduler for daily report.

## Now (pre-live blockers)

### Completed in Phase 2 prep

- [x] **First tenant setup path mapped and verified locally.** All endpoints (`POST /admin/tenants`, rotate-key, status, `GET /pilot/readiness`, `GET /integrations/health`, `GET /onboarding/status`, `POST /onboarding/test-lead`, `POST /verify/{tenant_id}`) verified via test suite.
- [x] **Pilot readiness verified** — 11 checks, all deterministic, no external API calls. `test_production_readiness.py` (169 tests) passes.
- [x] **Integration health verified** — reports `not_configured` safely without live tokens, no secrets in response. `test_integration_health.py` passes.
- [x] **Customer dashboard/status verified** — empty-state loads without crash. `test_customer_saas_surfaces.py` passes.
- [x] **`docs/08-runbook.md`** — added "First internal pilot tenant setup" section with concrete curl commands (Steps 1–11).
- [x] **`docs/02-first-customer-plan.md`** — added "Local pre-live setup checklist" (11 items).
- [x] **Flaky test fixed**: `test_sla_pass_already_run_today_skips` used `date.today()` (local TZ) vs UTC production code. Fixed to use `datetime.now(timezone.utc)`.

### Local blocker status

`GET /health` blocker is fixed locally and covered by tests.
`app/ui/index.html` is no longer an unknown fancy dirty state: it has been intentionally simplified into an Internal Operator Console with minimal black/white styling and included in the production deploy used for the passed Phase A-C checkpoint.
Production deploy and Phase A-C re-run completed on 2026-07-07. Live commit after Phase N hardening is `01f5763`. Phase D, E, F, G, H, I, J, K, L, M, N, and O PASSED. Phase O: **CONDITIONAL GO (2026-07-08)**. Next: prepare first controlled pilot run with real tenant. Conditions: set support email, review pending approval, rotate DB password.

### Remaining local quality gaps

- [ ] Broaden deterministic extraction for Swedish addresses/property details beyond current keyword/entity coverage.
- [ ] Add more tenant-specific eval scenarios once the first pilot tenant's real service taxonomy and routing hints are known.
- [ ] Consider wiring deterministic support analysis output more directly into older AI-backed `customer_inquiry_processor` payloads if pilot feedback shows operator UI needs one consolidated payload.
- [ ] Production `docker-compose` currently contains DB password directly. Rotate and move DB password to `.env.production` after live verification checkpoint.
- [x] SQLAlchemy SQL echo verbose in production — FIXED in Phase N. `DB_ECHO: bool = False` now default; `database.py` uses `echo=settings.DB_ECHO`. Committed `01f5763`, Docker image rebuilt, SQL echo eliminated in production.

### Pilotdrift Försteg — Tenant Google Mail OAuth (2026-07-19)

- [x] **Backend OAuth flow** — signed state, admin connect/disconnect/status, callback, code exchange, tenant `oauth_credentials` upsert with refresh preservation, auto refresh, test-read, health + onboarding wiring.
- [x] **Operator panel UI** — `GmailIntegrationPanel` on customer detail + onboarding connect button; states not_connected/connecting/connected/reconnect_required/error; no tokens in UI.
- [x] **Pilot scope contract** — `gmail.readonly` + `gmail.modify` only; `gmail.send` deferred until send paths are DB-wired and approved.
- [x] **Security tests** — `tests/test_google_oauth_security.py` (state tenant binding, revoked refresh, cross-tenant, secret scan, same-origin).
- [x] **Tests** — OAuth bundle 108+ security tests pass locally.
- [x] **GCP setup doc** — `docs/google-cloud-oauth-setup.md`.
- [x] **Callback state routing fix** — DB lookup replaces onboarding heuristic (`oauth_state_resolver.py`); deployed `rc-929ee642b1e1`.
- [x] **Live connect `T_NIKLAS_DEMO_001`** — tenant `oauth_credentials`, `credential_source=tenant_oauth`, test-read + refresh + dry-run PASS (2026-07-19).
- [x] **7-day soak started** — baseline + daily scripts; soak log `docs/niklas-gmail-soak-log.md`; scheduler remains paused.
- [ ] **7-day soak complete** — confirm automatic refresh without manual Playground updates across 7 days.
- [ ] **Scope re-consent before external pilot** — Google grant for pilot account still includes legacy `gmail.send` + `spreadsheets`; Krowolf uses only `readonly` + `modify` during soak; clean re-consent required before first external customer (new GCP consent screen / account without legacy grants).

### Blocker — Gmail send via platform-env (not read-only pilot)

- [ ] **`action_executor.py` send-gap** — `_build_email_result` and related paths call `get_integration_connection_config(...)` without `db=`, so approved email sends may resolve **platform-env** tokens instead of tenant `oauth_credentials`. **Does not block read-only pilot** (scan, test-read, dry-run). Blocks future Gmail-send until wired. See `docs/06-backlog.md` Pilotdrift Försteg send-gap.

### Pre-live blockers (require live environment)

- [ ] `ADMIN_API_KEY` must be set to strong random value in production.
- [ ] Correct admin-key success path must be verified with real `ADMIN_API_KEY` against a read-only admin endpoint such as `GET /admin/tenants`; do not print the key in reports.
- [ ] Operator must confirm `ENV=production`, non-empty `ADMIN_API_KEY`, `DATABASE_URL`, latest deployed code/container, Caddy/reverse proxy running, and DB backup completed before Phase D.
- [ ] Gmail OAuth flow must be completed for pilot tenant via `POST /admin/tenants/T_NIKLAS_DEMO_001/integrations/google_mail/connect` (legacy `/oauth/start` disabled — 410).
- [x] Monday `MONDAY_API_KEY` is SET (len=227) and `MONDAY_BOARD_ID` is SET — Phase L confirmed. Live item-creation not tested (intentional — no write in verification).
- [ ] DB backup must be run before first live onboarding.
- [ ] `python scripts/smoke_check.py --base-url <url> --expect-production` must pass.

---

## Next (Fas 2 — First Customer Pilot)

- [ ] Complete local pre-live setup checklist in `docs/02-first-customer-plan.md` against live server.
- [ ] Connect Gmail inbox to pilot tenant (live OAuth flow via operator panel — not Playground).
- [ ] Verify inbox sync reads real mail and creates cases.
- [ ] Verify customer-facing UI shows correct dashboard for pilot tenant.
- [ ] Verify approval-gated email flow works for pilot tenant.
- [ ] Complete go/no-go checklist in `docs/02-first-customer-plan.md`.

---

## Later (Fas 3–4)

- [x] Kapitel 10 — Operator alerts domain (`operator_alerts`), evaluation engine, in-app alertcenter (`/ops/alerts`), digest (`/ops/digests`); E2E + browser verified 2026-07-18 (26 API checks, 216 pytest regression bundle, responsive 320–1440 px). Email delivery deferred until `OPERATOR_ALERT_RECIPIENT` configured.
- [x] Kapitel 11 — Samlad säkerhetshärdning (inventory + Slice 1–3): critical-action registry, legacy route guards, audit fail-closed, tenant/idempotency fixes, OAuth legacy callback block, rate limits + security headers, routePolicy sync, secret scan + cross-tenant tests; docs + runbook `docs/runbooks/security-hardening.md`; DEC-028. PASS 2026-07-18.
- [x] Kapitel 2E — Gold dataset & adversarial evaluation coverage — **merged to `main` @ `3baae50` (PR #2, 2026-07-21).** `k2e-v1` (20 scenarios), manifest, `k2e-baseline-v1`, schema 2e.1, `semantic-json-v2` hashing, executable coverage gate, CI smoke + baseline regression + `pg_eval`; docs `10e-gold-dataset-adversarial-coverage.md`.
- [ ] **Kapitel 2F — Live Gmail + Live LLM E2E Testbot** (replay smoke set, `source_mode: live_gmail`; optional live LLM execution; runtime provenance in harness reports).
- [ ] **Kapitel 2G — AI-generated scenarios, fuzzing och volymtester** (seed-based variants from gold templates; 100–500 email volume runs; root-cause grouping).
- [ ] Stabilize daily operations routine (scheduler, alerts, failed job triage).
- [ ] Package standard onboarding steps for next customer.
- [ ] Improve UI where pilot feedback shows clear need.
- [ ] Define pricing and document in `docs/07-decisions.md`.
- [ ] Plan Outlook/Microsoft Mail intake.

---

## Explicitly Not Now

These items are forbidden before first customer unless `docs/00-master-plan.md` is explicitly updated:

- React or any other frontend framework.
- New frontend-stack.
- SSO or enterprise RBAC.
- Self-serve billing or subscription management.
- Full integration marketplace.
- Körjournal, resejournal, tidsstämpling.
- New large integrations not required for first customer.
- Free bookkeeping automation (Fortnox must remain read/preview/approval-gated).
- Generell chatbot without operational control.
- Any branschspecifik module not needed for first customer.

---

## Known risks (carried from archived backlog)

- `app/api/routes/jobs.py` is dead code (not mounted) — remove or wire up when safe.
- No DB migration tooling — schema changes via `create_all` + runtime safeguard.
- Gmail token is short-lived; onboarding OAuth refresh not self-service for customer.
- `create_internal_task` is stubbed — no persistence beyond job result payload.
