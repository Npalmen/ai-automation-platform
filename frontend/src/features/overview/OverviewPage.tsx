import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"

import { IntegrationStatusList } from "./components/IntegrationStatusList"
import { MetricGrid } from "./components/MetricGrid"
import { PlatformStatusBanner } from "./components/PlatformStatusBanner"
import { PriorityList } from "./components/PriorityList"
import { SystemStatusList } from "./components/SystemStatusList"
import { useOverviewQuery } from "./queries"

export function OverviewPage() {
  const { data, isLoading, isError, isFetching, refetch, error } =
    useOverviewQuery()

  if (isLoading && !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader
          title="Översikt"
          description="Global operativ översikt över plattformen."
        />
        <LoadingState label="Laddar översikt…" rows={6} />
      </div>
    )
  }

  if (isError && !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader
          title="Översikt"
          description="Global operativ översikt över plattformen."
        />
        <ErrorState
          title="Kunde inte hämta översikten"
          description="Operativ översikt är inte tillgänglig just nu."
          impact="Du kan inte se plattformsstatus, nyckeltal eller prioriterade åtgärder."
          recommendedAction="Försök uppdatera sidan. Om problemet kvarstår, kontrollera backend och databas."
          technicalDetails={
            error instanceof Error ? error.message : String(error)
          }
        />
        <button
          type="button"
          onClick={() => void refetch()}
          className="self-start rounded-md border border-border bg-surface px-4 py-2 text-label text-text-primary hover:bg-surface-subtle"
        >
          Försök igen
        </button>
      </div>
    )
  }

  if (!data) {
    return null
  }

  const noTenants = data.counters.active_tenants.value === 0

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Översikt"
        description={
          noTenants
            ? "Inga aktiva kunder konfigurerade ännu."
            : "Global operativ översikt över plattformen."
        }
      />

      <PlatformStatusBanner
        data={data}
        onRefresh={() => void refetch()}
        isRefreshing={isFetching}
      />

      <MetricGrid counters={data.counters} />

      <PriorityList items={data.priorities} />

      <div className="grid min-w-0 grid-cols-1 gap-6 lg:grid-cols-2">
        <IntegrationStatusList
          integrations={data.integrations}
          generatedAt={data.generated_at}
        />
        <SystemStatusList system={data.system} generatedAt={data.generated_at} />
      </div>
    </div>
  )
}
