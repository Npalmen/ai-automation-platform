import { useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"

import { DataTable } from "@/components/operator/DataTable"
import { FilterBar, FilterField } from "@/components/operator/FilterBar"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { TenantIdentifier } from "@/components/operator/TenantIdentifier"
import { useListLayout } from "@/hooks/useListLayout"

import {
  attentionStatusLabel,
  formatAiCostTableCell,
  formatOperatorBurdenTableCell,
  formatTimestamp,
  tenantStatusLabel,
} from "../formatters"
import type { UsageTenantFilters, UsageTenantItem } from "../types"

const inputClassName =
  "min-h-11 w-full min-w-0 rounded-md border border-border bg-page px-3 text-body text-text-primary"

const STATUS_OPTIONS = [
  { value: "", label: "Alla" },
  { value: "active", label: "Aktiv" },
  { value: "inactive", label: "Inaktiv" },
  { value: "unknown", label: "Okänd" },
] as const

const ATTENTION_OPTIONS = [
  { value: "", label: "Alla" },
  { value: "healthy", label: "Frisk" },
  { value: "warning", label: "Varning" },
  { value: "failed", label: "Fel" },
  { value: "paused", label: "Pausad" },
  { value: "unknown", label: "Okänd" },
] as const

const SORT_OPTIONS = [
  { value: "jobs", label: "Jobbvolym" },
  { value: "operator_actions", label: "Operatörsåtgärder" },
  { value: "manual_reviews", label: "Gmail-överlämningar" },
  { value: "integration_errors", label: "Integrationsfel" },
  { value: "latest_activity", label: "Senaste aktivitet" },
  { value: "customer", label: "Kundnamn" },
] as const

const DEFAULT_FILTERS: UsageTenantFilters = {
  sort: "jobs",
}

type UsageTenantTableProps = {
  items: UsageTenantItem[]
  filters: UsageTenantFilters
  onFiltersChange: (next: UsageTenantFilters) => void
  searchInput: string
  onSearchInputChange: (value: string) => void
}

export function UsageTenantTable({
  items,
  filters,
  onFiltersChange,
  searchInput,
  onSearchInputChange,
}: UsageTenantTableProps) {
  const navigate = useNavigate()
  const { ref: listLayoutRef, layout } = useListLayout()

  const columns = useMemo(
    () => [
      {
        key: "customer",
        header: "Kund",
        render: (row: UsageTenantItem) => (
          <div className="min-w-0 space-y-1">
            <p className="font-medium text-text-primary">{row.customer_name}</p>
            <TenantIdentifier tenantId={row.tenant_id} />
          </div>
        ),
      },
      {
        key: "attention",
        header: "Uppmärksamhet",
        render: (row: UsageTenantItem) => (
          <StatusBadge
            variant={row.attention_status}
            label={attentionStatusLabel(row.attention_status)}
          />
        ),
      },
      {
        key: "jobs",
        header: "Jobb",
        render: (row: UsageTenantItem) => row.jobs_received,
      },
      {
        key: "operator_actions",
        header: "Operatörsbörda",
        render: (row: UsageTenantItem) => (
          <span className="text-body-small text-text-secondary">
            {formatOperatorBurdenTableCell(
              row.operator_actions,
              row.open_manual_reviews_current,
              row.pending_approvals_current,
            )}
          </span>
        ),
      },
      {
        key: "integration_errors",
        header: "Fel",
        render: (row: UsageTenantItem) => row.integration_errors,
      },
      {
        key: "ai_cost",
        header: "AI-kostnad",
        render: (row: UsageTenantItem) => (
          <span className="text-body-small text-text-secondary">
            {formatAiCostTableCell(row.ai_cost)}
          </span>
        ),
      },
      {
        key: "activity",
        header: "Senaste aktivitet",
        render: (row: UsageTenantItem) => (
          <span className="whitespace-nowrap text-body-small text-text-secondary">
            {formatTimestamp(row.latest_activity_at)}
          </span>
        ),
      },
      {
        key: "open",
        header: "",
        render: (row: UsageTenantItem) => (
          <Link
            to={`/customers/${encodeURIComponent(row.tenant_id)}`}
            className="text-label text-accent hover:underline"
            onClick={(event) => event.stopPropagation()}
          >
            Öppna kund
          </Link>
        ),
      },
    ],
    [],
  )

  function resetFilters() {
    onSearchInputChange("")
    onFiltersChange({ ...DEFAULT_FILTERS })
  }

  return (
    <section aria-labelledby="usage-tenants-heading" className="space-y-4">
      <h2 id="usage-tenants-heading" className="text-section-title text-text-primary">
        Jämförelse per kund
      </h2>

      <FilterBar>
        <FilterField label="Sök" htmlFor="usage-tenant-search">
          <input
            id="usage-tenant-search"
            type="search"
            className={inputClassName}
            value={searchInput}
            onChange={(event) => onSearchInputChange(event.target.value)}
            placeholder="Kund eller tenant-ID"
          />
        </FilterField>
        <FilterField label="Kontostatus" htmlFor="usage-tenant-status">
          <select
            id="usage-tenant-status"
            className={inputClassName}
            value={filters.tenantStatus ?? ""}
            onChange={(event) =>
              onFiltersChange({ ...filters, tenantStatus: event.target.value || undefined })
            }
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Uppmärksamhet" htmlFor="usage-tenant-attention">
          <select
            id="usage-tenant-attention"
            className={inputClassName}
            value={filters.attentionStatus ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                attentionStatus: event.target.value || undefined,
              })
            }
          >
            {ATTENTION_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Minst antal jobb" htmlFor="usage-tenant-min-jobs">
          <input
            id="usage-tenant-min-jobs"
            type="number"
            min={0}
            className={inputClassName}
            value={filters.minimumJobs ?? ""}
            onChange={(event) => {
              const raw = event.target.value
              onFiltersChange({
                ...filters,
                minimumJobs: raw === "" ? undefined : Number(raw),
              })
            }}
          />
        </FilterField>
        <FilterField label="Operatörsbörda" htmlFor="usage-tenant-burden">
          <select
            id="usage-tenant-burden"
            className={inputClassName}
            value={
              filters.hasOperatorBurden === undefined
                ? ""
                : filters.hasOperatorBurden
                  ? "yes"
                  : "no"
            }
            onChange={(event) => {
              const value = event.target.value
              onFiltersChange({
                ...filters,
                hasOperatorBurden:
                  value === "" ? undefined : value === "yes",
              })
            }}
          >
            <option value="">Alla</option>
            <option value="yes">Har börda</option>
            <option value="no">Ingen börda</option>
          </select>
        </FilterField>
        <FilterField label="Sortering" htmlFor="usage-tenant-sort">
          <select
            id="usage-tenant-sort"
            className={inputClassName}
            value={filters.sort ?? "jobs"}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                sort: event.target.value as UsageTenantFilters["sort"],
              })
            }
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <div className="flex w-full flex-wrap gap-2 md:w-auto">
          <button
            type="button"
            className="min-h-11 rounded-md border border-border bg-page px-4 text-body text-text-secondary"
            onClick={resetFilters}
          >
            Återställ
          </button>
        </div>
      </FilterBar>

      <div ref={listLayoutRef} className="min-w-0">
        <DataTable
          columns={columns}
          rows={items}
          getRowKey={(row) => row.tenant_id}
          onRowClick={(row) =>
            navigate(`/customers/${encodeURIComponent(row.tenant_id)}`)
          }
          layout={layout}
          emptyTitle="Inga kunder matchar filtren."
          compactRow={(row) => (
            <button
              type="button"
              className="flex w-full min-w-0 items-start justify-between gap-3 rounded-lg border border-border bg-surface p-3 text-left hover:bg-surface-subtle"
              onClick={() =>
                navigate(`/customers/${encodeURIComponent(row.tenant_id)}`)
              }
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-text-primary">{row.customer_name}</p>
                  <StatusBadge
                    variant={row.attention_status}
                    label={attentionStatusLabel(row.attention_status)}
                  />
                </div>
                <p className="text-body-small text-text-secondary">
                  {row.jobs_received} jobb ·{" "}
                  {formatOperatorBurdenTableCell(
                    row.operator_actions,
                    row.open_manual_reviews_current,
                    row.pending_approvals_current,
                  )}
                </p>
              </div>
              <span className="shrink-0 text-label text-accent">Öppna</span>
            </button>
          )}
          mobileCard={(row) => (
            <article className="space-y-2 rounded-lg border border-border bg-surface p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-medium text-text-primary">{row.customer_name}</p>
                  <TenantIdentifier tenantId={row.tenant_id} />
                  <p className="text-body-small text-text-secondary">
                    {tenantStatusLabel(row.tenant_status)}
                  </p>
                </div>
                <StatusBadge
                  variant={row.attention_status}
                  label={attentionStatusLabel(row.attention_status)}
                />
              </div>
              <p className="text-body-small text-text-secondary">
                {row.jobs_received} jobb ·{" "}
                {formatOperatorBurdenTableCell(
                  row.operator_actions,
                  row.open_manual_reviews_current,
                  row.pending_approvals_current,
                )}{" "}
                · {row.integration_errors} fel
              </p>
              <p className="text-body-small text-text-muted">
                AI-kostnad: {formatAiCostTableCell(row.ai_cost)}
              </p>
              <Link
                to={`/customers/${encodeURIComponent(row.tenant_id)}`}
                className="inline-block text-label text-accent hover:underline"
              >
                Öppna kund
              </Link>
            </article>
          )}
        />
      </div>
    </section>
  )
}
