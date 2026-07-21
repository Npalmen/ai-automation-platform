import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, it } from "node:test"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const featureRoot = __dirname
const routerPath = path.join(featureRoot, "../../routes/router.tsx")
const detailPath = path.join(featureRoot, "../customers/CustomerDetailPage.tsx")
const pagePath = path.join(featureRoot, "CustomerSettingsPage.tsx")
const layoutPath = path.join(featureRoot, "CustomerSettingsLayout.tsx")
const apiPath = path.join(featureRoot, "api.ts")
const patchHookPath = path.join(featureRoot, "hooks/useCustomerSettingsPatch.ts")
const previewHookPath = path.join(featureRoot, "hooks/useCustomerSettingsPreview.ts")
const guardPath = path.join(featureRoot, "components/UnsavedChangesGuard.tsx")
const conflictPath = path.join(featureRoot, "components/ConflictDialog.tsx")
const previewPanelPath = path.join(featureRoot, "components/ConsequencePreview.tsx")
const integrationsPanelPath = path.join(featureRoot, "domains/IntegrationsSettingsPanel.tsx")
const automationPanelPath = path.join(featureRoot, "domains/AutomationSettingsPanel.tsx")
const readinessPanelPath = path.join(featureRoot, "components/ReadinessSummaryPanel.tsx")
const saveBarPath = path.join(featureRoot, "components/SaveBar.tsx")
const formattersPath = path.join(featureRoot, "formatters.ts")
const contractsPath = path.join(featureRoot, "../../../design/page-contracts.json")

const router = fs.readFileSync(routerPath, "utf8")
const detail = fs.readFileSync(detailPath, "utf8")
const page = fs.readFileSync(pagePath, "utf8")
const layout = fs.readFileSync(layoutPath, "utf8")
const api = fs.readFileSync(apiPath, "utf8")
const patchHook = fs.readFileSync(patchHookPath, "utf8")
const previewHook = fs.readFileSync(previewHookPath, "utf8")
const guard = fs.readFileSync(guardPath, "utf8")
const conflict = fs.readFileSync(conflictPath, "utf8")
const previewPanel = fs.readFileSync(previewPanelPath, "utf8")
const integrationsPanel = fs.readFileSync(integrationsPanelPath, "utf8")
const automationPanel = fs.readFileSync(automationPanelPath, "utf8")
const readinessPanel = fs.readFileSync(readinessPanelPath, "utf8")
const saveBar = fs.readFileSync(saveBarPath, "utf8")
const formatters = fs.readFileSync(formattersPath, "utf8")
const contracts = JSON.parse(fs.readFileSync(contractsPath, "utf8"))
const constantsSource = fs.readFileSync(path.join(featureRoot, "constants.ts"), "utf8")
const utilsSource = fs.readFileSync(path.join(featureRoot, "utils.ts"), "utf8")

function resolveActionDomainTab(actionDomain) {
  const map = {
    identity: "identity",
    modules: "modules",
    services: "modules",
    integrations: "integrations",
    finance_destination: "integrations",
    routing: "routing",
    automation: "automation",
    intake: "modules",
    readiness: "readiness",
  }
  if (!actionDomain) return "readiness"
  return map[actionDomain] ?? "readiness"
}

describe("customer settings operator interface", () => {
  it("route renders CustomerSettingsPage", () => {
    assert.match(router, /:tenantId\/settings/)
    assert.match(router, /CustomerSettingsPage/)
  })

  it("customer detail links to settings", () => {
    assert.match(detail, /Inställningar/)
    assert.match(detail, /\/customers\/\$\{tenant\.tenant_id\}\/settings/)
  })

  it("aggregate GET api exists", () => {
    assert.match(api, /\/admin\/tenants\/\$\{encodeURIComponent\(tenantId\)\}\/settings/)
    assert.match(page, /useCustomerSettingsQuery/)
  })

  it("tab navigation via search params", () => {
    assert.match(page, /parseTabParam/)
    assert.match(page, /setSearchParams/)
    assert.match(layout, /SettingsNavigation/)
  })

  it("action_domain opens mapped tab", () => {
    assert.equal(resolveActionDomainTab("finance_destination"), "integrations")
    assert.equal(resolveActionDomainTab("routing"), "routing")
    assert.match(constantsSource, /ACTION_DOMAIN_TAB_MAP/)
    assert.match(utilsSource, /resolveActionDomainTab/)
  })

  it("read_only lacks save when write permission false", () => {
    assert.match(page, /canWriteActiveTab/)
    assert.match(page, /canWriteDomain/)
    assert.match(page, /SaveBar/)
  })

  it("operations can save routing domain", () => {
    assert.match(page, /TAB_SAVE_DOMAINS/)
    assert.match(page, /"routing"/)
    assert.match(page, /canWriteDomain\(data\.permissions, "routing"\)/)
  })

  it("operations cannot save integrations without permission", () => {
    assert.match(page, /canWriteDomain\(data\.permissions, "integrations"\)/)
  })

  it("admin can save via domain permissions", () => {
    assert.match(page, /buildPatchPayloadForDomain/)
    assert.match(page, /patchMutation\.mutateAsync/)
  })

  it("expected_config_version is sent on patch", () => {
    assert.match(patchHook, /expected_config_version/)
    assert.match(page, /expected_config_version: latestVersion/)
  })

  it("409 shows ConflictDialog", () => {
    assert.match(patchHook, /status === 409/)
    assert.match(page, /ConflictDialog/)
    assert.match(conflict, /Konfigurationen har ändrats/)
  })

  it("reload after conflict refetches aggregate", () => {
    assert.match(page, /handleConflictReload/)
    assert.match(conflict, /Ladda om senaste version/)
    assert.match(page, /refetch\(\)/)
  })

  it("preview shown before risk save", () => {
    assert.match(page, /ConsequencePreview/)
    assert.match(page, /isRiskDomain/)
    assert.match(previewHook, /previewCustomerSettingsDomain/)
    assert.match(previewPanel, /Förhandsgranskning av ändringar/)
  })

  it("invalid preview blocks save confirmation", () => {
    assert.match(previewPanel, /Ogiltig konfiguration/)
    assert.match(previewPanel, /disabled=\{!canConfirm\}/)
    assert.match(page, /Ogiltig konfiguration/)
  })

  it("valid-but-not-ready can be confirmed", () => {
    assert.match(previewPanel, /Giltig men inte redo/)
    assert.match(previewPanel, /Bekräfta och spara/)
    assert.match(previewPanel, /fail-closed/)
  })

  it("success updates config_version via patch hook cache", () => {
    assert.match(patchHook, /config_version: result\.response\.config_version/)
    assert.match(page, /Ändringarna sparades/)
  })

  it("dirty state tracked per tab", () => {
    assert.match(page, /dirtyTabsForDraft/)
    assert.match(page, /isTabDirty/)
    assert.match(layout, /dirtyTabs/)
  })

  it("unsaved changes guard uses beforeunload and blocker", () => {
    assert.match(guard, /beforeunload/)
    assert.match(guard, /useBlocker/)
    assert.match(page, /UnsavedChangesGuard/)
  })

  it("integration tri-state labels", () => {
    assert.match(integrationsPanel, /not_selected/)
    assert.match(integrationsPanel, /selected_optional/)
    assert.match(integrationsPanel, /selected_required/)
    assert.match(formatters, /Ej aktuell/)
    assert.match(formatters, /Valfri/)
    assert.match(formatters, /Obligatorisk/)
  })

  it("coming_later integrations disabled", () => {
    assert.match(integrationsPanel, /coming_later/)
    assert.match(integrationsPanel, /Kommer senare/)
    assert.match(integrationsPanel, /disabled/)
  })

  it("manual routing requires visma disposition", () => {
    assert.match(integrationsPanel, /manual_accounting_routing/)
    assert.match(integrationsPanel, /visma-disposition/)
    assert.match(integrationsPanel, /not_selected/)
    assert.match(integrationsPanel, /selected_optional/)
  })

  it("credential preservation shown in preview", () => {
    assert.match(previewPanel, /Credentials bevaras/)
    assert.match(integrationsPanel, /Visma-credentials bevaras/)
  })

  it("scheduler is read-only in automation panel", () => {
    assert.match(automationPanel, /schedulerRunMode/)
    assert.match(automationPanel, /Skrivskyddad runtime/)
    assert.match(page, /scheduler_run_mode/)
  })

  it("enabled_external_writes is read-only", () => {
    assert.match(automationPanel, /externalWrites/)
    assert.match(automationPanel, /Externa writes/)
  })

  it("readiness blocker opens correct tab", () => {
    assert.match(readinessPanel, /resolveActionDomainTab/)
    assert.match(readinessPanel, /onOpenTab/)
    assert.match(page, /openActionDomainTab/)
  })

  it("responsive layout contract", () => {
    assert.match(layout, /lg:grid-cols-/)
    assert.match(layout, /min-w-0/)
    assert.match(saveBar, /sm:flex-row/)
    assert.match(integrationsPanel, /min-h-11/)
  })

  it("no raw enum labels in formatters for key statuses", () => {
    assert.match(formatters, /not_selected/)
    assert.match(formatters, /ready:/)
    assert.doesNotMatch(formatters, /return status\b/)
  })

  it("accessibility and focus styles on navigation", () => {
    assert.match(layout, /SettingsNavigation/)
    const navSource = fs.readFileSync(path.join(featureRoot, "components/SettingsNavigation.tsx"), "utf8")
    assert.match(navSource, /aria-current/)
    assert.match(navSource, /focus-visible:outline/)
    assert.match(conflict, /role="dialog"/)
    assert.match(previewPanel, /aria-labelledby/)
  })

  it("design contract documents customer settings page", () => {
    assert.ok(contracts["customer-settings"])
    assert.match(contracts["customer-settings"].purpose, /kundinställningar/i)
    assert.equal(contracts["customer-settings"].route, "/ops/customers/:tenantId/settings")
  })
})

console.log("customerSettings.test.mjs: PASS")
