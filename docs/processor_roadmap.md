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
Dessa steg utgör plattformens generiska backbone och ska hållas generella.

---

## Sales / Lead Processors

### Implementerade
- Lead Processor
- Decisioning Processor

### Nästa rimliga steg
- CRM Create/Update Processor
- Follow-up Processor
- Opportunity Summary Processor

### Kommentar
Lead-automation är det närmaste spåret till tydligt kommersiellt värde.

---

## Support / Inquiry Processors

### Implementerade
- Customer Inquiry Processor

### Behöver stärkas
- Triage Processor
- Response Draft Processor
- Escalation Processor
- Case Summary Processor

### Kommentar
Inquiry-spåret är strategiskt viktigt, men måste bli mer operativt innan det är säljklart.

---

## Finance / Invoice Processors

### Implementerade
- Invoice Processor

### Behöver stärkas
- Invoice AI Extraction
- Validation / Approval Processor
- Duplicate / Anomaly Processor
- Finance Summary Processor

### Kommentar
Finance-spåret ska byggas försiktigt eftersom felkostnaden är högre.

---

## Governance / Control

### Implementerade
- Policy Processor
- Human Handoff Processor
- Approval engine/service-lager
- Action execution logging
- Approval persistence

### Potentiella tillägg
- SLA / Timeout Processor
- Risk Processor
- Compliance Flag Processor
- Escalation Rules Processor

---

## Management / Analytics

### Ej prioriterat för första säljbara version
- KPI Processor
- Executive Summary Processor
- Risk Summary Processor
- Report Generator

### Kommentar
Dessa bör komma efter att operativa workflows ger tydligt affärsvärde.

---

## Processor Design Rules

Alla processors ska:

- vara stateless
- använda standardiserad payload-struktur
- kunna skriva till `processor_history`
- tåla orchestrerad pipeline
- degradera säkert vid fel eller osäkerhet

---

## Strategic Priority Order

1. Lead / CRM execution hardening
2. Inquiry triage + response/ticket path
3. Invoice extraction + approval hardening
4. Governance enhancers
5. Analytics / management processors