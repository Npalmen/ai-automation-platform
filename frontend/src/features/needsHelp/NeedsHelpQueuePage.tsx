import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { DataTable } from "@/components/operator/DataTable"
import { ErrorState } from "@/components/operator/ErrorState"
import { FilterBar, FilterField } from "@/components/operator/FilterBar"
import { LoadingState } from "@/components/operator/LoadingState"
import { MetricCard } from "@/components/operator/MetricCard"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"
import { TenantIdentifier } from "@/components/operator/TenantIdentifier"

import {
  categoryLabel,
  formatAgeHours,
  formatDetectedAt,
  panelSeverityLabel,
  signalStateLabel,
} from "./formatters"
import { useNeedsHelpQueueQuery } from "./queries"
import type { NeedsHelpFilters, NeedsHelpQueueItem } from "./types"

const SEVERITY_OPTIONS: { value: NeedsHelpFilters["severity"]; label: string }[] = [
  { value: "", label: "Alla" },
  { value: "critical", label: "Kritiskt" },
  { value: "failed", label: "Fel" },
  { value: "warning", label: "Varning" },
  { value: "information", label: "Information" },
]

const SIGNAL_OPTIONS: { value: NeedsHelpFilters["safeRetry"]; label: string }[] = [
  { value: "", label: "Alla" },
  { value: "yes", label: "Ja" },
  { value: "no", label: "Nej" },
  { value: "unknown", label: "Okänt" },
  { value: "not_applicable", label: "Ej tillämpligt" },
]

const inputClassName =
  "min-h-11 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"

function openDetail(navigate: ReturnType<typeof useNavigate>, row: NeedsHelpQueueItem) {
  const params = new URLSearchParams({ tenant_id: row.tenant_id })
  navigate(`/needs-help/${encodeURIComponent(row.id)}?${params.toString()}`)
}

export function NeedsHelpQueuePage() {
  const navigate = useNavigate()
  const [searchInput, setSearchInput] = useState("")
  const [filters, setFilters] = useState<NeedsHelpFilters>({
    sort: "priority",
    order: "asc",
    limit: 50,
    offset: 0,
  })

  const { data, isLoading, isError, error } = useNeedsHelpQueueQuery(filters)

  const columns = useMemo(
    () => [
      {
        key: "tenant",
        header: "Kund",
        render: (row: NeedsHelpQueueItem) => (
          <div className="min-w-0 space-y-1">
            <p className="font-medium text-text-primary">{row.customer_name}</p>
            <TenantIdentifier tenantId={row.tenant_id} />
          </div>
        ),
      },
      {
        key: "problem",
        header: "Problem",
        render: (row: NeedsHelpQueueItem) => (
          <div className="min-w-0 space-y-1">
            <p className="font-medium text-text-primary">{row.title}</p>
            <p className="text-caption text-text-muted">{categoryLabel(row.category)}</p>
          </div>
        ),
      },
      {
        key: "time",
        header: "Tid",
        render: (row: NeedsHelpQueueItem) => (
          <div className="text-body-small text-text-secondary">
            <p>{formatAgeHours(row.age_hours)}</p>
            <p className="hidden sm:block">{formatDetectedAt(row.detected_at)}</p>
          </div>
        ),
      },
      {
        key: "impact",
        header: "Påverkan",
        render: (row: NeedsHelpQueueItem) => (
          <p className="max-w-xs break-words text-body-small text-text-secondary">
            {row.impact || "—"}
          </p>
        ),
      },
      {
        key: "severity",
        header: "Allvarlighetsgrad",
        render: (row: NeedsHelpQueueItem) => (
          <div className="space-y-1">
            <SeverityBadge variant={row.severity_badge} />
            <p className="text-caption text-text-muted">
              {panelSeverityLabel(row.severity)}
            </p>
          </div>
        ),
      },
      {
        key: "next",
        header: "Nästa åtgärd",
        render: (row: NeedsHelpQueueItem) => (
          <p className="max-w-xs break-words text-body-small text-text-primary">
            {row.recommended_action || "—"}
          </p>
        ),
      },
    ],
    [],
  )

  function applyFilters() {
    setFilters((current) => ({
      ...current,
      search: searchInput.trim() || undefined,
      offset: 0,
    }))
  }

  if (isLoading && !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader
          title="Behöver hjälp"
          description="Operativ avvikelsekö över alla tenants."
        />
        <LoadingState label="Laddar kön…" rows={6} />
      </div>
    )
  }

  if (isError && !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Behöver hjälp" />
        <ErrorState
          title="Kunde inte ladda kön"
          description="Avvikelsekön kunde inte hämtas just nu."
          recommendedAction="Försök uppdatera sidan."
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
      </div>
    )
  }

  const summary = data?.summary

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Behöver hjälp"
        description="Aktuella operativa avvikelser som kräver operatörsuppmärksamhet."
      />

      {summary ? (
        <div className="grid min-w-0 grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          <MetricCard label="Kritiskt" value={summary.critical} />
          <MetricCard label="Fel" value={summary.failed} />
          <MetricCard label="Varning" value={summary.warning} />
          <MetricCard label="Information" value={summary.information} />
          <MetricCard label="Påverkade kunder" value={summary.affected_tenants} />
          <MetricCard label="Säker retry (ja)" value={summary.safe_retry_yes} />
          <MetricCard
            label="Extern effekt (ja/okänt)"
            value={summary.external_action_yes_or_unknown}
          />
        </div>
      ) : null}

      <FilterBar>
        <FilterField label="Sök" htmlFor="needs-help-search">
          <input
            id="needs-help-search"
            type="search"
            className={inputClassName}
            placeholder="Kund, tenant, titel, kategori…"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                applyFilters()
              }
            }}
          />
        </FilterField>
        <FilterField label="Allvarlighetsgrad" htmlFor="needs-help-severity">
          <select
            id="needs-help-severity"
            className={inputClassName}
            value={filters.severity ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                severity: event.target.value as NeedsHelpFilters["severity"],
                offset: 0,
              }))
            }
          >
            {SEVERITY_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Kategori" htmlFor="needs-help-category">
          <input
            id="needs-help-category"
            className={inputClassName}
            placeholder="t.ex. pipeline"
            value={filters.category ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                category: event.target.value || undefined,
                offset: 0,
              }))
            }
          />
        </FilterField>
        <FilterField label="Källtyp" htmlFor="needs-help-source-type">
          <input
            id="needs-help-source-type"
            className={inputClassName}
            placeholder="t.ex. job"
            value={filters.sourceType ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                sourceType: event.target.value || undefined,
                offset: 0,
              }))
            }
          />
        </FilterField>
        <FilterField label="Säker retry" htmlFor="needs-help-safe-retry">
          <select
            id="needs-help-safe-retry"
            className={inputClassName}
            value={filters.safeRetry ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                safeRetry: event.target.value as NeedsHelpFilters["safeRetry"],
                offset: 0,
              }))
            }
          >
            {SIGNAL_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Extern effekt" htmlFor="needs-help-external-impact">
          <select
            id="needs-help-external-impact"
            className={inputClassName}
            value={filters.externalImpact ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                externalImpact: event.target.value as NeedsHelpFilters["externalImpact"],
                offset: 0,
              }))
            }
          >
            {SIGNAL_OPTIONS.map((option) => (
              <option key={`ext-${option.label}`} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Min ålder (h)" htmlFor="needs-help-min-age">
          <input
            id="needs-help-min-age"
            type="number"
            min={0}
            className={inputClassName}
            value={filters.minimumAgeHours ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                minimumAgeHours: event.target.value
                  ? Number(event.target.value)
                  : undefined,
                offset: 0,
              }))
            }
          />
        </FilterField>
        <div className="flex items-end">
          <button
            type="button"
            className="min-h-11 rounded-md border border-border bg-page px-4 text-body text-text-primary"
            onClick={applyFilters}
          >
            Sök
          </button>
        </div>
      </FilterBar>

      <DataTable
        columns={columns}
        rows={data?.items ?? []}
        getRowKey={(row) => row.id}
        onRowClick={(row) => openDetail(navigate, row)}
        loading={isLoading && !data}
        emptyTitle="Ingen åtgärd behövs"
        emptyDescription="Inga operativa avvikelser matchar filtren just nu."
        mobileCard={(row) => (
          <button
            type="button"
            className="w-full rounded-lg border border-border bg-surface p-4 text-left shadow-sm"
            onClick={() => openDetail(navigate, row)}
          >
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <SeverityBadge variant={row.severity_badge} />
              <span className="font-medium text-text-primary">{row.customer_name}</span>
            </div>
            <p className="text-card-title text-text-primary">{row.title}</p>
            {row.impact ? (
              <p className="mt-2 break-words text-body-small text-text-secondary">
                {row.impact}
              </p>
            ) : null}
            <p className="mt-2 text-caption text-text-muted">
              {formatAgeHours(row.age_hours)} · {categoryLabel(row.category)}
            </p>
            {row.recommended_action ? (
              <p className="mt-2 text-body-small text-text-primary">
                <span className="font-medium">Nästa steg:</span> {row.recommended_action}
              </p>
            ) : null}
            <p className="mt-2 text-caption text-text-muted">
              Retry: {signalStateLabel(row.safe_retry_available)} · Extern:{" "}
              {signalStateLabel(row.external_action_may_have_occurred)}
            </p>
          </button>
        )}
      />

      {data && data.total > (data.limit ?? 50) ? (
        <p className="text-body-small text-text-muted">
          Visar {data.items.length} av {data.total} ärenden
        </p>
      ) : null}
    </div>
  )
}
