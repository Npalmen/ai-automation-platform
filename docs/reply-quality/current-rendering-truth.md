# Current rendering truth — digital coworker reply quality

Verified at merge base `f848d4ea` (post `PROFILE_DRIVEN_SEMI_AUTO_QUALITY_QUALIFIED`).

## Scope

Forensic trace of the five unique live-send scenarios from the latest quality qualification:

- `PTB-Q96-0000`, `PTB-Q96-0003` (canary + campaign)
- `PTB-Q96-0012`, `PTB-Q96-0015`, `PTB-Q96-0018` (campaign)

Nine Gmail send events occurred across canary (4) and campaign (5); hashes below are per unique scenario body.

## Pipeline (legacy qualified path)

```text
policy_processor.safe_acknowledgement_path = true
→ action_dispatch._build_safe_acknowledgement_action
→ build_missing_fact_plan
→ build_customer_reply_plan (reply_planning_v1)
→ render_customer_reply (deterministic only)
→ assess_reply_candidate_safety
→ optional render_customer_reply(use_fallback=True)
→ delivery payload body
→ approval → Gmail send
```

The richer `lead_analyzer_processor.generated_question_message` path in `_build_lead_default_actions` is **not used** when `safe_acknowledgement_path` is active.

## Renderer attribution

| Scenario | Renderer | LLM | Fallback | Template |
|----------|----------|-----|----------|----------|
| PTB-Q96-0000 | `legacy_safe_ack_v1` | no | no | `safe_ack_incomplete_lead_v1` |
| PTB-Q96-0003 | `legacy_safe_ack_v1` | no | no | `safe_ack_incomplete_lead_v1` |
| PTB-Q96-0012 | `legacy_safe_ack_v1` | no | no | `safe_ack_incomplete_lead_v1` |
| PTB-Q96-0015 | `legacy_safe_ack_v1` | no | no | `safe_ack_incomplete_lead_v1` |
| PTB-Q96-0018 | `legacy_safe_ack_v1` | no | no | `safe_ack_incomplete_lead_v1` |

No constrained LLM renderer exists on this path. `assess_reply_candidate_safety` did not trigger fallback for any audited send.

## Primary root cause of generic output

1. **Single deterministic template** — `render_customer_reply()` always opens with a fixed acknowledgement, fixed “För att vi ska kunna gå vidare behöver vi:” block, and fixed closing “Förfrågan granskas av oss innan vi återkommer.”
2. **Safe-ack path bypasses profile-aware lead analyzer output** — service-specific questions from `lead_analyzer_processor` are skipped.
3. **Template similarity across services** — solar continuation (`0003`) produced an **identical body hash** to first-contact solar (`0000`).
4. **Support/status mis-profiled as generic lead** — scenarios `0012`, `0015`, `0018` resolved to `generic_lead` with `service_hint = "din förfrågan"` and name/address questions instead of support/status playbooks.
5. **Profile YAML tone unused** — `safe_acknowledgements` and `response_tone` from the customer profile do not feed `render_customer_reply`.
6. **Name re-ask despite known identity** — plan `verified_facts` includes `contact_name` while `missing_questions` still lists “Ditt namn”.

## Evidence excerpts

Solar send (`0000` / `0003` — same hash `10589b0c…`):

```text
Hej,

Tack för din förfrågan. Vi tittar på den och återkommer.

Vi ser att du vill ha hjälp med solcellsinstallation.

För att vi ska kunna gå vidare behöver vi:
- Taktyp eller bild på taket ...
```

Support/status sends (`0012`, `0015`, `0018` — same hash `86327e2…`):

```text
Hej,

Tack för din förfrågan. Vi tittar på den och återkommer.

För att vi ska kunna gå vidare behöver vi:
- Ditt namn
- Adress (gatuadress och ort)
```

## Draft vs sent

Live qualification verifies transport/oracle contracts; draft text in the action payload is the approved candidate. No post-approval body mutation was observed in audited evidence (hash contract intact).

## Remediation (this chapter)

- Introduce `CustomerReplyPlanV2` + profile-aware deterministic renderer behind eval feature flag.
- Service playbooks + operational next-step + information-value planning before render.
- Renderer provenance on every payload (`_reply_render_provenance`).
- Blocking coworker-quality oracles so safe-but-generic replies fail qualification.

Reproduce audit:

```bash
python -c "from app.workflows.reply_quality.audit import audit_legacy_reply_path; print([r.scenario_id for r in audit_legacy_reply_path()])"
```
