# Runbook: Customer Onboarding



> **Safety:** Never enable `auto_actions` during onboarding without explicit operator confirmation after isolated integration testing.

> **Isolation:** Each customer must be provisioned as a separate tenant. Tenant API keys must be stored securely and never reused.



---



## Overview



This runbook covers provisioning a new customer tenant, verifying readiness, and handing off to the customer.



**Preferred path (Kapitel 9):** Operator panel at `/ops/customers/new` → wizard at `/ops/customers/{tenantId}/onboarding`.



**Legacy script path:** `POST /admin/tenants` — retained for automation/scripts only; the React operator panel does **not** call this endpoint.



**Registry source of truth:** `GET /admin/onboarding/registries` — capabilities, integrations, runtime features, and versioned automation presets. The panel loads this before enabling writable steps; there is no hardcoded fallback list.



---



## Pre-onboarding checklist



Before provisioning a new tenant:



- [ ] Platform health check passes: `GET /health` → 200

- [ ] DB backup taken (see `docs/runbooks/backup-and-restore.md`)

- [ ] Operator logged in at `/ops` with `operations` or `admin` role

- [ ] Customer-specific integration credentials are ready (if applicable)

- [ ] Support email agreed with customer

- [ ] Operator assigned as primary contact for this tenant



---



## Panel flow (Kapitel 9 slice 1)



### 1. Start onboarding



1. Open `/ops/customers` → **Ny kund**

2. Enter company name and slug

3. Submit — creates **inactive** tenant + open onboarding session (**no API key**)



### 2. Complete writable steps (1–3)



| Step | Action |

|------|--------|

| Identitet | Company name, slug, contacts |

| Moduler | Select product capabilities from `GET /admin/onboarding/registries` |

| Automation | Choose versioned preset (`observe_only` v1, `prepare_only` v1, …) |



> **Legacy values:** If a resumed session contains capability or preset keys no longer in the registry, the UI shows them as read-only “Legacy — inte längre valbar” and blocks save until the operator updates the selection.



### 3. Review read-only steps (4–6)



Steps **service profile**, **integrations**, and **data start** are read-only in slice 1. The UI shows `step_status` and whether each step **blocks activation**.



> For slice 1 smoke tests, `followups` alone can reach `ready_with_warnings` (scheduler configured but paused — not plain `ready`). Capabilities that require service profile or integrations may still block activation until slice 2 PATCH APIs exist.



### 4. Run readiness



Click **Kör readiness** in the wizard. Review blocking checks and platform-level warnings. Note `check_version` — activation requires the latest version.



### 5. Review activation plan + activate (admin only)



1. Open the **Aktivera** step — loads `GET /admin/onboarding/{session_id}/activation-plan` (consequences, capability states, `plan_hash`).

2. Role: `admin`

3. Confirmation phrase must match tenant **slug** exactly

4. If `ready_with_warnings`: acknowledge **every** warning ID shown

5. Submit activate with the **`plan_hash`** from the plan response (server returns `409 stale_activation_plan` if session, readiness, registry, or plan content drifted)

6. Scheduler remains `paused` after activation (fail-closed in slice 1)



### 6. API key (optional, separate)



Only when selected capabilities require **API access** (registry `required_runtime` includes `api_access`):



- `POST /admin/onboarding/{session_id}/api-key` (admin, reason + confirmation)

- Raw key shown once — store securely



---



## Curl fallback — registries



```bash

curl -sS https://api.krowolf.se/admin/onboarding/registries \

  -H "Cookie: admin_session=…" | python3 -m json.tool

```



Response includes `registry_schema_version`, `registry_revision`, and safe lists for capabilities, integrations, runtime features, and presets.



---



## Curl fallback — create session (no API key)



```bash

curl -sS -X POST https://api.krowolf.se/admin/onboarding \

  -H "Cookie: admin_session=…" \

  -H "Content-Type: application/json" \

  -d '{

    "company_name": "Customer Name AB",

    "slug": "customer-slug",

    "timezone": "Europe/Stockholm",

    "language": "sv"

  }'

```



Response includes `tenant_id`, `id` (session_id), `version`. Tenant status is `inactive`.



---



## Curl fallback — activation plan, readiness + activate



```bash

# Activation plan (review step)

curl -sS "https://api.krowolf.se/admin/onboarding/{session_id}/activation-plan" \

  -H "Cookie: admin_session=…" | python3 -m json.tool



# Readiness

curl -sS -X POST "https://api.krowolf.se/admin/onboarding/{session_id}/readiness" \

  -H "Cookie: admin_session=…" \

  -H "Content-Type: application/json" \

  -d '{}'



# Activate (admin session) — use plan_hash from activation-plan response

curl -sS -X POST "https://api.krowolf.se/admin/onboarding/{session_id}/activate" \

  -H "Cookie: admin_session=…" \

  -H "Content-Type: application/json" \

  -d '{

    "reason": "Pilot go-live after readiness review",

    "confirmation_phrase": "customer-slug",

    "version": 3,

    "readiness_check_version": 1,

    "plan_hash": "64-char-sha256-hex-from-activation-plan",

    "acknowledged_warning_ids": ["capability.followups.configured_not_running"]

  }'

```



---



## Legacy script path — `POST /admin/tenants` (deprecated for UI)



> Use only when the panel is unavailable. Creates **active** tenant and returns API key immediately.



```bash

curl -sS -X POST https://api.krowolf.se/admin/tenants \

  -H "X-Admin-API-Key: ADMIN_API_KEY" \

  -H "Content-Type: application/json" \

  -d '{

    "name": "Customer Name AB",

    "slug": "customer-slug",

    "enabled_job_types": ["lead"],

    "allowed_integrations": ["google_mail"],

    "auto_actions": {"lead": false}

  }'

```



Save the returned `api_key` immediately — it cannot be retrieved again.



---



## Post-activation verification



```bash

curl -sS https://api.krowolf.se/pilot/readiness \

  -H "X-API-Key: TENANT_KEY" | python3 -m json.tool



curl -sS -X POST https://api.krowolf.se/verify/TENANT_ID \

  -H "X-Admin-API-Key: ADMIN_API_KEY" \

  -H "Content-Type: application/json" \

  -d '{}'

```



---



## Hand off



- Provide tenant API key securely (if created via separate api-key action or legacy path).

- Confirm scheduler is `paused` until operator enables it.

- Confirm approval queue is empty.

- Brief customer on approval-first flow if preset requires it.



---



## Related runbooks



- `docs/runbooks/customer-offboarding.md`

- `docs/runbooks/oauth-errors.md`

- `docs/chapter-9-inventory.md`

- `docs/PILOT_READINESS_CHECKLIST.md`

