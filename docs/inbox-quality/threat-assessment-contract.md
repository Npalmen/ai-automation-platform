# Threat Assessment Contract

Contract version: `threat_assessment_v1`

## Module

`app/workflows/threat_assessment.py` — `ThreatAssessment`, `assess_threat`, `merge_threat_assessment`

## Integration points

1. **Intake** — `universal_intake_processor` runs `assess_threat` and stores `threat_assessment` in payload.
2. **Classification** — `classification_processor` applies `_apply_threat_override`; LLM cannot lower deterministic hard blockers.
3. **Policy** — `policy_processor` blocks `safe_acknowledgement_path` when `customer_draft_allowed=False`.
4. **Safe-ack eligibility** — `evaluate_safe_acknowledgement_eligibility(threat_assessment=...)`.

## Fail-closed rules

- `phishing`, `prompt_injection`, `credential_request` → `customer_draft_allowed=False`, `security_review`
- `payment_detail_change` → `customer_draft_allowed=False`, `security_review`
- `spam` → `customer_draft_allowed=False`, `reject`
- Quoted-history-only injection → advisory; does not block current legitimate request

## Known limitations

- No external URL fetching or link detonation
- No production blocklist side effects
- LLM may add advisory signals via `merge_threat_assessment` but cannot clear hard blockers
