import type { WorkItemListItem } from "@/customer/types/work-items"

const LONG_COMPANY_NAME =
  "Nordiska Energi- och Installationspartnergruppen för Hållbara Lösningar i Storstockholm AB"

const LONG_CUSTOMER_NAME =
  "Christina-Marie von Hohenstein-Lindqvist på Ekonomiavdelningen"

const LONG_EMAIL =
  "christina-marie.von-hohenstein-lindqvist.ekonomi@nordiska-energi-installationspartnergruppen-fiktiv.se"

const LONG_TITLE =
  "Komplett el- och solcellsinstallation med batterilagring, laddinfrastruktur och energioptimering för flerbostadshus i expansionsfas"

const LONG_SUMMARY =
  "Kunden önskar en samlad offert som täcker ny huvudcentral, kabeldragning i befintliga schakt, installation av växelriktare och batteripaket, samt integration mot befintligt styrsystem. Projektet kräver samordning med byggentreprenör och tydlig tidsplan för etappvis driftsättning utan avbrott i befintlig verksamhet."

const LONG_STATUS_LABEL =
  "Väntar på beslut från er sida efter intern teknisk genomgång"

const LONG_PRIORITY_LABEL =
  "Hög prioritet med kort svarstid enligt kundens önskemål"

export const LONG_CONTENT_WORK_ITEM: WorkItemListItem = {
  work_item_id: "wi-long-content-001",
  type: "lead",
  title: LONG_TITLE,
  customer_name: LONG_CUSTOMER_NAME,
  customer_email: LONG_EMAIL,
  customer_status: "waiting_for_decision",
  customer_status_label: LONG_STATUS_LABEL,
  priority_rank: 1,
  priority_label: LONG_PRIORITY_LABEL,
  summary: LONG_SUMMARY,
  created_at: "2026-07-20T08:00:00+02:00",
  updated_at: "2026-07-26T11:30:00+02:00",
}

export const LONG_CONTENT_LABELS = {
  companyName: LONG_COMPANY_NAME,
  customerName: LONG_CUSTOMER_NAME,
  email: LONG_EMAIL,
  title: LONG_TITLE,
  summary: LONG_SUMMARY,
  statusLabel: LONG_STATUS_LABEL,
  priorityLabel: LONG_PRIORITY_LABEL,
} as const
