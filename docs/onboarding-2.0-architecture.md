# Onboarding 2.0 — Architecture (DEC-032)

> Governed by `docs/00-master-plan.md`. Canonical index: `docs/DOCUMENT_INDEX.md`.

## Principle

Onboarding is a **guided workflow** over `tenant_configs.settings` — not a parallel config store. After activation, the same settings are edited via tenant settings API and customer card.

## Bindande decisions

See plan DEC-032: paused is operational (not lifecycle), super_admin via operator ID, DB-only OAuth routing, config_version-bound readiness, immutable activation snapshots, service catalog owned by `service_profiles/`.

## Lifecycle vs operations

| Concept | Storage | Values |
|---------|---------|--------|
| `lifecycle_status` | `tenant_configs.lifecycle_status` | draft, onboarding, waiting_for_customer, technical_verification, ready_for_activation, active, archived |
| Drift pause | `settings.operations.paused` + `settings.scheduler.run_mode` | paused ≠ lifecycle |
| Onboarding progress | `onboarding_sessions` | session status + current_step |
| Legacy `status` | `tenant_configs.status` | active/inactive (retained for compatibility) |

## New tables (migrations 012–014)

- `integration_invitations` — customer OAuth invites (hashed token, connected_account_email)
- `tenant_activation_snapshots` — append-only activation history

## New columns on `tenant_configs`

- `lifecycle_status`, `config_version`, `lifecycle_updated_at`, `lifecycle_updated_by`, `is_test_tenant`

## API extensions

| Endpoint | Purpose |
|----------|---------|
| `GET/PATCH /admin/tenants/{id}/lifecycle` | Lifecycle transitions |
| `POST /admin/tenants/{id}/lifecycle/archive\|restore` | admin only |
| `POST /admin/tenants/{id}/operations/pause\|resume` | Operational pause |
| `GET/PATCH /admin/tenants/{id}/settings/{section}` | Post-activation settings |
| `GET /admin/tenants/{id}/settings` | Aggregate customer settings (Slice C) |
| `GET /admin/tenants/{id}/activation-history` | Immutable snapshots |
| `POST/GET /admin/tenants/{id}/integrations/invitations` | Customer invites |
| `GET/POST /integrations/invite/{token}/*` | Public invite flow |
| `DELETE /admin/tenants/{id}` | super_admin + test tenant only |

## Compatibility

- Internal service profile keys unchanged (`ev_charger_installation`, etc.)
- `slice2a_registry.py` → presenter/filter only; catalog in `service_profiles/`
- Legacy `app/onboarding/readiness.py` → thin wrapper over admin readiness
- `is_onboarding_oauth_state()` heuristic removed from callback path
- `T_NIKLAS_DEMO_001`: map to `lifecycle_status=active`, scheduler paused, OAuth untouched

## Runtime gates

- Scheduler: only `lifecycle_status=active` + `scheduler.run_mode=scheduled`
- Gmail intake: `internalDate` UTC vs `intake_cutoff_at` before job creation
- Readiness stale when `config_version` changes after last check

## Integration selections (Slice B — migration 016)

| Concept | Location |
|---------|----------|
| Source of truth | `settings.integrations.selections` (canonical keys via `app/integrations/keys.py`) |
| Runtime allowlist | `allowed_integrations` — derived from selections (fail-closed sync) |
| External writes | `enabled_external_writes` — selection + verified credential only |
| Group requirements | `required_integration_groups` on capabilities (e.g. `invoice_handling` → `finance_destination`) |
| Group implementation | `group_implementations.finance_destination.type = manual_accounting_routing` |
| Backfill audit table | `integration_selection_backfill_runs` (migration 016 SQL only) |
| Backfill service | `scripts/run_integration_selection_backfill.py` — idempotent, dry-run capable |

### Canonical keys

- `gmail` → `google_mail` at ingest
- Registry keys (`visma`, `google_sheets`) map to canonical keys in selections

### Readiness

`evaluate_integrations_step` emits `integration_groups` and blocks with `group:finance_destination` when manual routing lacks valid invoice accounting route.

Operator flow: `docs/onboarding-2.0-operator-flow.md`
