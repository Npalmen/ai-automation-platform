import { HealthIndicator } from "@/components/operator/HealthIndicator"

import { formatTimestamp, freshnessLabel, statusLabel, toStatusVariant } from "../formatters"
import type { ComponentStatus, IntegrationRuntimeStatus } from "../types"

type StatusCardListProps = {
  items: { key: string; component: ComponentStatus | IntegrationRuntimeStatus }[]
  generatedAt: string
}

export function StatusCardList({ items, generatedAt }: StatusCardListProps) {
  const fallbackChecked = formatTimestamp(generatedAt)
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {items.map(({ key, component }) => (
        <HealthIndicator
          key={key}
          name={component.label}
          status={toStatusVariant(component.status)}
          lastChecked={formatTimestamp(component.checked_at) || fallbackChecked}
          explanation={[
            component.summary,
            component.limitation,
            component.freshness
              ? `Freshness: ${freshnessLabel(component.freshness)}`
              : null,
          ]
            .filter(Boolean)
            .join(" ")}
        />
      ))}
    </div>
  )
}

type DomainSummaryProps = {
  title: string
  status: ComponentStatus["status"]
  summary: string
  generatedAt: string
}

export function DomainSummary({ title, status, summary, generatedAt }: DomainSummaryProps) {
  return (
    <section className="rounded-lg border border-border bg-surface p-4">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <h2 className="text-section-title text-text-primary">{title}</h2>
          <p className="break-words text-body-small text-text-secondary">{summary}</p>
        </div>
        <p className="shrink-0 text-caption text-text-muted">
          {statusLabel(status)} · uppdaterad {formatTimestamp(generatedAt)}
        </p>
      </div>
    </section>
  )
}
