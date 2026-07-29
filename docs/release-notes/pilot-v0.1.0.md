# Release notes — pilot-v0.1.0

## Production pilot release (P0)

- Release candidate: `pilot-v0.1.0`
- Pilot tenant: `TENANT_PRODUCTION_PILOT_01`
- Activation stage: P0 (production dry run)
- Qualifications required: `FULL_FUNCTION_MATRIX_PASS`, `CONTINUOUS_REGRESSION_QUALIFIED`, `TESTBOT_SYSTEM_CLOSED`

## Included

- Production pilot release manifest and runtime verification
- P0–P3 activation stage matrix with fail-closed gates
- Kill switches (global scheduler pause, tenant pause, Gmail reply disable, shadow disable)
- Config snapshot/restore with hash verification
- Hermetic P0 preflight (synthetic inbound, 0 replies, 0 non-Gmail writes)
- Operator runbooks and daily report script

## Not included

- P1 observe-only pilot traffic (requires operator authorization)
- Live Gmail replies
- Sheets, Monday, or Visma activation
- Automatic verify, customer link, or merge
- Production GA

## Operator stop

```text
OPERATOR ACTION REQUIRED — Auktorisera P1 observe-only pilottrafik
```
