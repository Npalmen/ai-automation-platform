import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, it } from "node:test"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const typesPath = path.join(__dirname, "types.ts")
const wizardPath = path.join(__dirname, "OnboardingWizardPage.tsx")

const FORBIDDEN_EXPORTS = ["CAPABILITY_OPTIONS", "AUTOMATION_PRESET_OPTIONS"]

describe("onboarding registry source of truth", () => {
  it("types.ts does not export hardcoded capability or preset option lists", () => {
    const source = fs.readFileSync(typesPath, "utf8")
    for (const name of FORBIDDEN_EXPORTS) {
      assert.equal(
        source.includes(`export const ${name}`),
        false,
        `types.ts must not export ${name}`,
      )
    }
  })

  it("wizard loads options from registry query, not local constants", () => {
    const source = fs.readFileSync(wizardPath, "utf8")
    for (const name of FORBIDDEN_EXPORTS) {
      assert.equal(source.includes(name), false, `wizard must not reference ${name}`)
    }
    assert.match(source, /useOnboardingRegistriesQuery/)
    assert.match(source, /registries\.product_capabilities/)
    assert.match(source, /plan_hash/)
  })
})
