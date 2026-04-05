# AI Automation Platform

## Status: AI Core Complete (v1)

Systemet är nu en fungerande AI-driven workflow engine med:

- Multi-tenant stöd
- Pipeline-baserad job processing
- AI-processorer (LLM)
- Validation layer
- Observability (audit + processor logs)
- Integration dispatch

---

## Arkitektur

### Pipeline
1. Intake
2. Classification
3. Entity Extraction
4. Domain Processor (Lead / Invoice / Inquiry)
5. Decisioning
6. Policy
7. Human Handoff

---

## AI Processorer

- Classification (ärendetyp)
- Entity Extraction (datautvinning)
- Lead Scoring
- Customer Inquiry
- Invoice Processing
- Decisioning

Alla använder:
- `run_ai_step`
- central prompt registry
- fallback + validation

---

## Funktioner

### Lead flow
- Identifierar lead
- Extraherar kontaktinfo
- Score + prioritet
- Routing → CRM / queue

### Invoice flow
- Extraherar fakturadata
- Validerar
- Duplicate detection
- Approval route

### Inquiry flow
- Förstår kundfråga
- Klassificerar intent
- Skapar svar/route

---

## Observability

- Audit events
- Processor history
- Full trace per job

---

## Integrationer

- Dispatcher kopplad till decisioning
- Stöd för:
  - CRM
  - Notifications
  - framtida system

---

## Nästa steg

### 1. CRM Integration (PRIO 1)
- skapa leads automatiskt
- koppla till riktig affär

### 2. Queue system
- manual_review
- priority_sales_followup

### 3. UI / Dashboard
- lista jobb
- se pipeline
- hantera manuella ärenden

### 4. Prompt tuning
- bättre precision
- stabil confidence

### 5. Tenant config i DB
- flytta från kod → databas

---

## Kör projektet

```bash
uvicorn app.main:app --reload