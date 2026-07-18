import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, it } from "node:test"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const wizardPath = path.join(__dirname, "OnboardingWizardPage.tsx")
const apiPath = path.join(__dirname, "api.ts")
const mutationsPath = path.join(__dirname, "mutations.ts")
const utilsPath = path.join(__dirname, "routingStep.utils.ts")
const criticalDialogPath = path.join(
  __dirname,
  "..",
  "..",
  "components",
  "operator",
  "CriticalActionDialog.tsx",
)
const actionDialogPath = path.join(
  __dirname,
  "..",
  "..",
  "components",
  "operator",
  "ActionDialog.tsx",
)

describe("onboarding slice 2A wizard guards", () => {
  it("wizard exposes routing preview button and API hook", () => {
    const source = fs.readFileSync(wizardPath, "utf8")
    assert.match(source, /Förhandsgranska routing/)
    assert.match(source, /usePreviewRoutingMutation/)
    assert.match(source, /previewRouting\(/)
    assert.doesNotMatch(source, /manual_review\s*[=:]\s*["']/)
  })

  it("preview uses server API and does not patch routing draft", () => {
    const wizard = fs.readFileSync(wizardPath, "utf8")
    const api = fs.readFileSync(apiPath, "utf8")
    assert.match(api, /routing-preview/)
    assert.match(wizard, /previewRoutingMutation\.mutateAsync/)
    assert.doesNotMatch(wizard, /patchRoutingStep\([^)]*preview/)
  })

  it("reset button is conditional on override and calls routing-reset mutation", () => {
    const wizard = fs.readFileSync(wizardPath, "utf8")
    const api = fs.readFileSync(apiPath, "utf8")
    const mutations = fs.readFileSync(mutationsPath, "utf8")
    assert.match(api, /routing-reset/)
    assert.match(wizard, /hasOverride/)
    assert.match(wizard, /Återställ till standard/)
    assert.match(wizard, /useResetRoutingMutation/)
    assert.match(mutations, /invalidateSlice2aSideEffects/)
    assert.match(mutations, /activation-plan/)
  })

  it("routing effective values come from server merge helper, not client defaults", () => {
    const wizard = fs.readFileSync(wizardPath, "utf8")
    const utils = fs.readFileSync(utilsPath, "utf8")
    assert.match(utils, /mergeRoutingPreviewRows/)
    assert.match(wizard, /mergeRoutingPreviewRows/)
    assert.doesNotMatch(wizard, /profile\?\.default_route\s*\?\?/)
    assert.doesNotMatch(wizard, /"manual_review"/)
  })

  it("lead requirement reset to inherit is available in UI", () => {
    const wizard = fs.readFileSync(wizardPath, "utf8")
    assert.match(wizard, /resetLeadFieldToInherit/)
    assert.match(wizard, /mode !== "inherit"/)
  })

  it("dialog components avoid document overflow when closed", () => {
    const critical = fs.readFileSync(criticalDialogPath, "utf8")
    const action = fs.readFileSync(actionDialogPath, "utf8")
    assert.match(critical, /if \(!open\) return null/)
    assert.match(action, /if \(!open\) return null/)
    assert.match(critical, /w-\[min\(100vw/)
    assert.match(action, /w-\[min\(100vw/)
  })

  it("wizard layout uses min-w-0 for mobile overflow prevention", () => {
    const wizard = fs.readFileSync(wizardPath, "utf8")
    assert.match(wizard, /min-w-0/)
    assert.match(wizard, /break-words/)
  })
})
