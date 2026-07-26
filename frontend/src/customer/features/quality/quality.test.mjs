import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

const qualityDir = dirname(fileURLToPath(import.meta.url))
const customerDir = join(qualityDir, "..", "..")

function readCustomerFile(relativePath) {
  return readFileSync(join(customerDir, relativePath), "utf8")
}

function readFeatureFile(feature, relativePath) {
  return readFileSync(join(customerDir, "features", feature, relativePath), "utf8")
}

const TECHNICAL_COPY = [
  "pipeline",
  "processor",
  "adapter",
  "operation UUID",
  "job ID",
  "decision record",
  "execution intent",
  "execution outcome",
  "manual review",
  "payload",
  "mock adapter",
  "API key",
  "API-nyckel",
  "tenant",
  "stack trace",
  "enum",
]

function readVisibleCustomerSources() {
  return [
    readCustomerFile("layouts/CustomerAppShell.tsx"),
    readCustomerFile("components/CustomerHeader.tsx"),
    readCustomerFile("components/CustomerMobileNavigation.tsx"),
    readCustomerFile("components/CustomerSidebar.tsx"),
    readCustomerFile("components/CustomerPageHeader.tsx"),
    readCustomerFile("components/WorkspaceModeBadge.tsx"),
    readCustomerFile("auth/PreviewLoginPage.tsx"),
    readCustomerFile("auth/ForbiddenPage.tsx"),
    readCustomerFile("pages/NotFoundPage.tsx"),
    readCustomerFile("components/CustomerErrorBoundary.tsx"),
    readFeatureFile("overview", "OverviewHeader.tsx"),
    readFeatureFile("overview", "OverviewPage.tsx"),
    readFeatureFile("activity", "ActivityPage.tsx"),
    readFeatureFile("search", "SearchPage.tsx"),
    readFeatureFile("work-detail", "WorkDetailPage.tsx"),
    readFeatureFile("work-detail", "WorkDetailTimeline.tsx"),
    readFeatureFile("work-queues", "WorkQueueItemCard.tsx"),
    readFeatureFile("work-queues", "WorkQueuePagination.tsx"),
    readFeatureFile("work-queues", "WorkQueuePartialError.tsx"),
    readFeatureFile("approvals", "ApprovalsPage.tsx"),
  ].join("\n")
}

test("customer shell has main landmark and skip link", () => {
  const shell = readCustomerFile("layouts/CustomerAppShell.tsx")
  const skip = readCustomerFile("components/SkipToContentLink.tsx")
  assert.match(shell, /id="main-content"/)
  assert.match(shell, /<main/)
  assert.match(shell, /SkipToContentLink/)
  assert.match(skip, /Hoppa till huvudinnehåll/)
  assert.match(skip, /#main-content/)
})

test("route focus hook targets main heading on pathname change", () => {
  const hook = readCustomerFile("hooks/useRouteFocus.ts")
  assert.match(hook, /pathname/)
  assert.match(hook, /main-content/)
  assert.match(hook, /querySelector\("h1"\)/)
})

test("page headers expose focusable h1 for route changes", () => {
  const header = readCustomerFile("components/CustomerPageHeader.tsx")
  const overview = readFeatureFile("overview", "OverviewHeader.tsx")
  assert.match(header, /<h1[\s\S]*tabIndex=\{-1\}/)
  assert.match(overview, /<h1[\s\S]*tabIndex=\{-1\}/)
})

test("main routes render a page title via shared layout", () => {
  const pageLayout = readFeatureFile("work-queues", "WorkQueuePageLayout.tsx")
  const workQueuePage = readFeatureFile("work-queues", "WorkItemsQueuePage.tsx")
  assert.match(pageLayout, /CustomerPageHeader/)
  assert.match(workQueuePage, /WorkQueuePageLayout/)

  for (const feature of ["leads", "support", "needs-help"]) {
    const wrapper = readFeatureFile(feature, `${feature === "needs-help" ? "NeedsHelp" : feature.charAt(0).toUpperCase() + feature.slice(1)}Page.tsx`)
    assert.match(wrapper, /WorkItemsQueuePage/)
  }

  const directPages = [
    readFeatureFile("overview", "OverviewPage.tsx"),
    readFeatureFile("approvals", "ApprovalsPage.tsx"),
    readFeatureFile("activity", "ActivityPage.tsx"),
    readFeatureFile("search", "SearchPage.tsx"),
    readFeatureFile("work-detail", "WorkDetailPage.tsx"),
  ]
  for (const source of directPages) {
    assert.match(source, /CustomerPageHeader|OverviewHeader|WorkQueuePageLayout/)
  }
})

test("icon buttons and drawer triggers have accessible names", () => {
  const mobile = readCustomerFile("components/CustomerMobileNavigation.tsx")
  const header = readCustomerFile("components/CustomerHeader.tsx")
  const shell = readCustomerFile("layouts/CustomerAppShell.tsx")
  assert.match(header, /aria-label="Öppna meny"/)
  assert.match(mobile, /aria-label="Stäng meny"/)
  assert.match(shell, /aria-label=.*[Mm]eny/)
})

test("form controls in search and queues have visible labels", () => {
  const search = readFeatureFile("search", "SearchPage.tsx")
  const activity = readFeatureFile("activity", "ActivityPage.tsx")
  assert.match(search, /<label[\s\S]*htmlFor="global-search"/)
  assert.match(activity, /<label[\s\S]*htmlFor="activity-type-filter"/)
})

test("status is always presented with text", () => {
  const formatters = readFeatureFile("overview", "overviewFormatters.ts")
  const card = readFeatureFile("work-queues", "WorkQueueItemCard.tsx")
  assert.match(formatters, /Okänd status/)
  assert.match(card, /displayStatusLabel/)
})

test("navigation uses links and buttons, not clickable divs", () => {
  const combined = [
    readCustomerFile("components/CustomerSidebar.tsx"),
    readCustomerFile("components/WorkItemLink.tsx"),
    readFeatureFile("work-queues", "WorkQueueItemCard.tsx"),
  ].join("\n")
  assert.doesNotMatch(combined, /<div[^>]+onClick=/)
  assert.match(combined, /<Link|NavLink|<button/)
})

test("pagination exposes accessible names and disabled state", () => {
  const pagination = readFeatureFile("work-queues", "WorkQueuePagination.tsx")
  assert.match(pagination, /aria-label="Sidnavigering"/)
  assert.match(pagination, /aria-label="Föregående sida"/)
  assert.match(pagination, /aria-label="Nästa sida"/)
  assert.match(pagination, /disabled=\{isFirstPage\}/)
  assert.match(pagination, /disabled=\{isLastPage\}/)
})

test("drawer and more menu support Escape and focus return", () => {
  const mobile = readCustomerFile("components/CustomerMobileNavigation.tsx")
  const shell = readCustomerFile("layouts/CustomerAppShell.tsx")
  assert.match(mobile, /onCancel=/)
  assert.match(mobile, /moreTriggerRef/)
  assert.match(mobile, /\.focus\(\)/)
  assert.match(shell, /menuButtonRef/)
  assert.match(shell, /menuButtonRef\.current\?\.focus\(\)/)
})

test("back navigation only accepts internal app paths", () => {
  const nav = readCustomerFile("navigation/workItemNavigation.ts")
  assert.match(nav, /isSafeAppReturnPath/)
  assert.match(nav, /resolveWorkItemBackPath/)
  assert.match(nav, /path\.includes\(":\/\/"\)/)
})

test("critical containers use min-w-0 to avoid overflow", () => {
  const shell = readCustomerFile("layouts/CustomerAppShell.tsx")
  const container = readCustomerFile("components/CustomerPageContainer.tsx")
  const card = readFeatureFile("work-queues", "WorkQueueItemCard.tsx")
  assert.match(shell, /min-w-0/)
  assert.match(container, /min-w-0/)
  assert.match(card, /min-w-0/)
  assert.match(card, /break-words|break-all/)
})

test("timeline is semantic ordered list", () => {
  const timeline = readFeatureFile("work-detail", "WorkDetailTimeline.tsx")
  assert.match(timeline, /<ol/)
  assert.match(timeline, /aria-label="Tidslinje"/)
})

test("loading empty and error states are customer-friendly", () => {
  const loading = readFileSync(
    join(customerDir, "..", "components", "shared", "LoadingState.tsx"),
    "utf8",
  )
  const overview = readFeatureFile("overview", "OverviewPage.tsx")
  const notFound = readCustomerFile("pages/NotFoundPage.tsx")
  const forbidden = readCustomerFile("auth/ForbiddenPage.tsx")
  const login = readCustomerFile("auth/PreviewLoginPage.tsx")
  assert.match(loading, /aria-busy="true"/)
  assert.match(overview, /Försök igen/)
  assert.match(notFound, /Sidan hittades inte/)
  assert.match(forbidden, /Åtkomst nekad/)
  assert.match(login, /Förhandsvisning/)
})

test("partial errors keep messages and hide internal codes in UI", () => {
  const partial = readFeatureFile("work-queues", "WorkQueuePartialError.tsx")
  assert.match(partial, /error\.message/)
  assert.doesNotMatch(partial, /\{error\.code\}/)
})

test("preview mode does not claim live data", () => {
  const overview = readFeatureFile("overview", "OverviewHeader.tsx")
  const badge = readCustomerFile("components/WorkspaceModeBadge.tsx")
  assert.match(overview, /inte liveuppdatering/)
  assert.match(badge, /ej ansluten/)
})

test("long content fixtures exist for layout testing", () => {
  const fixtures = readFeatureFile("quality", "longContentFixtures.ts")
  const queue = readFeatureFile("work-queues", "workQueueFixtures.ts")
  assert.match(fixtures, /LONG_CONTENT_WORK_ITEM/)
  assert.match(queue, /long_content/)
})

test("reduced motion and focus styles are defined globally", () => {
  const globals = readFileSync(
    join(customerDir, "..", "styles", "globals.css"),
    "utf8",
  )
  assert.match(globals, /prefers-reduced-motion/)
  assert.match(globals, /:focus-visible/)
})

test("mobile navigation accounts for safe area inset", () => {
  const mobile = readCustomerFile("components/CustomerMobileNavigation.tsx")
  const shell = readCustomerFile("layouts/CustomerAppShell.tsx")
  assert.match(mobile, /safe-area-inset-bottom/)
  assert.match(shell, /safe-area-inset-bottom/)
})

test("error boundary offers reload without exposing stack traces", () => {
  const boundary = readCustomerFile("components/CustomerErrorBoundary.tsx")
  assert.match(boundary, /Ladda om sidan/)
  assert.doesNotMatch(boundary, /stack/i)
})

test("no technical copy in customer-visible component strings", () => {
  const visible = readVisibleCustomerSources()
  for (const term of TECHNICAL_COPY) {
    assert.doesNotMatch(
      visible,
      new RegExp(term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
      `found forbidden term: ${term}`,
    )
  }
})

test("quality pass does not introduce network clients or storage", () => {
  const combined = [
    readVisibleCustomerSources(),
    readCustomerFile("hooks/useRouteFocus.ts"),
    readCustomerFile("components/SkipToContentLink.tsx"),
    readFeatureFile("quality", "longContentFixtures.ts"),
  ].join("\n")
  const forbidden = [
    "fetch(",
    "axios",
    "localStorage",
    "sessionStorage",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "/workspace/v1",
    "/auth/customer",
  ]
  for (const token of forbidden) {
    const pattern =
      token === "fetch("
        ? /\bfetch\s*\(/
        : new RegExp(token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    assert.doesNotMatch(combined, pattern)
  }
})

test("Todo H closure docs are present on main", () => {
  const releaseNotes = readFileSync(
    join(customerDir, "..", "..", "..", "docs", "customer-workspace", "release-notes.md"),
    "utf8",
  )
  const verification = readFileSync(
    join(customerDir, "..", "..", "..", "docs", "customer-workspace", "verification.md"),
    "utf8",
  )
  assert.match(releaseNotes, /Preview release/)
  assert.match(verification, /Overall closure status: PARTIAL/)
})
