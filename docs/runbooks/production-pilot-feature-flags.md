# Production pilot feature flags

## Environment flags (fail-closed defaults)

| Flag | Default | P0 | P1 | P2 | P3 |
|------|---------|----|----|----|-----|
| `END_CUSTOMER_READ_API_ENABLED` | false | false | false | false | false |
| `END_CUSTOMER_WRITE_API_ENABLED` | false | false | false | false | false |
| `END_CUSTOMER_SHADOW_INTAKE_ENABLED` | false | false | true* | true* | true* |
| `END_CUSTOMER_SHADOW_MATCHING_ENABLED` | false | false | true* | true* | true* |
| `END_CUSTOMER_SHADOW_PROMOTION_ENABLED` | false | false | false | false | false |
| `PRODUCTION_PILOT_GLOBAL_SCHEDULER_PAUSE` | false | true** | operator | operator | operator |

\* Requires operator authorization at P1+ and tenant allowlist  
\** Recommended true until P1 authorization

## Tenant settings

| Setting | P0 value |
|---------|----------|
| `production_pilot.activation_stage` | `P0` |
| `production_pilot_intake.enabled` | `false` |
| `scheduler.run_mode` | `paused` |
| `automation.demo_mode` | `true` |
| `automation.automatic_gmail_replies` | `false` |
| `operations.paused` | `true` |
| `allowed_integrations` | `["google_mail"]` |

## Blocked capabilities (all stages)

- Automatic verify
- Automatic customer link
- Automatic merge
- Sheets / Monday / Visma writes
