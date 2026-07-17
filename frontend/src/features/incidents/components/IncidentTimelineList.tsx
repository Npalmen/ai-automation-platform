import type { IncidentTimelineEventOut } from "../types"
import { formatTimestamp } from "../formatters"

type IncidentTimelineListProps = {
  events: IncidentTimelineEventOut[]
}

export function IncidentTimelineList({ events }: IncidentTimelineListProps) {
  if (events.length === 0) {
    return (
      <p className="text-body text-text-muted">Ingen tidslinje ännu.</p>
    )
  }

  return (
    <ol className="flex min-w-0 flex-col gap-4">
      {events.map((event) => (
        <li
          key={event.event_id}
          className="rounded-md border border-border bg-surface p-4"
        >
          <div className="flex flex-wrap items-center gap-2 text-label text-text-muted">
            <span>{formatTimestamp(event.created_at)}</span>
            <span aria-hidden="true">·</span>
            <span>{event.actor_display_name}</span>
            <span aria-hidden="true">·</span>
            <span>{event.event_type}</span>
          </div>
          <p className="mt-2 whitespace-pre-wrap break-words text-body text-text-primary">
            {event.message}
          </p>
        </li>
      ))}
    </ol>
  )
}
