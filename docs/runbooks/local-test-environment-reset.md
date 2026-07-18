# Local test environment reset

> Mellankapitel 8B — routine before Kapitel 9 system verification.

## When to run

- Operator panel shows misleading counts from old local test data
- Before a full walkthrough of `/ops/needs-help`, `/ops/usage`, `/ops/system`
- After experimenting with demo seeds or legacy tenants (`TENANT_1001`, etc.)

## Preconditions

- `ENV` is `dev` or `local` (see allowlist in `app/tools/test_environment/guards.py`)
- PostgreSQL target is local (`localhost` / `127.0.0.1`, database `ai_platform` or `*_test`)
- You have a backup if the database contains anything you might need later

## Routine

### 1. Inventory

```bash
python -m scripts.reset_test_environment inventory
```

Review row counts per tenant. Tenants outside an explicit purge scope are reported as `SKIP`.

### 2. Purge dry-run

Only target tenants you intend to remove:

```bash
python -m scripts.reset_test_environment purge-tenants \
  --tenant-id T_LOCAL_OPS_SECONDARY
```

Or use the versioned allowlist profile (never deletes unknown tenants):

```bash
python -m scripts.reset_test_environment purge-tenants --profile local-standard
```

### 3. Prune stale data (optional, per tenant)

```bash
python -m scripts.reset_test_environment prune-stale-data \
  --tenant-id T_LOCAL_OPS_BASELINE \
  --data-type pending_approvals \
  --older-than-days 30
```

Repeat for `stuck_jobs` or `demo_seed_jobs` as needed.

### 4. Execute purge / prune

```bash
set RESET_TEST_ENVIRONMENT_ALLOWED=yes
python -m scripts.reset_test_environment purge-tenants \
  --execute --confirm LOCAL_TEST_RESET --tenant-id T_LOCAL_OPS_SECONDARY
```

### 5. Seed baseline

```bash
python -m scripts.reset_test_environment seed-baseline \
  --execute --confirm LOCAL_TEST_RESET
```

Creates/updates `T_LOCAL_OPS_BASELINE` with manual scheduler, approval-required `auto_actions`, sample jobs and one pending approval.

### 6. Verify operator panel

Start backend + frontend and check:

- http://localhost:5173/ops/needs-help
- http://localhost:5173/ops/usage
- http://localhost:5173/ops/system

**Responsive checklist (small-desktop):** 1280 px and 1366 px viewport with sidebar open; 125% and 150% browser zoom on needs-help and usage tables.

## Reference

- Dependency map: [`test-data-dependency-map.md`](test-data-dependency-map.md)
- Reserved IDs: `app/tools/test_environment/reserved_tenants.py`
