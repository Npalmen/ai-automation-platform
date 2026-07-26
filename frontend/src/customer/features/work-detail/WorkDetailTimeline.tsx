import type { WorkItemTimelineKind } from "@/customer/types/work-item-detail"
import { formatOverviewDateTime } from "@/customer/features/work-queues/workQueueFormatters"
import type { WorkItemTimelineItem } from "@/customer/types/work-item-detail"
import { cn } from "@/lib/utils"

type WorkDetailTimelineProps = {
  items: WorkItemTimelineItem[]
}

function timelineTone(kind: WorkItemTimelineKind): string {
  switch (kind) {
    case "failed":
    case "human_takeover":
      return "border-status-danger/30 bg-status-danger/5"
    case "completed":
      return "border-status-success/30 bg-status-success/5"
    case "waiting_for_decision":
    case "waiting_for_customer":
      return "border-status-warning/30 bg-status-warning/5"
    case "unknown":
      return "border-border bg-surface-subtle"
    default:
      return "border-border bg-surface"
  }
}

export function WorkDetailTimeline({ items }: WorkDetailTimelineProps) {
  if (items.length === 0) {
    return (
      <p className="rounded-lg border border-border bg-surface-subtle p-4 text-body text-text-secondary">
        Ingen historik finns att visa ännu.
      </p>
    )
  }

  return (
    <ol className="space-y-3" aria-label="Tidslinje">
      {items.map((item, index) => (
        <li
          key={`${item.at}-${item.kind}-${index}`}
          className={cn("rounded-lg border p-4", timelineTone(item.kind))}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h3 className="text-body font-semibold text-text-primary">
              {item.label}
            </h3>
            <time
              className="text-body-small text-text-secondary"
              dateTime={item.at}
            >
              {formatOverviewDateTime(item.at)}
            </time>
          </div>
          {item.detail ? (
            <p className="mt-2 break-words text-body text-text-secondary">
              {item.detail}
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  )
}
