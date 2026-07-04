# Execution Rules

> Governed by `docs/00-master-plan.md`. These rules apply to every AI bot, Cursor chat, and consultant working in this repository.

---

## Authority model

```
docs/00-master-plan.md       ← highest authority
docs/07-decisions.md         ← locked product and architecture decisions
docs/04-execution-rules.md   ← this file — how work is performed
docs/01-current-truth.md     ← verified state of the system
All other docs               ← reference material, subordinate to master plan
```

---

## Required read order

Every new AI/Cursor chat MUST read these before changing any file:

1. `docs/00-master-plan.md`
2. `docs/01-current-truth.md`
3. `docs/04-execution-rules.md`
4. The specific file or document directly related to this task

Do not rely on chat history. Rely on the repo.

---

## What execution agents may decide

- Choose the best technical implementation within the assigned task scope.
- Fix obvious bugs within the task scope.
- Create new files if technically motivated.
- Update documentation to reflect what was actually done.
- Update `docs/01-current-truth.md` when something has been verified.
- Reference `docs/07-decisions.md` when an already-locked decision applies to the work.

---

## What execution agents may not decide

- Change product strategy.
- Change product definition.
- Change phase order.
- Add new features because they seem good.
- Refactor broadly without an explicit assignment.
- Switch frontend stack.
- Build a new large integration before first customer.
- Create parallel roadmap documents.
- Let README or handoff become the new source of truth.
- Move scope from first customer to long-term vision.
- Change automation risk policy.
- Change integration priority.

---

## File creation rules

- Creating a new source file is allowed if technically required.
- Creating a new doc file is allowed only if it is a required deliverable of the assigned task.
- Do not create speculative documentation or future-planning documents unless explicitly assigned.

---

## Documentation update rules

Execution agents MUST update documentation when:

- A feature, endpoint, or behavior has been verified — update `docs/01-current-truth.md`.
- A decision was made during the task — add to `docs/07-decisions.md` using the next DEC-NNN number.

Execution agents MUST NOT:

- Update `docs/00-master-plan.md` as part of a technical execution task.
- Create parallel strategy or product documents.
- Leave docs/01-current-truth.md with stale Unverified items after verifying them.

---

## Test rules

Every code change must include one of:
- Updated or new tests covering the changed behavior.
- Clear manual test steps that can be reproduced without the agent.

Never leave changed logic unverified. Record test results in `docs/01-current-truth.md`.

---

## Stop conditions

Pause and report to the user if:

- The master plan appears technically wrong.
- Documents contradict each other in a way that blocks the task.
- A change requires a strategic decision.
- An implementation requires a major architecture change not approved in `docs/07-decisions.md`.
- An integration requires more scope than the plan allows.
- Tests reveal a major system failure outside the task scope.
- Any action would violate the automation risk policy.

Do not adjust strategy inside an execution task. Report and wait.

---

## Reporting format

Every execution chat MUST end with this summary:

```
Completed:
- ...

Changed files:
- ...

Tests/checks run:
- ...

Not run:
- ...

Plan alignment:
- Phase:
- Master plan item:

Issues / stop conditions:
- ...

Next allowed work:
- ...
```

---

## Definition of Done

A task is complete when:

1. The assigned work is implemented.
2. Tests pass (or clear manual test steps are documented).
3. `docs/01-current-truth.md` is updated if anything was verified.
4. `docs/07-decisions.md` is updated if a decision was made.
5. The reporting format above has been filled in.
6. No forbidden scope was introduced.
