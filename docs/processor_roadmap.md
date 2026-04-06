# Processor Roadmap

## Purpose

Detta dokument beskriver processorlandskapet i plattformen: vad som finns, vad som används i pipeline idag och vad som är rimligt att bygga härnäst.

---

## Core Pipeline Processors

### Implementerade och aktiva
- Universal Intake Processor
- Classification Processor
- Entity Extraction Processor
- Policy Processor
- Action Dispatch Processor
- Human Handoff Processor

### Kommentar
Dessa steg utgör plattformens generiska backbone.

---

## Sales Processors

### Implementerade
- Lead Processor
- Decisioning Processor

### Nästa rimliga steg
- CRM Create/Update Processor
- Quote Preparation Processor
- Follow-up Processor
- Opportunity Summary Processor

### Kommentar
Lead-automation är närmast att bli första verkliga kundbara use caset.

---

## Support Processors

### Implementerade
- Customer Inquiry Processor

### Behöver stärkas
- Inquiry AI Upgrade
- Triage Processor
- Response Draft Processor
- Escalation Processor
- Case Summary Processor

### Kommentar
Support-spåret har bra arkitekturposition men behöver mer produktnivålogik.

---

## Finance Processors

### Implementerade
- Invoice Processor

### Behöver stärkas
- Invoice AI Extraction
- Validation / Approval Processor
- Duplicate / Anomaly Processor
- Payment Follow-up Processor
- Finance Summary Processor

### Kommentar
Finance-spåret bör byggas försiktigt eftersom riskkostnaden för fel är högre.

---

## Governance / Control Processors

### Implementerade
- Policy Processor
- Human Handoff Processor
- Approval Engine (workflow service-lager snarare än vanlig processor)

### Potentiella tillägg
- SLA / Timeout Processor
- Risk Processor
- Compliance Flag Processor
- Escalation Rules Processor

---

## Management / Analytics Processors

### Ej prioriterat för första säljbara version
- KPI Processor
- Executive Summary Processor
- Risk Summary Processor
- Report Generator

### Kommentar
Dessa bör komma efter att operativa workflows ger affärsvärde.

---

## Processor Design Rules

Alla processors ska:

- vara stateless
- använda standardiserad payload-struktur
- kunna skriva till `processor_history`
- tåla att köras i orchestrerad pipeline
- degradera säkert vid osäkerhet eller fel

---

## Strategic Priority Order

1. Lead / CRM execution
2. Inquiry triage + response/ticket path
3. Invoice extraction + approval
4. Governance enhancers
5. Analytics / management processors