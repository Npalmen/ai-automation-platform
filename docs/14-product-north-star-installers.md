# Product North Star — Installation & Service Companies

## What this platform is

An **AI-powered operational layer** for installation and service companies (electricians, solar installers, HVAC, plumbers, general contractors).

The platform **does not replace** existing tools like Gmail, Monday.com, or Fortnox. Instead, it:

- Reads information from these systems
- Understands the business context
- Automates workflows
- Coordinates processes
- Compiles information
- Reduces administration
- Provides operational overview

The goal: customers continue working in their existing systems while the platform works intelligently in the background.

## Core problem solved

Installation companies commonly suffer from:

- Missed leads and slow response times
- Unstructured workflows and excessive administration
- Duplicate work across systems
- Poor overview of operations
- Slow invoicing and information chaos

This platform eliminates these problems through intelligent automation and coordination between existing systems.

## The end-to-end flow

```
Lead in → AI analysis → Case/project created → Work coordinated →
Project executed → Completion documented → Invoice preparation ready
```

### 1. Lead intake
Via Gmail, forms, customer emails, or integration systems. The platform reads and classifies automatically.

### 2. AI analysis
The system classifies the case, extracts customer information, identifies work type, sets priority, and suggests next steps — all deterministically where possible, with LLM augmentation where configured.

### 3. Case/project structure
Internal structure created: customer linkage, property/project context, activity history, operations workspace.

### 4. Customer communication
AI-generated reply drafts, follow-up suggestions, automated reminders — all **approval-gated** before external sends.

### 5. Workflow coordination
Monday updates, responsible person notifications, status tracking, bottleneck identification, reminders — via existing integration adapters.

### 6. Project execution (light layer)
Technicians and admins can: add notes, upload images, mark status, report materials/hours, document work. This is **lightweight** — not a full dispatch suite or complete ERP.

### 7. Completion
When a project is marked complete: AI summarizes work, documents are compiled, invoice preparation is generated, materials/hours organized.

### 8. Fortnox sync (preparation only)
The system sends prepared documents, creates invoice drafts via preview/export with approval gates. **The platform does not perform bookkeeping** — it prepares the documents.

## AI in the background (v1 definition)

In the current product version, "AI in the background" means:

1. **Structured operational insights** — deterministic rule-based signals that surface what needs attention across leads, support cases, operations, and finance preparation. Displayed in dashboard and daily digest.
   - Implementation: `app/insights/engine.py` — `get_operational_insights()` produces tenant-scoped insight rows (type, severity, title, detail, job_id, pipeline_stage, evidence).
   - Rule packs cover: stale leads, hot leads pending, missing customer info, email/dispatch approvals waiting, support escalation, work order blocked, delivery incomplete, underlag ready, fortnox export pending, stale active cases.
   - Exposed via `GET /dashboard/operational-insights` and wired into daily digest emails.

2. **Pipeline intelligence** — classification, entity extraction, lead/support analysis, offer drafts, and question generation via the existing processor pipeline (deterministic rules + optional LLM augmentation).
   - Lead layer: `app/lead/` — lead_type, intent, urgency, scoring (0–100), missing info, offer drafts, next best action, tenant-aware service filtering and geographic scoring.
   - Support layer: `app/support/` — ticket_type, category, urgency, sentiment, priority scoring, response drafts, SLA rules.
   - Both layers are deterministic by default; LLM augments classification/extraction when `LLM_API_KEY` is configured.

3. **Approval-gated actions** — the AI proposes, the human approves. No unsupervised customer-facing communication.
   - All email sends (customer replies, internal handoffs) are intercepted and held for operator approval when automation policy is manual/semi.
   - Controlled dispatch to external systems (Monday, Fortnox) follows the same approval gate.

4. **SLA monitoring** — deterministic SLA breach detection for unanswered leads, with internal reminder creation via the scheduler.
   - Implementation: `app/insights/sla_reminders.py` — `find_sla_breaches()` and `run_sla_reminder_pass()`.
   - Creates internal approval records as reminders (no customer-facing email without operator approval).
   - Exposed via `GET /dashboard/sla-breaches` and integrated into the scheduler.

5. **Dashboard KPIs** — extended operational KPIs beyond basic job counts.
   - Implementation: `app/insights/engine.py` — `compute_dashboard_kpis()`.
   - KPIs: email approval queue, dispatch approval queue, waiting on customer, underlag ready, active ops cases.
   - Exposed via `GET /dashboard/kpis` and displayed in both admin and customer dashboards.

A conversational chat assistant is **not** part of the current product milestone. It may be added as a post-MVP enhancement.

## What the product is NOT

- Not a full ERP system
- Not a bookkeeping system (preparation only)
- Not a payroll system
- Not an advanced dispatch/scheduling suite
- Not a platform with 100 integrations
- Not enterprise-complexity software

## Target experience

When a customer uses the platform correctly, they should feel:

- Less stress
- Better control
- Faster administration
- Fewer missed leads
- Better structure
- Easier follow-up

Without having to replace their entire operation.

## Technical anchor

- Backend-first: FastAPI + PostgreSQL + SQLAlchemy
- Frontend: vanilla single-file HTML/CSS/JS (no React/build toolchain) — DEC-005 scope lock
- Multi-tenant with per-tenant API key auth
- Integrations: Gmail (live), Monday (live), Fortnox (live read + approval-gated write)
- All external writes are approval-gated or controlled-dispatch with idempotency guards
- See `docs/05-current-state.md` for full implementation status
