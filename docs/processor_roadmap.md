# Processor roadmap

## Purpose
This file tracks the full processor roadmap for the AI automation platform.

The system should continue using the existing workflow architecture under:
- `app/workflows/processors/`
- `app/workflows/pipeline_runner.py`
- `app/workflows/processor_registry.py`

Do not build a separate processor framework outside the existing workflow system.

---

## Status legend
- [x] Implemented
- [~] Started / partial
- [ ] Planned

---

## Core processors
- [x] INTAKE
- [x] CLASSIFICATION
- [x] ENTITY_EXTRACTION
- [x] POLICY
- [x] HUMAN_HANDOFF

---

## Finance processors
- [x] INVOICE
- [ ] RECEIPT
- [ ] APPROVAL
- [ ] ANOMALY
- [ ] PAYMENT_FOLLOWUP
- [ ] FINANCE_SUMMARY

---

## Sales processors
- [ ] LEAD
- [ ] LEAD_QUALIFICATION
- [ ] QUOTE
- [ ] SALES_FOLLOWUP
- [ ] CRM_UPDATE
- [ ] OPPORTUNITY_SUMMARY

---

## Support processors
- [ ] CUSTOMER_INQUIRY
- [ ] SUPPORT_TRIAGE
- [ ] RESPONSE_DRAFT
- [ ] ESCALATION
- [ ] CASE_SUMMARY
- [ ] SLA_MONITORING

---

## Management processors
- [ ] KPI
- [ ] EXEC_SUMMARY
- [ ] RISK
- [ ] DECISION_SUPPORT
- [ ] REPORT

---

## Legacy / utility processors
- [~] EMAIL
- [~] CONTRACT
- [x] UNKNOWN

---

## Current implemented flow
### Base flow
- intake
- classification

### Current dynamic invoice flow
- intake
- classification
- entity_extraction
- invoice
- policy
- human_handoff

---

## Recommended build order
1. LEAD
2. CUSTOMER_INQUIRY
3. RESPONSE_DRAFT
4. CRM_UPDATE
5. APPROVAL
6. ANOMALY
7. KPI / EXEC_SUMMARY / REPORT

---

## Implementation rule
Every processor should:
1. build a `result`
2. append to `job.processor_history`
3. assign `job.result = result`
4. return `job`

## Context
This roadmap should be read together with:
- `docs/system_status.md`
- `docs/implementation_plan.md`
- `PROJECT_STATUS.md`