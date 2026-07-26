import type { PriorityWorkItemType } from "@/customer/types/overview"

const dateTimeFormatter = new Intl.DateTimeFormat("sv-SE", {
  dateStyle: "medium",
  timeStyle: "short",
})

const integerFormatter = new Intl.NumberFormat("sv-SE", {
  maximumFractionDigits: 0,
})

const hoursFormatter = new Intl.NumberFormat("sv-SE", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
})

const currencyFormatter = new Intl.NumberFormat("sv-SE", {
  style: "currency",
  currency: "SEK",
  maximumFractionDigits: 0,
})

export function formatOverviewDateTime(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return dateTimeFormatter.format(date)
}

export function formatInteger(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "0"
  return integerFormatter.format(Math.max(0, value))
}

export function formatHoursSaved(value: number | null | undefined): string | null {
  if (value == null || Number.isNaN(value)) return null
  return `${hoursFormatter.format(value)} tim`
}

export function formatSekValue(value: number | null | undefined): string | null {
  if (value == null || Number.isNaN(value)) return null
  return currencyFormatter.format(value)
}

export const WORK_ITEM_TYPE_LABELS: Record<PriorityWorkItemType, string> = {
  lead: "Lead",
  support: "Kundfråga",
  approval: "Godkännande",
  needs_help: "Behöver hjälp",
  unknown: "Ärende",
}

export function workItemTypeLabel(type: PriorityWorkItemType): string {
  return WORK_ITEM_TYPE_LABELS[type] ?? WORK_ITEM_TYPE_LABELS.unknown
}

export function displayStatusLabel(label: string | null | undefined): string {
  const trimmed = label?.trim()
  return trimmed && trimmed.length > 0 ? trimmed : "Okänd status"
}
