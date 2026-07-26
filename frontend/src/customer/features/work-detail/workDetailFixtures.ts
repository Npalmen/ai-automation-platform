import type { WorkItemListItem } from "@/customer/types/work-items"
import type {
  WorkItemDetail,
  WorkItemTimelineItem,
} from "@/customer/types/work-item-detail"

const TIMELINE_BY_ID: Record<string, WorkItemTimelineItem[]> = {
  "wi-lead-101": [
    {
      at: "2026-07-26T06:15:00+02:00",
      kind: "received",
      label: "Lead mottaget",
      detail: "Förfrågan om solcellsanläggning registrerades och prioriterades.",
    },
    {
      at: "2026-07-26T08:00:00+02:00",
      kind: "prepared",
      label: "Underlag förberett",
      detail: "Grundläggande projektinformation samlades in.",
    },
    {
      at: "2026-07-26T09:40:00+02:00",
      kind: "waiting_for_decision",
      label: "Väntar på beslut",
      detail: "Intern bedömning av projektomfattning väntar på ert godkännande.",
    },
  ],
  "wi-lead-103": [
    {
      at: "2026-07-25T14:30:00+02:00",
      kind: "received",
      label: "Lead mottaget",
      detail: "Förfrågan om serviceavtal registrerades.",
    },
    {
      at: "2026-07-26T07:20:00+02:00",
      kind: "waiting_for_decision",
      label: "Väntar på beslut",
      detail: "Offertutkast är förberett och väntar på ert godkännande.",
    },
  ],
  "wi-lead-104": [
    {
      at: "2026-07-24T10:00:00+02:00",
      kind: "received",
      label: "Lead mottaget",
      detail: "Förfrågan om elcentral registrerades.",
    },
    {
      at: "2026-07-25T16:45:00+02:00",
      kind: "waiting_for_customer",
      label: "Väntar på kund",
      detail: "Kompletterande frågor har skickats till kundens projektledare.",
    },
  ],
  "wi-lead-105": [
    {
      at: "2026-07-20T09:00:00+02:00",
      kind: "received",
      label: "Lead mottaget",
      detail: "Förfrågan om belysningsuppgradering registrerades.",
    },
    {
      at: "2026-07-25T11:30:00+02:00",
      kind: "completed",
      label: "Avslutat",
      detail: "Offert accepterad och ärendet är avslutat.",
    },
  ],
  "wi-lead-106": [
    {
      at: "2026-07-26T05:00:00+02:00",
      kind: "unknown",
      label: "Okänd händelse",
      detail: "Ärendet kunde inte klassificeras fullt ut.",
    },
  ],
  "wi-support-203": [
    {
      at: "2026-07-24T11:00:00+02:00",
      kind: "received",
      label: "Kundfråga mottagen",
      detail: "Förfrågan om servicebesök registrerades.",
    },
    {
      at: "2026-07-25T14:00:00+02:00",
      kind: "waiting_for_customer",
      label: "Väntar på kund",
      detail: "Två tidsförslag har skickats till kunden.",
    },
  ],
  "wi-support-205": [
    {
      at: "2026-07-26T06:00:00+02:00",
      kind: "received",
      label: "Kundfråga mottagen",
      detail: "Felbeskrivningen var ofullständig.",
    },
    {
      at: "2026-07-26T08:15:00+02:00",
      kind: "human_takeover",
      label: "Mänskligt övertagande behövs",
      detail: "En medarbetare behöver följa upp med kunden.",
    },
  ],
  "wi-support-206": [
    {
      at: "2026-07-23T15:20:00+02:00",
      kind: "received",
      label: "Kundfråga mottagen",
      detail: "Ärendet registrerades för automatisk hantering.",
    },
    {
      at: "2026-07-24T09:00:00+02:00",
      kind: "failed",
      label: "Misslyckades",
      detail: "Ärendet kunde inte hanteras automatiskt.",
    },
  ],
  "wi-help-301": [
    {
      at: "2026-07-26T07:00:00+02:00",
      kind: "received",
      label: "Ärende mottaget",
      detail: "Offertförfrågan saknade kontaktuppgifter.",
    },
    {
      at: "2026-07-26T09:00:00+02:00",
      kind: "human_takeover",
      label: "Mänskligt övertagande behövs",
      detail: "Kontaktnamn och adress behöver kompletteras manuellt.",
    },
  ],
  "wi-help-305": [
    {
      at: "2026-07-26T04:00:00+02:00",
      kind: "unknown",
      label: "Okänd händelse",
      detail: null,
    },
  ],
  "wi-help-empty": [],
}

const WAITING_FOR_BY_ID: Record<string, string | null> = {
  "wi-lead-101": "Ert beslut om projektomfattning",
  "wi-lead-103": "Ert godkännande av offertutkast",
  "wi-lead-104": "Svar från kundens projektledare",
  "wi-support-203": "Att kunden väljer en tid för servicebesök",
  "wi-support-204": "Granskning av förberett svar",
}

const HUMAN_TAKEOVER_BY_ID: Record<string, boolean> = {
  "wi-support-205": true,
  "wi-help-301": true,
  "wi-help-302": true,
  "wi-help-303": true,
}

function defaultTimeline(item: WorkItemListItem): WorkItemTimelineItem[] {
  return [
    {
      at: item.created_at,
      kind: "received",
      label: "Ärende mottaget",
      detail: item.summary,
    },
    {
      at: item.updated_at,
      kind: "system_action",
      label: "Senaste uppdatering",
      detail: null,
    },
  ]
}

export function buildWorkItemDetail(item: WorkItemListItem): WorkItemDetail {
  const timeline = TIMELINE_BY_ID[item.work_item_id] ?? defaultTimeline(item)

  return {
    work_item_id: item.work_item_id,
    type: item.type,
    title: item.title,
    customer_name: item.customer_name,
    customer_email: item.customer_email,
    customer_status: item.customer_status,
    customer_status_label: item.customer_status_label,
    priority_rank: item.priority_rank,
    priority_label: item.priority_label,
    summary: item.summary,
    created_at: item.created_at,
    updated_at: item.updated_at,
    timeline,
    waiting_for: WAITING_FOR_BY_ID[item.work_item_id] ?? null,
    human_takeover_required: HUMAN_TAKEOVER_BY_ID[item.work_item_id] ?? false,
  }
}

export function cloneWorkItemDetail(detail: WorkItemDetail): WorkItemDetail {
  return {
    ...detail,
    timeline: detail.timeline.map((entry) => ({ ...entry })),
  }
}

export const EMPTY_TIMELINE_WORK_ITEM_ID = "wi-help-empty"
