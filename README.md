# AI Automation Platform

## Overview

This system is a **multi-tenant AI workflow engine** designed to automate business processes such as:

- Lead handling
- Invoice processing
- Customer inquiries
- Internal workflows

The system combines:

- AI processors
- Deterministic orchestration
- Human-in-the-loop approvals
- Action execution (email, slack, etc.)

---

## Core Concept

Each request becomes a **Job**.

A Job flows through:


INTAKE → CLASSIFICATION → DOMAIN PROCESSORS → POLICY → ACTION / APPROVAL / HANDOFF


---

## Key Features

### AI Processing Pipeline
- Classification (what is this?)
- Entity extraction (what data is inside?)
- Domain processors (lead, invoice, etc.)
- Decisioning (what should happen?)
- Policy (what is allowed?)

---

### Orchestrator (Core Engine)

Handles:

- Step execution
- Dynamic routing
- Error handling
- Audit logging
- Approval gating

---

### Human-in-the-loop

Supports:

- Manual review
- Approval flows (email, slack, dashboard)

---

### Action Execution

Executes:

- Send email
- Notify Slack
- Create internal tasks

---

## Architecture


app/
core/ # config, audit, tenant
domain/workflows/ # models, enums, schemas
workflows/ # orchestrator, processors
integrations/ # adapters (email, slack)
repositories/ # DB layer


---

## Current Status

### Completed
- Multi-tenant system
- Job system
- AI processors
- Orchestrator
- Approval system
- Action dispatcher

### In Progress
- Integrations (real providers)
- UI
- Persistence improvements

---

## Example Flow

### Lead (auto execution)


Lead → classified → scored → policy approves → action executed → completed


### Invoice (manual review)


Invoice → extracted → validation fails → policy → manual_review


### Approval flow


Policy → send_for_approval → approval_dispatch → await approval
→ approve → action_dispatch → completed


---

## Philosophy

- AI decides → system enforces
- Always auditable
- Always overrideable by human
- Scalable across industries

---