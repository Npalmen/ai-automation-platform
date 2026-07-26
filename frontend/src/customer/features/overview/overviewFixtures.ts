import type { WorkspaceOverview } from "@/customer/types/overview"

export type OverviewMockScenario =
  | "populated"
  | "empty"
  | "partial_error"
  | "full_error"
  | "unknown_status"
  | "loading"

const LAST_UPDATED = "2026-07-26T08:30:00+02:00"

const POPULATED_OVERVIEW: WorkspaceOverview = {
  last_updated_at: LAST_UPDATED,
  summary: {
    cases_handled_today: 12,
    waiting_for_decision: 2,
    waiting_for_customer: 3,
    needs_help: 1,
    failed_today: 0,
    estimated_hours_saved: 2.5,
    estimated_value_sek: 1250,
  },
  priority_work_items: [
    {
      work_item_id: "wi-lead-001",
      type: "lead",
      title: "Offertförfrågan solceller — vill ha svar denna vecka",
      customer_name: "Erik Johansson",
      customer_status: "prioritized",
      customer_status_label: "Prioriterad",
      priority_rank: 1,
      priority_label: "Hög prioritet",
      updated_at: "2026-07-26T08:15:00+02:00",
    },
    {
      work_item_id: "wi-approval-002",
      type: "approval",
      title: "Godkänn utskick av offertutkast",
      customer_name: "Lindqvist VVS AB",
      customer_status: "waiting_for_decision",
      customer_status_label: "Väntar på beslut",
      priority_rank: 2,
      priority_label: null,
      updated_at: "2026-07-26T07:45:00+02:00",
    },
    {
      work_item_id: "wi-support-003",
      type: "support",
      title: "Fråga om installationstid för värmepump",
      customer_name: "Maria Lind",
      customer_status: "waiting_for_customer",
      customer_status_label: "Väntar på kund",
      priority_rank: 3,
      priority_label: null,
      updated_at: "2026-07-25T16:20:00+02:00",
    },
    {
      work_item_id: "wi-help-004",
      type: "needs_help",
      title: "Systemet behöver hjälp att tolka teknisk ritning",
      customer_name: "Bygg & Montage i Dalarna",
      customer_status: "needs_help",
      customer_status_label: "Behöver hjälp",
      priority_rank: 4,
      priority_label: null,
      updated_at: "2026-07-25T14:00:00+02:00",
    },
    {
      work_item_id: "wi-support-005",
      type: "support",
      title: "Bekräftelse mottagen — ärende avslutat",
      customer_name: "Anders Nyström",
      customer_status: "completed",
      customer_status_label: "Klar",
      priority_rank: 5,
      priority_label: null,
      updated_at: "2026-07-26T06:30:00+02:00",
    },
  ],
  partial_errors: [],
}

const EMPTY_OVERVIEW: WorkspaceOverview = {
  last_updated_at: LAST_UPDATED,
  summary: {
    cases_handled_today: 0,
    waiting_for_decision: 0,
    waiting_for_customer: 0,
    needs_help: 0,
    failed_today: 0,
  },
  priority_work_items: [],
  partial_errors: [],
}

const PARTIAL_ERROR_OVERVIEW: WorkspaceOverview = {
  ...POPULATED_OVERVIEW,
  partial_errors: [
    {
      section: "value_estimate",
      code: "preview_unavailable",
      message:
        "Värdeuppskattningen kunde inte visas just nu. Övrig information är tillgänglig.",
    },
  ],
}

const UNKNOWN_STATUS_OVERVIEW: WorkspaceOverview = {
  ...POPULATED_OVERVIEW,
  priority_work_items: [
    {
      work_item_id: "wi-unknown-001",
      type: "unknown",
      title: "Ärende med okänd status i förhandsvisning",
      customer_name: "Testperson AB",
      customer_status: "unknown",
      customer_status_label: "Okänd status",
      priority_rank: 1,
      priority_label: null,
      updated_at: "2026-07-26T08:00:00+02:00",
    },
    ...POPULATED_OVERVIEW.priority_work_items.slice(1),
  ],
}

export function createOverviewFixture(
  scenario: OverviewMockScenario,
): WorkspaceOverview | "full_error" | "loading" {
  switch (scenario) {
    case "populated":
      return POPULATED_OVERVIEW
    case "empty":
      return EMPTY_OVERVIEW
    case "partial_error":
      return PARTIAL_ERROR_OVERVIEW
    case "unknown_status":
      return UNKNOWN_STATUS_OVERVIEW
    case "full_error":
      return "full_error"
    case "loading":
      return "loading"
    default:
      return POPULATED_OVERVIEW
  }
}

export function cloneOverview(overview: WorkspaceOverview): WorkspaceOverview {
  return structuredClone(overview)
}
