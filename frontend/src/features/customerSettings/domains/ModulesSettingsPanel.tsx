type Props = {
  capabilities: string[]
  effectiveCapabilities: Array<{ key: string; label_sv: string }>
  serviceProfile: Record<string, unknown>
  canWrite: boolean
  onCapabilitiesChange: (capabilities: string[]) => void
  onServiceProfileChange: (profile: Record<string, unknown>) => void
}

export function ModulesSettingsPanel({
  capabilities,
  effectiveCapabilities,
  serviceProfile,
  canWrite,
  onCapabilitiesChange,
  onServiceProfileChange,
}: Props) {
  const selectedProfiles = Array.isArray(serviceProfile.selected_profiles)
    ? (serviceProfile.selected_profiles as string[])
    : []

  const toggleCapability = (key: string) => {
    if (!canWrite) return
    if (capabilities.includes(key)) {
      onCapabilitiesChange(capabilities.filter((item) => item !== key))
      return
    }
    onCapabilitiesChange([...capabilities, key])
  }

  const toggleProfile = (profileKey: string) => {
    if (!canWrite) return
    const next = selectedProfiles.includes(profileKey)
      ? selectedProfiles.filter((item) => item !== profileKey)
      : [...selectedProfiles, profileKey]
    onServiceProfileChange({ ...serviceProfile, selected_profiles: next })
  }

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-body font-medium text-text-primary">Aktiva capabilities</h3>
        <p className="mt-1 text-body-small text-text-secondary">
          Modulval väljer inte integrationsleverantör automatiskt.
        </p>
        <ul className="mt-3 space-y-2">
          {effectiveCapabilities.map((capability) => (
            <li key={capability.key}>
              <label className="flex min-h-11 items-center gap-2 rounded-md border border-border px-3 py-2">
                <input
                  type="checkbox"
                  checked={capabilities.includes(capability.key)}
                  disabled={!canWrite}
                  onChange={() => toggleCapability(capability.key)}
                />
                <span className="text-body text-text-primary">{capability.label_sv}</span>
              </label>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h3 className="text-body font-medium text-text-primary">Serviceprofiler</h3>
        <p className="mt-1 text-body-small text-text-secondary">
          Välj vilka serviceprofiler som gäller för kunden.
        </p>
        <ul className="mt-3 space-y-2">
          {["invoice_generic", "lead_generic", "support_generic"].map((profileKey) => (
            <li key={profileKey}>
              <label className="flex min-h-11 items-center gap-2 rounded-md border border-border px-3 py-2">
                <input
                  type="checkbox"
                  checked={selectedProfiles.includes(profileKey)}
                  disabled={!canWrite}
                  onChange={() => toggleProfile(profileKey)}
                />
                <span className="text-body text-text-primary">{profileKey}</span>
              </label>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
