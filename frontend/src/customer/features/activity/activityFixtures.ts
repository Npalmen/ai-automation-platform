import type { ActivityListItem } from "@/customer/types/activity"

const ACTIVITY_ITEMS: ActivityListItem[] = [
  {
    at: "2026-07-26T09:40:00+02:00",
    type: "lead",
    customer_status: "prioritized",
    customer_status_label: "Prioriterad",
    priority: "Hög prioritet",
    label: "Nytt lead prioriterades: Solcellsanläggning för villa i Täby",
  },
  {
    at: "2026-07-26T08:15:00+02:00",
    type: "support",
    customer_status: "needs_help",
    customer_status_label: "Behöver hjälp",
    priority: "Hög prioritet",
    label: "Kundfråga behöver mänsklig uppföljning",
  },
  {
    at: "2026-07-26T07:20:00+02:00",
    type: "lead",
    customer_status: "waiting_for_decision",
    customer_status_label: "Väntar på beslut",
    priority: "Medel prioritet",
    label: "Offertutkast förberett för serviceavtal",
  },
  {
    at: "2026-07-26T06:50:00+02:00",
    type: "support",
    customer_status: "prepared",
    customer_status_label: "Förberett svar",
    priority: null,
    label: "Svar om garanti förberett för granskning",
  },
  {
    at: "2026-07-25T16:45:00+02:00",
    type: "lead",
    customer_status: "waiting_for_customer",
    customer_status_label: "Väntar på kund",
    priority: null,
    label: "Kompletterande frågor skickade till Nordic Kontor AB",
  },
  {
    at: "2026-07-25T14:00:00+02:00",
    type: "support",
    customer_status: "waiting_for_customer",
    customer_status_label: "Väntar på kund",
    priority: null,
    label: "Tidsförslag för servicebesök väntar på kundens val",
  },
  {
    at: "2026-07-25T11:30:00+02:00",
    type: "lead",
    customer_status: "completed",
    customer_status_label: "Klar",
    priority: null,
    label: "Belysningsuppgradering markerad som avslutad",
  },
  {
    at: "2026-07-24T09:00:00+02:00",
    type: "support",
    customer_status: "failed",
    customer_status_label: "Misslyckades",
    priority: null,
    label: "Automatisk hantering kunde inte slutföras",
  },
  {
    at: "2026-07-24T08:30:00+02:00",
    type: "invoice",
    customer_status: "prepared",
    customer_status_label: "Förberett svar",
    priority: null,
    label: "Fakturaunderlag förberett för granskning",
  },
  {
    at: "2026-07-26T05:00:00+02:00",
    type: "unknown",
    customer_status: "unknown",
    customer_status_label: "Okänd status",
    priority: null,
    label: "Aktivitet med okänd klassificering",
  },
]

export type ActivityMockScenario =
  | "populated"
  | "empty"
  | "partial_error"
  | "full_error"
  | "unknown_status"
  | "delayed"

export function getActivityItemsForScenario(
  scenario: ActivityMockScenario,
): ActivityListItem[] {
  if (scenario === "empty") return []
  if (scenario === "unknown_status") {
    return ACTIVITY_ITEMS.filter((item) => item.customer_status === "unknown")
  }
  return ACTIVITY_ITEMS
}

export function cloneActivityItem(item: ActivityListItem): ActivityListItem {
  return { ...item }
}

export function getActivityPartialErrors(scenario: ActivityMockScenario) {
  if (scenario !== "partial_error") return []
  return [
    {
      section: "activity",
      code: "partial_unavailable",
      message:
        "Vissa aktiviteter kunde inte hämtas just nu. Listan kan vara ofullständig.",
    },
  ]
}
