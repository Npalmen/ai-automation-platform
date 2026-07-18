import { useMemo, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { DataTable } from "@/components/operator/DataTable"
import { ErrorState } from "@/components/operator/ErrorState"
import { FilterBar, FilterField } from "@/components/operator/FilterBar"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { useListLayout } from "@/hooks/useListLayout"

import {
  alertSeverityBadge,
  alertSeverityLabel,
  alertStatusLabel,
  formatAgeHours,
  formatTimestamp,
} from "./formatters"
import { useAlertsQuery } from "./queries"
import type { AlertFilters, AlertListItem } from "./types"

const inputClassName =
  "min-h-11 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"

const STATUS_OPTIONS = [
  { value: "", label: "Aktiva" },
  { value: "open", label: "Öppen" },
  { value: "acknowledged", label: "Bekräftad" },
  { value: "snoozed", label: "Snoozad" },
  { value: "resolved", label: "Löst" },
  { value: "suppressed", label: "Undertryckt" },
] as const

const SEVERITY_OPTIONS = [
  { value: "", label: "Alla" },
  { value: "critical", label: "Kritisk" },
  { value: "high", label: "Hög" },
  { value: "warning", label: "Varning" },
  { value: "info", label: "Information" },
] as const

export function AlertsPage() {
  const navigate = useNavigate()
  const { ref: listLayoutRef, layout } = useListLayout()
  const [filters, setFilters] = useState<AlertFilters>({ limit: 50, offset: 0 })
  const { data, isLoading, isError, error } = useAlertsQuery(filters)

  const columns = useMemo(
    () => [
      {
        key: "title",
        header: "Larm",
        render: (row: AlertListItem) => (
          <div className="min-w-0 space-y-1">
            <p className="font-medium text-text-primary">{row.title}</p>
            <p className="text-body-small text-text-muted">{row.alert_type_label}</p>
          </div>
        ),
      },
      {
        key: "severity",
        header: "Allvar",
        render: (row: AlertListItem) => (
          <div className="space-y-1">
            <SeverityBadge variant={alertSeverityBadge(row.severity)} />
            <p className="text-body-small text-text-muted">
              {alertSeverityLabel(row.severity)}
            </p>
          </div>
        ),
      },
      {
        key: "status",
        header: "Status",
        render: (row: AlertListItem) => (
          <StatusBadge
            variant={row.status === "resolved" ? "paused" : "warning"}
            label={alertStatusLabel(row.status)}
          />
        ),
      },
      {
        key: "tenant",
        header: "Kund",
        render: (row: AlertListItem) => (
          <span className="text-body text-text-secondary">
            {row.tenant_id ?? "Plattform"}
          </span>
        ),
      },
      {
        key: "age",
        header: "Ålder",
        render: (row: AlertListItem) => (
          <span className="text-body text-text-secondary">
            {formatAgeHours(row.age_hours)}
          </span>
        ),
      },
      {
        key: "updated",
        header: "Senast detekterad",
        render: (row: AlertListItem) => (
          <span className="text-body text-text-secondary">
            {formatTimestamp(row.last_detected_at)}
          </span>
        ),
      },
    ],
    [],
  )

  return (
    <div ref={listLayoutRef} className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Larm"
        description="Automatiskt detekterade operativa avvikelser."
        actions={
          <Link
            to="/digests"
            className="max-w-full rounded-md border border-border bg-surface px-3 py-2 text-center text-body text-text-primary sm:text-left"
          >
            <span className="sm:hidden">Sammanfattningar</span>
            <span className="hidden sm:inline">Dagliga sammanfattningar</span>
          </Link>
        }
      />

      <FilterBar>
        <FilterField label="Status" htmlFor="alerts-status">
          <select
            id="alerts-status"
            className={inputClassName}
            value={filters.status ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                status: event.target.value as AlertFilters["status"],
                offset: 0,
              }))
            }
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Allvar" htmlFor="alerts-severity">
          <select
            id="alerts-severity"
            className={inputClassName}
            value={filters.severity ?? ""}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                severity: event.target.value as AlertFilters["severity"],
                offset: 0,
              }))
            }
          >
            {SEVERITY_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FilterField>
      </FilterBar>

      {isLoading ? (
        <LoadingState label="Laddar larm…" rows={6} />
      ) : isError ? (
        <ErrorState
          title="Kunde inte ladda larm"
          description="Larmlistan kunde inte hämtas just nu."
          recommendedAction="Försök uppdatera sidan."
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
      ) : data && data.items.length === 0 ? (
        <p className="text-body text-text-muted">Inga larm matchar filtren.</p>
      ) : data ? (
        <div ref={listLayoutRef} className="min-w-0">
          <DataTable
            columns={columns}
            rows={data.items}
            getRowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/alerts/${row.id}`)}
            layout={layout}
            mobileCard={(item) => (
              <button
                type="button"
                onClick={() => navigate(`/alerts/${item.id}`)}
                className="block w-full rounded-md border border-border bg-surface p-4 text-left"
              >
                <p className="font-medium text-text-primary">{item.title}</p>
                <p className="text-body-small text-text-muted">
                  {alertStatusLabel(item.status)} · {formatAgeHours(item.age_hours)}
                </p>
              </button>
            )}
          />
        </div>
      ) : null}
    </div>
  )
}
