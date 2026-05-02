# Production Deployment Guide

## Required environment variables

Set these before starting the server. The app will start without them but key features will be disabled or insecure.

### Critical — security

| Variable | Description | Example |
|----------|-------------|---------|
| `TENANT_API_KEYS` | JSON map of tenant-id → API key. Empty = auth disabled (dev mode only). | `{"ACME_AB": "key-abc123", "DEMO": "key-xyz456"}` |
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

1. **Set `TENANT_API_KEYS`** — non-empty JSON; one entry per customer tenant.
2. **Set `ADMIN_API_KEY`** — non-empty; used to gate tenant creation, config writes, and admin overview.
3. **Set `DATABASE_URL`** — point to a real PostgreSQL instance (not localhost defaults).
4. **Run DB migrations** — `python scripts/create_tables.py` (idempotent).
5. **Verify `ENV=production`** — prevents dev-mode fallbacks.
6. **Create at least one tenant** — `POST /tenant` with `X-Admin-API-Key` header.
7. **Configure Gmail env vars** — all four OAuth fields or none (partial config causes silent failure).
8. **Check "Redo för drift"** — open the UI, navigate to Konfiguration → Redo för drift. All items should be green or yellow before going live.

---

## Authentication model

| Caller | Header | Grants access to |
|--------|--------|-----------------|
| Tenant user | `X-API-Key: <key>` | `/tenant`, `/jobs`, `/cases`, `/integrations/health`, all tenant-scoped endpoints |
| Admin operator | `X-Admin-API-Key: <key>` | `/tenant` (create), `/tenant/config/{id}` (read/write), `/tenants` (list), `/verify/{id}`, `/admin/tenants/overview` |
| No header | — | `GET /` (health), `GET /ui` (operator UI HTML only) |

When `TENANT_API_KEYS` is empty the tenant `get_verified_tenant` dependency accepts any key (dev mode). Set it to non-empty in production to enforce per-tenant auth.

When `ADMIN_API_KEY` is empty all admin endpoints return 401 (fail-closed).

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
