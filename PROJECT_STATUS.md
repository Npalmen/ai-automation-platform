# Project status

## Repository
https://github.com/Npalmen/ai-automation-platform

## Current architecture
The system uses the existing workflow-based architecture.

Main flow:
- `app/main.py` receives `/jobs`
- `app/workflows/pipeline_runner.py` runs the pipeline
- `app/workflows/job_runner.py` executes one processor
- `app/workflows/processor_registry.py` maps `JobType` to processor

## Implemented processors
Implemented and connected:

- `app/workflows/processors/intake_processor.py`
- `app/workflows/processors/classification_processor.py`
- `app/workflows/processors/entity_extraction_processor.py`
- `app/workflows/processors/policy_processor.py`
- `app/workflows/processors/human_handoff_processor.py`
- `app/workflows/processors/invoice_processor.py`
- `app/workflows/processors/invoice_extractor.py`

## Current pipeline behavior
Base pipeline:
- intake
- classification

Dynamic routing after classification.

Invoice flow:
- intake
- classification
- entity_extraction
- invoice
- policy
- human_handoff

## Important model updates
`app/domain/workflows/models.py`
- `Job` includes:
  - `processor_history: list[dict] = Field(default_factory=list)`

## Important schema updates
`app/domain/workflows/schemas.py`
- `CreateJobRequest` includes:
  - `job_type`
  - `input_data`

## Important enum updates
`app/domain/workflows/enums.py` includes:
- `INTAKE`
- `CLASSIFICATION`
- `ENTITY_EXTRACTION`
- `POLICY`
- `HUMAN_HANDOFF`
- `EMAIL`
- `CONTRACT`
- `INVOICE`
- `LEAD`
- `CUSTOMER_INQUIRY`
- `UNKNOWN`

## Important rule
Every processor should:
1. build a `result`
2. append to `job.processor_history`
3. assign `job.result = result`
4. return `job`

## Current recommendation for next steps
Build next in this order:
1. lead processor
2. customer inquiry processor
3. response draft processor
4. CRM update processor
5. approval/anomaly processor
6. management summary processor

## Important note for future work
Do not build a separate processor framework outside `app/workflows/processors/`.
Continue using the existing workflow architecture already present in the repo.

## Full processor roadmap
The full roadmap is tracked in:
- `docs/processor_roadmap.md`

All planned processors are already defined in `JobType`, even if not yet implemented.

Current implementation status:
- Core: implemented
- Invoice: implemented
- Remaining finance, sales, support, and management processors: planned

## Additional documentation
Detailed current-state documentation is stored in:
- `docs/system_status.md`
- `docs/implementation_plan.md`
- `docs/processor_roadmap.md`

#UPDATE

# PROJECT STATUS — AI Automation Platform

## ✅ Current State

Systemet är nu en fungerande automation backend med:

- Multi-tenant stöd
- Full pipeline execution
- Processor-based arkitektur
- Audit logging
- Integration framework (förberett)

---

## 🔧 Pipeline (fungerar)

1. Intake
2. Classification
3. Entity Extraction
4. Domain processors:
   - Lead Processor
   - Invoice Processor (v2)
   - Customer Inquiry Processor
5. Policy Processor (v2)
6. Human Handoff Processor

---

## 🧠 Decision Engine

### Invoice
- validation_status: validated / incomplete / duplicate
- approval_route:
  - auto_approve
  - approval_required
  - manual_review

### Lead
- lead_score (0–100)
- priority (low / medium / high)
- routing:
  - crm_update
  - priority_sales_followup

### Inquiry
- routing:
  - support_queue
  - billing_queue
  - sales_queue

---

## 🧾 Processor Standard

Alla processorer:
- sätter `result`
- append:ar till `processor_history`
- returnerar `job`

---

## ⚠️ Viktiga designbeslut

- `job_type` = affärstyp (inte pipeline-step)
- pipeline körs via kopior (`step_job`)
- ALL logik läser från `processor_history`
- ingen processor får bero direkt på input

---

## 🚀 Next Step

👉 Integration layer (CRM / Webhooks)

Systemet är redo att börja skapa affärsvärde.

These files should be used as the main handoff context for future sessions.