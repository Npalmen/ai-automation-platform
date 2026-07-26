import { EmptyState } from "@/components/shared/EmptyState"
import { WorkQueueItemCard } from "@/customer/features/work-queues/WorkQueueItemCard"
import type { WorkItemListItem } from "@/customer/types/work-items"

type WorkQueueListProps = {
  items: WorkItemListItem[]
  emptyTitle: string
  emptyDescription: string
  linkItems?: boolean
}

export function WorkQueueList({
  items,
  emptyTitle,
  emptyDescription,
  linkItems = false,
}: WorkQueueListProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
      />
    )
  }

  return (
    <ul className="space-y-3" aria-label="Arbetskö">
      {items.map((item) => (
        <li key={item.work_item_id}>
          <WorkQueueItemCard item={item} showDetailLink={linkItems} />
        </li>
      ))}
    </ul>
  )
}
