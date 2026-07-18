import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"

import { CriticalActionDialog } from "@/components/operator/CriticalActionDialog"
import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/features/auth/AuthProvider"

import { IntegrationsStepPanel } from "./IntegrationsStepPanel"
import {
  formatOnboardingError,
  useActivateOnboardingMutation,
  useCancelOnboardingMutation,
  usePatchAutomationMutation,
  usePatchDataStartMutation,
  usePatchIdentityMutation,
  usePatchModulesMutation,
  usePatchRoutingMutation,
  usePatchServiceProfileMutation,
  usePreviewRoutingMutation,
  useResetRoutingMutation,
  useRunReadinessMutation,
} from "./mutations"
import {
  findOpenSessionForTenant,
  useActivationPlanQuery,
  useDataStartStepQuery,
  useOnboardingRegistriesQuery,
  useOnboardingSessionQuery,
  useOnboardingSessionsQuery,
  useRoutingStepQuery,
  useServiceProfileStepQuery,
} from "./queries"
import { WIZARD_STEPS, type EffectiveRouteRow, type ReadinessResult } from "./types"
import {
  hasUnsavedRoutingDraft,
  mergeRoutingPreviewRows,
  routingSourceLabel,
  type RoutingPreviewDisplayRow,
} from "./routingStep.utils"

const inputClassName =
  "min-h-11 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"

function oauthReturnNotice(): string | null {
  const params = new URLSearchParams(window.location.search)
  const oauth = params.get("oauth")
  if (oauth === "complete") {
    return "OAuth slutförd. Uppdatera status och verifiera integrationen."
  }
  if (oauth === "error") {
    return "OAuth misslyckades. Försök koppla om integrationen."
  }
  return null
}

type LeadFieldMode = "required" | "optional" | "inherit"

function stepVariant(status: string): "healthy" | "warning" | "failed" | "paused" | "unknown" {
  if (status === "completed" || status === "not_applicable") return "healthy"
  if (status === "blocked" || status === "not_implemented") return "failed"
  if (status === "in_progress") return "warning"
  return "unknown"
}

export function OnboardingWizardPage() {
  const { tenantId } = useParams<{ tenantId: string }>()
  const navigate = useNavigate()
  const { auth } = useAuth()
  const registriesQuery = useOnboardingRegistriesQuery()
  const sessionsQuery = useOnboardingSessionsQuery(true)
  const openSession = findOpenSessionForTenant(sessionsQuery.data, tenantId ?? "")
  const sessionId = openSession?.id
  const sessionQuery = useOnboardingSessionQuery(sessionId)
  const session = sessionQuery.data
  const registries = registriesQuery.data

  const [activeStep, setActiveStep] = useState("identity")
  const [companyName, setCompanyName] = useState("")
  const [slug, setSlug] = useState("")
  const [capabilities, setCapabilities] = useState<string[]>([])
  const [integrations, setIntegrations] = useState<string[]>([])
  const [presetKey, setPresetKey] = useState("observe_only")
  const [presetVersion, setPresetVersion] = useState(1)
  const [readiness, setReadiness] = useState<ReadinessResult | null>(null)
  const [acknowledgedWarnings, setAcknowledgedWarnings] = useState<string[]>([])
  const [activateOpen, setActivateOpen] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [confirmationPhrase, setConfirmationPhrase] = useState("")
  const [selectedProfiles, setSelectedProfiles] = useState<string[]>([])
  const [leadRequirements, setLeadRequirements] = useState<
    Record<string, Record<string, LeadFieldMode>>
  >({})
  const [routeOverrides, setRouteOverrides] = useState<Record<string, string | null>>({})
  const [routingPreviewRows, setRoutingPreviewRows] = useState<RoutingPreviewDisplayRow[] | null>(
    null,
  )
  const [dataStartMode, setDataStartMode] = useState<"new_incoming_only">("new_incoming_only")

  const planQuery = useActivationPlanQuery(sessionId, activeStep === "review")
  const serviceProfileQuery = useServiceProfileStepQuery(
    sessionId,
    activeStep === "service_profile" || activeStep === "routing",
  )
  const routingQuery = useRoutingStepQuery(sessionId, activeStep === "routing")
  const dataStartQuery = useDataStartStepQuery(sessionId, activeStep === "data_start")

  const identityMutation = usePatchIdentityMutation(sessionId ?? "")
  const modulesMutation = usePatchModulesMutation(sessionId ?? "")
  const automationMutation = usePatchAutomationMutation(sessionId ?? "")
  const serviceProfileMutation = usePatchServiceProfileMutation(sessionId ?? "")
  const routingMutation = usePatchRoutingMutation(sessionId ?? "")
  const previewRoutingMutation = usePreviewRoutingMutation(sessionId ?? "")
  const resetRoutingMutation = useResetRoutingMutation(sessionId ?? "")
  const dataStartMutation = usePatchDataStartMutation(sessionId ?? "")
  const readinessMutation = useRunReadinessMutation(sessionId ?? "")
  const activateMutation = useActivateOnboardingMutation(sessionId ?? "")
  const cancelMutation = useCancelOnboardingMutation(sessionId ?? "")

  useEffect(() => {
    if (!session) return
    setCompanyName(session.company_name ?? "")
    setSlug(session.slug ?? "")
    setCapabilities(session.capabilities ?? [])
    setIntegrations(session.integrations ?? [])
    if (session.preset_key) setPresetKey(session.preset_key)
    if (session.preset_version) setPresetVersion(session.preset_version)
  }, [session])

  useEffect(() => {
    if (!session) return
    setActiveStep(session.current_step || "identity")
  }, [session?.id])

  useEffect(() => {
    if (!serviceProfileQuery.data) return
    const draft = serviceProfileQuery.data.draft as {
      selected_profiles?: string[]
      lead_requirements?: Record<string, Record<string, LeadFieldMode>>
    }
    setSelectedProfiles(draft.selected_profiles ?? [])
    setLeadRequirements(draft.lead_requirements ?? {})
  }, [serviceProfileQuery.data])

  useEffect(() => {
    if (!routingQuery.data) return
    const draft = routingQuery.data.draft as { route_overrides?: Record<string, string | null> }
    setRouteOverrides(draft.route_overrides ?? {})
    setRoutingPreviewRows(null)
  }, [routingQuery.data])

  useEffect(() => {
    if (!dataStartQuery.data) return
    const draft = dataStartQuery.data.draft as { mode?: "new_incoming_only" }
    if (draft.mode) setDataStartMode(draft.mode)
  }, [dataStartQuery.data])

  const role = auth.status === "authenticated" ? auth.operator.role : null

  const isAdmin = role === "admin"
  const canWrite = role === "operations" || role === "admin"
  const registryReady = registriesQuery.isSuccess && Boolean(registries)

  const registryCapabilityKeys = useMemo(
    () => new Set(registries?.product_capabilities.map((item) => item.key) ?? []),
    [registries],
  )

  const presetOptions = useMemo(() => {
    if (!registries) return []
    const byKey = new Map<string, (typeof registries.automation_presets)[number]>()
    for (const preset of registries.automation_presets) {
      const existing = byKey.get(preset.key)
      if (!existing || preset.version > existing.version) {
        byKey.set(preset.key, preset)
      }
    }
    return Array.from(byKey.values())
  }, [registries])

  const modulesInvalid =
    (session?.legacy_capability_keys.length ?? 0) > 0 ||
    session?.legacy_preset ||
    capabilities.some((key) => !registryCapabilityKeys.has(key))

  const automationInvalid =
    session?.legacy_preset ||
    !presetOptions.some((item) => item.key === presetKey && item.version === presetVersion)

  const currentStepIndex = useMemo(
    () => WIZARD_STEPS.findIndex((step) => step.key === activeStep),
    [activeStep],
  )

  if (registriesQuery.isLoading || sessionsQuery.isLoading || sessionQuery.isLoading) {
    return <LoadingState label="Laddar onboarding…" rows={4} />
  }

  if (registriesQuery.isError || !registries) {
    return (
      <ErrorState
        title="Kunde inte ladda register"
        description="Produktregister kunde inte hämtas. Onboarding kan inte fortsätta utan registerdata."
        technicalDetails={
          registriesQuery.error instanceof Error
            ? registriesQuery.error.message
            : String(registriesQuery.error)
        }
      />
    )
  }

  if (!tenantId || !sessionId || !session) {
    return (
      <ErrorState
        title="Ingen öppen onboarding"
        description="Det finns ingen aktiv onboarding-session för denna kund."
        recommendedAction="Starta en ny onboarding från kundlistan."
      />
    )
  }

  if (session.status === "active") {
    return (
      <div className="space-y-4">
        <PageHeader title="Onboarding klar" description="Kunden är redan aktiverad." />
        <Button onClick={() => navigate(`/customers/${encodeURIComponent(tenantId)}`)}>
          Öppna kunddetalj
        </Button>
      </div>
    )
  }

  async function saveIdentity() {
    await identityMutation.mutateAsync({
      version: session!.version,
      company_name: companyName.trim(),
      slug: slug.trim(),
    })
    setActiveStep("modules")
  }

  async function saveModules() {
    await modulesMutation.mutateAsync({
      version: session!.version,
      capabilities,
      integrations,
    })
    setActiveStep("automation")
  }

  async function saveAutomation() {
    const preset = presetOptions.find((item) => item.key === presetKey)
    await automationMutation.mutateAsync({
      version: session!.version,
      preset_key: presetKey,
      preset_version: preset?.version ?? presetVersion,
    })
    setActiveStep("service_profile")
  }

  async function saveServiceProfile() {
    await serviceProfileMutation.mutateAsync({
      version: session!.version,
      selected_profiles: selectedProfiles,
      lead_requirements: leadRequirements,
    })
    setActiveStep("routing")
  }

  async function saveRouting() {
    await routingMutation.mutateAsync({
      version: session!.version,
      route_overrides: routeOverrides,
    })
    setRoutingPreviewRows(null)
    setActiveStep("integrations")
  }

  async function previewRouting() {
    const savedDraft = (
      routingQuery.data?.draft as { route_overrides?: Record<string, string | null> } | undefined
    )?.route_overrides
    if (hasUnsavedRoutingDraft(savedDraft, routeOverrides)) {
      return
    }
    const result = await previewRoutingMutation.mutateAsync()
    const effectiveRoutes = (
      routingQuery.data?.effective as { routes?: EffectiveRouteRow[] } | undefined
    )?.routes
    setRoutingPreviewRows(mergeRoutingPreviewRows(result.preview, effectiveRoutes))
  }

  async function resetRoutingOverride(profileKey: string) {
    const savedHasOverride = Object.prototype.hasOwnProperty.call(
      savedRouteOverrides ?? {},
      profileKey,
    )
    if (savedHasOverride && session) {
      await resetRoutingMutation.mutateAsync({
        version: session.version,
        service_types: [profileKey],
      })
      setReadiness(null)
      setRoutingPreviewRows(null)
      return
    }
    setRouteOverrides((current) => {
      const next = { ...current }
      delete next[profileKey]
      return next
    })
    setRoutingPreviewRows(null)
  }

  function resetLeadFieldToInherit(profileKey: string, fieldKey: string) {
    setLeadRequirements((current) => {
      const profileFields = { ...(current[profileKey] ?? {}) }
      delete profileFields[fieldKey]
      const next = { ...current }
      if (Object.keys(profileFields).length === 0) {
        delete next[profileKey]
      } else {
        next[profileKey] = profileFields
      }
      return next
    })
  }

  function routeDestinationLabel(routeKey: string | null | undefined): string {
    if (!routeKey) return "—"
    return registries?.routing_destinations.find((item) => item.key === routeKey)?.label ?? routeKey
  }

  const savedRouteOverrides = (
    routingQuery.data?.draft as { route_overrides?: Record<string, string | null> } | undefined
  )?.route_overrides
  const routingHasUnsavedChanges = hasUnsavedRoutingDraft(savedRouteOverrides, routeOverrides)
  const effectiveRoutes = (
    routingQuery.data?.effective as { routes?: EffectiveRouteRow[] } | undefined
  )?.routes

  async function saveDataStart() {
    await dataStartMutation.mutateAsync({
      version: session!.version,
      mode: dataStartMode,
    })
    setActiveStep("readiness")
  }

  async function runReadiness() {
    const result = await readinessMutation.mutateAsync()
    setReadiness(result)
    setAcknowledgedWarnings([])
    setActiveStep("readiness")
  }

  function toggleWarning(id: string) {
    setAcknowledgedWarnings((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    )
  }

  const warningsComplete =
    readiness?.overall_status !== "ready_with_warnings" ||
    (readiness.warnings.length > 0 &&
      readiness.warnings.every((warning) => acknowledgedWarnings.includes(warning.id)))

  const activationPlan = planQuery.data
  const canActivate =
    Boolean(readiness) &&
    (readiness?.overall_status === "ready" ||
      readiness?.overall_status === "ready_with_warnings") &&
    warningsComplete &&
    confirmationPhrase === slug &&
    Boolean(activationPlan?.plan_hash) &&
    !planQuery.isLoading

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title={session.company_name ?? "Kundonboarding"}
        description={`Tenant ${session.tenant_id} · register ${registries.registry_revision.slice(0, 8)}`}
      />

      <div className="grid min-w-0 gap-6 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav className="min-w-0 space-y-1 rounded-lg border border-border bg-surface p-3">
          {WIZARD_STEPS.map((step, index) => (
            <button
              key={step.key}
              type="button"
              onClick={() => setActiveStep(step.key)}
              className={`flex w-full min-w-0 items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-body-small ${
                activeStep === step.key
                  ? "bg-surface-subtle font-medium text-text-primary"
                  : "text-text-secondary hover:bg-surface-subtle"
              }`}
            >
              <span className="min-w-0 break-words">
                {index + 1}. {step.label}
              </span>
              <StatusBadge
                variant={stepVariant(
                  session.steps.find((item) => item.step_key === step.key)?.step_status ??
                    "unknown",
                )}
                label=""
              />
            </button>
          ))}
        </nav>

        <section className="min-w-0 space-y-4 rounded-lg border border-border bg-surface p-4 sm:p-6">
          {activeStep === "identity" ? (
            <div className="space-y-4">
              <h2 className="text-section-title text-text-primary">Identitet</h2>
              <label className="block space-y-2">
                <span className="text-label">Företagsnamn</span>
                <input
                  className={inputClassName}
                  value={companyName}
                  onChange={(event) => setCompanyName(event.target.value)}
                  disabled={!canWrite}
                />
              </label>
              <label className="block space-y-2">
                <span className="text-label">Slug</span>
                <input
                  className={inputClassName}
                  value={slug}
                  onChange={(event) => setSlug(event.target.value)}
                  disabled={!canWrite}
                />
              </label>
            </div>
          ) : null}

          {activeStep === "modules" ? (
            <div className="space-y-4">
              <h2 className="text-section-title text-text-primary">Produktkapabiliteter</h2>
              {(session.legacy_capability_keys ?? []).map((key) => (
                <div
                  key={key}
                  className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface-subtle px-3 py-2"
                >
                  <span className="text-body text-text-primary">{key}</span>
                  <StatusBadge variant="warning" label="Legacy — inte längre valbar" />
                </div>
              ))}
              <div className="space-y-2">
                {registries.product_capabilities.map((option) => (
                  <label key={option.key} className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={capabilities.includes(option.key)}
                      disabled={!canWrite || !registryReady}
                      onChange={(event) => {
                        setCapabilities((current) =>
                          event.target.checked
                            ? [...current, option.key]
                            : current.filter((item) => item !== option.key),
                        )
                      }}
                    />
                    <span className="text-body text-text-primary">{option.label}</span>
                  </label>
                ))}
              </div>
              {modulesInvalid ? (
                <p className="text-body-small text-status-danger">
                  Ogiltig sparad konfiguration måste uppdateras innan sparning.
                </p>
              ) : null}
            </div>
          ) : null}

          {activeStep === "automation" ? (
            <div className="space-y-4">
              <h2 className="text-section-title text-text-primary">Automation preset</h2>
              {session.legacy_preset && session.preset_key ? (
                <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-surface-subtle px-3 py-2">
                  <span className="text-body text-text-primary">
                    {session.preset_key} v{session.preset_version ?? "?"}
                  </span>
                  <StatusBadge variant="warning" label="Legacy — inte längre valbar" />
                </div>
              ) : null}
              <select
                className={inputClassName}
                value={presetKey}
                disabled={!canWrite || !registryReady}
                onChange={(event) => {
                  const nextKey = event.target.value
                  const preset = presetOptions.find((item) => item.key === nextKey)
                  setPresetKey(nextKey)
                  if (preset) setPresetVersion(preset.version)
                }}
              >
                {presetOptions.map((option) => (
                  <option key={`${option.key}-${option.version}`} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
              {automationInvalid ? (
                <p className="text-body-small text-status-danger">
                  Ogiltig sparad konfiguration måste uppdateras innan sparning.
                </p>
              ) : null}
            </div>
          ) : null}

          {activeStep === "service_profile" ? (
            <div className="space-y-4">
              <h2 className="text-section-title text-text-primary">Serviceprofil</h2>
              {serviceProfileQuery.isLoading ? (
                <LoadingState label="Laddar serviceprofil…" rows={3} />
              ) : (
                <>
                  <p className="text-body-small text-text-secondary">
                    Välj profiler och justera lead-fältkrav per profil.
                  </p>
                  <div className="space-y-2">
                    {registries.service_profiles
                      .filter((p) => p.supported_in_current_slice)
                      .map((profile) => (
                        <label key={profile.key} className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            checked={selectedProfiles.includes(profile.key)}
                            disabled={!canWrite}
                            onChange={(event) => {
                              setSelectedProfiles((current) =>
                                event.target.checked
                                  ? [...current, profile.key]
                                  : current.filter((item) => item !== profile.key),
                              )
                            }}
                          />
                          <span className="text-body text-text-primary">
                            {profile.label}
                            <span className="block text-body-small text-text-secondary">
                              {profile.description}
                            </span>
                          </span>
                        </label>
                      ))}
                  </div>
                  {selectedProfiles.map((profileKey) => {
                    const profile = registries.service_profiles.find((p) => p.key === profileKey)
                    if (!profile) return null
                    const fields = [
                      ...profile.required_fields_summary,
                      ...profile.optional_fields_summary,
                    ]
                    return (
                      <div
                        key={profileKey}
                        className="rounded-md border border-border bg-surface-subtle p-3"
                      >
                        <h3 className="mb-2 text-label text-text-primary">{profile.label}</h3>
                        <div className="space-y-2">
                          {fields.map((fieldKey) => {
                            const fieldLabel =
                              registries.lead_field_registry.find((f) => f.key === fieldKey)
                                ?.label ?? fieldKey
                            const mode =
                              leadRequirements[profileKey]?.[fieldKey] ?? "inherit"
                            const platformDefault = profile.required_fields_summary.includes(
                              fieldKey,
                            )
                              ? "obligatoriskt"
                              : "valfritt"
                            return (
                              <div
                                key={`${profileKey}-${fieldKey}`}
                                className="flex min-w-0 flex-wrap items-center gap-2 text-body-small"
                              >
                                <span className="min-w-0 flex-1 break-words text-text-secondary">
                                  {fieldLabel}
                                </span>
                                <select
                                  className="min-w-0 max-w-full rounded border border-border bg-page px-2 py-1"
                                  value={mode}
                                  disabled={!canWrite}
                                  onChange={(event) => {
                                    const next = event.target.value as LeadFieldMode
                                    setLeadRequirements((current) => ({
                                      ...current,
                                      [profileKey]: {
                                        ...(current[profileKey] ?? {}),
                                        [fieldKey]: next,
                                      },
                                    }))
                                  }}
                                >
                                  <option value="inherit">Ärv plattformsdefault</option>
                                  <option value="required">Obligatoriskt</option>
                                  <option value="optional">Valfritt</option>
                                </select>
                                {mode !== "inherit" && canWrite ? (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    className="shrink-0"
                                    onClick={() => resetLeadFieldToInherit(profileKey, fieldKey)}
                                  >
                                    Återställ till standard ({platformDefault})
                                  </Button>
                                ) : null}
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
                </>
              )}
            </div>
          ) : null}

          {activeStep === "routing" ? (
            <div className="min-w-0 space-y-4">
              <h2 className="text-section-title text-text-primary">Intern routing</h2>
              {routingQuery.isLoading ? (
                <LoadingState label="Laddar routing…" rows={3} />
              ) : selectedProfiles.length === 0 ? (
                <p className="text-body-small text-text-secondary">
                  Välj minst en serviceprofil först.
                </p>
              ) : (
                <>
                  <p className="text-body-small text-text-secondary">
                    Sätt tenant-override per profil eller låt plattformsstandard gälla. Preview är
                    read-only och gör inga externa anrop.
                  </p>
                  <div className="space-y-3">
                    {selectedProfiles.map((profileKey) => {
                      const profile = registries.service_profiles.find((p) => p.key === profileKey)
                      const savedRoute = effectiveRoutes?.find(
                        (row) => row.service_type === profileKey,
                      )
                      const hasOverride = Object.prototype.hasOwnProperty.call(
                        routeOverrides,
                        profileKey,
                      )
                      const platformDefault = savedRoute?.platform_default ?? null
                      return (
                        <div
                          key={profileKey}
                          className="min-w-0 rounded-md border border-border bg-surface-subtle p-3"
                        >
                          <p className="break-words text-body text-text-primary">
                            {profile?.label ?? profileKey}
                          </p>
                          {savedRoute ? (
                            <p className="text-body-small text-text-secondary">
                              Sparad effektiv route: {routeDestinationLabel(savedRoute.effective)} (
                              {routingSourceLabel(savedRoute.source)})
                            </p>
                          ) : null}
                          <div className="mt-2 flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
                            <select
                              className={`${inputClassName} min-w-0`}
                              value={routeOverrides[profileKey] ?? ""}
                              disabled={!canWrite}
                              onChange={(event) => {
                                const value = event.target.value
                                setRouteOverrides((current) => {
                                  const next = { ...current }
                                  if (!value) delete next[profileKey]
                                  else next[profileKey] = value
                                  return next
                                })
                                setRoutingPreviewRows(null)
                              }}
                            >
                              <option value="">
                                Ärv plattformsstandard
                                {platformDefault
                                  ? ` (${routeDestinationLabel(platformDefault)})`
                                  : ""}
                              </option>
                              {registries.routing_destinations.map((dest) => (
                                <option key={dest.key} value={dest.key}>
                                  {dest.label}
                                </option>
                              ))}
                            </select>
                            {hasOverride && canWrite ? (
                              <Button
                                type="button"
                                variant="outline"
                                className="shrink-0"
                                disabled={resetRoutingMutation.isPending}
                                onClick={() => void resetRoutingOverride(profileKey)}
                              >
                                Återställ till standard
                                {platformDefault
                                  ? ` (${routeDestinationLabel(platformDefault)})`
                                  : ""}
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:flex-wrap">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={
                        previewRoutingMutation.isPending ||
                        routingHasUnsavedChanges ||
                        selectedProfiles.length === 0
                      }
                      onClick={() => void previewRouting()}
                    >
                      {previewRoutingMutation.isPending
                        ? "Förhandsgranskar…"
                        : "Förhandsgranska routing"}
                    </Button>
                  </div>
                  {routingHasUnsavedChanges ? (
                    <p className="text-body-small text-status-warning" role="status">
                      Spara osparade routingändringar innan preview. Preview använder endast sparad
                      draft från servern.
                    </p>
                  ) : null}
                  {previewRoutingMutation.isError ? (
                    <p className="text-body-small text-status-danger" role="alert">
                      {formatOnboardingError(previewRoutingMutation.error)}
                    </p>
                  ) : null}
                  {routingPreviewRows ? (
                    <div className="min-w-0 space-y-3 rounded-md border border-border bg-page p-3">
                      <p className="text-label text-text-primary">
                        Routing preview (read-only, mutated: false)
                      </p>
                      {routingPreviewRows.map((row) => (
                        <div
                          key={row.service_type}
                          className="min-w-0 space-y-1 border-t border-border pt-2 first:border-t-0 first:pt-0"
                        >
                          <p className="break-words text-body text-text-primary">
                            {registries.service_profiles.find((p) => p.key === row.service_type)
                              ?.label ?? row.service_type}
                          </p>
                          <p className="break-words text-body-small text-text-secondary">
                            Plattformsstandard:{" "}
                            {routeDestinationLabel(row.platform_default)}
                          </p>
                          <p className="break-words text-body-small text-text-secondary">
                            Tenant-override: {routeDestinationLabel(row.tenant_override)}
                          </p>
                          <p className="break-words text-body-small text-text-secondary">
                            Effektiv route: {routeDestinationLabel(row.effective_route)}
                          </p>
                          <p className="break-words text-body-small text-text-secondary">
                            Källa: {routingSourceLabel(row.source)}
                          </p>
                          {row.uses_fallback ? (
                            <p className="text-body-small text-status-warning">
                              Fallback till manual review används.
                            </p>
                          ) : null}
                          {row.manual_review ? (
                            <p className="text-body-small text-status-warning">
                              Manual review används.
                            </p>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              )}
            </div>
          ) : null}

          {activeStep === "data_start" ? (
            <div className="space-y-4">
              <h2 className="text-section-title text-text-primary">Datastart</h2>
              {dataStartQuery.isLoading ? (
                <LoadingState label="Laddar datastart…" rows={2} />
              ) : (
                <>
                  <p className="text-body-small text-text-secondary">
                    Cutoff sparas som metadata vid aktivering. Plattformen blockerar inte
                    tekniskt historiska mejl i denna slice (runtime enforcement: not_verifiable).
                  </p>
                  <div className="space-y-2">
                    {registries.data_start_modes
                      .filter((mode) => mode.supported_in_current_slice)
                      .map((mode) => (
                        <label key={mode.key} className="flex items-start gap-3">
                          <input
                            type="radio"
                            name="data_start_mode"
                            checked={dataStartMode === mode.key}
                            disabled={!canWrite}
                            onChange={() =>
                              setDataStartMode(mode.key as "new_incoming_only")
                            }
                          />
                          <span className="text-body text-text-primary">
                            {mode.label}
                            <span className="block text-body-small text-text-secondary">
                              {mode.description}
                            </span>
                          </span>
                        </label>
                      ))}
                  </div>
                </>
              )}
            </div>
          ) : null}

          {activeStep === "integrations" && sessionId && tenantId ? (
            <IntegrationsStepPanel
              sessionId={sessionId}
              tenantId={tenantId}
              version={session.version}
              canWrite={canWrite}
              oauthNotice={oauthReturnNotice()}
            />
          ) : null}

          {activeStep === "readiness" ? (
            <div className="space-y-4">
              <h2 className="text-section-title text-text-primary">Readiness</h2>
              <Button onClick={() => void runReadiness()} disabled={readinessMutation.isPending}>
                {readinessMutation.isPending ? "Kör…" : "Kör readiness"}
              </Button>
              {readiness ? (
                <div className="space-y-3">
                  <StatusBadge
                    variant={
                      readiness.overall_status === "ready"
                        ? "healthy"
                        : readiness.overall_status === "ready_with_warnings"
                          ? "warning"
                          : "failed"
                    }
                    label={readiness.overall_status}
                  />
                  {readiness.blocking_checks.map((check) => (
                    <p key={check.id} className="text-body-small text-status-danger">
                      {check.message}
                    </p>
                  ))}
                  {readiness.warnings.map((warning) => (
                    <label key={warning.id} className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        checked={acknowledgedWarnings.includes(warning.id)}
                        onChange={() => toggleWarning(warning.id)}
                      />
                      <span className="text-body-small text-text-secondary">
                        {warning.message}
                      </span>
                    </label>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {activeStep === "review" ? (
            <div className="space-y-4">
              <h2 className="text-section-title text-text-primary">Aktivera kund</h2>
              <p className="text-body text-text-secondary">
                Kräver admin-roll, slug-bekräftelse och färsk readiness (v
                {session.readiness_check_version}).
              </p>
              {planQuery.isLoading ? <LoadingState label="Laddar aktiveringsplan…" rows={2} /> : null}
              {planQuery.isError ? (
                <ErrorState
                  title="Kunde inte ladda aktiveringsplan"
                  description="Ladda om sidan och försök igen."
                />
              ) : null}
              {activationPlan ? (
                <div className="space-y-3 rounded-lg border border-border bg-surface-subtle p-4">
                  <p className="text-body-small text-text-secondary">
                    Plan {activationPlan.plan_id.slice(0, 12)}… · register{" "}
                    {activationPlan.registry_revision.slice(0, 8)}
                  </p>
                  {activationPlan.consequences.map((item) => (
                    <p key={item.id} className="text-body-small text-text-secondary">
                      {item.message}
                    </p>
                  ))}
                  {activationPlan.capability_states.map((state) => (
                    <p
                      key={state.capability_key}
                      className="text-body-small text-text-secondary"
                    >
                      {state.capability_key}: {state.lifecycle_state} — {state.message}
                    </p>
                  ))}
                </div>
              ) : null}
              {isAdmin ? (
                <>
                  <label className="block space-y-2">
                    <span className="text-label">Bekräfta slug</span>
                    <input
                      className={inputClassName}
                      value={confirmationPhrase}
                      onChange={(event) => setConfirmationPhrase(event.target.value)}
                      placeholder={slug}
                    />
                  </label>
                  <Button onClick={() => setActivateOpen(true)} disabled={!canActivate}>
                    Aktivera tenant
                  </Button>
                </>
              ) : (
                <p className="text-body-small text-text-secondary">
                  Endast admin kan aktivera.
                </p>
              )}
            </div>
          ) : null}

          <div className="flex min-w-0 flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:justify-between">
            <Button
              type="button"
              variant="outline"
              disabled={currentStepIndex <= 0}
              onClick={() =>
                setActiveStep(WIZARD_STEPS[Math.max(0, currentStepIndex - 1)].key)
              }
            >
              Föregående
            </Button>
            <div className="flex min-w-0 flex-wrap gap-2">
              {canWrite ? (
                <Button type="button" variant="outline" onClick={() => setCancelOpen(true)}>
                  Avbryt onboarding
                </Button>
              ) : null}
              {activeStep === "identity" ? (
                <Button onClick={() => void saveIdentity()} disabled={identityMutation.isPending}>
                  Spara &amp; fortsätt
                </Button>
              ) : null}
              {activeStep === "modules" ? (
                <Button
                  onClick={() => void saveModules()}
                  disabled={modulesMutation.isPending || modulesInvalid || !registryReady}
                >
                  Spara &amp; fortsätt
                </Button>
              ) : null}
              {activeStep === "automation" ? (
                <Button
                  onClick={() => void saveAutomation()}
                  disabled={automationMutation.isPending || automationInvalid || !registryReady}
                >
                  Spara &amp; fortsätt
                </Button>
              ) : null}
              {activeStep === "service_profile" ? (
                <Button
                  onClick={() => void saveServiceProfile()}
                  disabled={
                    serviceProfileMutation.isPending ||
                    !canWrite ||
                    selectedProfiles.length === 0
                  }
                >
                  Spara &amp; fortsätt
                </Button>
              ) : null}
              {activeStep === "routing" ? (
                <Button
                  onClick={() => void saveRouting()}
                  disabled={routingMutation.isPending || !canWrite}
                >
                  Spara &amp; fortsätt
                </Button>
              ) : null}
              {activeStep === "data_start" ? (
                <Button
                  onClick={() => void saveDataStart()}
                  disabled={dataStartMutation.isPending || !canWrite}
                >
                  Spara &amp; fortsätt
                </Button>
              ) : null}
              {activeStep === "data_start" ? (
                <Button variant="outline" onClick={() => void runReadiness()}>
                  Gå till readiness
                </Button>
              ) : null}
              {activeStep === "readiness" && readiness && warningsComplete ? (
                <Button onClick={() => setActiveStep("review")}>Gå till aktivering</Button>
              ) : null}
            </div>
          </div>
        </section>
      </div>

      <CriticalActionDialog
        open={activateOpen}
        title="Aktivera kund"
        consequence={`Tenant ${session.tenant_id} aktiveras. Skriv slug "${slug}" som bekräftelse.`}
        reasonLabel="Anledning"
        confirmationLabel="Jag bekräftar att readiness är genomförd och vill aktivera"
        primaryLabel="Aktivera"
        loading={activateMutation.isPending}
        error={
          activateMutation.isError ? formatOnboardingError(activateMutation.error) : undefined
        }
        onClose={() => {
          setActivateOpen(false)
          setConfirmationPhrase("")
          activateMutation.reset()
        }}
        onConfirm={(reason) => {
          if (!readiness || !activationPlan?.plan_hash) return
          activateMutation.mutate(
            {
              version: session.version,
              readiness_check_version: session.readiness_check_version,
              plan_hash: activationPlan.plan_hash,
              reason,
              confirmation_phrase: confirmationPhrase || slug,
              acknowledged_warning_ids: acknowledgedWarnings,
            },
            {
              onSuccess: () => {
                setActivateOpen(false)
                navigate(`/customers/${encodeURIComponent(tenantId)}`)
              },
            },
          )
        }}
      />

      <CriticalActionDialog
        open={cancelOpen}
        title="Avbryt onboarding"
        consequence="Onboarding-sessionen markeras som avbruten. Tenant förblir inactive."
        primaryLabel="Avbryt onboarding"
        loading={cancelMutation.isPending}
        error={cancelMutation.isError ? formatOnboardingError(cancelMutation.error) : undefined}
        onClose={() => {
          setCancelOpen(false)
          cancelMutation.reset()
        }}
        onConfirm={(reason) => {
          cancelMutation.mutate(
            { version: session.version, reason },
            { onSuccess: () => navigate("/customers") },
          )
        }}
      />
    </div>
  )
}
