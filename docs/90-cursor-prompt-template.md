# Cursor Execution Prompt Template

Copy and paste this template at the start of every new Cursor or AI execution session in this repository.

---

```
You are working in the `ai-automation-platform` repo.

Before changing any files, read:

1. `docs/00-master-plan.md`
2. `docs/01-current-truth.md`
3. `docs/04-execution-rules.md`
4. Any document directly related to this task

Task:

[PASTE TASK HERE]

Scope:

- Phase:
- Master plan item:
- Allowed files:
- Forbidden files:
- Definition of Done:
- Required tests/checks:

Rules:

- Do not change product strategy.
- Do not change roadmap.
- Do not add new feature scope.
- Do not refactor broadly unless required for the task.
- If the plan appears wrong, pause and report.
- If documents conflict, `docs/00-master-plan.md` wins.
- Update documentation only where required by the task.
- At the end, report completed work, changed files, tests, issues and next allowed work.
```

---

## End-of-task reporting format

Every execution session must end with this exact format:

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

## Stop conditions reminder

Pause and report immediately if:

- The master plan appears technically wrong.
- Documents contradict each other in a way that blocks the task.
- A change requires a strategic decision not in `docs/07-decisions.md`.
- An implementation requires a major architecture change.
- Tests reveal a major system failure outside task scope.
- Any action would violate the automation risk policy.

Do not adjust strategy. Report and wait for instruction.
