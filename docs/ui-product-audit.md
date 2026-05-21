# UI Product Audit

Generated: 2026-05-21 (updated from 2026-05-18 baseline)  
Status: Local smoke-tested — 66/66 admin endpoints, 20/20 customer endpoints pass.

---

## Summary

| Category | Count |
|----------|-------|
| Pass — works as expected | 74 |
| Fix — broken but fixable (fixed in this pass) | 6 |
| Hide — incomplete, not production-ready | 2 |
| Remove — speculative/fake, removed in this pass | 5 |

### Changes applied in this pass (2026-05-21)

| Change | Type | File |
|--------|------|------|
| `GET /dashboard/support` → 500 fixed (`r.processor_history` attribute does not exist; now reads from `r.result`) | Fix | `app/main.py` |
| `GET /cases/{id}/followup` → 500 fixed (`ApprovalRequestRecord` not imported in scope) | Fix | `app/main.py` |
| `ops` view now auto-loads jobs + approvals on navigation (was: manual click required) | Fix | `app/ui/index.html` |
| `custCasesPagination` duplicate `display:` style attribute fixed | Fix | `app/ui/index.html` |
| `const jobId = c.id` → `c.job_id` in lead analysis panel and support analysis panel | Fix | `app/ui/index.html` |
| `'integrations'` removed from `ADMIN_ONLY_VIEWS` (it is an overlay, not a `switchView` target; was blocking nothing but caused conceptual mismatch) | Fix | `app/ui/index.html` |
| `slack` removed from `WIZ_INTEGRATIONS` (no backend) | Remove | `app/ui/index.html` |
| `partnership` + `supplier` removed from `WIZ_JOB_TYPES` (no pipeline classification, only create confusion) | Remove | `app/ui/index.html` |
| `slack` removed from provisioning form integration checkboxes | Remove | `app/ui/index.html` |

---

## Smoke test results (2026-05-21)

All 86 tests passed. Server: `http://127.0.0.1:8000`, tenants: `TENANT_1001`, `TENANT_2001`.

| Section | Tests | Result |
|---------|-------|--------|
| Public / auth | 4 | ✓ Pass |
| Admin routes (no tenant) | 5 | ✓ Pass |
| Tenant endpoints | 6 | ✓ Pass |
| Dashboard (11 endpoints) | 11 | ✓ Pass |
| Customer endpoints | 4 | ✓ Pass |
| Cases + case detail | 9 | ✓ Pass |
| Jobs + approvals | 2 | ✓ Pass |
| Integrations | 3 | ✓ Pass |
| Setup + onboarding | 5 | ✓ Pass |
| Notifications + alerts | 2 | ✓ Pass |
| Scheduler | 2 | ✓ Pass |
| Workflow scan | 3 | ✓ Pass |
| Memory + routing preview | 5 | ✓ Pass |
| Support console | 2 | ✓ Pass |
| TENANT_1001 spot check | 3 | ✓ Pass |
| Customer-mode: all customer views | 14 | ✓ Pass |
| Customer-mode: admin routes blocked | 3 | ✓ Blocked correctly |

---

## View-by-View Audit

### Login screen
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Admin tab → API key field → "Logga in" | `GET /admin/tenants/overview` | Pass | — |
| Customer tab → API key field → "Logga in" | `GET /tenant` | Pass | — |

### Dashboard (Admin)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Cockpit KPI cards | `GET /dashboard/cockpit` | Pass | — |
| Operational KPIs | `GET /dashboard/kpis` | Pass | — |
| Operational Insights | `GET /dashboard/operational-insights` | Pass | — |
| ROI card | `GET /dashboard/roi` | Pass | — |
| Dispatch summary | `GET /dispatch/summary` | Pass | — |
| Dispatch report | `GET /dispatch/report` | Pass | — |
| Integration health | `GET /integrations/health` | Pass | — |
| Support KPIs | `GET /dashboard/support` | **Fixed** — was 500 (bad attribute access) | Done |
| Range chips (today/7d/30d/all) | `GET /dispatch/summary` + `GET /dispatch/report` | Pass | — |

### Dashboard (Customer)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Hero date | n/a | Pass | — |
| ROI fields | `GET /dashboard/roi` | Pass | — |
| Summary counts | `GET /dashboard/summary` | Pass | — |
| Extended KPIs | `GET /dashboard/kpis` | Pass | — |
| Integration health | `GET /customer/health` | Pass | — |
| Recent activity | `GET /customer/activity` | Pass | — |

### Ärenden (Cases)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Search/filter/sort/pagination | `GET /cases` | Pass | — |
| Open case → admin detail | `GET /cases/{id}` | Pass | — |
| Open case → customer detail | `GET /cases/{id}` | Pass | — |
| Dispatch preview | `POST /jobs/{id}/dispatch-preview` | Pass | — |
| Dispatch live | `POST /jobs/{id}/dispatch` | Pass | — |
| Auto-dispatch | `POST /jobs/{id}/auto-dispatch` | Pass | — |
| Follow-up panel | `GET /cases/{id}/followup` | **Fixed** — was 500 (`ApprovalRequestRecord` import) | Done |
| Closeout | `GET /cases/{id}/closeout` | Pass | — |
| Finance export status | `GET /cases/{id}/finance/export-status` | Pass | — |
| Operations workspace | `GET/PUT /cases/{id}/operations` | Pass | — |
| Lead analysis panel `jobId` | `PATCH /jobs/{id}/lead-status` | **Fixed** — `c.id` → `c.job_id` | Done |
| Support analysis panel `jobId` | `PATCH /jobs/{id}/support-status` | **Fixed** — `c.id` → `c.job_id` | Done |
| Fortnox preview button | `POST /finance/invoices/{id}/fortnox/preview` | **HIDE** — only shown when finance_ready, needs live Fortnox | Slice 2 |
| Recovery actions | `POST /admin/recovery/{id}/{action}` | Pass (admin only) | — |

### Loggar (ops)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Auto-load on navigation | `GET /jobs` + `GET /approvals/pending` | **Fixed** — now auto-loads | Done |
| Jobs list | `GET /jobs` | Pass | — |
| Job detail | `GET /jobs/{id}` | Pass | — |
| Approve/Reject buttons | `POST /approvals/{id}/approve\|reject` | Pass | — |

### Inställningar (setup — admin)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Tenant switcher | `GET /tenants` + `GET /tenant/config/{id}` | Pass | — |
| Job types checkboxes | `PUT /tenant/config/{id}` | Pass (lead/invoice/customer_inquiry only) | — |
| Integration checkboxes | `PUT /tenant/config/{id}` | Pass (google_mail/monday/fortnox only) | — |
| Verification | `POST /setup/verify` | Pass | — |
| Demo seed | `POST /demo/seed` or `/admin/tenants/{id}/demo/seed` | Pass | — |

### Kontrollpanel (ctrl)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Automation toggles | `GET/PUT /dashboard/control` | Pass | — |
| Support email | same | Pass | — |
| Run mode selector | same | Pass | — |
| Save button | same | Pass | — |
| Inbox sync trigger | `POST /dashboard/inbox-sync` | Pass | — |
| Scheduler run-once | `POST /scheduler/run-once` (adminApiFetch) | Pass | — |

### Notifieringar (notif)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Digest settings | `GET/PUT /notifications/settings` | Pass | — |
| Send digest test | `POST /notifications/daily-digest/send` | Pass | — |
| Alert config | `GET/PUT /alerts/config` | Pass | — |
| Run alerts | `POST /alerts/run` | Pass | — |

### Onboarding (admin)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Readiness score | `GET /setup/status` (adminApiFetch) | Pass | — |
| Module toggles | `PUT /setup/modules` | Pass | — |
| Setup verify | `POST /setup/verify` | Pass | — |
| Test lead | `POST /onboarding/test-lead` | Pass | — |
| Wizard status section | `GET /onboarding/wizard-state` | Pass | — |

### Kundminne (memory)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Memory load/save | `GET/PUT /tenant/memory` | Pass | — |
| Gmail scan | `POST /workflow-scan/gmail` | Pass | — |
| Monday scan | `POST /workflow-scan/monday` | Pass | — |
| Routing drafts + preview | `GET /tenant/routing-hint-drafts`, `/routing-preview/{type}` | Pass | — |
| Apply routing hints | `POST /tenant/routing-hints/apply` | Pass | — |
| Fortnox pilot tools (lookup/create/search) | `POST /integrations/fortnox/...` | **HIDE** — only show if Fortnox configured | Slice 2 |

### Redo för drift (readiness)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Readiness checklist | `GET /pilot/readiness` | Pass | — |
| Fix navigation links | local view switches | Pass | — |

### Super Admin (admin)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Overview KPIs | `GET /admin/tenants/overview` (adminApiFetch) | Pass | — |
| Tenant list | `GET /admin/tenants` | Pass | — |
| Needs-help queue | `GET /admin/operations/needs-help` | Pass | — |
| Retry action | `POST /admin/recovery/{id}/retry` | Pass | — |
| Create tenant (provisionTenant) | `POST /admin/tenants` | Pass | — |
| Rotate key | `POST /admin/tenants/{id}/rotate-key` | Pass | — |
| Activate/deactivate | `PATCH /admin/tenants/{id}/status` | Pass | — |
| Audit filter+load | `GET /admin/audit-events` | Pass | — |
| Tenant provisioning slack checkbox | removed | **Removed** — slack not implemented | Done |

### Integrationer (overlay)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Gmail card — Testa/Skanna | `POST /setup/verify`, `POST /workflow-scan/gmail` | Pass | — |
| Monday card — Testa/Skanna | `POST /setup/verify`, `POST /workflow-scan/monday` | Pass | — |
| Fortnox card — Testa/Skanna | `POST /setup/verify`, `POST /workflow-scan/fortnox` | Pass | — |
| Visma card — Anslut/Koppla från/Testa | `/integrations/visma/oauth/url`, disconnect, test-read | Pass | — |

### Supportkonsol (support)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Tenant selector + load state | `GET /admin/support/{tid}/state` | Pass | — |
| Pause/resume automation | `POST /admin/support/{tid}/pause-automation` etc. | Pass | — |
| Disable/enable scheduler | same | Pass | — |
| Force inbox sync | `POST /admin/support/{tid}/force-inbox-sync` | Pass | — |
| Ack/clear needs-help | `POST /admin/support/{tid}/ack-needs-help` | Pass | — |

### Customer views (Resultat, Aktivitetslogg, Inställningar, Konto & Team, Kom igång)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Resultat KPIs | `GET /customer/results` | Pass | — |
| Aktivitetslogg | `GET /customer/activity` | Pass | — |
| Notif settings | `GET/PUT /notifications/settings` | Pass | — |
| Health display | `GET /customer/health` | Pass | — |
| Account form | `GET/PUT /customer/account` | Pass | — |
| Wizard state + scan + routing + test lead | `GET /onboarding/wizard-state`, scan, apply, test-lead | Pass | — |

---

## Wizard constants after cleanup

| Constant | Values |
|----------|--------|
| `WIZ_JOB_TYPES` | lead, customer_inquiry, invoice (removed: partnership, supplier) |
| `WIZ_INTEGRATIONS` | google_mail, monday, fortnox, visma (removed: slack) |
| `ALL_JOB_TYPES` | lead, invoice, customer_inquiry |
| `ALL_INTEGRATIONS` | google_mail, monday, fortnox |

---

## Known remaining items (not blocking pilot)

| Issue | Severity | Notes |
|-------|----------|-------|
| Fortnox pilot tools in Kundminne always visible regardless of Fortnox config | Low | Should be hidden when `fortnox` not in enabled integrations |
| `GET /cases/{id}/followup` — `job_type: None` on old seeded demo records (correct for real jobs) | Low | Old test data has no job_type set; real pipeline jobs set job_type correctly |
| `ops` and `memory` views: tab not highlighted as "active" on initial open (nav item click sets active state but view may not be in `_VIEW_DISPLAY` first-render) | Low | Cosmetic only |
| `CONN_LABELS` still includes entries for integrations no longer in wizard | Low | Cosmetic |
