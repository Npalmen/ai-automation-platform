# Architecture

## High-level

System is built around a **Job execution model**.

Each Job:

- Has input_data
- Moves through processors
- Produces structured output
- Is persisted and auditable

---

## Core Components

### 1. Orchestrator

Responsible for:

- Running pipeline
- Routing steps
- Handling approval flows
- Skipping steps dynamically

Key logic:

- Skip ACTION_DISPATCH if approval required
- Resume AFTER approval without restarting pipeline

---

### 2. Processors

Each processor:

- Takes Job
- Returns Job
- Adds result to processor_history

Examples:

- intake
- classification
- entity_extraction
- lead
- invoice
- decisioning
- policy
- action_dispatch
- human_handoff

---

### 3. Approval System

Components:

- approval_service
- approval_dispatcher
- approval_engine

Flow:


policy → approval_required → dispatch → await
→ approve → resume → action_dispatch


---

### 4. Action Dispatcher

Executes external actions:

- send_email
- notify_slack
- create_internal_task

Supports:

- success/failure tracking
- fallback handling

---

### 5. Data Model

Job contains:

- job_id
- tenant_id
- job_type
- status
- input_data
- result
- processor_history

---

## Execution Modes

### Auto
→ direct action execution

### Manual Review
→ human required

### Approval
→ pause → resume after decision

---

## Key Design Decisions

- Stateless processors
- Stateful job history
- Deterministic orchestration
- AI only used for decision-making, not control flow

---