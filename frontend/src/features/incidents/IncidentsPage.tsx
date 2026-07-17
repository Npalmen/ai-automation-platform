import { useMemo, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { DataTable } from "@/components/operator/DataTable"
import { ErrorState } from "@/components/operator/ErrorState"
import { FilterBar, FilterField } from "@/components/operator/FilterBar"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"
import { StatusBadge } from "@/components/operator/StatusBadge"

import { CreateIncidentDialog } from "./components/CreateIncidentDialog"
import {
  formatAgeHours,
  formatTimestamp,
  incidentStatusLabel,
  panelSeverityLabel,
} from "./formatters"
import { useIncidentsQuery } from "./queries"
import type { IncidentFilters, IncidentListItem } from "./types"

const inputClassName =
  "min-h-11 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"

const STATUS_OPTIONS = [
  { value: "", label: "Alla" },
  { value: "open", label: "Öppen" },
  { value: "acknowledged", label: "Bekräftad" },
  { value: "investigating", label: "Utreds" },
  { value: "monitoring", label: "Övervakas" },
  { value: "resolved", label: "Löst" },
  { value: "closed", label: "Stängd" },
] as const

const SEVERITY_OPTIONS = [
  { value: "", label: "Alla" },
  { value: "critical", label: "Kritisk" },
  { value: "failed", label: "Fel" },
  { value: "warning", label: "Varning" },
  { value: "information", label: "Information" },
] as const

export function IncidentsPage() {
  const navigate = useNavigate()
  const [searchInput, setSearchInput] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [filters, setFilters] = useState<IncidentFilters>({
    sort: "updated_at",
    order: "desc",
  })

  const queryFilters = useMemo(
    () => ({ ...filters, search: searchInput || undefined }),
    [filters, searchInput],
  )
  const { data, isLoading, isError, error, refetch } = useIncidentsQuery(queryFilters)

  const columns = useMemo(
    () => [
      {
        key: "title",
        header: "Incident",
        render: (row: IncidentListItem) => (
          <div className="min-w-0 space-y-1">
            <p className="font-medium text-text-primary">{row.title}</p>
            <p className="text-body-small text-text-muted">{row.incident_id}</p>
          </div>
        ),
      },
      {
        key: "severity",
        header: "Allvar",
        render: (row: IncidentListItem) => (
          <div className="space-y-1">
            <SeverityBadge variant={row.severity_badge} />
            <p className="text-body-small text-text-muted">
              {panelSeverityLabel(row.severity)}
            </p>
          </div>
        ),
      },
      {
        key: "status",
        header: "Status",
        render: (row: IncidentListItem) => (
          <StatusBadge
            variant={row.status === "closed" ? "paused" : "warning"}
            label={incidentStatusLabel(row.status)}
          />
        ),
      },
      {
        key: "owner",
        header: "Ansvarig",
        render: (row: IncidentListItem) => (
          <span className="text-body text-text-secondary">
            {row.owner_display_name ?? "Otilldelad"}
          </span>
        ),
      },
      {
        key: "tenants",
        header: "Kunder",
        render: (row: IncidentListItem) => (
          <span className="text-body text-text-secondary">{row.tenant_count}</span>
        ),
      },
      {
        key: "updated",
        header: "Uppdaterad",
        render: (row: IncidentListItem) => (
          <span className="text-body-small text-text-secondary">
            {formatTimestamp(row.updated_at)}
          </span>
        ),
      },
      {
        key: "age",
        header: "Ålder",
        render: (row: IncidentListItem) => (
          <span className="text-body-small text-text-secondary">
            {formatAgeHours(row.age_hours)}
          </span>
        ),
      },
    ],
    [],
  )

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title="Incidenter"
        description="Intern incidenthantering för sammansatta driftproblem."
        actions={
          <button
            type="button"
            className="rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary"
            onClick={() => setCreateOpen(true)}
          >
            Skapa incident
          </button>
        }
      />

      {data && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-md border border-border bg-surface p-4">
            <p className="text-label text-text-muted">Öppna</p>
            <p className="text-heading-2 text-text-primary">{data.summary.open}</p>
          </div>
          <div className="rounded-md border border-border bg-surface p-4">
            <p className="text-label text-text-muted">Utreds</p>
            <p className="text-heading-2 text-text-primary">
              {data.summary.investigating}
            </p>
          </div>
          <div className="rounded-md border border-border bg-surface p-4">
            <p className="text-label text-text-muted">Kritiska</p>
            <p className="text-heading-2 text-text-primary">
              {data.summary.critical}
            </p>
          </div>
        </div>
      )}

      <FilterBar>
        <FilterField label="Sök" htmlFor="incidents-search">
          <input
            id="incidents-search"
            className={inputClassName}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Titel eller ID"
          />
        </FilterField>
        <FilterField label="Status" htmlFor="incidents-status">
          <select
            id="incidents-status"
            className={inputClassName}
            value={filters.status ?? ""}
            onChange={(e) =>
              setFilters((current) => ({
                ...current,
                status: e.target.value as IncidentFilters["status"],
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
        <FilterField label="Allvar" htmlFor="incidents-severity">
          <select
            id="incidents-severity"
            className={inputClassName}
            value={filters.severity ?? ""}
            onChange={(e) =>
              setFilters((current) => ({
                ...current,
                severity: e.target.value as IncidentFilters["severity"],
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

      {isLoading && <LoadingState label="Laddar incidenter…" rows={6} />}
      {isError && (
        <>
          <ErrorState
            title="Kunde inte ladda incidenter"
            description="Incidentlistan kunde inte hämtas just nu."
            recommendedAction="Försök uppdatera sidan."
            technicalDetails={error instanceof Error ? error.message : undefined}
          />
          <button
            type="button"
            onClick={() => void refetch()}
            className="self-start rounded-md border border-border bg-surface px-4 py-2 text-label text-text-primary"
          >
            Försök igen
          </button>
        </>
      )}

      {data && data.items.length === 0 && (
        <p className="text-body text-text-muted">Inga incidenter matchar filtren.</p>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="hidden lg:block">
            <DataTable
              columns={columns}
              rows={data.items}
              getRowKey={(row) => row.incident_id}
              onRowClick={(row) =>
                navigate(`/incidents/${encodeURIComponent(row.incident_id)}`)
              }
            />
          </div>
          <div className="flex flex-col gap-3 lg:hidden">
            {data.items.map((item) => (
              <Link
                key={item.incident_id}
                to={`/incidents/${encodeURIComponent(item.incident_id)}`}
                className="rounded-md border border-border bg-surface p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium text-text-primary">{item.title}</p>
                    <p className="text-body-small text-text-muted">
                      {incidentStatusLabel(item.status)} ·{" "}
                      {item.owner_display_name ?? "Otilldelad"}
                    </p>
                  </div>
                  <SeverityBadge variant={item.severity_badge} />
                </div>
              </Link>
            ))}
          </div>
        </>
      )}

      <CreateIncidentDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(incidentId) =>
          navigate(`/incidents/${encodeURIComponent(incidentId)}`)
        }
      />
    </div>
  )
}
