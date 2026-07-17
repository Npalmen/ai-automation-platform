import { EmptyState } from "@/components/operator/EmptyState"
import { SeverityBadge } from "@/components/operator/SeverityBadge"

import type { PriorityItem } from "../types"

type PriorityListProps = {
  items: PriorityItem[]
}

/**
 * Renders priorities in backend order — do not sort or reorder here.
 * Sorting is owned by the overview service (_build_priority_items).
 */
export function PriorityList({ items }: PriorityListProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="Ingen åtgärd krävs"
        description="Inga prioriterade avvikelser just nu."
      />
    )
  }

  return (
    <section aria-labelledby="overview-priority-heading">
      <h2
        id="overview-priority-heading"
        className="mb-3 text-section-title text-text-primary"
      >
        Prioriterad åtgärdslista
      </h2>
      <ul className="flex min-w-0 flex-col gap-3">
        {items.map((item) => (
          <li
            key={item.id}
            className="min-w-0 rounded-lg border border-border bg-surface p-4 shadow-sm"
          >
            <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <SeverityBadge variant={item.severity_badge} />
                  <span className="text-label font-medium text-text-primary">
                    {item.customer_name}
                  </span>
                  <span className="text-caption text-text-muted">
                    {item.category}
                  </span>
                </div>
                <p className="text-card-title text-text-primary">{item.title}</p>
                {item.impact ? (
                  <p className="break-words text-body-small text-text-secondary">
                    {item.impact}
                  </p>
                ) : null}
                {item.recommended_action ? (
                  <p className="break-words text-body-small text-text-primary">
                    <span className="font-medium">Nästa steg:</span>{" "}
                    {item.recommended_action}
                  </p>
                ) : null}
              </div>
              <div className="shrink-0 text-caption text-text-muted md:text-right">
                {item.age_hours != null ? (
                  <p>{item.age_hours} h sedan</p>
                ) : null}
                {item.detected_at ? (
                  <p className="hidden sm:block">
                    {new Date(item.detected_at).toLocaleString("sv-SE")}
                  </p>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
