import { useMemo, useState } from "react"
import { Link, useParams, useSearchParams } from "react-router-dom"

import { EmptyState } from "@/components/operator/EmptyState"
import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { ApiError } from "@/api/client"
import { useAuth } from "@/features/auth/AuthProvider"

import { ConflictDialog } from "./components/ConflictDialog"
import { ConsequencePreview } from "./components/ConsequencePreview"
import { ReadinessSummaryPanel } from "./components/ReadinessSummaryPanel"
import { SaveBar } from "./components/SaveBar"
import { UnsavedChangesGuard } from "./components/UnsavedChangesGuard"
import { SETTINGS_TABS } from "./constants"
import { CustomerSettingsLayout } from "./CustomerSettingsLayout"
import {
  buildAutomationPatchPayload,
  buildIdentityPatchPayload,
  buildIntegrationsPatchPayload,
  buildModulesPatchPayload,
  buildPreviewPayloadForDomain,
  buildRoutingPatchPayload,
  buildServicesPatchPayload,
  createDraftsFromAggregate,
  dirtyTabsForDraft,
  isAutomationDirty,
  isIdentityDirty,
  isIntegrationsDirty,
  isModulesDirty,
  isRoutingDirty,
  TAB_SAVE_DOMAINS,
  type DomainDraftState,
} from "./domainDraft"
import { AutomationSettingsPanel } from "./domains/AutomationSettingsPanel"
import { IdentitySettingsPanel } from "./domains/IdentitySettingsPanel"
import { IntegrationsSettingsPanel } from "./domains/IntegrationsSettingsPanel"
import { ModulesSettingsPanel } from "./domains/ModulesSettingsPanel"
import { RoutingSettingsPanel } from "./domains/RoutingSettingsPanel"
import { roleLabel } from "./formatters"
import { useCustomerSettingsPatch } from "./hooks/useCustomerSettingsPatch"
import { useCustomerSettingsPreview } from "./hooks/useCustomerSettingsPreview"
import { useCustomerSettingsQuery } from "./hooks/useCustomerSettingsQuery"
import type { ConflictState, CustomerSettingsPreviewResponse, SettingsTab } from "./types"
import {
  canPreviewDomain,
  canWriteDomain,
  isRiskDomain,
  parseTabParam,
  resolveActionDomainTab,
} from "./utils"

function tabLabel(tab: SettingsTab): string {
  return SETTINGS_TABS.find((item) => item.id === tab)?.label ?? tab
}

function isTabDirty(tab: SettingsTab, draft: DomainDraftState, original: DomainDraftState): boolean {
  switch (tab) {
    case "identity":
      return isIdentityDirty(draft, original)
    case "modules":
      return isModulesDirty(draft, original)
    case "integrations":
      return isIntegrationsDirty(draft, original)
    case "routing":
      return isRoutingDirty(draft, original)
    case "automation":
      return isAutomationDirty(draft, original)
    default:
      return false
  }
}

function buildPatchPayloadForDomain(
  domain: string,
  draft: DomainDraftState,
  original: DomainDraftState,
): Record<string, unknown> {
  switch (domain) {
    case "identity":
      return buildIdentityPatchPayload(draft)
    case "modules":
      return buildModulesPatchPayload(draft)
    case "services":
      return buildServicesPatchPayload(draft)
    case "integrations":
      return buildIntegrationsPatchPayload(draft, original)
    case "routing":
      return buildRoutingPatchPayload(draft)
    case "automation":
      return buildAutomationPatchPayload(draft)
    default:
      return {}
  }
}

function domainDirty(domain: string, draft: DomainDraftState, original: DomainDraftState): boolean {
  switch (domain) {
    case "identity":
      return isIdentityDirty(draft, original)
    case "modules":
      return (
        stableJson(draft.modules.capabilities) !== stableJson(original.modules.capabilities)
      )
    case "services":
      return (
        stableJson(draft.modules.serviceProfile) !== stableJson(original.modules.serviceProfile)
      )
    case "integrations":
      return isIntegrationsDirty(draft, original)
    case "routing":
      return isRoutingDirty(draft, original)
    case "automation":
      return isAutomationDirty(draft, original)
    default:
      return false
  }
}

function stableJson(value: unknown): string {
  return JSON.stringify(value)
}

export function CustomerSettingsPage() {
  const { tenantId } = useParams<{ tenantId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { auth } = useAuth()
  const { data, isLoading, isError, error, refetch } = useCustomerSettingsQuery(tenantId)
  const patchMutation = useCustomerSettingsPatch()
  const previewMutation = useCustomerSettingsPreview()

  const activeTab = parseTabParam(searchParams.get("tab"))
  const [draft, setDraft] = useState<DomainDraftState | null>(null)
  const [original, setOriginal] = useState<DomainDraftState | null>(null)
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(
    null,
  )
  const [conflict, setConflict] = useState<ConflictState | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewResult, setPreviewResult] = useState<CustomerSettingsPreviewResponse | null>(null)
  const [manualDialogOpen, setManualDialogOpen] = useState(false)
  const [dataRevision, setDataRevision] = useState<string | null>(null)

  const aggregateRevision = data ? `${data.tenant_id}:${data.config_version}` : null
  if (data && aggregateRevision !== dataRevision) {
    const next = createDraftsFromAggregate(data)
    setDataRevision(aggregateRevision)
    setDraft(next)
    setOriginal(next)
    setFeedback(null)
    setConflict(null)
    setPreviewOpen(false)
    setPreviewResult(null)
  }

  const operatorRole =
    auth.status === "authenticated" ? auth.operator.role : "read_only"
  const operatorRoleLabel = roleLabel(operatorRole)

  const dirtyTabs = useMemo(() => {
    if (!draft || !original) return new Set<string>()
    return dirtyTabsForDraft(draft, original)
  }, [draft, original])

  const hasUnsavedChanges = dirtyTabs.size > 0
  const tabDirty = draft && original ? isTabDirty(activeTab, draft, original) : false

  const canWriteActiveTab = useMemo(() => {
    if (!data) return false
    const domains = TAB_SAVE_DOMAINS[activeTab] ?? []
    return domains.some((domain) => canWriteDomain(data.permissions, domain))
  }, [activeTab, data])

  const canPreviewActiveTab = useMemo(() => {
    if (!data) return false
    const domains = TAB_SAVE_DOMAINS[activeTab] ?? []
    return domains.some((domain) => canPreviewDomain(data.permissions, domain) && isRiskDomain(domain))
  }, [activeTab, data])

  const setTab = (tab: SettingsTab) => {
    const next = new URLSearchParams(searchParams)
    next.set("tab", tab)
    setSearchParams(next, { replace: true })
  }

  const handleTabChange = (tab: SettingsTab) => {
    if (tab === activeTab) return
    if (tabDirty) {
      const proceed = window.confirm(
        "Du har osparade ändringar i denna flik. Vill du byta flik utan att spara?",
      )
      if (!proceed) return
      if (draft && original) {
        setDraft(resetTabDraft(draft, original, activeTab))
      }
    }
    setTab(tab)
  }

  const openActionDomainTab = (actionDomain: string) => {
    const tab = resolveActionDomainTab(actionDomain)
    handleTabChange(tab)
  }

  const runPreview = async (domain: string) => {
    if (!tenantId || !draft || !data) return null
    if (!canPreviewDomain(data.permissions, domain)) return null
    const payload = buildPreviewPayloadForDomain(domain, draft)
    const result = await previewMutation.mutateAsync({ tenantId, domain, payload })
    setPreviewResult(result)
    setPreviewOpen(true)
    return result
  }

  const executeSave = async () => {
    if (!tenantId || !data || !draft || !original) return
    setFeedback(null)
    setConflict(null)

    const domains = (TAB_SAVE_DOMAINS[activeTab] ?? []).filter((domain) =>
      domainDirty(domain, draft, original),
    )
    if (domains.length === 0) return

    let latestVersion = data.config_version

    for (const domain of domains) {
      if (!canWriteDomain(data.permissions, domain)) continue
      const result = await patchMutation.mutateAsync({
        tenantId,
        domain,
        body: {
          expected_config_version: latestVersion,
          payload: buildPatchPayloadForDomain(domain, draft, original),
        },
      })

      if (result.conflict) {
        setConflict(result.conflict)
        return
      }

      latestVersion = result.response.config_version
    }

    await refetch()
    setFeedback({ type: "success", message: "Ändringarna sparades." })
    setPreviewOpen(false)
    setPreviewResult(null)
  }

  const handleSave = async () => {
    if (!data || !draft || !original) return
    const domains = (TAB_SAVE_DOMAINS[activeTab] ?? []).filter(
      (domain) => canWriteDomain(data.permissions, domain) && isRiskDomain(domain),
    )
    const needsPreview = domains.some((domain) => domainDirty(domain, draft, original))

    if (needsPreview) {
      const domain = domains.find((item) => domainDirty(item, draft, original)) ?? domains[0]
      const preview = await runPreview(domain)
      if (!preview) return
      if (!preview.valid) {
        setFeedback({
          type: "error",
          message: "Ogiltig konfiguration. Åtgärda valideringsfel innan du sparar.",
        })
        return
      }
      return
    }

    await executeSave()
  }

  const handlePreview = async () => {
    if (!data) return
    const domain =
      (TAB_SAVE_DOMAINS[activeTab] ?? []).find(
        (item) => canPreviewDomain(data.permissions, item) && isRiskDomain(item),
      ) ?? activeTab
    await runPreview(domain)
  }

  const handleReset = () => {
    if (!original || !draft) return
    setDraft(resetTabDraft(draft, original, activeTab))
    setFeedback(null)
    setPreviewOpen(false)
    setPreviewResult(null)
  }

  const handleConflictReload = async () => {
    setConflict(null)
    await refetch()
    setFeedback({ type: "success", message: "Senaste konfigurationen laddades om." })
  }

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <LoadingState label="Laddar kundinställningar…" rows={10} />
      </div>
    )
  }

  if (isError || !data || !draft || !original) {
    const is404 = error instanceof ApiError && error.status === 404
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <ErrorState
          title={is404 ? "Kunden hittades inte" : "Kunde inte ladda inställningar"}
          description={
            is404
              ? "Det finns ingen tenant med det angivna ID:t."
              : "Kundinställningarna kunde inte hämtas just nu."
          }
          recommendedAction={is404 ? "Gå tillbaka till kundlistan." : "Försök uppdatera sidan."}
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
        <Link to="/customers" className="self-start text-body text-text-primary underline">
          Tillbaka till kunder
        </Link>
      </div>
    )
  }

  const tabHeading = tabLabel(activeTab)

  return (
    <>
      <UnsavedChangesGuard when={hasUnsavedChanges} />
      <CustomerSettingsLayout
        data={data}
        roleLabel={operatorRoleLabel}
        activeTab={activeTab}
        dirtyTabs={dirtyTabs}
        onTabChange={handleTabChange}
        footer={
          activeTab !== "readiness" ? (
            <SaveBar
              canSave={canWriteActiveTab}
              canPreview={canPreviewActiveTab}
              isDirty={tabDirty}
              isSaving={patchMutation.isPending}
              isPreviewing={previewMutation.isPending}
              onSave={() => void handleSave()}
              onPreview={canPreviewActiveTab ? () => void handlePreview() : undefined}
              onReset={handleReset}
              feedback={feedback}
            />
          ) : null
        }
      >
        <div className="min-w-0">
          <h2 id="settings-tab-heading" className="text-section-title text-text-primary">
            {tabHeading}
          </h2>

          {activeTab === "identity" ? (
            <div className="mt-4">
              <IdentitySettingsPanel
                value={draft.identity}
                tenantStatus={data.tenant_status}
                canWrite={canWriteDomain(data.permissions, "identity")}
                onChange={(next) => setDraft({ ...draft, identity: next })}
              />
            </div>
          ) : null}

          {activeTab === "modules" ? (
            <div className="mt-4">
              {data.effective_capabilities.length === 0 ? (
                <EmptyState
                  title="Inga capabilities"
                  description="Denna tenant har inga tillgängliga capabilities ännu."
                />
              ) : (
                <ModulesSettingsPanel
                  capabilities={draft.modules.capabilities}
                  effectiveCapabilities={data.effective_capabilities}
                  serviceProfile={draft.modules.serviceProfile}
                  canWrite={
                    canWriteDomain(data.permissions, "modules") ||
                    canWriteDomain(data.permissions, "services")
                  }
                  onCapabilitiesChange={(capabilities) =>
                    setDraft({
                      ...draft,
                      modules: { ...draft.modules, capabilities },
                    })
                  }
                  onServiceProfileChange={(serviceProfile) =>
                    setDraft({
                      ...draft,
                      modules: { ...draft.modules, serviceProfile },
                    })
                  }
                />
              )}
            </div>
          ) : null}

          {activeTab === "integrations" ? (
            <div className="mt-4">
              <IntegrationsSettingsPanel
                data={data}
                draftSelections={draft.integrations.selections}
                financeChoice={draft.integrations.financeChoice}
                vismaDisposition={draft.integrations.vismaDisposition}
                manualDialogOpen={manualDialogOpen}
                canWrite={canWriteDomain(data.permissions, "integrations")}
                onSelectionChange={(integrationKey, status) =>
                  setDraft({
                    ...draft,
                    integrations: {
                      ...draft.integrations,
                      selections: {
                        ...draft.integrations.selections,
                        [integrationKey]: {
                          ...draft.integrations.selections[integrationKey],
                          selection_status: status,
                        },
                      },
                    },
                  })
                }
                onFinanceChoice={(choice) =>
                  setDraft({
                    ...draft,
                    integrations: {
                      ...draft.integrations,
                      financeChoice: choice,
                      vismaDisposition:
                        choice === "manual_accounting_routing"
                          ? draft.integrations.vismaDisposition
                          : null,
                    },
                  })
                }
                onVismaDisposition={(value) =>
                  setDraft({
                    ...draft,
                    integrations: { ...draft.integrations, vismaDisposition: value },
                  })
                }
                onManualDialogOpen={setManualDialogOpen}
              />
            </div>
          ) : null}

          {activeTab === "routing" ? (
            <div className="mt-4">
              <RoutingSettingsPanel
                routing={draft.routing}
                canWrite={canWriteDomain(data.permissions, "routing")}
                onChange={(routing) => setDraft({ ...draft, routing })}
              />
            </div>
          ) : null}

          {activeTab === "automation" ? (
            <div className="mt-4">
              <AutomationSettingsPanel
                automation={draft.automation}
                schedulerRunMode={data.automation_policy_summary.scheduler_run_mode}
                autoActions={data.automation_policy_summary.auto_actions}
                externalWrites={data.automation_policy_summary.enabled_external_writes}
                canWrite={canWriteDomain(data.permissions, "automation")}
                onChange={(automation) => setDraft({ ...draft, automation })}
              />
            </div>
          ) : null}

          {activeTab === "readiness" ? (
            <div className="mt-4">
              <ReadinessSummaryPanel
                readiness={data.effective_readiness}
                onOpenTab={openActionDomainTab}
              />
            </div>
          ) : null}
        </div>
      </CustomerSettingsLayout>

      <ConflictDialog
        open={Boolean(conflict)}
        message={conflict?.message ?? ""}
        serverConfigVersion={conflict?.serverConfigVersion ?? data.config_version}
        onReload={() => void handleConflictReload()}
        onCancel={() => setConflict(null)}
      />

      <ConsequencePreview
        open={previewOpen}
        preview={previewResult}
        isLoading={previewMutation.isPending}
        onConfirm={() => void executeSave()}
        onCancel={() => {
          setPreviewOpen(false)
          setPreviewResult(null)
        }}
      />
    </>
  )
}

function resetTabDraft(
  draft: DomainDraftState,
  original: DomainDraftState,
  tab: SettingsTab,
): DomainDraftState {
  switch (tab) {
    case "identity":
      return { ...draft, identity: { ...original.identity } }
    case "modules":
      return { ...draft, modules: { ...original.modules } }
    case "integrations":
      return { ...draft, integrations: { ...original.integrations } }
    case "routing":
      return { ...draft, routing: { ...original.routing } }
    case "automation":
      return { ...draft, automation: { ...original.automation } }
    default:
      return draft
  }
}
