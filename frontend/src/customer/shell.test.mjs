import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

const customerDir = dirname(fileURLToPath(import.meta.url))
const frontendDir = join(customerDir, "..", "..")

function readCustomerFile(relativePath) {
  return readFileSync(join(customerDir, relativePath), "utf8")
}

function readAllCustomerSources() {
  const files = [
    "main.tsx",
    "app/App.tsx",
    "routes/router.tsx",
    "routes/navConfig.ts",
    "auth/CustomerAuthProvider.tsx",
    "auth/PreviewLoginPage.tsx",
    "auth/ForbiddenPage.tsx",
    "api/mockDataSource.ts",
    "api/types.ts",
    "types/workspace.ts",
    "components/CustomerHeader.tsx",
    "components/CustomerSidebar.tsx",
    "components/CustomerMobileNavigation.tsx",
    "layouts/CustomerAppShell.tsx",
  ]
  return files.map((file) => readCustomerFile(file)).join("\n")
}

test("customer routes include all required paths", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  const requiredPaths = [
    "<OverviewPage />",
    "<LeadsPage />",
    "<SupportPage />",
    "<ApprovalsPage />",
    "<NeedsHelpPage />",
    'path: "activity"',
    'path: "search"',
    'path: "work/:workItemId"',
    'path: "/login"',
    'path: "/forbidden"',
    'basename: "/app"',
  ]
  for (const fragment of requiredPaths) {
    assert.match(routerSource, new RegExp(fragment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
  }
})

test("navigation config exposes primary and more mobile items", () => {
  const navSource = readCustomerFile("routes/navConfig.ts")
  assert.match(navSource, /Översikt/)
  assert.match(navSource, /Leads/)
  assert.match(navSource, /Kundfrågor/)
  assert.match(navSource, /Godkännanden/)
  assert.match(navSource, /Behöver hjälp/)
  assert.match(navSource, /Aktivitet/)
  assert.match(navSource, /MOBILE_PRIMARY_NAV/)
  assert.match(navSource, /MOBILE_MORE_NAV/)
})

test("feature flags default to safe preview values", () => {
  const flagsSource = readCustomerFile("types/workspace.ts")
  assert.match(flagsSource, /customer_workspace_writes:\s*false/)
  assert.match(flagsSource, /connected_api:\s*false/)
  assert.match(flagsSource, /preview_mode:\s*true/)
})

test("auth boundary uses preview mode without admin auth", () => {
  const authSource = readCustomerFile("auth/CustomerAuthProvider.tsx")
  assert.match(authSource, /role:\s*"customer_viewer"/)
  assert.match(authSource, /connected:\s*false/)
  assert.doesNotMatch(authSource, /\/auth\/admin/)
  assert.doesNotMatch(authSource, /X-API-Key/)
})

test("mock adapter does not perform network calls", () => {
  const mockSource = readCustomerFile("api/mockDataSource.ts")
  assert.doesNotMatch(mockSource, /\bfetch\s*\(/)
  assert.doesNotMatch(mockSource, /XMLHttpRequest/)
  assert.match(mockSource, /Exempel El & Service AB/)
})

test("customer shell avoids secret storage and forbidden APIs", () => {
  const combined = [
    readAllCustomerSources(),
    readFileSync(join(customerDir, "features/overview/OverviewPage.tsx"), "utf8"),
    readFileSync(join(customerDir, "features/overview/overviewFixtures.ts"), "utf8"),
    readFileSync(join(customerDir, "features/work-queues/WorkItemsQueuePage.tsx"), "utf8"),
    readFileSync(join(customerDir, "features/work-queues/workQueueFixtures.ts"), "utf8"),
    readFileSync(join(customerDir, "features/approvals/ApprovalsPage.tsx"), "utf8"),
  ].join("\n")
  const forbidden = [
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "X-API-Key",
    "X-Tenant-ID",
    "/auth/admin/",
    "/approvals/pending",
    "/jobs",
    "/workspace/v1",
  ]
  for (const token of forbidden) {
    assert.doesNotMatch(combined, new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
  }
})

test("preview login page is informational, not connected login", () => {
  const loginSource = readCustomerFile("auth/PreviewLoginPage.tsx")
  assert.match(loginSource, /Förhandsvisning/)
  assert.doesNotMatch(loginSource, /type="password"/)
  assert.doesNotMatch(loginSource, /X-API-Key/)
})

test("error boundary component exists", () => {
  const boundarySource = readCustomerFile("components/CustomerErrorBoundary.tsx")
  assert.match(boundarySource, /CustomerErrorBoundary/)
  assert.match(boundarySource, /getDerivedStateFromError/)
})

test("vite customer config uses app base and dist-customer output", () => {
  const viteConfig = readFileSync(
    join(frontendDir, "vite.customer.config.ts"),
    "utf8",
  )
  assert.match(viteConfig, /base:\s*"\/app\/"/)
  assert.match(viteConfig, /outDir:\s*"dist-customer"/)
  assert.match(viteConfig, /customer\.html/)
})
