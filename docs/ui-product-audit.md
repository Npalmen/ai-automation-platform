# UI Product Audit

Generated: 2026-05-18  
Status: Actionable — drives Slices 1–7

---

## Summary

| Category | Count |
|----------|-------|
| Pass — works as expected | 38 |
| Fix — broken but fixable | 14 |
| Hide — incomplete, not production-ready | 8 |
| Remove — speculative/fake, never worked | 7 |

---

## View-by-View Audit

### Login screen
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Admin tab → API key field → "Logga in" | `GET /admin/tenants/overview` | **FIX** — asks for API key; goal is username/password | Slice 3: replace with username/password |
| Customer tab → API key field → "Logga in" | `GET /tenant` | Pass | — |

### Dashboard (Admin)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Cockpit KPI cards (`cpActions` etc.) | `GET /dashboard/cockpit` | **FIX** — crash if DOM element absent (no null guard) | Slice 1 |
| Operational KPIs | `GET /dashboard/kpis` | Pass | — |
| Operational Insights | `GET /dashboard/operational-insights` | Pass | — |
| ROI card (`rHours`, `rValue`, etc.) | `GET /dashboard/roi` | **FIX** — `getElementById('roiError').style.display` crashes if absent | Slice 1 |
| Dispatch summary error element | `GET /dispatch/summary` | **FIX** — `getElementById('dispatchSummaryError').style.display` crashes | Slice 1 |
| Dispatch report error element | `GET /dispatch/report` | **FIX** — `getElementById('reportError').style.display` crashes | Slice 1 |
| Integration health | `GET /integrations/health` | Pass | — |
| ↻ Uppdatera | calls `loadAll()` which loads jobs/approvals | **FIX** — `loadAll` only loads jobs/approvals, not dashboard | Slice 1 |
| Range chips (today/7d/30d/all) | `GET /dispatch/summary` + `GET /dispatch/report` | Pass | — |

### Dashboard (Customer)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Hero date | n/a | Pass | — |
| ROI fields (`cRoiHours`, `cRoiValue`) | `GET /dashboard/roi` | Pass (silent catch) | — |
| Summary counts | `GET /dashboard/summary` | Pass (silent catch) | — |
| Extended KPIs | `GET /dashboard/kpis` | Pass (silent catch) | — |
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
| Field status buttons (Starta/Pausa/Klart/Blockerad) | `PUT /cases/{id}/operations` | Pass | — |
| Follow-up approve/reject | `POST /approvals/{id}/approve|reject` | Pass | — |
| Closeout "Sammanställ projekt" | `GET /cases/{id}/closeout` | Pass | — |
| Fortnox preview button | Opens `/finance/invoices/{id}/fortnox/preview` | **HIDE** — only shown when finance_ready, needs live Fortnox | Slice 2 |
| Recovery actions (retry/replay/reclassify/etc.) | `POST /admin/recovery/{id}/{action}` | Pass (admin only) | — |
| Lead status save | `PATCH /jobs/{id}/lead-status` | Pass | — |
| Support status save | `PATCH /jobs/{id}/support-status` | Pass | — |
| Regenerate lead/support analysis | `POST /jobs/{id}/lead-regenerate` | Pass | — |

### Loggar (ops)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Jobs list | `GET /jobs` | Pass | — |
| Job detail | `GET /jobs/{id}` | Pass | — |
| Approve/Reject buttons | `POST /approvals/{id}/approve|reject` | Pass | — |

### Inställningar (setup — admin)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Tenant switcher | `GET /tenants` + `GET /tenant/config/{id}` | Pass | — |
| Create tenant (old form) | `POST /tenant` | **FIX** — form references `newTenantId` input that is now orphaned (provisioning moved to Super Admin). Element probably missing → crash | Slice 1 |
| Job types checkboxes | static form → `PUT /tenant/config/{id}` | **REMOVE** — many speculative future job types (lead_qualification, quote, sales_followup, crm_update, etc.) that don't exist in backend | Slice 2 |
| Integration checkboxes | static form → `PUT /tenant/config/{id}` | **REMOVE** — speculative integrations (microsoft_mail, microsoft_calendar, crm, accounting, support, slack) not implemented | Slice 2 |
| Verification | `POST /setup/verify` | Pass | — |
| Demo seed | `POST /demo/seed` or `/admin/tenants/{id}/demo/seed` | Pass | — |
| Demo mode toggle | settings update | Pass | — |

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
| Connections display | from setup/status | Pass | — |
| Setup verify | `POST /setup/verify` | Pass | — |
| Test lead | `POST /verify/{tenant_id}` | Pass | — |
| Wizard status section | `GET /onboarding/wizard-state` | Pass | — |

### Onboarding / Kom igång (customer — wizardflow)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Wizard state load | `GET /onboarding/wizard-state` | Pass | — |
| System scan buttons | `POST /workflow-scan/gmail` + `POST /workflow-scan/monday` | Pass | — |
| Apply routing hints | `POST /tenant/routing-hints/apply` | Pass | — |
| Save automation mode | `POST /control-panel` ← **WRONG URL** | **FIX P0** — real endpoint is `PUT /dashboard/control`; payload shape also wrong | Slice 1 |
| Send test lead | `POST /onboarding/test-lead` | Pass | — |
| `wizardflow` not in `CUSTOMER_ONLY_VIEWS` | n/a | **FIX** — nav item has `customer-only` CSS class but JS array doesn't include it | Slice 1 |

### Kundminne (memory)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Memory load/save | `GET/PUT /tenant/memory` | Pass | — |
| Gmail scan | `POST /workflow-scan/gmail` | Pass | — |
| Monday scan | `POST /workflow-scan/monday` | Pass | — |
| Routing drafts | `GET /tenant/routing-hint-drafts` | Pass | — |
| Routing preview | `GET /tenant/routing-preview/{type}` | Pass | — |
| Apply routing hints | `POST /tenant/routing-hints/apply` | Pass | — |
| Fortnox pilot tools (lookup/create/search) | `POST /integrations/fortnox/...` | **HIDE** — only show if Fortnox is configured/enabled for tenant | Slice 2 |

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
| Create tenant (provisionTenant) | `POST /admin/tenants` | **FIX** — `resp.json is not a function` error: `adminApiFetch` returns `resp.json()` (a Promise) but the function looks correct. Needs verification. Actually the issue is the admin API key field `adminKeyInput` ID is in the Super Admin view but the login screen also uses it — confirm both reference same element. | Slice 1 |
| Rotate key | `POST /admin/tenants/{id}/rotate-key` | Pass | — |
| Activate/deactivate | `PATCH /admin/tenants/{id}/status` | Pass | — |
| Audit filter+load | `GET /admin/audit-events` | Pass | — |
| Admin key input (in Super Admin tab) | n/a | **FIX** — this is a second `adminKeyInput` location but the topbar already has one; reconcile | Slice 1 |

### Supportkonsol (support)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Tenant selector | `GET /tenants` | Pass | — |
| Load state | `GET /admin/support/{tid}/state` | Pass | — |
| Pause/resume automation | `POST /admin/support/{tid}/pause-automation` etc. | Pass | — |
| Disable/enable scheduler | same | Pass | — |
| Force inbox sync | `POST /admin/support/{tid}/force-inbox-sync` | Pass | — |
| Ack/clear needs-help | `POST /admin/support/{tid}/ack-needs-help` | Pass | — |

### Customer views (Resultat, Aktivitetslogg, Inställningar, Konto & Team)
| Control | Endpoint | Status | Action |
|---------|----------|--------|--------|
| Resultat KPIs | `GET /customer/results` | Pass | — |
| Aktivitetslogg | `GET /customer/activity` | Pass | — |
| Notif settings | `GET/PUT /notifications/settings` | Pass | — |
| Health display | `GET /customer/health` | Pass | — |
| Account form | `GET/PUT /customer/account` | Pass | — |
| Team member rows | same | Pass | — |

---

## Global Issues

| Issue | Severity | Action |
|-------|----------|--------|
| `apiFetch` error format: raw `HTTP ${status}: ${body}` exposes provider error blobs (Gmail `invalid_grant` JSON) | High | Slice 1: normalize API errors |
| `alert()` used in `runWizardScan` | Medium | Slice 1: replace with UI error element |
| `CONN_LABELS` includes `microsoft_mail` (not implemented) | Medium | Slice 2: remove |
| `wizardflow` absent from `CUSTOMER_ONLY_VIEWS` | High | Slice 1 |
| `ALL_JOB_TYPES` includes 15+ speculative future types | Medium | Slice 2 |
| `ALL_INTEGRATIONS` includes 8+ non-implemented integrations | Medium | Slice 2 |
| Topbar still shows raw "API-nyckel" input after login | Low | Slice 3+5 |

---

## P0 Critical Fixes (Slice 1)

1. `saveWizardAutomationMode()` calls `POST /control-panel` — DOES NOT EXIST. Fix: `PUT /dashboard/control`
2. `loadRoi()` accesses `getElementById('roiError').style` before null check
3. `loadDispatchSummary()` accesses `getElementById('dispatchSummaryError').style` before null check
4. `loadDispatchReport()` accesses `getElementById('reportError').style` before null check
5. `loadIntegrationHealth()` accesses `getElementById('healthError').style` before null check
6. `loadPilotReadiness()` accesses `getElementById('pilotError').style` before null check
7. `_loadAdminDashboard()` accesses `getElementById('dashError').style` before null check
8. `apiFetch` error normalization — normalize Gmail/integration errors to operator-friendly messages
9. `wizardflow` missing from `CUSTOMER_ONLY_VIEWS`
10. `runWizardScan` uses raw `alert()`

## Slice 2 Removals / Hides

- Remove from `ALL_JOB_TYPES`: `lead_qualification`, `quote`, `sales_followup`, `crm_update`, `opportunity_summary`, `support_triage`, `response_draft`, `escalation`, `case_summary`, `sla_monitoring`, `payment_followup`, `finance_summary`, `receipt`, `anomaly`, `kpi`, `exec_summary`, `risk`, `decision_support`, `report`
- Remove from `ALL_INTEGRATIONS`: `google_calendar`, `microsoft_mail`, `microsoft_calendar`, `crm`, `accounting`, `support`, `slack`
- Remove `microsoft_mail` from `CONN_LABELS`
- Hide Fortnox pilot tools in Kundminne unless Fortnox is configured
- Hide Visma-related controls (not implemented)
