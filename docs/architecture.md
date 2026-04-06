# Architecture

## Purpose

AI Automation Platform är en multi-tenant backend för att ta emot, analysera, besluta och exekvera administrativa eller operativa workflows med stöd av AI, policyregler och integrationslager.

Plattformen är byggd för att kunna användas som:

- intern automation engine
- kundspecifik automation backend
- framtida produktplattform med tenant-isolering

---

## High-Level Architecture

```text
Client / External System
        |
        v
    FastAPI API
        |
        v
 Tenant Resolution
        |
        v
 Workflow Orchestrator
        |
        +--> AI / Domain Processors
        |
        +--> Policy / Approval / Human Handoff
        |
        +--> Action Dispatch
        |
        v
 PostgreSQL Repositories + Audit + Integration Events