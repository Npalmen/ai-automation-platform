import { Link, useParams } from "react-router-dom"

import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { ApiError } from "@/api/client"

import { AssignSelfButton } from "./components/AssignSelfButton"
import { IncidentActionsSection } from "./components/IncidentActionsSection"
import { IncidentNoteForm } from "./components/IncidentNoteForm"
import { IncidentSignalsPanel } from "./components/IncidentSignalsPanel"
import { IncidentTenantsPanel } from "./components/IncidentTenantsPanel"
import { IncidentTimelineList } from "./components/IncidentTimelineList"
import {
  formatTimestamp,
  incidentStatusLabel,
  isIncidentWritable,
  panelSeverityLabel,
} from "./formatters"
import { useIncidentDetailQuery } from "./queries"

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[10rem_1fr]">
      <dt className="text-label text-text-muted">{label}</dt>
      <dd className="break-words text-body text-text-primary">{value}</dd>
    </div>
  )
}

export function IncidentDetailPage() {
  const { incidentId } = useParams<{ incidentId: string }>()
  const { data, isLoading, isError, error } = useIncidentDetailQuery(incidentId)
  const writable = data ? isIncidentWritable(data.status) : false
  const showAssignSelf = data?.available_actions.some(
    (action) => action.action_id === "incident.assign_self" && action.allowed,
  )

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Incidentdetalj" description="Laddar incident…" />
        <LoadingState label="Laddar incident…" rows={6} />
      </div>
    )
  }

  if (isError || !data) {
    const is404 = error instanceof ApiError && error.status === 404
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Incidentdetalj" />
        <ErrorState
          title={is404 ? "Incidenten hittades inte" : "Kunde inte ladda incident"}
          description={
            is404
              ? "Det finns ingen incident med det angivna ID:t."
              : "Incidentdetaljen kunde inte hämtas just nu."
          }
          recommendedAction={
            is404 ? "Gå tillbaka till listan." : "Försök uppdatera sidan."
          }
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
        <Link
          to="/incidents"
          className="self-start text-body text-text-primary underline"
        >
          Tillbaka till incidenter
        </Link>
      </div>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title={data.title}
        description={data.incident_id}
        actions={
          <Link
            to="/incidents"
            className="rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary"
          >
            Tillbaka
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <SeverityBadge variant={data.severity_badge} />
        <span className="text-body text-text-secondary">
          {panelSeverityLabel(data.severity)}
        </span>
        <StatusBadge
          variant={data.status === "closed" ? "paused" : "warning"}
          label={incidentStatusLabel(data.status)}
        />
      </div>

      <section className="grid gap-3 rounded-md border border-border bg-surface p-4">
        <dl className="grid gap-3">
          <DetailRow
            label="Ansvarig"
            value={data.owner_display_name ?? "Otilldelad"}
          />
          <DetailRow label="Skapad" value={formatTimestamp(data.created_at)} />
          <DetailRow label="Uppdaterad" value={formatTimestamp(data.updated_at)} />
          <DetailRow
            label="Skapad av"
            value={data.created_by_display_name}
          />
        </dl>
        {data.description && (
          <p className="whitespace-pre-wrap break-words text-body text-text-primary">
            {data.description}
          </p>
        )}
        {data.resolution_summary && (
          <div>
            <h2 className="text-heading-3 text-text-primary">Sammanfattning</h2>
            <p className="mt-2 whitespace-pre-wrap break-words text-body text-text-primary">
              {data.resolution_summary}
            </p>
          </div>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="flex min-w-0 flex-col gap-6">
          <section className="flex min-w-0 flex-col gap-3">
            <h2 className="text-heading-3 text-text-primary">Tidslinje</h2>
            <IncidentTimelineList events={data.timeline} />
          </section>
          <section className="flex min-w-0 flex-col gap-3">
            <h2 className="text-heading-3 text-text-primary">Anteckningar</h2>
            <IncidentNoteForm incident={data} disabled={!writable} />
          </section>
        </div>

        <aside className="flex min-w-0 flex-col gap-6">
          <section className="flex min-w-0 flex-col gap-3">
            <h2 className="text-heading-3 text-text-primary">Berörda kunder</h2>
            <IncidentTenantsPanel tenants={data.tenants} />
          </section>
          <section className="flex min-w-0 flex-col gap-3">
            <h2 className="text-heading-3 text-text-primary">Kopplade signaler</h2>
            <IncidentSignalsPanel signals={data.signals} />
          </section>
          <IncidentActionsSection incident={data} writable={writable} />
          {showAssignSelf && (
            <AssignSelfButton incident={data} disabled={!writable} />
          )}
        </aside>
      </div>
    </div>
  )
}
