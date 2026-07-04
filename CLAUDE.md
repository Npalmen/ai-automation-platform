
# CLAUDE.md

## Mandatory governance

Before performing any work, read:

1. `docs/00-master-plan.md`
2. `docs/01-current-truth.md`
3. `docs/04-execution-rules.md`

`docs/00-master-plan.md` is the governing document. If any file conflicts with it, the master plan wins.

Execution agents may choose implementation details but may not change product direction, roadmap, phase order, integration priority or automation risk policy.

If the plan appears wrong, pause and report. Do not adjust strategy inside an execution task.

---

## Project Mission

You are working on a backend-first, multi-tenant AI automation platform.

The goal is to build a **deployable MVP** where:
- jobs are processed through a workflow pipeline
- AI + rules classify and extract data
- policy decides automation vs approval
- approvals can pause and resume flows
- integrations execute real actions
- everything is auditable

---

## Source of Truth (READ FIRST)

You MUST follow these documents in this order:

1. `docs/00-master-plan.md` — highest authority
2. `docs/01-current-truth.md` — verified system state
3. `docs/04-execution-rules.md` — how to execute work
4. The specific document related to your current task

If something conflicts:
→ `docs/00-master-plan.md` wins, NOT assumptions, NOT chat history.

---

## Hard Rules

- DO NOT redesign the architecture
- DO NOT expand scope beyond MVP
- DO NOT rewrite working code unnecessarily
- DO NOT modify unrelated files
- DO NOT introduce new patterns without justification
- DO NOT build features outside the current slice
- DO NOT rely on chat history — rely on repo

---

## Required Workflow

Always follow this sequence:

1. Analyze task
2. Identify affected files
3. Propose implementation plan
4. Wait (if needed) or proceed stepwise
5. Implement in SMALL changes
6. Provide test or smoke-test instructions
7. Propose documentation updates

---

## Implementation Rules

- Prefer minimal patches over rewrites
- Respect existing structure and modules
- Keep processors stateless
- Keep jobs stateful
- Do not bypass approval flow
- Use existing integration patterns (adapter/factory)
- Maintain multi-tenant (`X-Tenant-ID`)

---

## Testing Rules

Every change must include:

- Either:
  - updated tests
  - OR clear manual test steps

Never leave logic unverified.

---

## Documentation Rules

If your changes affect behavior, you MUST update:

- `docs/01-current-truth.md` — when something is verified
- `docs/06-backlog.md` — when a task is completed or added
- `docs/07-decisions.md` — when a locked decision is referenced or a new one is made

Do not update `docs/00-master-plan.md` as part of an execution task.

---

## Scope Discipline

Focus ONLY on:

- current slice (from handoff)
- minimal necessary functionality
- working end-to-end flow

Avoid:
- feature creep
- premature optimization
- "while I'm here" changes

---

## What NOT to Do

- No full refactors
- No broad rewrites
- No frontend expansion unless explicitly requested
- No silent config changes
- No breaking existing flows

---

## Expected Output Format

When responding:

1. Affected files
2. Plan
3. Implementation (code)
4. Test instructions
5. Docs updates

---

## Mindset

You are not designing a system.

You are **executing a controlled build of an existing system**.

Focus on:
- stability
- clarity
- incremental progress
- working software