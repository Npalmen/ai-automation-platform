# Release Checklist

## Code
- [x] Relevant code committed
- [x] No obvious dead paths in MVP flow
- [x] Env variables documented (`env.example`)
- [x] DB setup verified (`docker-compose.yml` + `scripts/create_tables.py`)

## Test
- [x] Automated tests pass — 141/141 (`python -m pytest`) — zero warnings
- [x] Official MVP smoke test documented in README (curl commands, step by step)
- [ ] Gmail integration path verified with live token (requires valid `GOOGLE_MAIL_ACCESS_TOKEN`)

## Docs
- [x] current-state updated
- [x] backlog updated
- [x] handoff updated
- [x] decisions updated (DEC-001 revised, DEC-004 added)

## Deployment / operability
- [x] Local start from clean environment documented in README
- [x] Docker path documented and verified (`docker-compose up -d` starts Postgres)
- [x] Health endpoint verified (`GET /` returns `{"status":"ok"}`)
- [x] Demo instructions verified (README smoke test + operator UI at `/ui`)
- [x] All 6 DB tables register with `database.Base` and are created by `create_all` on startup

## Completed before full release
- [x] UI auth — operator UI sends X-API-Key; key stored in localStorage
- [x] UI rendering stable — HTML escaping + layout height fix applied
- [x] DB-driven tenant config — `tenant_configs` table + repository + fallback logic
- [x] Gmail OAuth token refresh — refresh on 401, retry once, fail cleanly
- [x] Integration event persistence — real DB row on every `POST /integrations/{type}/execute`
- [x] MVP hardening — removed unauthenticated `/tenant/test` debug route; fixed Pydantic v2 deprecation warnings