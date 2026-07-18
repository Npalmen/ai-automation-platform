# Testing and Release

> Governed by `docs/00-master-plan.md`.
> Historical test strategy and release checklists are in `docs/archive/legacy-10-test-strategy.md`, `docs/archive/legacy-11-release-checklist.md`, `docs/archive/legacy-12-production-guide.md`, `docs/archive/legacy-13-5-customer-launch-checklist.md`.
> **Live verification plan (first pilot go-live):** see `docs/10-live-verification-plan.md`.

---

## Local test command

```bash
# Full test suite
python -m pytest

# Quiet mode (faster output)
python -m pytest --tb=no -q
```

**Note:** `httpx` must be installed for the test client to work. It is in `requirements.txt`.
Run `pip install -r requirements.txt` if tests fail with `ModuleNotFoundError: No module named 'httpx'`.

Record the pass count in `docs/01-current-truth.md` after each run.

**Verified 2026-07-16:** Python 3.14.3 — 3265 passed, 0 failed, 4 warnings, ~12s (full suite). R1 release gate: regression 513 + e2e 155 passed (~5.3s). Visma focused set: 64 passed.

### Kapitel 12 Slice 1 + 2 verification

```bash
python scripts/kapitel12_slice1_verify.py
python scripts/kapitel12_slice2_verify.py
python scripts/kapitel12_perf_baseline.py
python -m pytest tests/test_kapitel12_backup_offsite.py tests/test_kapitel12_incident_drills.py -q
```

Offsite backup on pilot server (example):

```bash
export OFFSITE_BACKUP_DEST_DIR=/mnt/offsite/krowolf-backups   # separate mount
export OFFSITE_BACKUP_COMMAND="python3 /opt/krowolf/scripts/offsite_backup_upload.py"
export OFFSITE_STATUS_FILE=/opt/krowolf/storage/status/offsite_status.json
bash /opt/krowolf/scripts/backup_postgres.sh
bash /opt/krowolf/scripts/restore_from_offsite_rehearsal.sh
```

Live performance against running server:

```bash
export K12_PERF_BASE_URL=http://127.0.0.1:8000
python scripts/kapitel12_perf_baseline.py
```

Reports: `scripts/kapitel12_slice1_report.json`, `scripts/kapitel12_slice2_report.json`, `scripts/kapitel12_perf_report.json`.

### Kapitel 12 Slice 3 verification

```bash
python scripts/kapitel12_slice3_verify.py
```

Reports: `scripts/kapitel12_slice3_report.json`, `scripts/kapitel12_browser_report.json`.

**Browser matrix (pilot):** `docs/runbooks/kapitel12-browser-matrix.md` — env `/opt/krowolf/.env.browser-test`; per-role CDP via `kapitel12_browser_pilot_verify.py`.

**Verified 2026-07-18:** Security bundle 196 passed; full suite **3586 passed / 0 failed**; frontend gates PASS; release **CONDITIONAL GO** (authenticated browser matrix pending — see `docs/kapitel-12-release-notes.md`, `docs/kapitel-12-slice3-legacy-parity.md`).

### Kapitel 11 security regression gate

Run after any change touching auth, admin routes, sessions, OAuth, or operator surfaces:

```bash
python -m pytest tests/test_admin_security_contracts.py tests/test_admin_cross_tenant_security.py tests/test_security_secret_scan.py tests/test_recovery_actions.py tests/test_alerting.py tests/test_admin_alerts.py tests/test_admin_auth.py tests/test_admin_session.py tests/test_tenant_isolation_http.py -q
```

Optional local E2E (API server running):

```bash
python scripts/kapitel11_security_e2e_verify.py
```

Inventory and runbook: `docs/security/kapitel-11-inventory.md`, `docs/runbooks/security-hardening.md`.

### Core intelligence evals

```bash
python -m pytest tests/test_core_intelligence_quality.py -q
```

Local deterministic evals for Swedish installation-company classification,
qualification, missing info, risk/do-not-touch, customer reply, and
approval/routing behavior. No live credentials or external APIs required.

### Service profile pipeline evals

```bash
# All four targeted suites for local final spurt
python -m pytest tests/test_service_profile_pipeline.py -q
python -m pytest tests/test_customer_reply_quality.py -q
python -m pytest tests/test_tenant_routing_hints.py -q
python -m pytest tests/test_local_golden_path.py -q

# All at once
python -m pytest tests/test_service_profile_pipeline.py tests/test_customer_reply_quality.py tests/test_tenant_routing_hints.py tests/test_local_golden_path.py -q
```

Covers:
- Service profile selection wired into lead_analyzer_processor and support_analyzer_processor
- Profile-specific question message in customer auto-reply
- Risk/high-risk safe acknowledgement behavior
- Tenant routing hint and schema overrides
- Local golden path scenarios (EV charger, solar, debt collection, electrical fault, tenant routing)

### Pilot transition rehearsal (production, read-only)

```bash
# On production server — no writes
python3 /tmp/run_internal_demo_rehearsal_prod.py
```

See `docs/PILOT_TRANSITION.md` Part A for results and demo narrative.

---

```bash
python -m pytest tests/test_root_routing.py tests/test_production_hardening.py -q
```

Covers:
- `GET /` returns public health payload for API host.
- `GET /health` returns HTTP 200 with `status`, `app_name`, and `env`.
- `GET /health` does not expose secret-like config keys.
- App/UI host and `/ui` return HTML for the Internal Operator Console.
- Production docs URLs remain disabled via `_openapi_urls_for()`.

---

## Release gate command

```bash
# Full R1 release gate (regression + E2E pilot flow)
python -m scripts.run_release_gate_r1

# Or with verbose output
python scripts/run_release_gate_r1.py --verbose

# Single phase only
python -m scripts.run_release_gate_r1 --phase regression
python -m scripts.run_release_gate_r1 --phase e2e
```

---

## Smoke check command

```bash
# Basic production smoke check
python scripts/smoke_check.py --base-url <BASE_URL> --expect-production

# With admin surface check
python scripts/smoke_check.py --base-url <BASE_URL> --expect-production --admin-api-key <ADMIN_API_KEY>

# With tenant surface check
python scripts/smoke_check.py --base-url <BASE_URL> --tenant-api-key <TENANT_API_KEY>
```

---

## DB setup (before first start)

```bash
# Verify database connection
python -m scripts.test_db_connection
# Expected: DB OK: 1

# Create tables (idempotent)
python scripts/create_tables.py
```

---

## Local development start

```bash
# Start backend (auto-reload)
uvicorn app.main:app --reload

# Verify
curl http://localhost:8000/
# Expected: {"status":"ok","app_name":"AI Automation Platform","env":"dev"}

curl http://localhost:8000/health
# Expected: {"status":"ok","app_name":"AI Automation Platform","env":"dev"}

# Open UI
# http://localhost:8000/ui
```

---

## CI gate (GitHub Actions)

File: `.github/workflows/release-gate.yml`

Steps:
1. Install dependencies: `pip install -r requirements.txt`
2. Run release gate: `python scripts/run_release_gate_r1.py --verbose`
3. Run full test suite: `python -m pytest`
4. Build Docker image: `docker build -t ai-automation-platform:release .`
5. Validate prod compose: `docker compose -f docker-compose.prod.yml config`

---

## Production checks

### Pre-launch checklist (run before every pilot go-live)

- [ ] `TENANT_API_KEYS` or DB-backed tenant keys configured — production must not rely on dev-mode fallback.
- [ ] `ADMIN_API_KEY` is non-empty.
- [ ] `DATABASE_URL` points to a real PostgreSQL instance.
- [ ] `ENV=production` is set.
- [ ] `GET /health` returns HTTP 200 with `status: ok` after deploy.
- [ ] `python scripts/create_tables.py` run (idempotent).
- [ ] At least one tenant provisioned.
- [ ] Gmail env vars configured (all four for refresh, or none — partial fails on first expiry).
- [ ] Monday API key and board ID configured.
- [ ] Release gate passes: `python scripts/run_release_gate_r1.py --verbose`
- [ ] Full test suite passes: `python -m pytest`
- [ ] Docker image builds: `docker build -t ai-automation-platform:release .`
- [ ] Smoke check passes: `python scripts/smoke_check.py --base-url <url> --expect-production`
- [ ] "Redo för drift" view in UI shows green or documented yellow for pilot tenant.
- [ ] `GET /admin/tenants/overview` shows no critical errors.
- [ ] Backup cron is configured and at least one backup has been completed.
- [ ] Restore rehearsal completed within the past 30 days.

---

## What must pass before first customer

The following gate criteria must all be green before pilot go-live:

1. All unit and integration tests pass (`python -m pytest`).
2. R1 release gate passes (`python -m scripts.run_release_gate_r1`).
3. Production smoke check passes (`scripts/smoke_check.py --expect-production`).
4. Pilot readiness at green: `GET /pilot/readiness` returns `ready`.
5. Integration health not error: `GET /integrations/health` returns `healthy` or `warning` (not `error`).
6. Approval flow end-to-end verified (create job → awaiting_approval → approve → completed).
7. Gmail inbox sync verified (send test mail → case created).
8. No critical rows in needs-help queue.
9. Named support owner confirmed for pilot tenant.

---

## Golden path smoke test (manual, after local start)

Run after `uvicorn app.main:app --reload` with `TENANT_API_KEYS` configured:

**Step 1** — Create job with forced approval:
```bash
curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{
    "tenant_id": "TENANT_1001",
    "job_type": "lead",
    "input_data": {
      "subject": "Test lead",
      "message_text": "Interested in your services.",
      "sender_name": "Test User",
      "sender_email": "test@example.com",
      "force_approval_test": true
    }
  }'
```
Expected: `"status": "awaiting_approval"`. Note `job_id`.

**Step 2** — Check pending approval:
```bash
curl -s http://localhost:8000/approvals/pending -H "X-API-Key: key-abc123"
```
Expected: `{"items": [...], "total": 1}`. Note `approval_id`.

**Step 3** — Approve (body `{}` is required):
```bash
curl -s -X POST http://localhost:8000/approvals/<approval_id>/approve \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-abc123" \
  -d '{}'
```
Expected: `"status": "completed"` (or `"failed"` if no Gmail credentials).

**Step 4** — Inspect:
```bash
curl -s http://localhost:8000/jobs/<job_id>/actions -H "X-API-Key: key-abc123"
curl -s http://localhost:8000/audit-events -H "X-API-Key: key-abc123"
```

---

## How to record verified status

After running tests or checks, update `docs/01-current-truth.md`:

1. Find the relevant row in the Test status or Existing integrations tables.
2. Change `Unverified` to the actual result with date.
3. Note the test count if running the full suite.
4. If a new sharp edge or inconsistency is found, add it to the Known inconsistencies section.

---

## Docker deployment

```bash
# Build production image
docker build -t ai-automation-platform:release .

# Start production stack (requires .env with real secrets)
docker compose -f docker-compose.prod.yml up -d --build

# Check health
docker compose -f docker-compose.prod.yml ps

# Post-start smoke check
python scripts/smoke_check.py --base-url http://127.0.0.1:8000 --expect-production
```

---

## Environment variables (required for production)

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `ADMIN_API_KEY` | Yes | Empty = admin access blocked (fail-closed) |
| `TENANT_API_KEYS` | Conditional | JSON map; may be empty if DB-backed keys are provisioned |
| `ENV` | Yes | Set to `production` |
| `GOOGLE_MAIL_ACCESS_TOKEN` | Gmail | All four required for token refresh |
| `GOOGLE_OAUTH_REFRESH_TOKEN` | Gmail | |
| `GOOGLE_OAUTH_CLIENT_ID` | Gmail | |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Gmail | |
| `GOOGLE_MAIL_USER_ID` | Gmail | Usually `me` |
| `MONDAY_API_KEY` | Monday | |
| `MONDAY_BOARD_ID` | Monday | Integer |
| `FORTNOX_ACCESS_TOKEN` | Fortnox | |
| `FORTNOX_CLIENT_SECRET` | Fortnox | |
| `LLM_API_KEY` | Optional | OpenAI key for AI classification; falls back to deterministic without it |
| `LLM_MODEL` | Optional | Default: `gpt-4.1-mini` |

---

## No markdown/docs linter configured

No `package.json`, `pyproject.toml` with markdown lint, `ruff.toml`, or `setup.cfg` with markdown linting was found in the repository. No docs lint was run in this session. If a linter is added in the future, document the command here.
