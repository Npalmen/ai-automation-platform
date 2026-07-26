import { WorkItemLink } from "@/customer/components/WorkItemLink"
import {
  displayStatusLabel,
  formatOverviewDateTime,
} from "@/customer/features/work-queues/workQueueFormatters"
import type { ApprovalListItem } from "@/customer/types/approvals"
import type { ApprovalWorkItemType } from "@/customer/types/approvals"
import { cn } from "@/lib/utils"

const APPROVAL_TYPE_LABELS: Record<ApprovalWorkItemType, string> = {
  lead: "Lead",
  support: "Kundfråga",
  unknown: "Ärende",
}

function approvalTypeLabel(type: ApprovalWorkItemType): string {
  return APPROVAL_TYPE_LABELS[type] ?? APPROVAL_TYPE_LABELS.unknown
}

function statusTone(status: ApprovalListItem["customer_status"]): string {
  switch (status) {
    case "waiting_for_decision":
    case "prepared":
      return "border-status-warning/30 bg-status-warning/5"
    case "unknown":
      return "border-border bg-surface-subtle"
    default:
      return "border-border bg-surface"
  }
}

type ApprovalItemCardProps = {
  item: ApprovalListItem
}

export function ApprovalItemCard({ item }: ApprovalItemCardProps) {
  const statusLabel = displayStatusLabel(item.customer_status_label)

  return (
    <article
      className={cn("rounded-lg border p-4", statusTone(item.customer_status))}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-body-small font-medium text-text-secondary">
            {approvalTypeLabel(item.work_item_type)}
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
        <div className="flex flex-wrap gap-1">
          <dt className="font-medium text-text-primary">Gäller:</dt>
          <dd className="break-words">
            <WorkItemLink workItemId={item.work_item_id}>
              {item.work_item_title}
            </WorkItemLink>
          </dd>
        </div>
        <div className="flex flex-wrap gap-1">
          <dt className="font-medium text-text-primary">Skapad:</dt>
          <dd>{formatOverviewDateTime(item.requested_at)}</dd>
        </div>
      </dl>

      <p className="mt-4 rounded-md border border-border bg-page px-3 py-2 text-body-small text-text-secondary">
        Beslut kan inte fattas i förhandsvisningen.
      </p>
    </article>
  )
}
