import type { ActivityType } from "@/customer/types/activity"
import { formatOverviewDateTime } from "@/customer/features/work-queues/workQueueFormatters"
import { displayStatusLabel } from "@/customer/features/work-queues/workQueueFormatters"
import type { ActivityListItem } from "@/customer/types/activity"
import { cn } from "@/lib/utils"

const ACTIVITY_TYPE_LABELS: Record<ActivityType, string> = {
  lead: "Lead",
  support: "Kundfråga",
  invoice: "Faktura",
  unknown: "Aktivitet",
}

type ActivityItemCardProps = {
  item: ActivityListItem
}

function statusTone(status: ActivityListItem["customer_status"]): string {
  switch (status) {
    case "waiting_for_decision":
    case "prepared":
      return "border-status-warning/30 bg-status-warning/5"
    case "failed":
    case "needs_help":
      return "border-status-danger/30 bg-status-danger/5"
    case "completed":
      return "border-status-success/30 bg-status-success/5"
    case "unknown":
      return "border-border bg-surface-subtle"
    default:
      return "border-border bg-surface"
  }
}

export function ActivityItemCard({ item }: ActivityItemCardProps) {
  const statusLabel = displayStatusLabel(item.customer_status_label)

  return (
    <article className={cn("rounded-lg border p-4", statusTone(item.customer_status))}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-body-small font-medium text-text-secondary">
            {ACTIVITY_TYPE_LABELS[item.type]}
            {item.priority ? ` · ${item.priority}` : null}
          </p>
          <h2 className="mt-1 break-words text-body font-semibold text-text-primary">
            {item.label}
          </h2>
        </div>
        <span className="shrink-0 rounded-full border border-border bg-page px-3 py-1 text-caption font-medium text-text-primary">
          {statusLabel}
        </span>
      </div>
      <p className="mt-3 text-body-small text-text-secondary">
        {formatOverviewDateTime(item.at)}
      </p>
    </article>
  )
}

export function groupActivitiesByDate(items: ActivityListItem[]): Array<{
  dateLabel: string
  items: ActivityListItem[]
}> {
  const formatter = new Intl.DateTimeFormat("sv-SE", { dateStyle: "full" })
  const groups = new Map<string, ActivityListItem[]>()

  for (const item of items) {
    const date = new Date(item.at)
    const key = Number.isNaN(date.getTime())
      ? "Okänt datum"
      : formatter.format(date)
    const existing = groups.get(key) ?? []
    existing.push(item)
    groups.set(key, existing)
  }

  return Array.from(groups.entries()).map(([dateLabel, groupedItems]) => ({
    dateLabel,
    items: groupedItems,
  }))
}
