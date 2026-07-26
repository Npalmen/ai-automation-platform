import {
  displayStatusLabel,
  formatOverviewDateTime,
  formatRelativeWaitTime,
  workQueueTypeLabel,
} from "@/customer/features/work-queues/workQueueFormatters"
import type { WorkItemListItem } from "@/customer/types/work-items"
import { cn } from "@/lib/utils"

type WorkQueueItemCardProps = {
  item: WorkItemListItem
}

function statusTone(status: WorkItemListItem["customer_status"]): string {
  switch (status) {
    case "prioritized":
    case "waiting_for_decision":
      return "border-status-warning/30 bg-status-warning/5"
    case "needs_help":
    case "failed":
      return "border-status-danger/30 bg-status-danger/5"
    case "completed":
      return "border-status-success/30 bg-status-success/5"
    case "unknown":
      return "border-border bg-surface-subtle"
    default:
      return "border-border bg-surface"
  }
}

export function WorkQueueItemCard({ item }: WorkQueueItemCardProps) {
  const statusLabel = displayStatusLabel(item.customer_status_label)

  return (
    <article
      className={cn("rounded-lg border p-4", statusTone(item.customer_status))}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-body-small font-medium text-text-secondary">
            {workQueueTypeLabel(item.type)}
            {item.priority_label ? ` · ${item.priority_label}` : null}
          </p>
          <h2 className="mt-1 break-words text-body font-semibold text-text-primary">
            {item.title}
          </h2>
        </div>
        <span className="shrink-0 rounded-full border border-border bg-page px-3 py-1 text-caption font-medium text-text-primary">
          {statusLabel}
        </span>
      </div>

      <p className="mt-3 break-words text-body text-text-secondary">
        {item.summary}
      </p>

      <dl className="mt-3 grid gap-1 text-body-small text-text-secondary">
        {item.customer_name ? (
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-text-primary">Kund:</dt>
            <dd className="break-words">{item.customer_name}</dd>
          </div>
        ) : null}
        {item.customer_email ? (
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-text-primary">E-post:</dt>
            <dd className="break-all">{item.customer_email}</dd>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-1">
          <dt className="font-medium text-text-primary">Skapad:</dt>
          <dd>{formatOverviewDateTime(item.created_at)}</dd>
        </div>
        <div className="flex flex-wrap gap-1">
          <dt className="font-medium text-text-primary">Uppdaterad:</dt>
          <dd>
            {formatOverviewDateTime(item.updated_at)}
            {" · "}
            {formatRelativeWaitTime(item.updated_at)}
          </dd>
        </div>
      </dl>
    </article>
  )
}
