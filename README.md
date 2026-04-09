# AI Automation Platform

## Overview

AI Automation Platform är en backend-first, multi-tenant plattform för att automatisera företagsprocesser med hjälp av AI, regler och integrationsflöden.

Systemet tar emot inkommande ärenden (jobs), klassificerar dem, extraherar data, tillämpar policy, kräver approval vid behov och exekverar åtgärder via integrationer.

---

## Current Status

Projektet har en fungerande backend-kärna med:

* FastAPI API
* PostgreSQL persistence
* Multi-tenant via X-Tenant-ID
* Workflow/orchestrator
* AI-processorer
* Approval flow (pause/resume)
* Action execution
* Audit logging
* Gmail integration (testad)

👉 Se aktuell status:

* docs/05-current-state.md
* docs/08-handoff.md

---

## Repository Structure

app/                # Core backend (API, workflows, integrations)
docs/               # Source of truth (product, scope, architecture, etc.)
docs/archive/       # Legacy documentation (read-only)
tests/              # Test suite
scripts/            # Utility scripts
docker-compose.yml  # Local environment setup

---

## Quick Start (Local Development)

### Requirements

* Python 3.10+
* PostgreSQL
* (Optional) Docker

### Installation

pip install -r requirements.txt

### Environment Setup

Create a .env file with required configuration (database, API keys, etc.).

### Start Database (if not running locally)

docker-compose up -d

### Run Backend

uvicorn app.main:app --reload

### Verify Server

Open:
http://localhost:8000/

---

## Smoke Test (MVP Flow)

After starting the server:

1. Create a job
   POST /jobs

2. List jobs
   GET /jobs

3. Check pending approvals
   GET /approvals/pending

4. Approve a job
   POST /approvals/{id}/approve

5. Verify actions and audit logs
   GET /jobs/{job_id}/actions
   GET /audit-events

---

## Core MVP Flow

The official MVP flow:

1. Job intake
2. Classification
3. Entity extraction
4. Decisioning / policy
5. Approval (if required)
6. Resume workflow
7. Execute action (e.g. Gmail)
8. Audit logging

---

## API Overview

### Core

* POST /jobs
* GET /jobs
* GET /jobs/{job_id}

### Approvals

* GET /approvals/pending
* POST /approvals/{id}/approve
* POST /approvals/{id}/reject

### Actions

* GET /jobs/{job_id}/actions

### Integrations

* GET /integrations
* POST /integrations/{type}/execute

### Audit

* GET /audit-events

---

## Documentation (Source of Truth)

Start here:

* docs/02-mvp-scope.md
* docs/03-system-architecture.md
* docs/05-current-state.md
* docs/06-backlog.md
* docs/07-decisions.md
* docs/08-handoff.md

---

## Working Model

* Development is done in vertical slices
* The repository is the source of truth, not chat history
* Docs in docs/01–11 define the system
* Legacy documents are stored in docs/archive/

---

## Current Limitations

* Full authentication system not implemented
* Frontend is not established or minimal
* Tenant configuration is partially static
* Some integrations exist as architecture paths, not production-ready features

---

## Goal

Deliver a deployable MVP where a complete end-to-end workflow can be demonstrated to an external user.
