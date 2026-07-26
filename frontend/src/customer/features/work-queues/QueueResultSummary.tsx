import { formatResultRange } from "@/customer/features/work-queues/workQueueFormatters"

type QueueResultSummaryProps = {
  offset: number
  limit: number
  total: number
  isRefreshing?: boolean
}

export function QueueResultSummary({
  offset,
  limit,
  total,
  isRefreshing = false,
}: QueueResultSummaryProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-body-small text-text-secondary">
      <p>{formatResultRange(offset, limit, total)}</p>
      {isRefreshing ? (
        <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-caption text-text-secondary">
          Uppdaterar…
        </span>
      ) : null}
    </div>
  )
}
