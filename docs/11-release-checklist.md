# Release Checklist

## Code
- [x] Relevant code committed
- [x] No obvious dead paths in MVP flow
- [x] Env variables documented (`env.example`)
- [x] DB setup verified (`docker-compose.yml` + `scripts/create_tables.py`)

## Test
- [x] Automated tests pass — 74/74 (`python -m pytest`)
- [x] Official MVP smoke test documented in README (curl commands, step by step)
- [ ] Gmail integration path verified with live token (requires valid `GOOGLE_MAIL_ACCESS_TOKEN`)

## Docs
- [x] current-state updated
- [x] backlog updated
- [x] handoff updated
- [ ] decisions updated if architecture changes (none in this slice)

## Deployment / operability
- [x] Local start from clean environment documented in README
- [x] Docker path documented and verified (`docker-compose up -d` starts Postgres)
- [x] Health endpoint verified (`GET /` returns `{"status":"ok"}`)
- [x] Demo instructions verified (README smoke test + operator UI at `/ui`)

## Remaining before full release
- [x] UI auth — operator UI sends X-API-Key; key stored in localStorage
- [ ] Gmail OAuth token refresh
- [ ] DB-driven tenant config