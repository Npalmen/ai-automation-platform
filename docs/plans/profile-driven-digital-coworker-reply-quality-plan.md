---
title: Profile-driven Digital Coworker Reply Quality
slug: profile-driven-digital-coworker-reply-quality
status: approved
created: 2026-08-02
qualification_target: PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED
qualification_registry_status: PENDING
gates:
  R1_HERMETIC: PASS
  R2_PRECHECK: FAIL
  R2_HUMAN_REVIEW: PENDING
  R3_LIVE_CANARY: PASS
  R4_LIVE_CAMPAIGN: PENDING
  R5_CLOSURE: PENDING
human_review_failure_sha: 8b167280e8190be0e79d6f127416a7819f84c4d7
human_review_package_status: NON_QUALIFYING_DIAGNOSTIC_PACKAGE
closure_branch: fix/digital-coworker-llm-reproducibility-and-precheck
production_activation: false
automatic_gmail_activation: false
todos:
  A: completed
  B: completed
  C: completed
  D: completed
  E: completed
  F: completed
  G: completed
  H: completed
  I: in_progress
  J: pending
---

# Profile-driven Digital Coworker Reply Quality

## 1. Executive summary

The platform has qualified safety, routing, approval, Gmail transport, threat detection, extraction, replay protection, and semi-automatic quality infrastructure. The remaining product gap is the actual customer experience.

The live replies are still dominated by a generic acknowledgement structure: thank the sender, repeat the service category, request name and sometimes telephone number, and state that the company will review and return. This is safe, but it does not yet behave like a competent digital coworker.

This chapter makes replies:

- specific to the service and customer situation,
- operationally useful for the company,
- concise and natural,
- consistent with the customer profile,
- aware of known facts and thread context,
- varied because the business situation differs, not because wording is randomized,
- safe, approval-gated, and fully auditable.

Automatic Gmail remains out of scope.

## 2. Verified current truth

Already valid on `main`:

- `PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED = VALID`
- `PROFILE_DRIVEN_SEMI_AUTO_QUALITY_QUALIFIED = VALID`
- threat assessment and prompt-injection blocking
- business intent classification
- safe extraction with provenance
- central safe-ack eligibility
- deterministic missing-fact planning
- reply planning/rendering separation
- internal operator note separation
- Gmail thread, duplicate, replay, and idempotency controls
- live provider acceptance and recipient verification
- hard-safety and no-send quality gates

Still pending:

- `PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED`
- `PROFILE_DRIVEN_TESTBOT_PASS`

Verified limitation:

- replies across distinct scenarios remain structurally almost identical,
- the service profile has limited visible influence on wording and questions,
- questions focus too often on name and telephone instead of operational facts,
- the response behaves like an acknowledgement template rather than a coworker,
- existing quality gates prioritize safety and decision correctness over usefulness, specificity, naturalness, and business progression.

## 3. Product objective

After this chapter, a reviewer must be able to recognize:

1. what the customer asked about,
2. what the company already knows,
3. what the company needs next,
4. why the selected questions are relevant,
5. what the customer should do next,
6. that the response sounds like the configured company,
7. that no unsupported promise was made.

The system should feel like a careful office coworker, not a generic autoresponder.

## 4. Target architecture

```text
normalized message
→ threat and trust result
→ business intent
→ safe extracted facts with provenance
→ customer/thread context
→ service playbook selection
→ operational next-step selection
→ information-value planner
→ structured CustomerReplyPlanV2
→ deterministic safety validation
→ profile-aware renderer
→ post-render contract validation
→ approval
→ existing qualified Gmail execution
```

Keep three artifacts strictly separate:

```text
CustomerReplyPlanV2
InternalOperatorNote
CustomerFacingReply
```

The renderer may express an approved plan naturally, but it may not introduce new facts, add new questions, change the selected next step, make commitments, weaken threat decisions, or expose internal notes.

## 5. Core contracts

### 5.1 ServicePlaybook

Versioned, profile-driven contract with:

- `playbook_id`
- `version`
- `service_family`
- `supported_intents`
- `next_step_options`
- `required_facts_by_next_step`
- `optional_high_value_facts`
- `forbidden_email_questions`
- `question_priority`
- `question_dependencies`
- `maximum_questions_first_reply`
- `maximum_questions_followup`
- `allowed_acknowledgement_modes`
- `allowed_commitment_classes`
- `operator_review_conditions`
- `reply_examples`
- `anti_examples`

Initial families:

- solar installation
- battery installation
- EV charger
- combined solar and battery
- existing installation support
- job status
- general consultation
- complaint or warranty
- unknown service

### 5.2 OperationalNextStep

Deterministic business objective selected before rendering, such as:

- collect minimum site facts
- collect contact preference
- request attachment
- clarify service scope
- distinguish new installation from support
- confirm case receipt only
- route to manual technical review
- route to safety handling
- provide status acknowledgement
- decline or no reply

### 5.3 InformationValuePlan

Ranks candidate questions by operational usefulness and records:

- candidate questions
- selected questions
- excluded questions
- selection reasons
- already-known facts
- question budget
- playbook and policy versions

Identical inputs must produce identical question sets.

### 5.4 CustomerReplyPlanV2

Must include:

- response objective
- acknowledgement mode
- service family
- business intent
- verified facts allowed to repeat
- facts not allowed to repeat
- selected questions
- next-step statement
- commitment constraints
- tone profile
- language
- salutation and closing strategy
- signature profile
- thread context summary
- rendering constraints
- fallback reason
- evidence

### 5.5 ReplyQualityEvaluation

Dimensions:

- safety
- factual fidelity
- service specificity
- operational usefulness
- question relevance
- question consistency
- profile fidelity
- thread awareness
- naturalness
- concision
- next-step clarity
- template similarity
- fallback usage
- forbidden commitment absence

Statuses:

- pass
- fail
- advisory
- not_applicable
- unresolved

## 6. Todo A — Audit the real rendering path

### Goal

Verify why the latest live replies remained generic.

### Implementation

Trace the real path for all nine sent replies from the latest qualification:

```text
CustomerReplyPlan
→ renderer selection
→ LLM or deterministic renderer
→ fallback selection
→ post-render validation
→ delivery_payload
→ sent Gmail body
```

Record:

- renderer used,
- whether LLM rendering ran,
- whether fallback was used and why,
- populated plan fields,
- profile fields available,
- selected missing facts,
- draft versus sent body differences,
- template contribution,
- service-playbook influence.

Add renderer provenance:

- renderer type
- model and prompt version where applicable
- fallback reason
- template version
- plan hash
- final body hash

### Acceptance criteria

- every reply is attributable to one exact path,
- the primary cause of generic output is verified,
- no implementation begins before the audit is documented.

### Documentation

- `docs/reply-quality/current-rendering-truth.md`
- decision record for reply provenance.

## 7. Todo B — Service playbooks and next-step selection

### Goal

Make response objectives service-specific and operationally useful.

### Initial playbook facts

**Solar installation:** address/municipality, property type, roof type, approximate annual usage, battery interest, existing installation, supported attachment.

**Battery installation:** existing solar system, current inverter/system, intended purpose, property address, annual usage, explicit battery preference.

**EV charger:** property type, installation address, number of charging points, known electrical capacity, private/business/housing-association context, load balancing need.

**Existing support:** system type, symptom, start time, error code, safety state, known case reference, relevant image/document.

**Status:** job/case reference, safe customer identifier, requested status dimension.

**Complaint/warranty:** original case, issue description, discovery time, evidence, safety relevance.

### Tests

- same service and facts select the same next step,
- different services select different priorities,
- support does not use a new-sales flow,
- status requests do not receive installation language,
- complaints do not receive generic sales wording.

### Non-goals

No pricing, booking, warranty decision, or technical diagnosis.

## 8. Todo C — Information-value question policy

### Goal

Ask the smallest useful set of questions that enables the next operational step.

### Rules

- never ask for known information,
- do not ask for name merely because a template expects it,
- request telephone only when the profile or selected next step justifies it,
- prefer operational facts over administrative trivia,
- enforce first-reply question budget,
- allow one concise clarification when intent is uncertain,
- preserve service, location, and thread facts,
- record why each selected question was chosen and why others were excluded.

Use a deterministic scoring or rule model based on:

```text
next-step relevance
+ information gain
+ profile priority
- customer effort
- sensitivity
- redundancy
```

### Acceptance criteria

- identical inputs produce identical questions,
- every question has an operational reason,
- the reply moves the case toward a defined next step.

## 9. Todo D — CustomerReplyPlanV2

### Goal

Provide enough structured context for a useful natural reply without allowing the renderer to make business decisions.

### Implementation

Implement `CustomerReplyPlanV2` and a compatibility adapter from the current plan.

The plan must:

- distinguish acknowledgement from business progression,
- include verified facts worth referencing,
- include selected questions in priority order,
- define one next step,
- define tone and signature from the customer profile,
- define forbidden wording and commitments,
- include safe thread context,
- include length and question limits,
- select response mode: receipt acknowledgement, information request, support acknowledgement, status acknowledgement, manual-review acknowledgement, or no reply.

### Acceptance criteria

- renderer gets enough context to differentiate responses,
- the plan remains inspectable and deterministic,
- existing safety and approval contracts remain intact.

## 10. Todo E — Profile-aware renderer

### Goal

Render the approved plan as concise, natural language that sounds like the configured company.

### Renderers

1. deterministic structured renderer,
2. constrained LLM renderer.

The constrained renderer receives only the approved plan, tone, signature, and safe rendering instructions. It must not receive raw threat spans as business content.

Post-render validation must verify:

- no new facts,
- no extra questions,
- no forbidden commitments,
- no internal-note content,
- no unsupported price or schedule language,
- profile and language compliance,
- next-step consistency.

On validation failure:

- reject the LLM body,
- use deterministic structured rendering,
- record fallback reason,
- keep approval required.

### Style requirements

- natural Swedish by default,
- no unnecessary repetition,
- no generic “we are reviewing it” when a useful next step is known,
- no mechanical repetition of the full customer message,
- natural use of known service and location,
- prose or short list based on question count,
- one clear next step,
- configured company signature,
- no eval or internal names.

Variation must come from the plan, not random synonym changes.

### Acceptance criteria

- distinct services produce distinct and useful replies,
- semantically identical plans remain consistent,
- provenance is complete,
- safety remains approval-gated.

## 11. Todo F — Thread-aware coworker behavior

### Goal

Treat a thread as a conversation rather than a sequence of first contacts.

### Required cases

- first contact,
- customer supplies requested facts,
- partial answer,
- changed fact,
- new question in the same thread,
- status follow-up,
- prior operator reply,
- previous safe acknowledgement.

### Rules

- do not thank the customer for a “new enquiry” on every continuation,
- do not request facts already supplied,
- acknowledge newly supplied information,
- ask only remaining high-value questions,
- ignore quoted history as new input,
- avoid duplicate acknowledgements,
- retain approval gating.

### Acceptance criteria

- follow-ups feel continuous,
- partial answers lead to only remaining questions,
- ambiguous context routes to manual review.

## 12. Todo G — Reply-quality dataset

### Goal

Create a dataset that cannot pass with one generic acknowledgement template.

### Minimum

- at least 120 curated scenarios,
- at least 15 scenario families,
- at least 30 multi-turn scenarios,
- at least 20 scenarios where commonly requested facts are already known,
- at least 20 scenarios where name or telephone must not be requested,
- at least 20 scenarios requiring service-specific prequalification facts,
- Swedish majority and smaller English subset.

Required families include solar, battery, EV charger, support, status, complaint/warranty, consultation, missing attachment, follow-up facts, mixed intent, out-of-scope, threat regressions, duplicates/replay, and multi-turn continuation.

Each scenario defines:

- profile,
- message and thread context,
- verified facts,
- expected playbook,
- expected next step,
- expected and forbidden questions,
- expected response objective,
- facts allowed to repeat,
- forbidden commitments,
- expected structural characteristics,
- expected send/no-send,
- rationale.

No family may dominate and suffix mutations may not be the main coverage strategy.

## 13. Todo H — Blocking quality oracles

### Goal

Make generic but safe replies fail qualification.

### Blocking areas

**Plan fidelity:** every fact and question must be authorized by the plan.

**Service specificity:** known service family must visibly affect the reply when relevant.

**Question utility:** no re-asking known facts, no unjustified name/phone request, correct priority, question budget respected.

**Conversation quality:** follow-up wording, no repeated answered questions, clear next step.

**Template similarity:** versioned structural-similarity metrics must detect excessive sameness across distinct service families without penalizing legitimate consistency for equivalent cases.

**Fallback rate:** fallback is safe but excessive fallback blocks qualification; every fallback needs a reason.

**Language/profile:** correct language, signature, tone, no internal names.

### Human review rubric

Score:

- sounds like a competent coworker,
- progresses the case,
- asks useful questions,
- is specific without overpromising,
- is clear and natural.

Human review cannot override hard-safety failures.

An LLM judge may be advisory for naturalness, tone, relevance, and concision, but is not the sole qualification authority.

## 14. Todo I — Hermetic and live qualification

### New qualification

`PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED`

### Gate R1 — Hermetic plan and reply quality

- 120/120 scenario contract execution,
- hard-safety 100%,
- plan fidelity 100%,
- no known-fact re-asking in blocking scenarios,
- service-playbook and question-quality thresholds met,
- template-similarity gate PASS,
- fallback-rate gate PASS,
- all multi-turn blocking oracles PASS.

### Gate R2 — Human review

Review at least 40 rendered replies, balanced across services and including:

- at least 10 multi-turn,
- at least 10 no-name/no-phone cases,
- at least 10 technical prequalification cases.

No reply may be unacceptable; minimum per-dimension and per-family scores are required.

### Gate R3 — Live semi-auto canary

Suggested:

- 15 scenarios,
- at least 10 families,
- max 8 sends,
- at least 5 no-send,
- at least 4 multi-turn cases,
- no semantically duplicate send scenarios.

### Gate R4 — Live coworker-quality campaign

Suggested:

- 36 scenarios,
- at least 15 families,
- max 20 sends,
- at least 10 multi-turn,
- at least 10 cases where name/phone must not be requested,
- at least 10 service-specific prequalification cases.

### Gate R5 — Closure

Register the new qualification only after R1–R4 PASS.

Automatic Gmail and full testbot remain PENDING.

## 15. Todo J — Closure

### Deliverables

- qualification registry update,
- current truth and decision records,
- known limitations,
- service-playbook authoring guide,
- scenario authoring guide,
- human-review rubric,
- renderer provenance documentation,
- feature-flag and rollback documentation,
- local redacted live-review reports.

### Closure requirements

- Todos A–J completed,
- all PRs merged,
- post-merge Release Gate PASS,
- Regression Main PASS,
- R1–R5 PASS,
- `PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED = VALID`,
- automatic Gmail remains PENDING,
- production activation remains false.

## 16. PR strategy

### PR 1 — Foundation

Branch: `feature/digital-coworker-reply-foundation`

Scope: Todo A–C — audit, service playbooks, next-step selection, information-value planning.

### PR 2 — Planning and rendering

Branch: `feature/digital-coworker-reply-rendering`

Scope: Todo D–F — `CustomerReplyPlanV2`, constrained renderer, fallback validation, thread-aware behavior.

### PR 3 — Dataset and gates

Branch: `feature/digital-coworker-reply-evaluation`

Scope: Todo G–H — 120-scenario dataset, blocking quality oracles, similarity/fallback metrics, human-review tooling.

### PR 4 — Qualification and closure

Branch: `release/digital-coworker-reply-quality`

Scope: Todo I–J — hermetic/live qualification, registry, documentation, closure.

Each PR must be squash-merged only after full required CI PASS.

## 17. Metrics

Report at minimum:

- service-playbook accuracy,
- next-step accuracy,
- selected-question precision and recall,
- known-fact re-ask rate,
- unjustified name-request rate,
- unjustified telephone-request rate,
- service-specific fact coverage,
- factual and profile fidelity,
- next-step clarity,
- template similarity by family pair,
- deterministic fallback rate,
- LLM validation rejection rate,
- human-review score by dimension,
- provider acceptance and recipient verification,
- unauthorized, duplicate, wrong-recipient, cross-tenant, and non-Gmail-write counts.

Hard-safety remains a 100% requirement.

## 18. Risks and mitigations

- **Natural language introduces hallucination:** structured plan, constrained renderer, deterministic validation, safe fallback, approval remains mandatory.
- **Artificial variation:** variation derives from business context, not random synonyms.
- **Too many questions:** question budget and information-value ranking.
- **Industry hardcoding:** versioned profile resources and generic contracts.
- **LLM judge becomes authority:** deterministic oracles remain authoritative; human rubric is fixed.
- **Regression of existing qualifications:** retain feature-flagged fallback and run existing safety/transport suites.

## 19. Rollback and fail-closed behavior

- New reply-quality path is eval-feature-flagged first.
- Plan failure routes to current qualified safe fallback and records a quality failure.
- Renderer failure uses deterministic rendering.
- Post-render validation failure uses safe fallback and requires approval.
- Ambiguous thread context routes to manual review.
- Uncertain provider outcome never triggers automatic resend.
- Existing Gmail, idempotency, recipient, and tenant-isolation contracts remain unchanged.

## 20. Explicit non-goals

This chapter does not:

- activate production Gmail,
- activate automatic Gmail,
- remove approval,
- calculate or send prices,
- book appointments,
- promise timelines,
- make warranty decisions,
- perform technical diagnosis,
- add Sheets/Monday/Visma writes,
- auto-verify/link/merge customers,
- redesign the full customer profile domain,
- replace qualified threat and safety architecture.

## 21. Documentation plan

Create or update:

- `docs/01-current-truth.md`
- `docs/07-decisions.md`
- `docs/reply-quality/current-rendering-truth.md`
- `docs/reply-quality/service-playbook-contract.md`
- `docs/reply-quality/information-value-policy.md`
- `docs/reply-quality/customer-reply-plan-v2.md`
- `docs/reply-quality/renderer-contract.md`
- `docs/reply-quality/human-review-rubric.md`
- `docs/reply-quality/scenario-authoring-guide.md`
- `docs/reply-quality/known-limitations.md`
- qualification registry documentation.

## 22. Final closure definition

The chapter is complete only when:

```text
PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED = VALID
```

and:

- real replies are visibly service-specific,
- questions are operationally useful,
- known information is not requested again,
- multi-turn replies continue naturally,
- generic-template similarity is below the approved threshold,
- fallback usage is below the approved threshold,
- human review confirms competent-coworker quality,
- all existing safety, approval, transport, and isolation qualifications remain valid,
- automatic Gmail remains disabled and PENDING,
- production activation remains false.
