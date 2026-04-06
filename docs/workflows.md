# Workflows

## Base Pipeline


INTAKE → CLASSIFICATION


---

## Lead Flow


ENTITY_EXTRACTION
→ LEAD
→ DECISIONING
→ POLICY

IF auto:
→ ACTION_DISPATCH

IF approval:
→ HUMAN_HANDOFF → APPROVAL_DISPATCH

IF manual:
→ HUMAN_HANDOFF


---

## Invoice Flow


ENTITY_EXTRACTION
→ INVOICE
→ POLICY

→ HUMAN_HANDOFF


---

## Approval Resume Flow

After approval:


APPROVAL_ENGINE
→ ACTION_DISPATCH
→ COMPLETED


---

## Important Behavior

- No re-running pipeline after approval
- No actions before approval
- Always auditable

---