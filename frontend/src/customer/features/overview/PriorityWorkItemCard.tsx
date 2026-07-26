import { WorkItemLink } from "@/customer/components/WorkItemLink"
import {
  displayStatusLabel,
  formatOverviewDateTime,
  workItemTypeLabel,
} from "@/customer/features/overview/overviewFormatters"
import type { PriorityWorkItem } from "@/customer/types/overview"
import { cn } from "@/lib/utils"

type PriorityWorkItemCardProps = {
  item: PriorityWorkItem
}

function statusTone(status: PriorityWorkItem["customer_status"]): string {
  switch (status) {
    case "prioritized":
    case "waiting_for_decision":
      return "border-status-warning/30 bg-status-warning/5 text-text-primary"
    case "needs_help":
    case "failed":
      return "border-status-danger/30 bg-status-danger/5 text-text-primary"
    case "completed":
      return "border-status-success/30 bg-status-success/5 text-text-primary"
    case "unknown":
      return "border-border bg-surface-subtle text-text-secondary"
    default:
      return "border-border bg-surface text-text-primary"
  }
}

export function PriorityWorkItemCard({ item }: PriorityWorkItemCardProps) {
  const statusLabel = displayStatusLabel(item.customer_status_label)

  return (
    <article
      className={cn(
        "rounded-lg border p-4",
        statusTone(item.customer_status),
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-body-small font-medium text-text-secondary">
            {workItemTypeLabel(item.type)}
            {item.priority_label ? ` · ${item.priority_label}` : null}
          </p>
          <h3 className="mt-1 break-words text-body font-semibold text-text-primary">
            {item.title}
          </h3>
        </div>
        <span className="shrink-0 rounded-full border border-border bg-page px-3 py-1 text-caption font-medium text-text-primary">
          {statusLabel}
        </span>
      </div>
      <dl className="mt-3 grid gap-1 text-body-small text-text-secondary">
        {item.customer_name ? (
          <div className="flex flex-wrap gap-1">
            <dt className="font-medium text-text-primary">Kund:</dt>
            <dd className="break-words">{item.customer_name}</dd>
          </div>
        ) : null}
        <div className="flex flex-wrap gap-1">
          <dt className="font-medium text-text-primary">Uppdaterad:</dt>
          <dd>{formatOverviewDateTime(item.updated_at)}</dd>
        </div>
      </dl>
      <p className="mt-4">
        <WorkItemLink workItemId={item.work_item_id}>
          Visa detalj
        </WorkItemLink>
      </p>
    </article>
  )
}
