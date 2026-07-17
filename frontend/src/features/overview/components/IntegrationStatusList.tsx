import { HealthIndicator } from "@/components/operator/HealthIndicator"

import type { IntegrationsBlock } from "../types"

type IntegrationStatusListProps = {
  integrations: IntegrationsBlock
  generatedAt: string
}

const INTEGRATION_LABELS: Record<keyof IntegrationsBlock, string> = {
  gmail: "Gmail",
  visma: "Visma",
  google_sheets: "Google Sheets",
}

function integrationExplanation(
  key: keyof IntegrationsBlock,
  data: IntegrationsBlock[keyof IntegrationsBlock],
): string {
  const source =
    data.data_source === "integration_health_check"
      ? "Hälsokontroll"
      : "Händelselogg"
  const issues =
    data.issues > 0
      ? `${data.issues} fel, ${data.affected_tenants} kund(er) påverkad(e).`
      : "Inga fel i vald period."
  return `${INTEGRATION_LABELS[key]} — ${source}. ${issues}`
}

export function IntegrationStatusList({
  integrations,
  generatedAt,
}: IntegrationStatusListProps) {
  const entries = Object.entries(integrations) as [
    keyof IntegrationsBlock,
    IntegrationsBlock[keyof IntegrationsBlock],
  ][]

  return (
    <section aria-labelledby="overview-integrations-heading">
      <h2
        id="overview-integrations-heading"
        className="mb-3 text-section-title text-text-primary"
      >
        Integrationer
      </h2>
      <div className="flex min-w-0 flex-col gap-3">
        {entries.map(([key, data]) => (
          <HealthIndicator
            key={key}
            name={INTEGRATION_LABELS[key]}
            status={data.status}
            lastChecked={new Date(generatedAt).toLocaleString("sv-SE")}
            explanation={integrationExplanation(key, data)}
          />
        ))}
      </div>
    </section>
  )
}
