import {
  displayStatusLabel,
  formatOverviewDateTime,
} from "@/customer/features/overview/overviewFormatters"
import type { WorkItemType } from "@/customer/types/work-items"

const relativeTimeFormatter = new Intl.RelativeTimeFormat("sv-SE", {
  numeric: "auto",
})

const WORK_ITEM_TYPE_LABELS: Record<WorkItemType, string> = {
  lead: "Lead",
  support: "Kundfråga",
  needs_help: "Behöver hjälp",
  unknown: "Ärende",
}

export function workQueueTypeLabel(type: WorkItemType): string {
  return WORK_ITEM_TYPE_LABELS[type] ?? WORK_ITEM_TYPE_LABELS.unknown
}

export { displayStatusLabel, formatOverviewDateTime }

export function formatRelativeWaitTime(
  updatedAt: string | null | undefined,
  referenceDate = new Date("2026-07-26T12:00:00+02:00"),
): string {
  if (!updatedAt) return "—"
  const updated = new Date(updatedAt)
  if (Number.isNaN(updated.getTime())) return "—"

  const diffMs = updated.getTime() - referenceDate.getTime()
  const diffMinutes = Math.round(diffMs / (1000 * 60))

  if (Math.abs(diffMinutes) < 60) {
    return relativeTimeFormatter.format(diffMinutes, "minute")
  }

  const diffHours = Math.round(diffMinutes / 60)
  if (Math.abs(diffHours) < 48) {
    return relativeTimeFormatter.format(diffHours, "hour")
  }

  const diffDays = Math.round(diffHours / 24)
  return relativeTimeFormatter.format(diffDays, "day")
}

export function formatResultRange(
  offset: number,
  limit: number,
  total: number,
): string {
  if (total === 0) return "0 resultat"
  const start = offset + 1
  const end = Math.min(offset + limit, total)
  return `${start}–${end} av ${total}`
}
