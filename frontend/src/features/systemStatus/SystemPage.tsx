import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { StatusBadge } from "@/components/operator/StatusBadge"

import { DomainSummary, StatusCardList } from "./components/StatusSections"
import {
  DeployReadinessSection,
  LimitationsNote,
  ResilienceSection,
  RunbookLinks,
} from "./components/SystemDetailSections"
import { formatTimestamp, statusLabel, toStatusVariant } from "./formatters"
import { useSystemStatusQuery } from "./queries"

export function SystemPage() {
  const statusQuery = useSystemStatusQuery()

  if (statusQuery.isLoading && !statusQuery.data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader
          title="Systemstatus"
          description="Laddar teknisk driftstatus…"
        />
        <LoadingState label="Laddar systemstatus…" rows={8} />
      </div>
    )
  }

  if (statusQuery.isError || !statusQuery.data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader
          title="Systemstatus"
          description="Verifierbar read-only vy för runtime, resiliens och deploy readiness."
        />
        <ErrorState
          title="Systemstatus kunde inte hämtas"
          description="Teknisk driftstatus är inte tillgänglig just nu."
          impact="Operatören saknar verifierbar systembild tills data kan hämtas."
          recommendedAction="Försök uppdatera sidan."
          technicalDetails={
            statusQuery.error instanceof Error
              ? statusQuery.error.message
              : String(statusQuery.error)
          }
        />
        <button
          type="button"
          onClick={() => void statusQuery.refetch()}
          className="self-start rounded-md border border-border bg-surface px-4 py-2 text-label text-text-primary hover:bg-surface-subtle"
        >
          Försök igen
        </button>
      </div>
    )
  }

  const data = statusQuery.data
  const generatedAt = data.generated_at
  const integrationItems = Object.entries(data.runtime.integrations).map(
    ([key, component]) => ({ key, component }),
  )

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Systemstatus"
        description="Verifierbar teknisk driftstatus — read-only, inga serveråtgärder."
        actions={
          <button
            type="button"
            onClick={() => void statusQuery.refetch()}
            disabled={statusQuery.isFetching}
            className="rounded-md border border-border bg-surface px-4 py-2 text-label text-text-primary hover:bg-surface-subtle disabled:opacity-60"
          >
            {statusQuery.isFetching ? "Uppdaterar…" : "Uppdatera"}
          </button>
        }
      />

      <section className="rounded-lg border border-border bg-surface p-4">
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 space-y-2">
            <h2 className="text-section-title text-text-primary">Övergripande status</h2>
            <p className="break-words text-body-small text-text-secondary">
              {data.overall_status.summary}
            </p>
            <p className="text-caption text-text-muted">
              Senast kontrollerad: {formatTimestamp(generatedAt)}
            </p>
          </div>
          <StatusBadge
            variant={toStatusVariant(data.overall_status.status)}
            label={statusLabel(data.overall_status.status)}
          />
        </div>
      </section>

      <DomainSummary
        title="Runtime"
        status={data.runtime_status.status}
        summary={data.runtime_status.summary}
        generatedAt={generatedAt}
      />

      <section aria-labelledby="system-runtime-heading" className="flex min-w-0 flex-col gap-4">
        <h2 id="system-runtime-heading" className="text-section-title text-text-primary">
          Runtime-komponenter
        </h2>
        <StatusCardList
          generatedAt={generatedAt}
          items={[
            { key: "api", component: data.runtime.api },
            { key: "database", component: data.runtime.database },
            { key: "scheduler", component: data.runtime.scheduler },
            { key: "jobs", component: data.runtime.jobs },
            ...integrationItems,
          ]}
        />
      </section>

      <DomainSummary
        title="Resiliens"
        status={data.resilience_status.status}
        summary={data.resilience_status.summary}
        generatedAt={generatedAt}
      />
      <ResilienceSection resilience={data.resilience} generatedAt={generatedAt} />

      <DomainSummary
        title="Deploy readiness"
        status={data.deploy_readiness_status.status}
        summary={data.deploy_readiness_status.summary}
        generatedAt={generatedAt}
      />
      <DeployReadinessSection deployment={data.deployment} generatedAt={generatedAt} />

      <LimitationsNote limitations={data.limitations} />
      <RunbookLinks runbooks={data.runbooks} />
    </div>
  )
}
