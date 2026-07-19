# Gmail soak log — T_NIKLAS_DEMO_001 (intern pilot)

> Secret-free operational log for the 7-day Gmail soak.
> Baseline: `storage/status/gmail_soak_baseline.json`
> Daily reports: `storage/status/gmail_soak/day_XX_YYYY-MM-DD.json`

## Soak policy (locked)

| Rule | Value |
|------|-------|
| Tenant | `T_NIKLAS_DEMO_001` |
| Label / query | `label:krowolf-demo-niklas is:unread` |
| Credential | `tenant_oauth` only — no Playground / `platform_env` |
| Scheduler | **paused** — manual scans only |
| Gmail send | **disabled** — approval-first; no outbound Gmail |
| Scopes used by Krowolf | `gmail.readonly`, `gmail.modify` only |
| Stored Google grant | May include legacy `gmail.send` + `spreadsheets` from prior account consent — **do not invoke** |

## Scope note (2026-07-19)

Google token grant for `niklas.palm@sol-f.se` includes older scopes (`gmail.send`, `spreadsheets`) from historical consent. Pilot OAuth request uses minimal scopes (`readonly` + `modify`). Krowolf must not call send or Sheets APIs during soak.

**Before first external pilot customer:** run clean re-consent with scope-minimal GCP OAuth client (see backlog).

---

## Day 0 — baseline (2026-07-19)

- Tenant OAuth verified: connect, test-read, refresh, dry-run PASS
- Baseline: `/opt/krowolf/storage/status/gmail_soak_baseline.json`
- OAuth cleanup: 2 expired unconsumed states removed; 0 remaining unconsumed
- Email metadata backfilled (`email_domain=sol-f.se`) via Gmail profile API
- Scheduler: `paused` (unchanged)
- First live scan: **blocked** — 2 unread in label, both duplicates (0 new candidates; need 3–5)

### Baseline counts

| Metric | Value |
|--------|-------|
| jobs_total | 17 |
| pending approvals | 8 |
| operator alerts (open) | 16 |
| incidents | 0 |
| integration_errors (failed events) | 11 (historical) |
| credential_source | tenant_oauth |
| token expires_at | set |
| backup | success, offsite verified 2026-07-19 |

---

## Day 2 — post-stabilization clean baseline (2026-07-20)

Stabilization chapter completed. Operational data reset; soak may proceed.

| Metric | Value |
|--------|-------|
| jobs | 0 |
| approvals | 0 |
| tenant alerts (open) | 0 |
| incidents | 0 |
| integration_events | 0 |
| audit_events | 1 (reset summary) |
| credential_source | tenant_oauth |
| scheduler | paused |
| backup | success, offsite verified |
| baseline report | `/opt/krowolf/storage/status/niklas_live_clean_baseline.json` |
| pre-clean archive | `/opt/krowolf/storage/status/pre_live_niklas_archive.json` |
| **ready_for_soak_day_1** | **true** (live scan still needs 3–5 new unread labeled messages) |

---

## Day 1 (2026-07-19)

- Daily report: `/opt/krowolf/storage/status/gmail_soak/day_01_2026-07-19.json`
- **Tenant whitelist cleanup** executed — only `T_NIKLAS_DEMO_001` remains (6 tenants removed)
- Backup before cleanup: `ai_platform_2026-07-19-214638` (offsite verified)
- Live scan: **not run** (awaiting 3–5 new unread labeled messages)
- Recommendation: **fortsätt manuellt** — add test mail, then `pilot_gmail_soak_first_scan.py`

---

## Daily checklist (operator)

1. Confirm scheduler still `paused`
2. Add test emails to `krowolf-demo-niklas` if running live scan
3. Run `pilot_gmail_soak_first_scan.py` (live) OR dry-run probe only
4. Run `pilot_gmail_soak_daily.py <day>`
5. Review `/ops` jobs + approvals; no unexpected sends

## Scripts

| Script | Purpose |
|--------|---------|
| `pilot_gmail_soak_baseline.py` | Day-0 baseline |
| `pilot_gmail_soak_daily.py` | Daily secret-free report |
| `pilot_gmail_soak_first_scan.py` | First live scan (min 3 new messages) |
| `pilot_oauth_cleanup_states.py` | Remove expired/superseded OAuth states |
| `pilot_oauth_backfill_email.py` | Fill credential metadata email |
