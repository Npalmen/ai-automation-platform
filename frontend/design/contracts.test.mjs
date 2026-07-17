import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, it } from "node:test"

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const IMPLEMENTED_COMPONENTS = new Set([
  "AppShell",
  "PageHeader",
  "StatusBadge",
  "SeverityBadge",
  "HealthIndicator",
  "MetricCard",
  "DataTable",
  "FilterBar",
  "EmptyState",
  "ErrorState",
  "LoadingState",
  "ActionDialog",
  "CriticalActionDialog",
  "AuditTimeline",
  "TenantIdentifier",
])

const TYPOGRAPHY_KEYS = [
  "display",
  "pageTitle",
  "sectionTitle",
  "cardTitle",
  "body",
  "bodySmall",
  "label",
  "caption",
  "metric",
  "table",
  "code",
]

const STATUS_TOKENS = [
  "success",
  "warning",
  "danger",
  "critical",
  "information",
  "neutral",
  "paused",
  "unknown",
]

function readJson(filename) {
  const filePath = path.join(__dirname, filename)
  const raw = fs.readFileSync(filePath, "utf8")
  return JSON.parse(raw)
}

describe("krowolf-ui-profile.json", () => {
  const profile = readJson("krowolf-ui-profile.json")

  it("has profile metadata", () => {
    assert.ok(profile.profile)
    assert.equal(profile.profile.version, "1.0.0")
    assert.equal(profile.profile.locale, "sv-SE")
    assert.equal(profile.profile.direction, "nordic_operations")
  })

  it("has all color groups", () => {
    assert.ok(profile.colors.page)
    assert.ok(profile.colors.surface)
    assert.ok(profile.colors.border)
    assert.ok(profile.colors.text)
    assert.ok(profile.colors.brand)
    assert.ok(profile.colors.status)
  })

  it("has all 8 status tokens", () => {
    for (const token of STATUS_TOKENS) {
      assert.ok(profile.colors.status[token], `missing status token: ${token}`)
    }
  })

  it("has all typography categories", () => {
    for (const key of TYPOGRAPHY_KEYS) {
      assert.ok(profile.typography[key], `missing typography: ${key}`)
    }
  })

  it("has non-empty spacing, radii, and shadows", () => {
    assert.ok(Object.keys(profile.spacing).length > 0)
    assert.ok(Object.keys(profile.radii).length > 0)
    assert.ok(Object.keys(profile.shadows).length > 0)
  })

  it("has strictly ascending breakpoints", () => {
    const values = Object.values(profile.breakpoints)
    for (let i = 1; i < values.length; i++) {
      assert.ok(values[i] > values[i - 1], `breakpoints not ascending at index ${i}`)
    }
    assert.deepEqual(values, [320, 375, 768, 1024, 1366, 1440, 1920])
  })

  it("has accessibility section", () => {
    assert.ok(profile.accessibility)
    assert.equal(profile.accessibility.statusNotColorAlone, true)
  })

  it("has non-empty forbiddenPatterns", () => {
    assert.ok(Array.isArray(profile.forbiddenPatterns))
    assert.ok(profile.forbiddenPatterns.length > 0)
  })
})

describe("component-contracts.json", () => {
  const contracts = readJson("component-contracts.json")

  it("every component has required fields", () => {
    for (const [name, contract] of Object.entries(contracts)) {
      assert.ok(contract.purpose, `${name}: missing purpose`)
      assert.ok(contract.accessibility, `${name}: missing accessibility`)
      assert.ok(contract.forbiddenUses, `${name}: missing forbiddenUses`)
      assert.equal(typeof contract.implemented, "boolean", `${name}: missing implemented`)
    }
  })

  it("StatusBadge and SeverityBadge variants are objects with text and color", () => {
    for (const component of ["StatusBadge", "SeverityBadge"]) {
      const variants = contracts[component].variants
      assert.ok(variants && typeof variants === "object" && !Array.isArray(variants))
      for (const [key, variant] of Object.entries(variants)) {
        assert.ok(variant.text, `${component}.${key}: missing text`)
        assert.ok(variant.color, `${component}.${key}: missing color`)
      }
    }
  })

  it("implemented:true matches exactly the implemented operator components", () => {
    const implemented = new Set(
      Object.entries(contracts)
        .filter(([, c]) => c.implemented === true)
        .map(([name]) => name),
    )
    assert.deepEqual(implemented, IMPLEMENTED_COMPONENTS)
  })
})

describe("page-contracts.json", () => {
  const contracts = readJson("page-contracts.json")

  it("every page has purpose, desktopLayout, and mobileLayout", () => {
    for (const [name, contract] of Object.entries(contracts)) {
      assert.ok(contract.purpose, `${name}: missing purpose`)
      assert.ok(contract.desktopLayout, `${name}: missing desktopLayout`)
      assert.ok(contract.mobileLayout, `${name}: missing mobileLayout`)
    }
  })
})
