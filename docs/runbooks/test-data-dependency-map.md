# Test environment reset CLI (Mellankapitel 8B)

> Local/test-only tooling. Never run against production.

## Purpose

Prepare a predictable local database for operator panel verification and Kapitel 9 system tests by:

- inventory of tenant-linked rows
- explicit tenant purge (`purge-tenants`)
- explicit stale pruning (`prune-stale-data`)
- baseline seed (`seed-baseline`)

## Tenant data dependency map

### Tenant-scoped tables (per `tenant_id`)

| Order | Table | Notes |
|------:|-------|-------|
| 1 | `incident_signals` | Unlink tenant signals only |
| 2 | `incident_tenants` | Unlink tenant ↔ incident link |
| 3 | `integration_events` | Includes idempotency keys |
| 4 | `action_executions` | Job-linked executions |
| 5 | `approval_requests` | Pending/historical approvals |
| 6 | `jobs` | Includes Gmail intake + manual review state in JSON |
| 7 | `audit_events` | Includes `operator_action` category rows |
| 8 | `oauth_credentials` | Per-tenant OAuth rows |
| 9 | `tenant_api_keys` | Hashed API keys |
| 10 | `tenant_configs` | Tenant root row |

### Cross-tenant incident tables

| Order | Table | Policy |
|------:|-------|--------|
| 11 | `incident_timeline_events` | Delete only when no `incident_tenants` remain for `incident_id` |
| 12 | `incidents` | Delete only when orphaned (no tenant links) |

**Locked policy:** Purge for tenant `T` removes only `T`'s `incident_signals` and `incident_tenants` rows. Shared incidents and timelines remain while any other tenant link exists.

### Not separate tables

| Concept | Storage |
|---------|---------|
| Gmail intake | `jobs.input_data` (`source.system = gmail`) |
| Manual review | `jobs.status` / `jobs.result` JSON |
| Operator actions | `audit_events.category = operator_action` |
| Idempotency | `integration_events.idempotency_key` |

## Reserved tenant IDs

Defined in `app/tools/test_environment/reserved_tenants.py`:

- `T_LOCAL_OPS_BASELINE` — baseline seed target
- `T_LOCAL_OPS_SECONDARY` — optional second local test tenant
- `local-standard` purge profile expands **only** to the allowlist above

Unknown tenants are never auto-selected. Inventory marks them `SKIP`.

## Commands

```bash
# Read-only inventory (requires allowlisted ENV)
python -m scripts.reset_test_environment inventory

# Dry-run purge (default)
python -m scripts.reset_test_environment purge-tenants --tenant-id T_LOCAL_OPS_SECONDARY

# Execute purge
RESET_TEST_ENVIRONMENT_ALLOWED=yes python -m scripts.reset_test_environment purge-tenants \
  --execute --confirm LOCAL_TEST_RESET --tenant-id T_LOCAL_OPS_SECONDARY

# Prune stale pending approvals for one tenant
python -m scripts.reset_test_environment prune-stale-data \
  --tenant-id T_LOCAL_OPS_BASELINE --data-type pending_approvals --older-than-days 30

# Seed baseline tenant
RESET_TEST_ENVIRONMENT_ALLOWED=yes python -m scripts.reset_test_environment seed-baseline \
  --execute --confirm LOCAL_TEST_RESET
```

## Execute guards (positive allowlist)

All `--execute` operations require:

1. `ENV` ∈ `{local, dev, development, test, testing}`
2. `RESET_TEST_ENVIRONMENT_ALLOWED=yes`
3. `DATABASE_URL` matches `app/tools/test_environment/allowed_database_fingerprints.json`
4. `--confirm LOCAL_TEST_RESET`

Unknown databases are blocked (fail closed).

## Prune data types

| `--data-type` | Deletes |
|---------------|---------|
| `pending_approvals` | `approval_requests` with `state=pending` older than threshold |
| `stuck_jobs` | `jobs` in `pending`/`processing` older than threshold |
| `demo_seed_jobs` | `jobs` flagged `demo_seed` or `source.system=demo_seed` |

No generic audit/integration heuristics.
