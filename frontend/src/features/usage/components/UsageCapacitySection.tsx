import { MetricCard } from "@/components/operator/MetricCard"

import { formatNullableNumber } from "../formatters"
import type { CapacityBlock } from "../types"

type UsageCapacitySectionProps = {
  capacity: CapacityBlock
}

export function UsageCapacitySection({ capacity }: UsageCapacitySectionProps) {
  return (
    <section aria-labelledby="usage-capacity-heading">
      <h2 id="usage-capacity-heading" className="mb-3 text-section-title text-text-primary">
        Kapacitet
      </h2>
      <p className="mb-3 text-body-small text-text-muted">
        Baslinje saknas — inga konfigurerade varningsgränser.
      </p>
      <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          label="Jobb per dag (snitt)"
          value={formatNullableNumber(capacity.jobs_per_day_average)}
        />
        <MetricCard
          label="Topp jobb per timme"
          value={formatNullableNumber(capacity.peak_jobs_per_hour)}
        />
        <MetricCard
          label="Operatörsåtgärder per dag"
          value={formatNullableNumber(capacity.operator_actions_per_day)}
        />
        <MetricCard
          label="Öppna incidenter"
          value={formatNullableNumber(capacity.open_incidents_current)}
        />
        <MetricCard
          label="Öppna behöver-hjälp-signaler"
          value={formatNullableNumber(capacity.needs_help_open_current)}
        />
      </div>
    </section>
  )
}
