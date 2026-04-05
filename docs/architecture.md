# AI Automation Platform - Architecture

## Purpose
This platform is a multi-tenant automation backend for Swedish SMB and mid-market companies.
It is designed to support:
- configurable workflows
- tenant-specific policies
- tenant-specific integrations
- local, hosted, or hybrid deployment models

## High-level architecture

### 1. API layer
`app/main.py`

Responsibilities:
- FastAPI application
- request entrypoints
- tenant-aware route handling
- policy enforcement before execution

### 2. Core layer
`app/core/`

Responsibilities:
- settings and environment config
- logging
- tenant context
- temporary tenant config storage

### 3. Workflow domain
`app/domain/workflows/`

Responsibilities:
- job model
- job type enum
- job status enum
- request schemas

### 4. Workflow execution
`app/workflows/`

Responsibilities:
- job routing
- job execution
- processor registry
- workflow policies
- processor metadata

### 5. Processors
`app/workflows/processors/`

Responsibilities:
- implement job-specific business logic
- produce standardized results

Currently implemented:
- invoice
- email
- contract
- unknown

### 6. Integrations domain
`app/integrations/`

Responsibilities:
- integration enums
- integration metadata
- integration factory
- integration registry
- integration policies
- integration config models
- tenant-aware integration service

Currently implemented adapters:
- Google
- Microsoft
- Visma
- Fortnox
- Monday

## Request flow: jobs
1. request enters `POST /jobs`
2. tenant is resolved from header
3. tenant policy validates job type
4. `Job` model is created
5. `run_job(job)` executes
6. processor is selected from registry
7. result is returned

## Request flow: integrations
1. request enters `/integrations/{integration_type}/...`
2. tenant is resolved from header
3. tenant policy validates integration access
4. tenant-specific connection config is loaded
5. adapter is resolved via factory
6. status or action is executed
7. result is returned

## Multi-tenant model
Each tenant can have:
- allowed integrations
- enabled job types
- integration connection configs
- different automation policy levels

## Current limitations
The following are still prototype-level:
- tenant config stored in Python file
- no PostgreSQL persistence yet
- no audit trail yet
- adapters are mock implementations
- processors use simplified extraction logic

## Next recommended steps
1. move tenant config into PostgreSQL
2. persist jobs in database
3. add audit events
4. build admin panel
5. implement first real integration
6. implement first real AI-backed processor

## Audit model
The platform now includes an in-memory audit foundation.

Current audit categories:
- job
- integration

Examples of audit actions:
- job_received
- job_completed
- job_failed
- integration_status_checked
- integration_action_executed
- integration_status_denied
- integration_action_denied

Current limitation:
- audit events are stored in memory only
- they will later be moved to PostgreSQL