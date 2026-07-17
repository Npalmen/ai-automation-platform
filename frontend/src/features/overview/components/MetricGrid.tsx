import { MetricCard } from "@/components/operator/MetricCard"

import { formatWindow } from "../formatters"
import type { Counters } from "../types"

type MetricGridProps = {
  counters: Counters
}

const METRIC_CONFIG: {
  key: keyof Counters
  label: string
}[] = [
  { key: "active_tenants", label: "Aktiva kunder" },
  { key: "jobs_last_24h", label: "Jobb" },
  { key: "pending_approvals", label: "Väntande godkännanden" },
  { key: "open_manual_reviews", label: "Manuell granskning" },
  { key: "failed_jobs", label: "Misslyckade jobb" },
  { key: "integration_errors", label: "Integrationsfel" },
]

export function MetricGrid({ counters }: MetricGridProps) {
  return (
    <section aria-labelledby="overview-metrics-heading">
      <h2
        id="overview-metrics-heading"
        className="mb-3 text-section-title text-text-primary"
      >
        Nyckeltal
      </h2>
      <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {METRIC_CONFIG.map(({ key, label }) => {
          const counter = counters[key]
          return (
            <MetricCard
              key={key}
              label={label}
              value={counter.value}
              trendText={formatWindow(counter.window_hours)}
            />
          )
        })}
      </div>
    </section>
  )
}
