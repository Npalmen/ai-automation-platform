import { Link } from "react-router-dom"

import { SeverityBadge } from "@/components/operator/SeverityBadge"

import { panelSeverityLabel } from "../formatters"
import type { IncidentSignalOut } from "../types"

type IncidentSignalsPanelProps = {
  signals: IncidentSignalOut[]
}

export function IncidentSignalsPanel({ signals }: IncidentSignalsPanelProps) {
  if (signals.length === 0) {
    return <p className="text-body text-text-muted">Inga kopplade signaler.</p>
  }

  return (
    <ul className="flex min-w-0 flex-col gap-3">
      {signals.map((signal) => (
        <li
          key={`${signal.signal_id}-${signal.linked_at}`}
          className="rounded-md border border-border bg-surface p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge
              variant={
                signal.snapshot_severity === "critical"
                  ? "P1"
                  : signal.snapshot_severity === "failed"
                    ? "P2"
                    : signal.snapshot_severity === "warning"
                      ? "P3"
                      : "P4"
              }
            />
            <span className="text-label text-text-muted">
              {panelSeverityLabel(signal.snapshot_severity)}
            </span>
          </div>
          <p className="mt-2 font-medium text-text-primary">
            {signal.snapshot_title}
          </p>
          <p className="mt-1 whitespace-pre-wrap break-words text-body-small text-text-secondary">
            {signal.snapshot_summary}
          </p>
          <Link
            to={`/needs-help/${encodeURIComponent(signal.signal_id)}?tenant_id=${encodeURIComponent(signal.tenant_id)}`}
            className="mt-2 inline-block text-body-small text-text-primary underline"
          >
            Visa källa
          </Link>
        </li>
      ))}
    </ul>
  )
}
