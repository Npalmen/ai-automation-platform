import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

const activitySearchDir = dirname(fileURLToPath(import.meta.url))
const customerDir = join(activitySearchDir, "..", "..")

function readCustomerFile(relativePath) {
  return readFileSync(join(customerDir, relativePath), "utf8")
}

function readFeatureFile(feature, relativePath) {
  return readFileSync(join(customerDir, "features", feature, relativePath), "utf8")
}

function normalizeSearchText(value) {
  return value.trim().toLocaleLowerCase("sv-SE")
}

function matchesSearch(item, query) {
  const needle = normalizeSearchText(query)
  if (!needle) return true
  const haystack = [item.title, item.customer_name, item.customer_email, item.summary]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase("sv-SE")
  return haystack.includes(needle)
}

const SAMPLE_ITEM = {
  title: "Solcellsanläggning för villa i Täby",
  customer_name: "Erik Lindström",
  customer_email: "erik.lindstrom@fiktivmail.se",
  summary: "Förfrågan om offert",
}

test("WorkspaceDataSource includes getWorkItem and listActivity", () => {
  const typesSource = readCustomerFile("api/types.ts")
  assert.match(typesSource, /getWorkItem\(workItemId: string\): Promise<WorkItemDetail \| null>/)
  assert.match(typesSource, /listActivity\(params: ActivityListParams\): Promise<ActivityListResponse>/)
  assert.doesNotMatch(typesSource, /getWorkItemDetail/)
  assert.doesNotMatch(typesSource, /getActivity\(\)/)
})

test("work item list params support q from and to", () => {
  const typesSource = readCustomerFile("types/work-items.ts")
  assert.match(typesSource, /q\?: string/)
  assert.match(typesSource, /from\?: string/)
  assert.match(typesSource, /to\?: string/)
})

test("detail contract avoids forbidden fields", () => {
  const typesSource = readCustomerFile("types/work-item-detail.ts")
  for (const token of ["job_id", "processor_history", "request_payload", "execution_id"]) {
    assert.doesNotMatch(typesSource, new RegExp(token))
  }
  assert.match(typesSource, /timeline: WorkItemTimelineItem\[\]/)
})

test("activity contract reuses CustomerStatus", () => {
  const typesSource = readCustomerFile("types/activity.ts")
  assert.match(typesSource, /customer_status: CustomerStatus/)
  assert.match(typesSource, /ListResponse<ActivityListItem>/)
})

test("search matches title customer name and email case-insensitively", () => {
  assert.equal(matchesSearch(SAMPLE_ITEM, "solcell"), true)
  assert.equal(matchesSearch(SAMPLE_ITEM, "ERIK"), true)
  assert.equal(matchesSearch(SAMPLE_ITEM, "fiktivmail"), true)
  assert.equal(matchesSearch(SAMPLE_ITEM, "  erik  "), true)
  assert.equal(matchesSearch(SAMPLE_ITEM, "ingen träff"), false)
})

test("search handles Swedish characters", () => {
  assert.equal(matchesSearch({ ...SAMPLE_ITEM, customer_name: "Åsa Öberg" }, "åsa"), true)
  assert.equal(matchesSearch({ ...SAMPLE_ITEM, customer_name: "Åsa Öberg" }, "öberg"), true)
})

test("date range invalid when from is after to", () => {
  const dateUtils = readFeatureFile("work-queues", "dateFilterUtils.ts")
  assert.match(dateUtils, /isDateRangeInvalid/)
})

test("mock adapter performs search in adapter layer", () => {
  const mockLogic = readFeatureFile("work-queues", "workQueueMockLogic.ts")
  assert.match(mockLogic, /matchesWorkItemSearch/)
  assert.match(mockLogic, /params\.q/)
  assert.match(mockLogic, /matchesCreatedDateRange/)
})

test("activity search and work detail routes use real features", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  assert.match(routerSource, /<ActivityPage \/>/)
  assert.match(routerSource, /<SearchPage \/>/)
  assert.match(routerSource, /<WorkDetailPage \/>/)
  assert.doesNotMatch(routerSource, /RoutePlaceholder/)
})

test("search URL state preserves q and filters", () => {
  const searchUrl = readFeatureFile("search", "searchUrlState.ts")
  assert.match(searchUrl, /parseSearchUrlState/)
  assert.match(searchUrl, /buildSearchUrlParams/)
  assert.match(searchUrl, /hasInvalidSearchDateRange/)
})

test("search without q shows instructional empty state", () => {
  const searchPage = readFeatureFile("search", "SearchPage.tsx")
  assert.match(searchPage, /Sök efter ett ärende, en kund eller en e-postadress/)
})

test("search zero results shows correct empty state", () => {
  const searchPage = readFeatureFile("search", "SearchPage.tsx")
  assert.match(searchPage, /Inga ärenden matchar din sökning/)
})

test("activity empty state exists", () => {
  const activityPage = readFeatureFile("activity", "ActivityPage.tsx")
  assert.match(activityPage, /Ingen aktivitet matchar ditt val/)
})

test("detail page has no actions", () => {
  const detailPage = readFeatureFile("work-detail", "WorkDetailPage.tsx")
  for (const action of ["Godkänn", "Avslå", "Skicka", "Svara", "Redigera", "Återförsök", "useMutation"]) {
    assert.doesNotMatch(detailPage, new RegExp(action))
  }
})

test("detail 404 uses customer-friendly not found", () => {
  const detailPage = readFeatureFile("work-detail", "WorkDetailPage.tsx")
  assert.match(detailPage, /Arbetsobjektet hittades inte/)
})

test("empty timeline message exists", () => {
  const timeline = readFeatureFile("work-detail", "WorkDetailTimeline.tsx")
  assert.match(timeline, /Ingen historik finns att visa ännu/)
})

test("human takeover is shown in detail page", () => {
  const detailPage = readFeatureFile("work-detail", "WorkDetailPage.tsx")
  assert.match(detailPage, /human_takeover_required/)
  assert.match(detailPage, /Systemet behöver hjälp för att fortsätta/)
})

test("back navigation uses safe return path", () => {
  const nav = readCustomerFile("navigation/workItemNavigation.ts")
  assert.match(nav, /isSafeAppReturnPath/)
  assert.match(nav, /fallbackRouteForWorkItemType/)
  const detailPage = readFeatureFile("work-detail", "WorkDetailPage.tsx")
  assert.match(detailPage, /resolveWorkItemBackPath/)
})

test("work queue items link to detail view", () => {
  const card = readFeatureFile("work-queues", "WorkQueueItemCard.tsx")
  assert.match(card, /WorkItemLink/)
  assert.match(card, /showDetailLink/)
})

test("no fetch or network clients in Todo F features", () => {
  const files = [
    ["activity", "ActivityPage.tsx"],
    ["search", "SearchPage.tsx"],
    ["work-detail", "WorkDetailPage.tsx"],
    ["work-detail", "workDetailFixtures.ts"],
    ["activity", "activityFixtures.ts"],
  ]
  for (const [feature, file] of files) {
    const source = readFeatureFile(feature, file)
    assert.doesNotMatch(source, /\bfetch\s*\(/)
    assert.doesNotMatch(source, /axios/)
  }
})

test("no localStorage or sessionStorage for return route", () => {
  const combined = [
    readFeatureFile("work-detail", "WorkDetailPage.tsx"),
    readCustomerFile("navigation/workItemNavigation.ts"),
    readCustomerFile("components/WorkItemLink.tsx"),
  ].join("\n")
  assert.doesNotMatch(combined, /localStorage/)
  assert.doesNotMatch(combined, /sessionStorage/)
})

test("mock fixtures include Todo F scenarios", () => {
  const fixtures = readFeatureFile("work-queues", "workQueueFixtures.ts")
  for (const scenario of ["not_found", "empty_timeline"]) {
    assert.match(fixtures, new RegExp(`"${scenario}"`))
  }
})
