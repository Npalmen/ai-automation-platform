# Krowolf Operator Panel — Frontend

Internal operator panel frontend for Krowolf. This is **not** the customer portal.

The legacy single-file UI at `app/ui/index.html` remains in place and continues to be served at `/` (host-gated) and `/ui`. **K11:** legacy UI shows a deprecation banner — use `/ops` for operator work. This React app is served at `/ops`.

## Security (Kapitel 11)

- No secrets in browser storage — no `localStorage`/`sessionStorage` for auth or API keys.
- Route guards in `src/routes/routePolicy.ts` must stay in sync with backend `require_operator_role` (integrity enforced by backend contract tests).
- Onboarding wizard and operator digests require `operations` or `admin` (not `read_only`).
- All writes use session cookie (`credentials: "include"`) — never `X-Admin-API-Key` from the browser.
- Run `tests/test_security_secret_scan.py` before release; see `docs/runbooks/security-hardening.md`.

## Kapitel 12 Slice 3 verification

```bash
python scripts/kapitel12_slice3_verify.py
```

Reports: `scripts/kapitel12_slice3_report.json`, `scripts/kapitel12_browser_report.json`. Release decision: **CONDITIONAL GO** (see `docs/kapitel-12-release-notes.md`).

## Stack

- React + TypeScript + Vite
- Tailwind CSS v3 + Krowolf design tokens (from JSON contracts)
- shadcn/ui baseline (`button`, `badge`) + operator components
- React Router (`basename: /ops`)
- TanStack Query

## Authentication (Kapitel 1C)

Session-based operator auth reuses existing backend routes:

| Endpoint | Purpose |
|----------|---------|
| `POST /auth/admin/login` | Username/password login; sets HttpOnly `admin_session` cookie |
| `GET /auth/admin/me` | Current operator identity, role, and environment |
| `POST /auth/admin/logout` | Clears session cookie |

Frontend rules:

- `credentials: "include"` on all auth API calls (`src/api/client.ts`)
- No `X-Admin-API-Key`, no `localStorage`/`sessionStorage` for auth
- `AuthProvider` + TanStack Query `["auth","me"]` as single source of session state
- Environment indicator reads `environment` from `/auth/admin/me` (not `/health`)

### Roles

Configured server-side via `ADMIN_ROLE` (`read_only` | `operations` | `admin`). Invalid values fail at settings startup (fail-closed).

Frontend route guards:

- `RequireAuth` — redirects unauthenticated users to `/ops/login`
- `RequireRole` — renders forbidden state when role is insufficient

Route policy table: `src/routes/routePolicy.ts` (typed, includes foundation/design-reference admin-only policy).

### Public vs protected routes

| Path | Access |
|------|--------|
| `/ops/login` | Public |
| `/ops`, `/ops/needs-help`, `/ops/customers`, `/ops/incidents`, `/ops/alerts`, `/ops/usage` | Authenticated (all roles) |
| `/ops/onboarding`, `/ops/onboarding/*` | `operations`, `admin` |
| `/ops/digests`, `/ops/digests/*` | `operations`, `admin` |
| `/ops/system` | `operations`, `admin` |
| `/ops/foundation`, `/ops/design-reference` | `admin` only |

`/ops` (index) is the live **Global översikt** (Kapitel 2). `/ops/needs-help` is the live **Behöver hjälp** queue (Kapitel 4). `/ops/customers` is the live **Kundlista** (Kapitel 3). `/ops/incidents` is the live **Incidenthantering** (Kapitel 6). `/ops/alerts` is the live **Larmcenter** (Kapitel 10). `/ops/digests` is the live **Operatörssammanfattningar** (Kapitel 10). `/ops/usage` is the live **Användning och kapacitet** (Kapitel 7). `/ops/system` is the live **Systemstatus** (Kapitel 8). Safe operator writes are available from customer detail and needs-help detail (Kapitel 5).

## Systemstatus (Kapitel 8)

Read-only technical operations view at `/ops/system` (`operations` + `admin` roles). No deploy/backup/restore actions.

| Area | Source |
|------|--------|
| Endpoint | `GET /admin/system/status` |
| Runtime | API, database ping, scheduler, jobs/queues, integrations |
| Resilience | Separate backup + restore-test cards from status JSON files |
| Deploy readiness | Build metadata from image; deploy time unknown; routing not verified in VCS |
| Limitations | Metadata write failures visible in script logs only, not API |

Honest gaps: `build_time` ≠ deploy time; `Caddyfile.example` is not production truth; pilot readiness not included.

Frontend: `src/features/systemStatus/` — domain summaries, HealthIndicator lists, limitations, runbook labels.

## Användning och kapacitet (Kapitel 7)

Read-only usage, cost and capacity at `/ops/usage`. No writes, no charts, no fabricated AI cost.

| Area | Source |
|------|--------|
| Overview | `GET /admin/usage/overview?days=7\|30\|90` — summary, capacity, AI blocks, data-quality notes |
| Tenant list | `GET /admin/usage/tenants` — batched per-tenant metrics, filter/sort/paginate |
| Period | Half-open UTC `[start, end)`; comparison = preceding equal window |
| Auth | Single `require_operator_role(read_only\|operations\|admin)` — no double auth dependency |
| Tenant link | Rows link to `/ops/customers/:tenantId` (no separate usage detail page) |

Honest gaps (shown as `not_measured` / `unknown`, never fake zeros):

- `automation_rate` — `not_measured` (audit_events lacks indexed `job_id` for operator_action linkage).
- `manual_reviews_created` — `not_measured`; `gmail_manual_review_handoffs` is the auditable Gmail-only signal.
- `jobs_completed` / `jobs_failed` — `updated_at` proxy (`timestamp_basis: updated_at_proxy`).
- `ai_usage` — `not_measured`; `ai_cost` — `unknown`.
- `capacity.status` — `baseline_missing` (no configured thresholds).
- `attention_status` — reuses `collect_all_triage_rows()` (pre-existing O(tenants) cost, documented).

UI filters exclude non-differentiating `ai_cost_status` / `automation_rate` sort options this chapter.

Frontend: `src/features/usage/` — metric cards, capacity section, tenant table/cards, data-quality section.

## Incidenthantering (Kapitel 6)

Internal incident management at `/ops/incidents` and `/ops/incidents/:incidentId`. No external effects.

| Area | Source |
|------|--------|
| List | `GET /admin/incidents` — filter, sort, paginate, summary |
| Detail | `GET /admin/incidents/{incident_id}` — tenants, signals, timeline, `available_actions` |
| Create | `POST /admin/incidents` — no client-supplied owner |
| Status | `POST /admin/incidents/{id}/status` — backend transition table + `expected_version` |
| Notes | `POST /admin/incidents/{id}/notes` — plain text only |
| Assign self | `POST /admin/incidents/{id}/actions/assign-self` — owner from session |
| Links | tenant/signal link+unlink; signal snapshot at link time |
| Needs-help | detail exposes `recommended_incident_action` + `linked_incidents.open/closed` |

Rules:

- New tables via explicit `import app.admin.incident_models` in startup + `create_all()` (no Alembic).
- Incident row writes use atomic `UPDATE … WHERE version = :expected_version`.
- Timeline + audit share one `db.commit()` per write (`_add_audit_event_no_commit`).
- `closed` is terminal — all writes return 409.
- Soft-unlink only — no hard deletes; `tenant_name_snapshot` preserved.
- Frontend: `src/features/incidents/` — explicit API endpoints, mutations `retry: false`, no `dangerouslySetInnerHTML`.

## Säkra operatörsåtgärder (Kapitel 5)

First chapter with real writes — scope limited to five verified-safe actions.

| Action | Endpoint | Role |
|--------|----------|------|
| Pausa automation | `POST /admin/tenants/{tenant_id}/actions/pause` | `operations`/`admin` |
| Återuppta automation | `POST /admin/tenants/{tenant_id}/actions/resume` | `operations`/`admin` |
| Pausa scheduler | `POST /admin/tenants/{tenant_id}/scheduler/pause` | `operations`/`admin` |
| Återuppta scheduler | `POST /admin/tenants/{tenant_id}/scheduler/resume` | `operations`/`admin` |
| Avslå dispatch-godkännande | `POST /admin/tenants/{tenant_id}/approvals/{approval_id}/reject` | `operations`/`admin` |

Rules:

- Backend generates `available_actions` on tenant overview and needs-help detail (`allowed` + `blocked_reason` for `read_only`).
- Frontend maps each action to a **fixed** endpoint in `src/features/operatorActions/api.ts` — never from `action_id`.
- All writes require `reason`, `confirmation: true`, and use session cookie auth (`credentials: "include"`).
- Mutations use `retry: false`; on success invalidate tenant detail, needs-help, overview, and customers queries.
- `idempotency_key` is sent and stored in audit for traceability; state is the primary idempotency guarantee.
- Blocked this chapter: manual review resolve, reclassify, re-extract, replay dispatch, approve, critical writes.

UI: **Operatörsåtgärder** section on customer detail; actions after recommended action on needs-help detail. `ActionDialog` with mandatory reason + checkbox confirmation.

## Behöver hjälp (Kapitel 4)

Read-only cross-tenant deviation queue at `/ops/needs-help` and `/ops/needs-help/:itemId`.

| Area | Source |
|------|--------|
| Queue | `GET /admin/operations/needs-help` — typed, paginated, filterable |
| Detail | `GET /admin/operations/needs-help/{item_id}` — optional `tenant_id` scopes lookup |
| Incidents | `recommended_incident_action` + `linked_incidents` (open/closed metadata) on detail |
| Signals | Shared `collect_all_triage_rows()` with dedupe/current-state normalization |
| Severity (API) | Panel vocabulary: `critical` / `failed` / `warning` / `information` |
| Summary | Computed on filtered set pre-pagination (`affected_tenants`, `safe_retry_yes`, etc.) |
| Runbooks | Allowlisted IDs + Swedish labels only (no filesystem paths) |
| Legacy | `get_admin_needs_help()` retained for existing tests/consumers |

## Kundlista och kunddetalj (Kapitel 3)

Read-only customer list and detail at `/ops/customers` and `/ops/customers/:tenantId`.

| Area | Source |
|------|--------|
| List | `GET /admin/tenants` — enriched items; batched `GROUP BY` for approvals, manual review, jobs_30d, last_activity |
| Detail | `GET /admin/tenants/{tenant_id}/overview` — single round-trip per page |
| `tenant_status` | Verbatim from `tenant_configs.status` (`active`/`inactive`/`unknown`) |
| `health` | Separate from tenant status; `paused` only on verified `demo_mode` or scheduler pause |
| Gmail (list summary) | Triage integration rows (same source as Kapitel 2) |
| Visma / Google Sheets | `oauth_credentials` + `IntegrationEvent` per tenant; `unknown` when no signal |
| gmail/monday/fortnox (detail) | `get_integration_health` |
| `package` / `operator_owner` | Always `null` — no source in platform |
| `enabled_modules` | `enabled_job_types` + `allowed_integrations` (allowlisted rename) |
| Settings | Never serialized wholesale; allowlist only |

### Performance note (list)

Approvals, manual-review counts, `jobs_last_30d`, and `last_activity_at` use batched queries. `open_issues_count` inherits per-tenant cost from one `collect_all_triage_rows` call (same as Kapitel 2). Smoke-tested with ~50 mock tenants; not an SLA.

## Global översikt (Kapitel 2)

Read-only operator dashboard at `/ops` backed by `GET /admin/operations/overview`.

| Area | Source |
|------|--------|
| Counters | Global SQL aggregations (`JobRecord`, `ApprovalRequestRecord`, `IntegrationEvent`, `TenantConfigRecord`) |
| Priority list | `collect_all_triage_rows()` from needs-help triage (sorted independently in overview service) |
| Gmail integration | Per-tenant `get_integration_health` signals (via triage rows) |
| Visma / Google Sheets | `IntegrationEvent` log (24h); zero events → `unknown`, not `healthy` |
| System.api | Process responded; does **not** prove background flows are healthy |
| System.backup/deploy | `unknown` — no source in platform yet |

### Counter time windows (`window_hours`)

| Counter | Window |
|---------|--------|
| `jobs_last_24h`, `integration_errors` | 24 h |
| `failed_jobs`, `stuck_jobs` | 48 h |
| `pending_approvals`, `open_manual_reviews`, `active_tenants` | point-in-time (`null`) |

### Stuck jobs rule

`status IN ("pending","processing")` AND `updated_at < now - 48h`. Excludes `awaiting_approval` and `manual_review`.

### Error handling

Mandatory aggregation failure → HTTP **503** (no partial counters). Frontend shows `ErrorState` with manual retry.

### Priority list sorting (backend-owned)

1. Severity → 2. external/uncertain impact → 3. oldest first → 4. stable ID. Frontend renders backend order as-is.

### Performance note

Inherited per-tenant N+1 from `collect_all_triage_rows` (one call per overview request). Smoke-tested with ~50 mock tenants; not an SLA.

See **Behöver hjälp** (Kapitel 4) for the full queue UI.

## Design contracts (authoritative)

Machine-readable contracts in `frontend/design/`:

- `krowolf-ui-profile.json` — colors, typography, spacing, breakpoints, accessibility, forbidden patterns
- `component-contracts.json` — component purpose, variants, states, accessibility
- `page-contracts.json` — page templates and responsive layout rules

### Changing design tokens

1. Edit values in `frontend/design/krowolf-ui-profile.json` only.
2. Run `npm run tokens:generate` (also runs automatically via `predev` / `prebuild`).
3. Node tooling reads the JSON via `createRequire` in `tailwind.config.js` and `scripts/generate-design-tokens.mjs`.
4. Generated CSS variables land in `src/styles/tokens.generated.css` (gitignored).

Do not duplicate token values in component files or Tailwind config.

### Adding a component variant

1. Add a new key to the relevant `variants` object in `component-contracts.json`.
2. Add the matching key to the component's `satisfies Record<DerivedVariant, ...>` style map.
3. `npm run typecheck` fails until both sides match.

Variant types are derived with `keyof typeof` from the JSON — no hand-written unions.

## Local development

```bash
cd frontend
npm install
npm run dev
```

Vite dev server proxies `/health`, `/auth/admin`, and `/admin` to `http://localhost:8000`.

Production-style `/ops` (same-origin cookie auth):

```bash
npm run build
# from repo root, with backend running:
# uvicorn app.main:app --reload
# open http://localhost:8000/ops/login
```

Configure backend session auth (`ADMIN_PASSWORD_HASH`, `SESSION_SECRET_KEY`, optional `ADMIN_ROLE`, `ADMIN_DISPLAY_NAME`).

## Quality gates

```bash
npm run tokens:generate
npm run typecheck
npm run lint
npm run test:contracts
npm run build
```

## Responsive manual checklist

Verify login, AppShell, and navigation at 320, 375, 768, 1024, 1100, 1250, 1366, 1440, 1920 px and 125%, 150%, 200% zoom.

**Small-desktop focus (sidebar open):** `/ops/needs-help` and `/ops/usage` at **1280 px** and **1366 px** with **125%** and **150%** zoom — compact row layout must stay readable (no word/character breaks in prose, severity badges intact).

- [ ] No global horizontal scroll
- [ ] Behöver hjälp + usage use compact rows (not squeezed multi-column tables) between ~768–1199px content width
- [ ] Login form usable at 320px / 200% zoom
- [ ] Mobile drawer opens/closes; Escape closes; backdrop blocks interaction
- [ ] FilterBar fields wrap; reset buttons visible; inputs ≥ 44px touch height
- [ ] Long Swedish nav labels wrap
- [ ] Touch targets ≥ 44px on menu and logout
- [ ] Environment badge visible in topbar

## Backend integration

- Vite builds to `frontend/dist/` with `base: "/ops/"`.
- Docker multi-stage build runs `npm ci && npm run build` in a Node stage.
- FastAPI serves SPA fallback and `/ops/assets/*` (see Kapitel 1A).

## Not built yet

- Tenant selector / `X-Tenant-ID` context
- Full Behöver hjälp queue, customer detail, incidents, usage trends
- Critical writes, approvals, recovery actions from overview

## Deploy note

`infra/Caddyfile` is not production-verified. Set `ALLOWED_ORIGINS` in production for origin-checked login/logout. See [`infra/README.md`](../infra/README.md).

## Cursor rule

Frontend work is governed by `.cursor/rules/frontend-ui.mdc`.
