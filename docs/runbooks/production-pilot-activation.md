# Production pilot activation runbook

## Scope

- Exactly one pilot tenant: `TENANT_PRODUCTION_PILOT_01`
- Activation stages: P0 → P1 → P2 → P3 (one step at a time, operator approval required)
- No Sheets, Monday, or Visma writes during pilot
- No automatic verify, customer link, or merge

## P1 — Observe-only pilot traffic (qualified)

| Control | State |
|---------|-------|
| Gmail intake | ON |
| Observe/manual review | ON |
| Shadow intake/matching | ON |
| Shadow promotion | OFF |
| Approvals (external write) | OFF |
| Gmail replies | 0 |
| Automatic Gmail | OFF |
| Sheets/Monday/Visma | OFF |

Activation:

```bash
python scripts/production_pilot/activate_p1.py
python scripts/production_pilot/p1_preflight.py
```

**Stop** — do not enable P2 without explicit authorization.

## P0 — Production dry run (completed)

| Control | State |
|---------|-------|
| Gmail intake | OFF |
| Observe | ON (synthetic/hermetic only) |
| Approvals | OFF |
| Automatic Gmail | OFF |
| Shadow intake/matching/promotion | OFF |
| Scheduler | PAUSED |
| External writes | 0 |

### Operator checklist

1. Confirm release manifest exists: `storage/status/production-pilot/release-manifest.json`
2. Confirm backup reference documented before deploy/migration
3. Run P0 preflight: `python scripts/production_pilot/p0_preflight.py`
4. Verify `PRODUCTION_PILOT_RELEASE_READY` in preflight output
5. **Stop** — do not enable P1 without explicit authorization

### P0 → P1 gate (not automated)

Requires operator authorization:

- release deployed
- migrations PASS
- health PASS
- pilot tenant created in production DB
- Gmail OAuth PASS
- mailbox preflight PASS
- automation paused
- rollback tested
- 0 external writes

## Kill switches

| Switch | Action |
|--------|--------|
| Global scheduler pause | Set `PRODUCTION_PILOT_GLOBAL_SCHEDULER_PAUSE=true` |
| Tenant automation pause | `POST /admin/support/TENANT_PRODUCTION_PILOT_01/pause-automation` |
| Disable scheduler | `POST /admin/support/TENANT_PRODUCTION_PILOT_01/disable-scheduler` |
| Disable Gmail replies | Set `automation.automatic_gmail_replies=false` + demo_mode |
| Disable shadow intake | Env `END_CUSTOMER_SHADOW_INTAKE_ENABLED=false` |
| Disable shadow matching | Env `END_CUSTOMER_SHADOW_MATCHING_ENABLED=false` |
| Disable shadow promotion | Env `END_CUSTOMER_SHADOW_PROMOTION_ENABLED=false` |
| Disable Gmail intake | `production_pilot_intake.enabled=false` |
| Read-only operator mode | `python scripts/production_pilot/restore_baseline.py` |
| Deployment rollback | See `production-pilot-rollback.md` |
| Database restore | See `production-pilot-rollback.md` |

## Daily report

```bash
python scripts/production_pilot/daily_report.py
```

Output: `storage/status/production-pilot/daily-report.json`
