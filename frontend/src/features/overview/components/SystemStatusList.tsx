import { HealthIndicator } from "@/components/operator/HealthIndicator"

import type { SystemBlock } from "../types"

type SystemStatusListProps = {
  system: SystemBlock
  generatedAt: string
}

const SYSTEM_LABELS: Record<string, string> = {
  api: "API",
  database: "Databas",
  scheduler: "Scheduler",
  backup: "Backup",
  deploy: "Deploy",
}

export function SystemStatusList({ system, generatedAt }: SystemStatusListProps) {
  const lastChecked = new Date(generatedAt).toLocaleString("sv-SE")
  const entries: {
    key: string
    status: SystemBlock[keyof SystemBlock]["status"]
    explanation: string
  }[] = [
    {
      key: "api",
      status: system.api.status,
      explanation: system.api.description ?? "API-processens svar.",
    },
    {
      key: "database",
      status: system.database.status,
      explanation: system.database.description ?? "Databasaggregering.",
    },
    {
      key: "scheduler",
      status: system.scheduler.status,
      explanation: system.scheduler.description ?? "Scheduler-status.",
    },
    {
      key: "backup",
      status: system.backup.status,
      explanation: system.backup.data_source,
    },
    {
      key: "deploy",
      status: system.deploy.status,
      explanation: system.deploy.data_source,
    },
  ]

  return (
    <section aria-labelledby="overview-system-heading">
      <h2
        id="overview-system-heading"
        className="mb-3 text-section-title text-text-primary"
      >
        System
      </h2>
      <div className="flex min-w-0 flex-col gap-3">
        {entries.map(({ key, status, explanation }) => (
          <HealthIndicator
            key={key}
            name={SYSTEM_LABELS[key] ?? key}
            status={status}
            lastChecked={lastChecked}
            explanation={explanation}
          />
        ))}
      </div>
    </section>
  )
}
