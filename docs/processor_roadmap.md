# Processor Roadmap

## Core Processors
- Universal Intake Processor ✅
- Classification AI Processor ✅
- Entity Extraction AI Processor ✅
- Policy Processor ✅
- Human Handoff Processor ✅
- Decisioning AI Processor ✅

## Sales Processors
- Lead Scoring AI Processor ✅
- Quote Processor ⏳
- CRM Update Processor ⏳
- Sales Follow-up Processor ⏳
- Opportunity Summary Processor ⏳

## Support Processors
- Customer Inquiry Processor ✅
- Customer Inquiry AI Upgrade ⏳
- Support Triage Processor ⏳
- Response Draft Processor ⏳
- Escalation Processor ⏳
- Case Summary Processor ⏳
- SLA Monitoring Processor ⏳

## Finance Processors
- Invoice Processor ✅
- Invoice AI Extraction Upgrade ⏳
- Receipt Processor ⏳
- Approval Processor ⏳
- Anomaly Processor ⏳
- Payment Follow-up Processor ⏳
- Finance Summary Processor ⏳

## Management Processors
- KPI Processor ⏳
- Executive Summary Processor ⏳
- Risk Processor ⏳
- Decision Support Processor ⏳
- Report Processor ⏳

## Design Rules
- processors must be stateless
- communication between processors happens via processor history
- outputs must be strict JSON-compatible payloads
- routing decisions are made in pipeline layer
- AI failures must degrade to manual review safely