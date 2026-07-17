import { cn } from "@/lib/utils"

import { EmptyState } from "./EmptyState"
import { ErrorState } from "./ErrorState"
import { LoadingState } from "./LoadingState"

export type AuditTimelineEvent = {
  event_id: string
  category: string
  action: string
  status: string
  created_at: string
}

type AuditTimelineProps = {
  events: AuditTimelineEvent[]
  total?: number
  loading?: boolean
  error?: Error | null
  className?: string
}

function formatTimestamp(value: string): string {
  try {
    return new Intl.DateTimeFormat("sv-SE", {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value))
  } catch {
    return value
  }
}

export function AuditTimeline({
  events,
  total,
  loading = false,
  error = null,
  className,
}: AuditTimelineProps) {
  if (loading) {
    return <LoadingState label="Laddar granskning…" rows={4} className={className} />
  }

  if (error) {
    return (
      <ErrorState
        title="Kunde inte ladda granskning"
        description="Granskningshändelser kunde inte hämtas."
        recommendedAction="Försök uppdatera sidan."
        technicalDetails={error.message}
        className={className}
      />
    )
  }

  if (events.length === 0) {
    return (
      <EmptyState
        title="Inga granskningshändelser"
        description="Det finns inga audit-händelser att visa för denna kund."
        className={className}
      />
    )
  }

  return (
    <div className={cn("min-w-0 space-y-3", className)}>
      {typeof total === "number" ? (
        <p className="text-body-small text-text-secondary">
          Visar {events.length} av {total} händelser
        </p>
      ) : null}
      <ol className="space-y-3 border-l border-border pl-4">
        {events.map((event) => (
          <li key={event.event_id} className="relative min-w-0">
            <span
              aria-hidden
              className="absolute -left-[1.3rem] top-1.5 h-2 w-2 rounded-full bg-border"
            />
            <p className="text-body font-medium text-text-primary">
              {event.category} · {event.action}
            </p>
            <p className="text-caption text-text-secondary">
              {formatTimestamp(event.created_at)} · {event.status}
            </p>
          </li>
        ))}
      </ol>
    </div>
  )
}
