# Production Deployment Guide

## Required environment variables

Set these before starting the server. The app will start without them but key features will be disabled or insecure.

### Critical — security

| Variable | Description | Example |
|----------|-------------|---------|
| `TENANT_API_KEYS` | Optional JSON map of tenant-id → API key for legacy/env tenants. Production may also use DB-backed provisioned tenant API keys. Empty is allowed only when active DB-backed keys exist; otherwise production fails closed. | `{"ACME_AB": "key-abc123", "DEMO": "key-xyz456"}` |
| `ADMIN_API_KEY` | Secret for admin endpoints (`X-Admin-API-Key`). Empty = admin access blocked (fail-closed). | `admin-secret-key-prod` |
| `DATABASE_URL` | PostgreSQL connection string. | `postgresql://user:pass@host:5432/ai_platform` |

### Gmail integration

All four required for OAuth token refresh. Missing any one causes `invalid_grant` on first token expiry.

| Variable | Description |
|----------|-------------|
| `GOOGLE_MAIL_ACCESS_TOKEN` | Current OAuth access token |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | OAuth refresh token |
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_MAIL_USER_ID` | Gmail user ID, usually `me` |

### Monday.com integration

| Variable | Description |
|----------|-------------|
| `MONDAY_API_KEY` | Monday API key |
| `MONDAY_BOARD_ID` | Default board ID (integer) |

### Fortnox integration

| Variable | Description |
|----------|-------------|
| `FORTNOX_ACCESS_TOKEN` | Fortnox OAuth access token |
| `FORTNOX_CLIENT_SECRET` | Fortnox client secret |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `AI Automation Platform` | Shown in health endpoint |
| `ENV` | `dev` | Set to `production` in prod |
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | Bind port |
| `STORAGE_PATH` | `./storage/local_dev` | File storage root |
| `LLM_API_KEY` | — | OpenAI/LLM key for AI classification |
| `LLM_MODEL` | `gpt-4.1-mini` | LLM model name |
| `SLACK_WEBHOOK_URL` | — | Slack notifications |
| `VISMA_ACCESS_TOKEN` | — | Visma integration |

---

## Pre-launch checklist

1. **Configure tenant auth** — use either DB-backed provisioned tenant API keys or non-empty `TENANT_API_KEYS`. Production must not rely on dev-mode tenant fallback.
2. **Set `ADMIN_API_KEY`** — non-empty; used to gate tenant creation, config writes, and admin overview.
3. **Set `DATABASE_URL`** — point to a real PostgreSQL instance (not localhost defaults).
4. **Run DB migrations** — `python scripts/create_tables.py` (idempotent).
5. **Verify `ENV=production`** — disables dev-mode tenant fallback and public OpenAPI/docs.
6. **Create at least one tenant** — `POST /tenant` with `X-Admin-API-Key` header.
7. **Configure Gmail env vars** — all four OAuth fields or none (partial config causes silent failure).
8. **Check "Redo för drift"** — open the UI, navigate to Konfiguration → Redo för drift. All items should be green or yellow before going live.
9. **Run the release gate and smoke check** — `python scripts/run_release_gate_r1.py --verbose`, `python -m pytest`, then `python scripts/smoke_check.py --base-url <url> --expect-production`.
10. **Check the 5-customer launch checklist** — see `docs/13-5-customer-launch-checklist.md`.

---

## Authentication model

| Caller | Header | Grants access to |
|--------|--------|-----------------|
| Tenant user | `X-API-Key: <key>` | `/tenant`, `/jobs`, `/cases`, `/integrations/health`, all tenant-scoped endpoints |
| Admin operator | `X-Admin-API-Key: <key>` | `/tenant` (create), `/tenant/config/{id}` (read/write), `/tenants` (list), `/verify/{id}`, `/admin/tenants/overview`, all-tenant scheduler trigger |
| No header | — | `GET /` (health), `GET /ui` (operator UI HTML only) |

Tenant auth resolves DB-backed hashed API keys first, then falls back to the `TENANT_API_KEYS` env map. When `ENV=production`, missing tenant credentials fail closed. Dev-mode fallback to `X-Tenant-ID` or `TENANT_1001` is local-only.

When `ADMIN_API_KEY` is empty all admin endpoints return 401 (fail-closed).

Admin UI currently stores the admin key in browser localStorage and sends it via `X-Admin-API-Key`. For the 5-customer pilot, protect `/ui` and admin access with network controls such as VPN, IP allowlist, or a trusted operator machine. Treat this as an MVP/pilot auth model, not enterprise SSO.

---

## Production API surface

When `ENV=production`, public FastAPI docs are disabled:

- `/docs`
- `/redoc`
- `/openapi.json`

Use local/dev environments for schema exploration.

---

## Scheduler trigger

`POST /scheduler/run-once` runs scheduler logic across all configured tenants and therefore requires `X-Admin-API-Key`. Tenant API keys can still read their own `GET /scheduler/status`, but cannot trigger all-tenant scheduler work.

---

## Running the server

```bash
# Install dependencies
pip install -r requirements.txt

# Create DB tables (idempotent)
python scripts/create_tables.py

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The operator UI is available at `/ui`. The API is available at `/`.

---

## Docker deployment baseline

Production-compatible container files are included:

```bash
docker build -t ai-automation-platform:release .
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

After the stack is healthy, run:

```bash
python scripts/smoke_check.py --base-url http://127.0.0.1:8000 --expect-production
```

The compose file expects `.env` to contain real secrets. Keep `ADMIN_API_KEY`, tenant API keys, OAuth tokens and database credentials out of git.

---

## CI release gate

GitHub Actions workflow `.github/workflows/release-gate.yml` runs:

- dependency install on Python 3.10
- `python scripts/run_release_gate_r1.py --verbose`
- full `python -m pytest`
- Docker image build
- `docker compose -f docker-compose.prod.yml config`

Use the workflow as the merge gate for `main`.

---

## Error behaviour

- Backend never returns Python stack traces in HTTP responses.
- Exception details are logged server-side (check `uvicorn` / application logs).
- Customer-facing UI shows generic Swedish error messages. Admin UI shows HTTP status codes.
- The "Redo för drift" view shows a live readiness score — bookmark it for on-call reference.

---

## What is NOT in scope for MVP

- HTTPS termination — use a reverse proxy (nginx, Caddy, Traefik) in front.
- Rate limiting — add at the proxy layer.
- Multi-region — single-process, single-database.
- Background worker — the scheduler runs on-demand via `POST /scheduler/run-once`. Wire a cron job or systemd timer to call it.
