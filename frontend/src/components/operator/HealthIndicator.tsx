import type { StatusVariant } from "@/design/types"

import { StatusBadge } from "@/components/operator/StatusBadge"
import { cn } from "@/lib/utils"

type HealthIndicatorProps = {
  name: string
  status: StatusVariant
  lastChecked: string
  explanation: string
  className?: string
}

export function HealthIndicator({
  name,
  status,
  lastChecked,
  explanation,
  className,
}: HealthIndicatorProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        <p className="text-card-title text-text-primary">{name}</p>
        <p className="break-words text-body-small text-text-secondary">
          {explanation}
        </p>
      </div>
      <div className="flex min-w-0 shrink-0 flex-col items-start gap-1 sm:items-end">
        <StatusBadge variant={status} />
        <p className="text-caption text-text-muted">Senast: {lastChecked}</p>
      </div>
    </div>
  )
}
