# Business Intent and Safe Extraction Contract

Contract versions: `business_intent_v1`, `safe_extraction_v1`

## Modules

- `app/workflows/business_intent.py` — `BusinessIntentResult`, `build_business_intent_from_classification`
- `app/workflows/safe_extraction.py` — `ExtractedFactSet`, `sanitize_entities`, `identify_untrusted_spans`

## Integration points

1. **Classification** — attaches `business_intent` dict to classification payload.
2. **Entity extraction** — `sanitize_entities` filters untrusted spans; attaches `extracted_fact_set`.

## Rules

- Classification runs on threat-annotated representation; threat hard blockers force `primary_intent=unknown`.
- Prompt-injection spans never become authoritative `requested_service` or other business facts.
- Low confidence (<0.5) flagged in `ambiguity_flags`.
- Location and contact facts preserved when not from excluded spans.

## Known limitations

- No automatic customer profile verification
- Quote/signature stripping not yet a dedicated pipeline stage (Todo G scope)
