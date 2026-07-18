# Kapitel 9 — Nulägesinventering (pre-implementation)

> Gate-dokument före Kapitel 9 slice 1. Gällande implementation: `app/admin/onboarding/`.

## Återanvändbart idag

| Område | Status | Nyckelfiler |
|--------|--------|-------------|
| Tenant persistence | Finns | `tenant_config_models.py`, `tenant_config_repository.py` |
| Legacy provision | `POST /admin/tenants` → `active`, `T_{SLUG}` | `main.py` |
| Schema safeguard | Additiv DDL | `schema_migrations.py` |
| API-nycklar | Hash, rotate | `tenant_api_key_repository.py` |
| Visma OAuth | Per-tenant | `integrations/visma/oauth_routes.py` |
| Gmail / Monday | Plattforms-env | settings env |
| Automation | `auto_actions`, scheduler | `workflows/dispatchers/policy.py` |
| Legacy checklista | Tenant-key, 8 steg | `onboarding/readiness.py` |
| Operator audit | Fail-closed | `audit_service.py`, `operator_actions.py` |
| Kundlista React | Read-only | `frontend/src/features/customers/` |

## Gap (adresseras i slice 1)

| Krav | Gap före Kapitel 9 |
|------|-------------------|
| OnboardingSession | Saknades |
| Additiv migration | Onboarding-tabeller saknades |
| Panel-onboarding | Saknades |
| Tre register | Blandat i `_MODULE_JOB_TYPES` |
| Readiness källklassificering | Global health användes som tenant-bevis |
| Transaktionell aktivering | Saknades |
| API-nyckel vid create | Legacy `POST /admin/tenants` skapade nyckel automatiskt |

## Verifieringsmatris (sammanfattning)

| Kategori | Obligatoriskt | Verifierbart lokalt | Extern interaktion | Hemligheter |
|----------|---------------|---------------------|-------------------|-------------|
| Identitet | name, slug | Ja | — | — |
| Capabilities | Minst ett i slice 1 | Ja | — | — |
| Integrations | Per vald capability | Delvis | Visma OAuth | Tokens aldrig i API |
| Automation preset | Ja | Ja | — | — |
| API-nyckel | Endast om `api_access` | Ja | — | Visas en gång |

## Legacy

`POST /admin/tenants` förblir script/intern bypass — ingen ny frontend.
