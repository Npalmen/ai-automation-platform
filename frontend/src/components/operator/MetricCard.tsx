import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type MetricCardProps = {
  label: string
  value: ReactNode
  helpText?: string
  status?: ReactNode
  trendText?: string
  loading?: boolean
  className?: string
}

export function MetricCard({
  label,
  value,
  helpText,
  status,
  trendText,
  loading = false,
  className,
}: MetricCardProps) {
  return (
    <article
      className={cn(
        "flex min-h-[7rem] min-w-0 flex-col gap-2 rounded-lg border border-border bg-surface p-4 shadow-sm",
        className,
      )}
      aria-busy={loading}
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <p className="text-label text-text-secondary">{label}</p>
        {status}
      </div>
      {loading ? (
        <div className="h-8 w-24 animate-pulse rounded bg-surface-subtle" />
      ) : (
        <p className="text-metric text-text-primary">{value}</p>
      )}
      {helpText ? (
        <p className="break-words text-body-small text-text-muted">{helpText}</p>
      ) : null}
      {trendText ? (
        <p className="text-caption text-text-secondary">{trendText}</p>
      ) : null}
    </article>
  )
}
