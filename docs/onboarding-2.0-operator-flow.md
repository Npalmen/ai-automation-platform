# Onboarding 2.0 — Operator flow (integrations & routing)

> Governed by `docs/00-master-plan.md`. Slice B (`feature/integration-selection-slice-b`).

## Integrations step — separation of concerns

| Layer | What the operator does | Stored in |
|-------|------------------------|-----------|
| **Selection** | Ej aktuell / Valfri / Obligatorisk per integration | `settings.integrations.selections` (SoT after activation) |
| **Group implementation** | Ekonomidestination: Visma eller manuell ekonomirouting | `group_implementations.finance_destination` in onboarding integrations draft |
| **Connection** | OAuth / API credentials | `oauth_credentials`, integration draft `requested` flags |
| **Verification** | Explicit verify action | `onboarding_integration_verifications` |
| **Runtime write** | Enabled only when selection + verification + credential | `settings.integrations.enabled_external_writes` |

**Rule (DEC-037):** Changing selection does **not** connect, verify, or enable external writes.

## Finance destination (`finance_destination`)

Shown in **Ekonomi** category above Visma connection card.

| Choice | Effect |
|--------|--------|
| Visma | Clears `group_implementations.finance_destination`; Visma tri-state unchanged by group logic |
| Manuell ekonomirouting | Sets `manual_accounting_routing`; requires **explicit** `visma_disposition`: `not_selected` or `selected_optional` |
| Fortnox / Bokio | Disabled (`Kommer senare`) — no PATCH |

### Visma disposition dialog

When switching to manuell ekonomirouting the operator must choose what happens to Visma **selection** (not credential):

- **Ej aktuell** → `visma.selection_status = not_selected`
- **Valfri** → `visma.selection_status = selected_optional`

Visma OAuth credentials are **never deleted** on this switch. Local unlink is a separate explicit action.

### Manual routing readiness

`manual_accounting_routing` satisfies module group `finance_destination` only when:

- `invoice_handling` capability is active, and
- at least one invoice profile (e.g. `invoice_generic`) routes to `finance` or `invoice`

Otherwise readiness blocks with `group:finance_destination`. UI links to Routing step (`?step=routing`).

## Tri-state per integration

- Categories on Swedish labels (E-post, Ekonomi, …)
- Fortnox/Bokio hidden from cards (handled in finance destination panel)
- Visma card remains for connection/verification only

## Roles

- `operations` / `admin`: PATCH integrations draft
- `read_only`: read step GET; PATCH → 403

## Slice C boundary

Customer self-service settings (`CustomerSettingsPage`) and transactional multi-section edits are **not** in Slice B. Slice B is operator onboarding wizard only.
