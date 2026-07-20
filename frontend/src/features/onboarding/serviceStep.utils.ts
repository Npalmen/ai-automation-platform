import type { RegistryServiceProfile } from "./types"

export type ServiceGroup = {
  title: string
  items: RegistryServiceProfile[]
}

export function groupServiceProfiles(
  profiles: RegistryServiceProfile[],
  options: {
    selected: string[]
    recommended: string[]
    industries: string[]
    capabilities: string[]
  },
): { recommended: ServiceGroup; selected: ServiceGroup; all: ServiceGroup } {
  const { selected, recommended, industries, capabilities } = options
  const available = profiles.filter((p) => p.supported_in_current_slice)

  const isCompatible = (profile: RegistryServiceProfile): boolean => {
    const mods = profile.module_keys ?? profile.capability_dependencies ?? []
    const inds = profile.industry_keys ?? []
    const modOk = !capabilities.length || mods.some((m) => capabilities.includes(m))
    const indOk =
      !industries.length || inds.some((i) => industries.includes(i)) || industries.includes("other")
    return modOk && indOk
  }

  const recommendedItems = available.filter(
    (p) => recommended.includes(p.key) && !selected.includes(p.key),
  )
  const selectedItems = available.filter((p) => selected.includes(p.key))
  const allItems = available.filter(
    (p) => !selected.includes(p.key) && !recommended.includes(p.key),
  )

  return {
    recommended: { title: "Rekommenderade", items: recommendedItems },
    selected: { title: "Valda", items: selectedItems },
    all: {
      title: "Alla tillgängliga",
      items: allItems.map((p) => ({
        ...p,
        _incompatible: !isCompatible(p),
      })) as RegistryServiceProfile[],
    },
  }
}

export function recommendedProfileKeys(
  capabilities: string[],
  industries: string[],
  industriesRegistry: Array<{ key: string; suggested_service_keys: string[] }>,
): string[] {
  const keys = new Set<string>()
  for (const cap of capabilities) {
    // capability hints handled server-side; use industry suggestions
    void cap
  }
  for (const ind of industries) {
    const def = industriesRegistry.find((i) => i.key === ind)
    for (const k of def?.suggested_service_keys ?? []) {
      keys.add(k)
    }
  }
  return [...keys]
}
