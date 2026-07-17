import { StatusBadge } from "@/components/operator/StatusBadge"

import { formatGeneratedAt } from "../formatters"
import type { OperationsOverviewResponse } from "../types"

type PlatformStatusBannerProps = {
  data: OperationsOverviewResponse
  onRefresh: () => void
  isRefreshing: boolean
}

export function PlatformStatusBanner({
  data,
  onRefresh,
  isRefreshing,
}: PlatformStatusBannerProps) {
  const { platform_status: status, period, generated_at } = data

  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="text-section-title text-text-primary">
              Plattformsstatus
            </h2>
            <StatusBadge variant={status.level} label={status.label} />
          </div>
          <p className="break-words text-body text-text-secondary">
            {status.summary}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="shrink-0 rounded-md border border-border bg-surface px-3 py-1.5 text-label text-text-primary hover:bg-surface-subtle disabled:opacity-60"
        >
          {isRefreshing ? "Uppdaterar…" : "Uppdatera"}
        </button>
      </div>
      <div className="flex min-w-0 flex-wrap gap-x-4 gap-y-1 text-caption text-text-muted">
        <span>Senast uppdaterad: {formatGeneratedAt(generated_at)}</span>
        <span>Period: senaste {period.hours} timmar</span>
      </div>
    </section>
  )
}
