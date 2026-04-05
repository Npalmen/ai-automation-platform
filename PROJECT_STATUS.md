# PROJECT STATUS

## Current Status
Platform is running with:
- FastAPI API layer
- PostgreSQL persistence
- SQLAlchemy repositories
- Multi-tenant policy controls
- Processor-based workflow engine
- Integration dispatcher with retry support
- AI Core with LLM client and prompt system
- AI-driven lead pipeline

## Verified Workflow State
The following lead pipeline is working end-to-end:

1. universal_intake_processor
2. classification_processor
3. entity_extraction_processor
4. lead_processor
5. decisioning_processor
6. policy_processor
7. human_handoff_processor

Verified output:
- classification identifies lead correctly
- entity extraction returns strict JSON
- lead scoring returns score/priority/routing
- decisioning returns target queue and action flags
- policy uses AI confidence and routing output
- human handoff is skipped when automation is allowed

## AI Core Status
Implemented:
- `app/ai/llm/client.py`
- `app/ai/prompts/registry.py`
- `app/ai/schemas.py`
- `app/ai/exceptions.py`

Behavior:
- strict JSON response handling
- schema validation with Pydantic
- safe fallback to manual review on AI failure
- processor outputs always written to `processor_history`

## Processor Status

### Implemented and Active
- Universal Intake Processor
- Classification AI Processor
- Entity Extraction AI Processor
- Lead Scoring AI Processor
- Decisioning AI Processor
- Policy Processor
- Human Handoff Processor

### Existing Domain Processors
- Invoice Processor
- Customer Inquiry Processor

## Persistence Status
Current state:
- workflow runs correctly in memory through the full processor chain
- audit events are written during workflow execution
- repository-based persistence for per-step job state is not fully wired yet

Note:
- direct SQLAlchemy `Session.add/merge` on `app.domain.workflows.models.Job` is not valid in the current architecture
- next implementation step is to persist workflow state through the repository layer instead of direct ORM session usage

## Audit Status
Implemented:
- job_created
- processor_step_completed
- job_pipeline_completed
- job_pipeline_failed

## Testing Status
Passing:
- AI classification success
- AI classification fallback
- entity extraction success
- lead scoring success
- decisioning fallback
- low-confidence classification manual review

## Current Architecture Rules
- processors are stateless
- all inter-step communication goes via `processor_history`
- no direct processor-to-processor dependencies
- AI outputs must be strict JSON
- workflow routing is done in pipeline layer, not in LLM client

## Next Recommended Phase
1. Customer Inquiry AI
2. Invoice AI extraction/decisioning
3. Integration dispatch from decisioning output
4. More test coverage for full pipeline and DB persistence
5. Update docs continuously with each completed phase