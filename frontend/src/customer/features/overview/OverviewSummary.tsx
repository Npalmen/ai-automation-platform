import { OverviewMetricCard } from "@/customer/features/overview/OverviewMetricCard"
import {
  formatHoursSaved,
  formatInteger,
  formatSekValue,
} from "@/customer/features/overview/overviewFormatters"
import type { OverviewSummary } from "@/customer/types/overview"

type OverviewSummaryProps = {
  summary: OverviewSummary
  hideValueEstimate?: boolean
}

export function OverviewSummarySection({
  summary,
  hideValueEstimate = false,
}: OverviewSummaryProps) {
  const hoursSaved = formatHoursSaved(summary.estimated_hours_saved)
  const valueSek = formatSekValue(summary.estimated_value_sek)

  return (
    <section aria-labelledby="overview-summary-heading" className="space-y-4">
      <h2 id="overview-summary-heading" className="text-section-title text-text-primary">
        Dagens läge
      </h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <OverviewMetricCard
          label="Hanterade idag"
          value={formatInteger(summary.cases_handled_today)}
        />
        <OverviewMetricCard
          label="Väntar på beslut"
          value={formatInteger(summary.waiting_for_decision)}
        />
        <OverviewMetricCard
          label="Väntar på kund"
          value={formatInteger(summary.waiting_for_customer)}
        />
        <OverviewMetricCard
          label="Behöver hjälp"
          value={formatInteger(summary.needs_help)}
        />
        <OverviewMetricCard
          label="Misslyckades idag"
          value={formatInteger(summary.failed_today)}
        />
      </div>
      {!hideValueEstimate && (hoursSaved || valueSek) ? (
        <div className="rounded-lg border border-border bg-surface-subtle p-4">
          <p className="text-body-small font-medium text-text-secondary">
            Uppskattat värde idag
          </p>
          <p className="mt-1 text-body text-text-primary">
            {[hoursSaved, valueSek].filter(Boolean).join(" · ")}
          </p>
        </div>
      ) : null}
    </section>
  )
}
