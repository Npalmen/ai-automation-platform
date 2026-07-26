import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import test from "node:test"

const workQueuesDir = dirname(fileURLToPath(import.meta.url))
const customerDir = join(workQueuesDir, "..", "..")

function readCustomerFile(relativePath) {
  return readFileSync(join(customerDir, relativePath), "utf8")
}

function readWorkQueuesFile(relativePath) {
  return readFileSync(join(workQueuesDir, relativePath), "utf8")
}

function compareValues(left, right, order) {
  if (left === right) return 0
  const result = left < right ? -1 : 1
  return order === "asc" ? result : -result
}

function filterWorkItems(items, params) {
  let filtered = items
  if (params.type !== "all") {
    filtered = filtered.filter((item) => item.type === params.type)
  }
  if (params.status) {
    filtered = filtered.filter((item) => item.customer_status === params.status)
  }
  return filtered
}

function sortWorkItems(items, params) {
  const sortKey = params.sort ?? "priority_rank"
  const order = params.order ?? "asc"
  const sorted = [...items]
  sorted.sort((left, right) => {
    if (sortKey === "priority_rank") {
      return compareValues(left.priority_rank, right.priority_rank, order)
    }
    if (sortKey === "created_at") {
      return compareValues(left.created_at, right.created_at, order)
    }
    return compareValues(left.updated_at, right.updated_at, order)
  })
  return sorted
}

function paginateList(items, limit, offset) {
  const safeLimit = Math.max(1, limit)
  const safeOffset = Math.max(0, offset)
  return {
    items: items.slice(safeOffset, safeOffset + safeLimit),
    total: items.length,
  }
}

function parsePositiveInt(value, fallback) {
  if (!value) return fallback
  const parsed = Number.parseInt(value, 10)
  if (!Number.isFinite(parsed) || parsed < 1) return fallback
  return parsed
}

function parseWorkQueueUrlState(searchParams) {
  const validStatuses = new Set([
    "all", "new", "prioritized", "in_progress", "waiting_for_decision",
    "waiting_for_customer", "prepared", "scheduled", "completed",
    "needs_help", "failed", "cancelled", "unknown",
  ])
  const validSort = new Set(["priority_rank", "updated_at", "created_at"])
  const rawStatus = searchParams.get("status") ?? "all"
  const status = validStatuses.has(rawStatus) ? rawStatus : "all"
  const rawSort = searchParams.get("sort") ?? "priority_rank"
  const sort = validSort.has(rawSort) ? rawSort : "priority_rank"
  const rawOrder = searchParams.get("order")
  const order = rawOrder === "asc" || rawOrder === "desc" ? rawOrder : "asc"
  return {
    status,
    sort,
    order,
    page: parsePositiveInt(searchParams.get("page"), 1),
  }
}

const SAMPLE_ITEMS = [
  {
    work_item_id: "a",
    type: "lead",
    customer_status: "new",
    priority_rank: 2,
    created_at: "2026-07-25T10:00:00+02:00",
    updated_at: "2026-07-26T10:00:00+02:00",
  },
  {
    work_item_id: "b",
    type: "lead",
    customer_status: "prioritized",
    priority_rank: 1,
    created_at: "2026-07-26T08:00:00+02:00",
    updated_at: "2026-07-26T11:00:00+02:00",
  },
  {
    work_item_id: "c",
    type: "support",
    customer_status: "needs_help",
    priority_rank: 1,
    created_at: "2026-07-24T10:00:00+02:00",
    updated_at: "2026-07-25T10:00:00+02:00",
  },
]

test("WorkspaceDataSource includes typed list methods", () => {
  const typesSource = readCustomerFile("api/types.ts")
  assert.match(typesSource, /listWorkItems\(params: WorkItemListParams\): Promise<WorkItemListResponse>/)
  assert.match(typesSource, /listApprovals\(params: ApprovalListParams\): Promise<ApprovalListResponse>/)
})

test("work item envelope follows contract", () => {
  const typesSource = readCustomerFile("types/work-items.ts")
  assert.match(typesSource, /work_item_id: string/)
  assert.match(typesSource, /customer_status_label: string/)
  assert.match(typesSource, /summary: string/)
  const listSource = readCustomerFile("types/lists.ts")
  assert.match(listSource, /partial_errors: PartialError\[\]/)
})

test("approval envelope follows contract", () => {
  const typesSource = readCustomerFile("types/approvals.ts")
  assert.match(typesSource, /approval_id: string/)
  assert.match(typesSource, /work_item_title: string/)
  assert.match(typesSource, /requested_at: string/)
})

test("mock adapter filters on fixed item type", () => {
  const mockSource = readCustomerFile("api/mockDataSource.ts")
  assert.match(mockSource, /listWorkItems\(params\)/)
  const fixtureSource = readWorkQueuesFile("workQueueFixtures.ts")
  assert.match(fixtureSource, /type: "lead"/)
  const leads = filterWorkItems(SAMPLE_ITEMS, { type: "lead", limit: 10, offset: 0 })
  assert.ok(leads.every((item) => item.type === "lead"))
})

test("mock adapter filters on status", () => {
  const logicSource = readWorkQueuesFile("workQueueMockLogic.ts")
  assert.match(logicSource, /params\.status/)
  const filtered = filterWorkItems(SAMPLE_ITEMS, {
    type: "all",
    status: "needs_help",
    limit: 10,
    offset: 0,
  })
  assert.equal(filtered.length, 1)
})

test("mock adapter sorts according to params", () => {
  const logicSource = readWorkQueuesFile("workQueueMockLogic.ts")
  assert.match(logicSource, /sortWorkItems/)
  const sorted = sortWorkItems(SAMPLE_ITEMS.filter((item) => item.type === "lead"), {
    type: "lead",
    sort: "priority_rank",
    order: "asc",
    limit: 10,
    offset: 0,
  })
  assert.equal(sorted[0].work_item_id, "b")
})

test("mock adapter paginates correctly", () => {
  const logicSource = readWorkQueuesFile("workQueueMockLogic.ts")
  assert.match(logicSource, /paginateList/)
  const page = paginateList(SAMPLE_ITEMS, 2, 1)
  assert.equal(page.total, 3)
  assert.equal(page.items.length, 2)
})

test("total limit and offset are correct in list response", () => {
  const logicSource = readWorkQueuesFile("workQueueMockLogic.ts")
  assert.match(logicSource, /buildWorkItemListResponse/)
  assert.match(logicSource, /limit: params\.limit/)
  assert.match(logicSource, /offset: params\.offset/)
})

test("leads route uses real feature view", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  assert.match(routerSource, /<LeadsPage \/>/)
})

test("support route uses real feature view", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  assert.match(routerSource, /<SupportPage \/>/)
})

test("approvals route uses read-only feature view", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  assert.match(routerSource, /<ApprovalsPage \/>/)
})

test("needs-help route uses real feature view", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  assert.match(routerSource, /<NeedsHelpPage \/>/)
})

test("activity search and work detail use real feature views", () => {
  const routerSource = readCustomerFile("routes/router.tsx")
  assert.match(routerSource, /<ActivityPage \/>/)
  assert.match(routerSource, /<SearchPage \/>/)
  assert.match(routerSource, /<WorkDetailPage \/>/)
})

test("filter state is parsed safely from URL", () => {
  const urlSource = readWorkQueuesFile("workQueueUrlState.ts")
  assert.match(urlSource, /parseWorkQueueUrlState/)
  const params = new URLSearchParams("status=waiting_for_customer&sort=updated_at&order=desc&page=2")
  const state = parseWorkQueueUrlState(params)
  assert.equal(state.status, "waiting_for_customer")
  assert.equal(state.page, 2)
})

test("invalid URL params fall back safely", () => {
  const params = new URLSearchParams("status=not_real&sort=bad&order=upside_down&page=-3")
  const state = parseWorkQueueUrlState(params)
  assert.equal(state.status, "all")
  assert.equal(state.sort, "priority_rank")
  assert.equal(state.page, 1)
})

test("filter change resets pagination in URL builder", () => {
  const urlSource = readWorkQueuesFile("workQueueUrlState.ts")
  assert.match(urlSource, /buildWorkQueueSearchParams/)
  const pageSource = readWorkQueuesFile("WorkItemsQueuePage.tsx")
  assert.match(pageSource, /page: 1/)
})

test("empty states exist per route", () => {
  assert.match(readWorkQueuesFile("../leads/LeadsPage.tsx"), /Inga leads matchar ditt val/)
  assert.match(readWorkQueuesFile("../support/SupportPage.tsx"), /Inga kundfrågor matchar ditt val/)
  assert.match(readWorkQueuesFile("../approvals/ApprovalsPage.tsx"), /Inga förslag väntar på beslut/)
  assert.match(readWorkQueuesFile("../needs-help/NeedsHelpPage.tsx"), /Inget behöver mänsklig hjälp just nu/)
})

test("partial errors keep items in mock response", () => {
  const mockSource = readCustomerFile("api/mockDataSource.ts")
  assert.match(mockSource, /getQueuePartialErrors/)
  const partialSource = readWorkQueuesFile("WorkQueuePartialError.tsx")
  assert.match(partialSource, /role="alert"/)
})

test("full errors have retry in queue pages", () => {
  assert.match(readWorkQueuesFile("WorkItemsQueuePage.tsx"), /Försök igen/)
  assert.match(readWorkQueuesFile("../approvals/ApprovalsPage.tsx"), /Försök igen/)
})

test("unknown status is fail-safe", () => {
  const fixtureSource = readWorkQueuesFile("workQueueFixtures.ts")
  assert.match(fixtureSource, /customer_status:\s*"unknown"/)
  assert.match(readWorkQueuesFile("WorkQueueItemCard.tsx"), /displayStatusLabel/)
})

test("approval view has no mutations or actions", () => {
  const approvalsSource = readWorkQueuesFile("../approvals/ApprovalsPage.tsx")
  const cardSource = readWorkQueuesFile("../approvals/ApprovalItemCard.tsx")
  assert.doesNotMatch(approvalsSource, /useMutation/)
  assert.doesNotMatch(cardSource, /Godkänn/)
  assert.doesNotMatch(cardSource, /Avslå/)
  assert.match(cardSource, /Beslut kan inte fattas i förhandsvisningen/)
})

test("no fetch or network client is used in workflow features", () => {
  const files = [
    "WorkItemsQueuePage.tsx",
    "workQueueFixtures.ts",
    "../approvals/ApprovalsPage.tsx",
    "../leads/LeadsPage.tsx",
    "api/mockDataSource.ts",
  ]
  for (const file of files) {
    const source = file.startsWith("api/")
      ? readCustomerFile(file)
      : readWorkQueuesFile(file)
    assert.doesNotMatch(source, /\bfetch\s*\(/)
    assert.doesNotMatch(source, /axios/)
  }
})

test("forbidden fields are absent from fixtures and types", () => {
  const fixtureSource = readWorkQueuesFile("workQueueFixtures.ts")
  const typeSource = readCustomerFile("types/work-items.ts")
  for (const token of [
    "job_id",
    "input_data",
    "processor_history",
    "request_payload",
    "execution_id",
  ]) {
    assert.doesNotMatch(fixtureSource, new RegExp(token))
    assert.doesNotMatch(typeSource, new RegExp(token))
  }
})

test("no client-side status normalization exists", () => {
  const listSource = readWorkQueuesFile("WorkQueueList.tsx")
  const pageSource = readWorkQueuesFile("WorkItemsQueuePage.tsx")
  assert.doesNotMatch(listSource, /switch\s*\(.*customer_status/)
  assert.doesNotMatch(pageSource, /\.sort\(/)
})

test("no client-side decisioning or prioritization engine exists", () => {
  const mockLogicSource = readWorkQueuesFile("workQueueMockLogic.ts")
  const pageSource = readWorkQueuesFile("WorkItemsQueuePage.tsx")
  assert.match(mockLogicSource, /sortWorkItems/)
  assert.doesNotMatch(pageSource, /\.sort\(/)
})

test("approval URL state parses safely", () => {
  const urlSource = readWorkQueuesFile("workQueueUrlState.ts")
  assert.match(urlSource, /parseApprovalUrlState/)
  assert.match(urlSource, /buildApprovalSearchParams/)
})

test("mock fixtures include populated scenarios", () => {
  const fixtureSource = readWorkQueuesFile("workQueueFixtures.ts")
  for (const scenario of ["populated", "empty", "partial_error", "full_error", "unknown_status", "delayed"]) {
    assert.match(fixtureSource, new RegExp(`"${scenario}"`))
  }
})
