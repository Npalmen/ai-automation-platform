import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

const overviewDir = dirname(fileURLToPath(import.meta.url))
const customerDir = join(overviewDir, "..", "..")

function readOverviewSource(relativePath) {
  return readFileSync(join(overviewDir, relativePath), "utf8")
}

function readCustomerFile(relativePath) {
  return readFileSync(join(customerDir, relativePath), "utf8")
}

const dateTimeFormatter = new Intl.DateTimeFormat("sv-SE", {
  dateStyle: "medium",
  timeStyle: "short",
})

const currencyFormatter = new Intl.NumberFormat("sv-SE", {
  style: "currency",
  currency: "SEK",
  maximumFractionDigits: 0,
})

test("WorkspaceDataSource getOverview uses WorkspaceOverview type", () => {
  const typesSource = readCustomerFile("api/types.ts")
  assert.match(typesSource, /getOverview\(\): Promise<WorkspaceOverview>/)
})

test("populated fixture contains realistic prioritized items", () => {
  const fixtureSource = readOverviewSource("overviewFixtures.ts")
  assert.match(fixtureSource, /cases_handled_today:\s*12/)
  assert.match(fixtureSource, /waiting_for_decision:\s*2/)
  assert.match(fixtureSource, /work_item_id:\s*"wi-lead-001"/)
  assert.match(fixtureSource, /priority_rank:\s*1/)
})

test("priority order is preserved and list does not resort", () => {
  const fixtureSource = readOverviewSource("overviewFixtures.ts")
  assert.match(fixtureSource, /priority_rank:\s*1[\s\S]*priority_rank:\s*2[\s\S]*priority_rank:\s*3/)
  const listSource = readOverviewSource("PriorityWorkList.tsx")
  assert.doesNotMatch(listSource, /\.sort\(/)
})

test("summary labels are rendered in Swedish", () => {
  const summarySource = readOverviewSource("OverviewSummary.tsx")
  for (const label of [
    "Hanterade idag",
    "Väntar på beslut",
    "Väntar på kund",
    "Behöver hjälp",
    "Misslyckades idag",
  ]) {
    assert.match(summarySource, new RegExp(label))
  }
})

test("currency formatting uses SEK in formatter module", () => {
  const formatterSource = readOverviewSource("overviewFormatters.ts")
  assert.match(formatterSource, /currency:\s*"SEK"/)
  const formatted = currencyFormatter.format(1250)
  assert.match(formatted, /kr/)
})

test("dates use sv-SE Intl formatting", () => {
  const formatterSource = readOverviewSource("overviewFormatters.ts")
  assert.match(formatterSource, /Intl\.DateTimeFormat\("sv-SE"/)
  const formatted = dateTimeFormatter.format(new Date("2026-07-26T08:30:00+02:00"))
  assert.match(formatted, /2026/)
})

test("empty fixture and empty state exist", () => {
  const fixtureSource = readOverviewSource("overviewFixtures.ts")
  assert.match(fixtureSource, /EMPTY_OVERVIEW/)
  assert.match(fixtureSource, /priority_work_items:\s*\[\]/)
  const listSource = readOverviewSource("PriorityWorkList.tsx")
  assert.match(listSource, /Inget behöver din uppmärksamhet just nu/)
})

test("partial error fixture keeps populated data", () => {
  const fixtureSource = readOverviewSource("overviewFixtures.ts")
  assert.match(fixtureSource, /PARTIAL_ERROR_OVERVIEW/)
  assert.match(fixtureSource, /partial_errors:\s*\[/)
})

test("full error scenario throws from mock data source", () => {
  const mockSource = readCustomerFile("api/mockDataSource.ts")
  assert.match(mockSource, /full_error/)
  assert.match(mockSource, /throw new Error/)
})

test("unknown status fixture is fail-safe", () => {
  const fixtureSource = readOverviewSource("overviewFixtures.ts")
  assert.match(fixtureSource, /customer_status:\s*"unknown"/)
  assert.match(fixtureSource, /customer_status_label:\s*"Okänd status"/)
  const formatterSource = readOverviewSource("overviewFormatters.ts")
  assert.match(formatterSource, /Okänd status/)
})

test("overview feature avoids raw internal enum presentation", () => {
  const cardSource = readOverviewSource("PriorityWorkItemCard.tsx")
  assert.match(cardSource, /customer_status_label/)
  assert.doesNotMatch(cardSource, /awaiting_approval/)
})

test("overview feature does not use network clients", () => {
  const sources = [
    readOverviewSource("OverviewPage.tsx"),
    readCustomerFile("api/mockDataSource.ts"),
    readOverviewSource("overviewFixtures.ts"),
  ].join("\n")
  assert.doesNotMatch(sources, /\bfetch\s*\(/)
  assert.doesNotMatch(sources, /axios/)
  assert.doesNotMatch(sources, /\/workspace\/v1/)
})

test("overview route uses OverviewPage and Todo F routes stay placeholders", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  assert.match(routerSource, /<OverviewPage \/>/)
  assert.match(routerSource, /path: "activity"[\s\S]*?<RoutePlaceholder/)
  assert.match(routerSource, /path: "search"[\s\S]*?<RoutePlaceholder/)
  assert.match(routerSource, /path: "work\/:workItemId"[\s\S]*?<RoutePlaceholder/)
})

test("work item type labels are customer-friendly", () => {
  const formatterSource = readOverviewSource("overviewFormatters.ts")
  assert.match(formatterSource, /lead:\s*"Lead"/)
  assert.match(formatterSource, /support:\s*"Kundfråga"/)
  assert.match(formatterSource, /approval:\s*"Godkännande"/)
  assert.match(formatterSource, /needs_help:\s*"Behöver hjälp"/)
})

test("OverviewPage has retry on full error", () => {
  const pageSource = readOverviewSource("OverviewPage.tsx")
  assert.match(pageSource, /isError/)
  assert.match(pageSource, /refetch/)
  assert.match(pageSource, /Försök igen/)
})

test("main entry wraps customer app with QueryClientProvider", () => {
  const mainSource = readCustomerFile("main.tsx")
  assert.match(mainSource, /QueryClientProvider/)
  assert.match(mainSource, /customerQueryClient/)
})
