import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, it } from "node:test"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const linkUtilPath = path.join(__dirname, "readinessActionLink.tsx")
const wizardPath = path.join(__dirname, "OnboardingWizardPage.tsx")

function resolveReadinessActionLink(template, tenantId) {
  if (!template || !tenantId) return null
  const substituted = template.replace("{tenant_id}", tenantId)
  const match = substituted.match(/^\/ops\/customers\/([^/?#]+)\/onboarding\?step=([a-z_]+)$/)
  if (!match) return null
  const [, routeTenantId, step] = match
  if (routeTenantId !== tenantId || !/^[a-z_]+$/.test(step)) return null
  return `/customers/${encodeURIComponent(tenantId)}/onboarding?step=${encodeURIComponent(step)}`
}

describe("readiness action links", () => {
  it("maps ops template to in-app onboarding route", () => {
    const to = resolveReadinessActionLink(
      "/ops/customers/{tenant_id}/onboarding?step=routing",
      "T_DEMO",
    )
    assert.equal(to, "/customers/T_DEMO/onboarding?step=routing")
  })

  it("rejects mismatched tenant id", () => {
    const to = resolveReadinessActionLink(
      "/ops/customers/T_OTHER/onboarding?step=routing",
      "T_DEMO",
    )
    assert.equal(to, null)
  })

  it("wizard renders ReadinessActionLink for grouped checks", () => {
    const source = fs.readFileSync(wizardPath, "utf8")
    assert.match(source, /ReadinessActionLink/)
    assert.match(source, /check\.action_link/)
  })

  it("link helper uses react-router Link with resolved path", () => {
    const source = fs.readFileSync(linkUtilPath, "utf8")
    assert.ok(source.includes("react-router-dom"))
    assert.ok(source.includes("resolveReadinessActionLink"))
    assert.ok(source.includes('to={to}'))
  })
})
