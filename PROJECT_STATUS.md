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