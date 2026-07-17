import { MetricCard } from "@/components/operator/MetricCard"

import {
  formatAiCostStatus,
  formatComparisonTrend,
  formatNotMeasured,
} from "../formatters"
import type { UsageOverviewResponse } from "../types"

type UsageMetricGridProps = {
  overview: UsageOverviewResponse
}

export function UsageMetricGrid({ overview }: UsageMetricGridProps) {
  const { summary } = overview

  return (
    <section aria-labelledby="usage-metrics-heading">
      <h2 id="usage-metrics-heading" className="mb-3 text-section-title text-text-primary">
        Viktigaste mått
      </h2>
      <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <MetricCard
          label="Jobb mottagna"
          value={summary.jobs_received.current}
          trendText={formatComparisonTrend(
            summary.jobs_received.current,
            summary.jobs_received.previous,
            summary.jobs_received.percentage_change,
          )}
        />
        <MetricCard
          label="Jobb slutförda"
          value={summary.jobs_completed.current.value}
          helpText="Baserat på updated_at (proxy), inte exakt sluttid."
          trendText={formatComparisonTrend(
            summary.jobs_completed.current.value,
            summary.jobs_completed.previous.value,
            summary.jobs_completed.percentage_change,
          )}
        />
        <MetricCard
          label="Jobb misslyckade"
          value={summary.jobs_failed.current.value}
          helpText="Baserat på updated_at (proxy), inte exakt sluttid."
          trendText={formatComparisonTrend(
            summary.jobs_failed.current.value,
            summary.jobs_failed.previous.value,
            summary.jobs_failed.percentage_change,
          )}
        />
        <MetricCard
          label="Automatiseringsgrad"
          value="Ej mätt"
          helpText={formatNotMeasured(summary.automation_rate)}
        />
        <MetricCard
          label="Operatörsåtgärder"
          value={summary.operator_actions.current}
          trendText={formatComparisonTrend(
            summary.operator_actions.current,
            summary.operator_actions.previous,
            summary.operator_actions.percentage_change,
          )}
        />
        <MetricCard
          label="Gmail manual review-överlämningar"
          value={summary.gmail_manual_review_handoffs.current}
          helpText="Endast Gmail-driven överlämning, inte alla manual reviews."
          trendText={formatComparisonTrend(
            summary.gmail_manual_review_handoffs.current,
            summary.gmail_manual_review_handoffs.previous,
            summary.gmail_manual_review_handoffs.percentage_change,
          )}
        />
        <MetricCard
          label="Integrationsfel"
          value={summary.integration_errors.current}
          trendText={formatComparisonTrend(
            summary.integration_errors.current,
            summary.integration_errors.previous,
            summary.integration_errors.percentage_change,
          )}
        />
        <MetricCard
          label="AI-kostnad"
          value={formatAiCostStatus(overview.ai_cost)}
          helpText="Kostnad visas endast när tillförlitlig mätdata finns."
        />
      </div>
    </section>
  )
}
