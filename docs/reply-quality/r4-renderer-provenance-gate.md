# R4 renderer provenance gate

## Purpose

R4 send candidates are qualifying for human review only when they are produced by a
**live constrained LLM** with full provenance. Deterministic/hermetic/safe fallback
bodies are valid for R1 and default production rendering, but they are
**non-qualifying** for R4.

## Qualifying send-candidate requirements

For each of the 20 send scenarios:

- `renderer_requirement=constrained_llm_required`
- `renderer_type=constrained_llm_v1`
- `llm_used=true`
- `invocation_attempted=true`
- `live_call=true`
- `provider_outcome=success`
- `requested_model_id=gpt-4o-mini`
- `returned_model_id` present
- `prompt_version=coworker_constrained_llm_v5`
- post-render validation PASS
- final customer text validation PASS
- reply-quality oracle blockers = 0
- `fallback_used=false`
- plan hash and body hash present (body hash of the exact LLM text)

Package PASS also requires:

- scenario count 36 (20 send / 16 no-send)
- constrained LLM success 20/20
- deterministic renderer count 0
- fallback / missing model / missing prompt / provider / parse / post-render /
  final-text / oracle blocking failures all 0
- Gmail sends/drafts/triggers = 0
- external writes = 0
- `candidate_package_semantic_hash` present
- `provenance_audit_pass=true`

## Non-qualifying diagnostic example

Runtime SHA `29407be98ef6feef4e3494f3f60435c3ed0de5d6` produced a structurally
valid package that failed provenance audit:

- failure_code: `PROVENANCE_AUDIT_FAIL`
- failure_reason: `live_llm_not_invoked`
- renderer_type: `deterministic_structured_v1` for 20/20
- model_id / prompt_version missing 20/20
- `qualification_status=NON_QUALIFYING_DIAGNOSTIC`
- `human_review_unauthorized`
- body hashes retained as diagnostic evidence (must not be rewritten)

## Human-review authorization

`build_digital_coworker_r4_human_review_package.py` creates PENDING review slots
only when the candidate package meets the provenance gate. Otherwise it writes a
diagnostic package with `human_review_authorized=false` and zero review rows.

## Explicit non-goals

This gate does not authorize:

- R4 `--execute` (requires separate manual approval per campaign)
- automatic Gmail
- production activation

R5 closure and `PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED=VALID` are documented separately in `docs/plans/profile-driven-digital-coworker-reply-quality-r5-closure.md`.
