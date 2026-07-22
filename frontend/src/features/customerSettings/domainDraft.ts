import type { CustomerSettingsAggregate } from "./types"

export type IntegrationsDraft = {
  selections: Record<string, { selection_status: string; migration_review_required?: boolean }>
  financeChoice: "visma" | "manual_accounting_routing" | "none"
  vismaDisposition: "not_selected" | "selected_optional" | null
}

export type ModulesDraft = {
  capabilities: string[]
  serviceProfile: Record<string, unknown>
}

export type DomainDraftState = {
  identity: Record<string, unknown>
  modules: ModulesDraft
  integrations: IntegrationsDraft
  routing: Record<string, unknown>
  automation: Record<string, unknown>
}

export function createDraftsFromAggregate(data: CustomerSettingsAggregate): DomainDraftState {
  const integrationsDomain = data.domains.integrations ?? {}
  const storedSelections =
    (integrationsDomain.selections as Record<string, { selection_status: string }> | undefined) ?? {}
  const finance = data.integration_group_status.finance_destination as Record<string, unknown>
  const activeImpl = String(finance.active_implementation ?? "none")
  const servicesDomain = data.domains.services ?? {}

  return {
    identity: { ...data.domains.identity },
    modules: {
      capabilities: [...((data.domains.modules?.capabilities as string[] | undefined) ?? [])],
      serviceProfile: {
        ...((servicesDomain.service_profile as Record<string, unknown> | undefined) ??
          servicesDomain),
      },
    },
    integrations: {
      selections: Object.fromEntries(
        data.integration_selection_view.map((item) => [
          item.integration_key,
          {
            selection_status:
              storedSelections[item.integration_key]?.selection_status ?? item.selection_status,
            migration_review_required: item.migration_review_required,
          },
        ]),
      ),
      financeChoice:
        activeImpl === "manual_accounting_routing"
          ? "manual_accounting_routing"
          : activeImpl === "visma"
            ? "visma"
            : "none",
      vismaDisposition: null,
    },
    routing: { ...(data.domains.routing ?? {}) },
    automation: {
      ...((data.domains.automation?.policy as Record<string, unknown> | undefined) ?? {}),
    },
  }
}

function stableJson(value: unknown): string {
  return JSON.stringify(value)
}

export function isIdentityDirty(draft: DomainDraftState, original: DomainDraftState): boolean {
  return stableJson(draft.identity) !== stableJson(original.identity)
}

export function isModulesDirty(draft: DomainDraftState, original: DomainDraftState): boolean {
  return (
    stableJson(draft.modules.capabilities) !== stableJson(original.modules.capabilities) ||
    stableJson(draft.modules.serviceProfile) !== stableJson(original.modules.serviceProfile)
  )
}

export function isIntegrationsDirty(draft: DomainDraftState, original: DomainDraftState): boolean {
  return stableJson(draft.integrations) !== stableJson(original.integrations)
}

export function isRoutingDirty(draft: DomainDraftState, original: DomainDraftState): boolean {
  return stableJson(draft.routing) !== stableJson(original.routing)
}

export function isAutomationDirty(draft: DomainDraftState, original: DomainDraftState): boolean {
  return stableJson(draft.automation) !== stableJson(original.automation)
}

export function dirtyTabsForDraft(
  draft: DomainDraftState,
  original: DomainDraftState,
): Set<string> {
  const tabs = new Set<string>()
  if (isIdentityDirty(draft, original)) tabs.add("identity")
  if (isModulesDirty(draft, original)) tabs.add("modules")
  if (isIntegrationsDirty(draft, original)) tabs.add("integrations")
  if (isRoutingDirty(draft, original)) tabs.add("routing")
  if (isAutomationDirty(draft, original)) tabs.add("automation")
  return tabs
}

export function buildIdentityPatchPayload(draft: DomainDraftState): Record<string, unknown> {
  const payload = { ...draft.identity }
  delete payload.slug
  delete payload.tenant_status
  return payload
}

export function buildModulesPatchPayload(draft: DomainDraftState): Record<string, unknown> {
  return { capabilities: draft.modules.capabilities }
}

export function buildServicesPatchPayload(draft: DomainDraftState): Record<string, unknown> {
  return { service_profile: draft.modules.serviceProfile }
}

export function buildIntegrationsPatchPayload(
  draft: DomainDraftState,
  original?: DomainDraftState,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  const selections: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(draft.integrations.selections)) {
    const originalStatus = original?.integrations.selections[key]?.selection_status
    if (!original || originalStatus !== value.selection_status) {
      selections[key] = { selection_status: value.selection_status }
    }
  }
  if (Object.keys(selections).length > 0) {
    payload.selections = selections
  }
  if (
    !original ||
    draft.integrations.financeChoice !== original.integrations.financeChoice ||
    draft.integrations.vismaDisposition !== original.integrations.vismaDisposition
  ) {
    if (draft.integrations.financeChoice === "visma") {
      payload.finance_destination = { choice: "visma" }
    } else if (draft.integrations.financeChoice === "manual_accounting_routing") {
      payload.finance_destination = {
        choice: "manual_accounting_routing",
        visma_disposition: draft.integrations.vismaDisposition ?? "not_selected",
      }
    }
  }
  return payload
}

export function buildRoutingPatchPayload(draft: DomainDraftState): Record<string, unknown> {
  return { routing: draft.routing }
}

export function buildAutomationPatchPayload(draft: DomainDraftState): Record<string, unknown> {
  return { ...draft.automation }
}

export function buildPreviewPayloadForDomain(
  domain: string,
  draft: DomainDraftState,
): Record<string, unknown> {
  switch (domain) {
    case "modules":
      return buildModulesPatchPayload(draft)
    case "services":
      return buildServicesPatchPayload(draft)
    case "integrations":
      return buildIntegrationsPatchPayload(draft)
    case "routing":
      return buildRoutingPatchPayload(draft)
    case "automation":
      return buildAutomationPatchPayload(draft)
    default:
      return {}
  }
}

export const TAB_SAVE_DOMAINS: Record<string, string[]> = {
  identity: ["identity"],
  modules: ["modules", "services"],
  integrations: ["integrations"],
  routing: ["routing"],
  automation: ["automation"],
  readiness: [],
}
