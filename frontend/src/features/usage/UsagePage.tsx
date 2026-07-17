import { useMemo, useState } from "react"

import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"

import { DataQualityNote } from "./components/DataQualityNote"
import { UsageCapacitySection } from "./components/UsageCapacitySection"
import { UsageMetricGrid } from "./components/UsageMetricGrid"
import { UsageTenantTable } from "./components/UsageTenantTable"
import { formatTimestamp, periodLabel } from "./formatters"
import { useUsageOverviewQuery, useUsageTenantsQuery } from "./queries"
import type { UsageDays, UsageTenantFilters } from "./types"

const PERIOD_OPTIONS: { value: UsageDays; label: string }[] = [
  { value: 7, label: "7 dagar" },
  { value: 30, label: "30 dagar" },
  { value: 90, label: "90 dagar" },
]

export function UsagePage() {
  const [days, setDays] = useState<UsageDays>(30)
  const [searchInput, setSearchInput] = useState("")
  const [tenantFilters, setTenantFilters] = useState<UsageTenantFilters>({
    sort: "jobs",
    order: "desc",
    limit: 50,
    offset: 0,
  })

  const overviewQuery = useUsageOverviewQuery(days)
  const tenantQueryFilters = useMemo(
    () => ({
      ...tenantFilters,
      days,
      search: searchInput || undefined,
    }),
    [tenantFilters, days, searchInput],
  )
  const tenantsQuery = useUsageTenantsQuery(tenantQueryFilters)

  const isLoading = overviewQuery.isLoading && !overviewQuery.data
  const isError = overviewQuery.isError && !overviewQuery.data

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader
          title="Användning och kapacitet"
          description="Laddar användnings- och kapacitetsdata…"
        />
        <LoadingState label="Laddar användning…" rows={8} />
      </div>
    )
  }

  if (isError || !overviewQuery.data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader
          title="Användning och kapacitet"
          description="Verifierbar read-only vy för användning, kostnad och kapacitet."
        />
        <ErrorState
          title="Vyn kunde inte hämtas"
          description="Användnings- och kapacitetsbilden är inte tillgänglig just nu."
          impact="Kostnads- och kapacitetsunderlag saknas tills data kan hämtas."
          recommendedAction="Försök uppdatera sidan."
          technicalDetails={
            overviewQuery.error instanceof Error
              ? overviewQuery.error.message
              : String(overviewQuery.error)
          }
        />
        <button
          type="button"
          onClick={() => void overviewQuery.refetch()}
          className="self-start rounded-md border border-border bg-surface px-4 py-2 text-label text-text-primary hover:bg-surface-subtle"
        >
          Försök igen
        </button>
      </div>
    )
  }

  const overview = overviewQuery.data
  const tenants = tenantsQuery.data

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Användning och kapacitet"
        description={`${periodLabel(days)} · uppdaterad ${formatTimestamp(overview.generated_at)}`}
      />

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-label text-text-secondary">
          Period
          <select
            className="min-h-11 rounded-md border border-border bg-page px-3 text-body text-text-primary"
            value={days}
            onChange={(event) => setDays(Number(event.target.value) as UsageDays)}
          >
            {PERIOD_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            void overviewQuery.refetch()
            void tenantsQuery.refetch()
          }}
          disabled={overviewQuery.isFetching || tenantsQuery.isFetching}
          className="min-h-11 rounded-md border border-border bg-surface px-4 text-label text-text-primary hover:bg-surface-subtle disabled:opacity-60"
        >
          {overviewQuery.isFetching || tenantsQuery.isFetching
            ? "Uppdaterar…"
            : "Uppdatera"}
        </button>
      </div>

      <UsageMetricGrid overview={overview} />
      <UsageCapacitySection capacity={overview.capacity} />

      {tenantsQuery.isLoading && !tenants ? (
        <LoadingState label="Laddar kundjämförelse…" rows={4} />
      ) : tenantsQuery.isError ? (
        <ErrorState
          title="Kundjämförelsen kunde inte hämtas"
          description="Tenantlistan är inte tillgänglig."
          impact="Jämförelse per kund saknas."
          recommendedAction="Försök uppdatera sidan."
        />
      ) : tenants ? (
        <UsageTenantTable
          items={tenants.items}
          filters={tenantFilters}
          onFiltersChange={setTenantFilters}
          searchInput={searchInput}
          onSearchInputChange={setSearchInput}
        />
      ) : null}

      <DataQualityNote notes={overview.data_quality_notes} />
    </div>
  )
}
