import type { ApprovalListItem } from "@/customer/types/approvals"
import type { WorkItemListItem } from "@/customer/types/work-items"
import { LONG_CONTENT_WORK_ITEM } from "@/customer/features/quality/longContentFixtures"

const LEAD_ITEMS: WorkItemListItem[] = [
  {
    work_item_id: "wi-lead-101",
    type: "lead",
    title: "Solcellsanläggning för villa i Täby",
    customer_name: "Erik Lindström",
    customer_email: "erik.lindstrom@fiktivmail.se",
    customer_status: "prioritized",
    customer_status_label: "Prioriterad",
    priority_rank: 1,
    priority_label: "Hög prioritet",
    summary:
      "Förfrågan om offert på 12 kW solceller med batterilagring. Kunden vill ha svar inom veckan.",
    created_at: "2026-07-26T06:15:00+02:00",
    updated_at: "2026-07-26T09:40:00+02:00",
  },
  {
    work_item_id: "wi-lead-102",
    type: "lead",
    title: "Laddbox till flerbostadshus",
    customer_name: "Brf Solhöjden",
    customer_email: "styrelsen@brfsolhojden-fiktiv.se",
    customer_status: "new",
    customer_status_label: "Ny",
    priority_rank: 3,
    priority_label: null,
    summary:
      "Intresseanmälan för installation av laddboxar i garage. Behöver bedömning av elkapacitet.",
    created_at: "2026-07-26T08:00:00+02:00",
    updated_at: "2026-07-26T08:00:00+02:00",
  },
  {
    work_item_id: "wi-lead-103",
    type: "lead",
    title: "Serviceavtal för värmepump",
    customer_name: "Maria Holm",
    customer_email: "maria.holm@fiktivmail.se",
    customer_status: "waiting_for_decision",
    customer_status_label: "Väntar på beslut",
    priority_rank: 2,
    priority_label: "Medel prioritet",
    summary:
      "Kunden vill ha årligt serviceavtal. Offertutkast är förberett och väntar på ert godkännande.",
    created_at: "2026-07-25T14:30:00+02:00",
    updated_at: "2026-07-26T07:20:00+02:00",
  },
  {
    work_item_id: "wi-lead-104",
    type: "lead",
    title: "Elcentral i nybyggt kontor",
    customer_name: "Nordic Kontor AB",
    customer_email: "projekt@nordickontor-fiktiv.se",
    customer_status: "waiting_for_customer",
    customer_status_label: "Väntar på kund",
    priority_rank: 4,
    priority_label: null,
    summary:
      "Vi har skickat kompletterande frågor om ritningar. Väntar på svar från kundens projektledare.",
    created_at: "2026-07-24T10:00:00+02:00",
    updated_at: "2026-07-25T16:45:00+02:00",
  },
  {
    work_item_id: "wi-lead-105",
    type: "lead",
    title: "Belysningsuppgradering i butik",
    customer_name: "Ljus & Form HB",
    customer_email: "info@ljusform-fiktiv.se",
    customer_status: "completed",
    customer_status_label: "Klar",
    priority_rank: 8,
    priority_label: null,
    summary:
      "Offert accepterad och ärendet är avslutat. Uppföljning planeras av ert team.",
    created_at: "2026-07-20T09:00:00+02:00",
    updated_at: "2026-07-25T11:30:00+02:00",
  },
  {
    work_item_id: "wi-lead-106",
    type: "lead",
    title: "Okänt inkommande ärende",
    customer_name: "Okänd avsändare",
    customer_email: null,
    customer_status: "unknown",
    customer_status_label: "Okänd status",
    priority_rank: 9,
    priority_label: null,
    summary:
      "Ett inkommande meddelande kunde inte klassificeras fullt ut. Kontrollera manuellt.",
    created_at: "2026-07-26T05:00:00+02:00",
    updated_at: "2026-07-26T05:00:00+02:00",
  },
]

const SUPPORT_ITEMS: WorkItemListItem[] = [
  {
    work_item_id: "wi-support-201",
    type: "support",
    title: "Fråga om faktura för juli",
    customer_name: "Johan Berg",
    customer_email: "johan.berg@fiktivmail.se",
    customer_status: "new",
    customer_status_label: "Ny",
    priority_rank: 2,
    priority_label: null,
    summary:
      "Kunden undrar över en post på fakturan och vill ha förtydligande innan betalning.",
    created_at: "2026-07-26T07:30:00+02:00",
    updated_at: "2026-07-26T07:30:00+02:00",
  },
  {
    work_item_id: "wi-support-202",
    type: "support",
    title: "Felkod på värmepump",
    customer_name: "Karin Nyström",
    customer_email: "karin.nystrom@fiktivmail.se",
    customer_status: "in_progress",
    customer_status_label: "Pågår",
    priority_rank: 1,
    priority_label: "Hög prioritet",
    summary:
      "Kunden rapporterar felkod E42. Systemet har samlat teknisk information och förbereder svar.",
    created_at: "2026-07-25T18:00:00+02:00",
    updated_at: "2026-07-26T09:10:00+02:00",
  },
  {
    work_item_id: "wi-support-203",
    type: "support",
    title: "Bekräftelse av servicebesök",
    customer_name: "Anders Viklund",
    customer_email: "anders.viklund@fiktivmail.se",
    customer_status: "waiting_for_customer",
    customer_status_label: "Väntar på kund",
    priority_rank: 4,
    priority_label: null,
    summary:
      "Vi har föreslagit två tider för servicebesök. Väntar på att kunden väljer ett alternativ.",
    created_at: "2026-07-24T11:00:00+02:00",
    updated_at: "2026-07-25T14:00:00+02:00",
  },
  {
    work_item_id: "wi-support-204",
    type: "support",
    title: "Svar om garanti efter installation",
    customer_name: "Helena Fors",
    customer_email: "helena.fors@fiktivmail.se",
    customer_status: "prepared",
    customer_status_label: "Förberett svar",
    priority_rank: 3,
    priority_label: null,
    summary:
      "Ett utkast till svar om garantivillkor är klart för granskning innan det skickas.",
    created_at: "2026-07-25T08:45:00+02:00",
    updated_at: "2026-07-26T06:50:00+02:00",
  },
  {
    work_item_id: "wi-support-205",
    type: "support",
    title: "Otydlig felbeskrivning från kund",
    customer_name: "Per Sandberg",
    customer_email: "per.sandberg@fiktivmail.se",
    customer_status: "needs_help",
    customer_status_label: "Behöver hjälp",
    priority_rank: 1,
    priority_label: "Hög prioritet",
    summary:
      "Beskrivningen räcker inte för att avgöra nästa steg. En medarbetare behöver följa upp.",
    created_at: "2026-07-26T06:00:00+02:00",
    updated_at: "2026-07-26T08:15:00+02:00",
  },
  {
    work_item_id: "wi-support-206",
    type: "support",
    title: "Misslyckad automatisk kategorisering",
    customer_name: "Teknik Partner AB",
    customer_email: "support@teknikpartner-fiktiv.se",
    customer_status: "failed",
    customer_status_label: "Misslyckades",
    priority_rank: 5,
    priority_label: null,
    summary:
      "Ärendet kunde inte hanteras automatiskt. Kontrollera uppgifterna innan ärendet tas vidare.",
    created_at: "2026-07-23T15:20:00+02:00",
    updated_at: "2026-07-24T09:00:00+02:00",
  },
]

const NEEDS_HELP_ITEMS: WorkItemListItem[] = [
  {
    work_item_id: "wi-help-301",
    type: "needs_help",
    title: "Saknar kunduppgifter för offert",
    customer_name: null,
    customer_email: "okand@fiktivmail.se",
    customer_status: "needs_help",
    customer_status_label: "Behöver hjälp",
    priority_rank: 1,
    priority_label: "Hög prioritet",
    summary:
      "Systemet behöver hjälp för att fortsätta. Kontaktnamn och adress saknas i inkommande förfrågan.",
    created_at: "2026-07-26T07:00:00+02:00",
    updated_at: "2026-07-26T09:00:00+02:00",
  },
  {
    work_item_id: "wi-help-302",
    type: "needs_help",
    title: "Oklar förfrågan om elarbete",
    customer_name: "Lisa Ekman",
    customer_email: "lisa.ekman@fiktivmail.se",
    customer_status: "needs_help",
    customer_status_label: "Behöver hjälp",
    priority_rank: 2,
    priority_label: null,
    summary:
      "Meddelandet innehåller motstridiga uppgifter. Kontrollera uppgifterna innan ärendet hanteras vidare.",
    created_at: "2026-07-25T16:30:00+02:00",
    updated_at: "2026-07-26T05:45:00+02:00",
  },
  {
    work_item_id: "wi-help-303",
    type: "needs_help",
    title: "Blockerad hantering av serviceärende",
    customer_name: "Västergård Fastigheter",
    customer_email: "forvaltning@vastergard-fiktiv.se",
    customer_status: "needs_help",
    customer_status_label: "Behöver hjälp",
    priority_rank: 3,
    priority_label: null,
    summary:
      "Systemet behöver hjälp för att fortsätta. Ytterligare information krävs innan nästa steg kan tas.",
    created_at: "2026-07-24T13:00:00+02:00",
    updated_at: "2026-07-25T10:20:00+02:00",
  },
  {
    work_item_id: "wi-help-304",
    type: "needs_help",
    title: "Misslyckad uppföljning av kundärende",
    customer_name: "Gustav Alm",
    customer_email: "gustav.alm@fiktivmail.se",
    customer_status: "failed",
    customer_status_label: "Misslyckades",
    priority_rank: 4,
    priority_label: null,
    summary:
      "En automatisk uppföljning kunde inte slutföras. Kontrollera uppgifterna innan ärendet hanteras vidare.",
    created_at: "2026-07-23T09:15:00+02:00",
    updated_at: "2026-07-24T14:30:00+02:00",
  },
  {
    work_item_id: "wi-help-305",
    type: "needs_help",
    title: "Oklassificerat ärende",
    customer_name: "Okänd kund",
    customer_email: null,
    customer_status: "unknown",
    customer_status_label: "Okänd status",
    priority_rank: 5,
    priority_label: null,
    summary:
      "Ärendet kunde inte tolkas tillräckligt för automatisk hantering.",
    created_at: "2026-07-26T04:00:00+02:00",
    updated_at: "2026-07-26T04:00:00+02:00",
  },
]

const APPROVAL_ITEMS: ApprovalListItem[] = [
  {
    approval_id: "appr-401",
    work_item_id: "wi-lead-103",
    work_item_type: "lead",
    work_item_title: "Serviceavtal för värmepump",
    title: "Offertutkast för serviceavtal",
    summary:
      "Ett utkast till offert för årligt serviceavtal är förberett. Beslut kan inte fattas i förhandsvisningen.",
    customer_status: "waiting_for_decision",
    customer_status_label: "Väntar på beslut",
    requested_at: "2026-07-26T07:20:00+02:00",
  },
  {
    approval_id: "appr-402",
    work_item_id: "wi-support-204",
    work_item_type: "support",
    work_item_title: "Svar om garanti efter installation",
    title: "Förslag på svar till kund",
    summary:
      "Ett svar om garantivillkor är förberett. Granska innehållet innan det skickas i produktion.",
    customer_status: "prepared",
    customer_status_label: "Förberett svar",
    requested_at: "2026-07-26T06:50:00+02:00",
  },
  {
    approval_id: "appr-403",
    work_item_id: "wi-lead-101",
    work_item_type: "lead",
    work_item_title: "Solcellsanläggning för villa i Täby",
    title: "Intern bedömning av projektomfattning",
    summary:
      "Förslag på resursplanering och tidsuppskattning väntar på intern bedömning.",
    customer_status: "waiting_for_decision",
    customer_status_label: "Väntar på beslut",
    requested_at: "2026-07-26T09:40:00+02:00",
  },
  {
    approval_id: "appr-404",
    work_item_id: "wi-support-999",
    work_item_type: "unknown",
    work_item_title: "Oklassificerat ärende",
    title: "Okänt förslag",
    summary:
      "Ett förslag kunde inte kopplas till en känd kategori. Kontrollera manuellt.",
    customer_status: "unknown",
    customer_status_label: "Okänd status",
    requested_at: "2026-07-26T05:00:00+02:00",
  },
]

export type QueueMockScenario =
  | "populated"
  | "empty"
  | "partial_error"
  | "full_error"
  | "unknown_status"
  | "delayed"
  | "not_found"
  | "empty_timeline"
  | "long_content"

export function getPopulatedWorkItems(): WorkItemListItem[] {
  return [...LEAD_ITEMS, ...SUPPORT_ITEMS, ...NEEDS_HELP_ITEMS]
}

export function getPopulatedApprovals(): ApprovalListItem[] {
  return [...APPROVAL_ITEMS]
}

export function cloneWorkItem(item: WorkItemListItem): WorkItemListItem {
  return { ...item }
}

export function cloneApproval(item: ApprovalListItem): ApprovalListItem {
  return { ...item }
}

export function getWorkItemsForScenario(
  scenario: QueueMockScenario,
): WorkItemListItem[] {
  if (scenario === "empty") return []
  if (scenario === "long_content") return [LONG_CONTENT_WORK_ITEM]
  if (scenario === "unknown_status") {
    return getPopulatedWorkItems().filter(
      (item) => item.customer_status === "unknown",
    )
  }
  return getPopulatedWorkItems()
}

export function getApprovalsForScenario(
  scenario: QueueMockScenario,
): ApprovalListItem[] {
  if (scenario === "empty") return []
  if (scenario === "unknown_status") {
    return getPopulatedApprovals().filter(
      (item) => item.customer_status === "unknown",
    )
  }
  return getPopulatedApprovals()
}

export function getQueuePartialErrors(scenario: QueueMockScenario) {
  if (scenario !== "partial_error") return []
  return [
    {
      section: "work_items",
      code: "partial_unavailable",
      message:
        "Vissa poster kunde inte hämtas just nu. Listan kan vara ofullständig.",
    },
  ]
}
