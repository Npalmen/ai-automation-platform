import { useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"

import { DataTable } from "@/components/operator/DataTable"
import { ErrorState } from "@/components/operator/ErrorState"
import { FilterBar, FilterField } from "@/components/operator/FilterBar"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { TenantIdentifier } from "@/components/operator/TenantIdentifier"
import { Button } from "@/components/ui/button"
import type { StatusVariant } from "@/design/types"
import { useAuth } from "@/features/auth/AuthProvider"
import { isRoleAllowed } from "@/features/auth/permissions"
import { useListLayout } from "@/hooks/useListLayout"

import { formatActivityAt, tenantStatusLabel } from "./formatters"
import { useTenantsQuery } from "./queries"
import type { TenantListFilters, TenantListItem } from "./types"

const STATUS_OPTIONS: { value: TenantListFilters["status"]; label: string }[] = [
  { value: "", label: "Alla" },
  { value: "active", label: "Aktiv" },
  { value: "inactive", label: "Inaktiv" },
  { value: "unknown", label: "Okänd" },
]

const HEALTH_OPTIONS: { value: TenantListFilters["health"]; label: string }[] = [
  { value: "", label: "Alla" },
  { value: "healthy", label: "Frisk" },
  { value: "warning", label: "Varning" },
  { value: "failed", label: "Fel" },
  { value: "paused", label: "Pausad" },
  { value: "unknown", label: "Okänd" },
]

const inputClassName =
  "min-h-11 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"

export function CustomersListPage() {
  const navigate = useNavigate()
  const { auth } = useAuth()
  const { ref: listLayoutRef, layout } = useListLayout()
  const [searchInput, setSearchInput] = useState("")
  const [filters, setFilters] = useState<TenantListFilters>({
    sort: "name",
    order: "asc",
  })

  const { data, isLoading, isError, error, refetch } = useTenantsQuery(filters)

  const role = auth.status === "authenticated" ? auth.operator.role : null

  const columns = useMemo(
    () => [
      {
        key: "customer",
        header: "Kund",
        render: (row: TenantListItem) => (
          <div className="min-w-0 space-y-1">
            <p className="font-medium text-text-primary">{row.name}</p>
            <TenantIdentifier tenantId={row.tenant_id} />
          </div>
        ),
      },
      {
        key: "tenant_status",
        header: "Kontostatus",
        render: (row: TenantListItem) => (
          <span className="text-body text-text-secondary">
            {tenantStatusLabel(row.tenant_status)}
          </span>
        ),
      },
      {
        key: "health",
        header: "Drift",
        render: (row: TenantListItem) => (
          <StatusBadge variant={row.health.level} label={row.health.label} />
        ),
      },
      {
        key: "activity",
        header: "Senaste aktivitet",
        render: (row: TenantListItem) => (
          <span className="text-body-small text-text-secondary">
            {formatActivityAt(row.last_activity_at)}
          </span>
        ),
      },
      {
        key: "issues",
        header: "Öppna avvikelser",
        render: (row: TenantListItem) => row.open_issues_count,
      },
      {
        key: "jobs",
        header: "Jobb (30 d)",
        render: (row: TenantListItem) => row.jobs_last_30d,
      },
    ],
    [],
  )

  function applyFilters() {
    setFilters((current) => ({
      ...current,
      search: searchInput.trim() || undefined,
    }))
  }

  if (isLoading && !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Kunder" description="Operativ kundlista över alla tenants." />
        <LoadingState label="Laddar kunder…" rows={6} />
      </div>
    )
  }

  if (isError && !data) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Kunder" description="Operativ kundlista över alla tenants." />
        <ErrorState
          title="Kunde inte ladda kunder"
          description="Kundlistan kunde inte hämtas just nu."
          recommendedAction="Försök uppdatera sidan."
          technicalDetails={error instanceof Error ? error.message : String(error)}
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

  const items = data?.items ?? []

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Kunder"
        description={
          data
            ? `${data.total} kund(er) — sök, filtrera och öppna detaljvy.`
            : "Operativ kundlista över alla tenants."
        }
        actions={
          role && isRoleAllowed(role, ["operations", "admin"]) ? (
            <Button type="button" onClick={() => navigate("/customers/new")}>
              Ny kund
            </Button>
          ) : undefined
        }
      />

      <FilterBar>
        <FilterField label="Sök" htmlFor="customers-search">
          <input
            id="customers-search"
            type="search"
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") applyFilters()
            }}
            placeholder="Namn, ID eller slug"
            className={inputClassName}
          />
        </FilterField>
        <FilterField label="Kontostatus" htmlFor="customers-status">
          <select
            id="customers-status"
            className={inputClassName}
            value={filters.status ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                status: event.target.value as TenantListFilters["status"],
              }))
            }
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.label} value={option.value ?? ""}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Driftstatus" htmlFor="customers-health">
          <select
            id="customers-health"
            className={inputClassName}
            value={filters.health ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                health: event.target.value as StatusVariant | "",
              }))
            }
          >
            {HEALTH_OPTIONS.map((option) => (
              <option key={option.label} value={option.value ?? ""}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <div className="flex w-full gap-2 sm:w-auto">
          <button
            type="button"
            onClick={applyFilters}
            className="min-h-11 rounded-md border border-border bg-surface px-4 text-label text-text-primary hover:bg-surface-subtle"
          >
            Filtrera
          </button>
        </div>
      </FilterBar>

      <div ref={listLayoutRef} className="min-w-0">
        <DataTable
          columns={columns}
          rows={items}
          getRowKey={(row) => row.tenant_id}
          onRowClick={(row) => navigate(`/customers/${encodeURIComponent(row.tenant_id)}`)}
          layout={layout}
          loading={isLoading && !data}
          emptyTitle="Inga kunder"
          emptyDescription="Inga tenants matchar valda filter."
          compactRow={(row) => (
            <button
              type="button"
              onClick={() => navigate(`/customers/${encodeURIComponent(row.tenant_id)}`)}
              className="flex w-full min-w-0 items-start justify-between gap-3 rounded-lg border border-border bg-surface p-3 text-left hover:bg-surface-subtle"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-text-primary">{row.name}</p>
                  <StatusBadge variant={row.health.level} label={row.health.label} />
                </div>
                <TenantIdentifier tenantId={row.tenant_id} />
                <p className="text-body-small text-text-secondary">
                  {tenantStatusLabel(row.tenant_status)} · {formatActivityAt(row.last_activity_at)}
                </p>
              </div>
            </button>
          )}
          mobileCard={(row) => (
          <button
            type="button"
            onClick={() => navigate(`/customers/${encodeURIComponent(row.tenant_id)}`)}
            className="w-full rounded-lg border border-border bg-surface p-4 text-left hover:bg-surface-subtle"
          >
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="font-medium text-text-primary">{row.name}</p>
              <StatusBadge variant={row.health.level} label={row.health.label} />
            </div>
            <TenantIdentifier tenantId={row.tenant_id} />
            <p className="mt-2 text-body-small text-text-secondary">
              {tenantStatusLabel(row.tenant_status)} · {formatActivityAt(row.last_activity_at)}
            </p>
            <p className="text-body-small text-text-secondary">
              {row.open_issues_count} avvikelser · {row.jobs_last_30d} jobb (30 d)
            </p>
          </button>
        )}
        />
      </div>
    </div>
  )
}
