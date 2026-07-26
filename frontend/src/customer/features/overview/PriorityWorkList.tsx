import { EmptyState } from "@/components/shared/EmptyState"
import { PriorityWorkItemCard } from "@/customer/features/overview/PriorityWorkItemCard"
import type { PriorityWorkItem } from "@/customer/types/overview"

type PriorityWorkListProps = {
  items: PriorityWorkItem[]
}

export function PriorityWorkList({ items }: PriorityWorkListProps) {
  return (
    <section aria-labelledby="overview-priority-heading" className="mt-8 space-y-4">
      <h2 id="overview-priority-heading" className="text-section-title text-text-primary">
        Behöver din uppmärksamhet
      </h2>
      {items.length === 0 ? (
        <EmptyState
          title="Inget behöver din uppmärksamhet just nu"
          description="Nya ärenden som behöver hanteras visas här när de prioriteras i arbetsytan."
        />
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.work_item_id}>
              <PriorityWorkItemCard item={item} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
