import { Link, useParams, useSearchParams } from "react-router-dom"
import { useState } from "react"

import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"
import { TenantIdentifier } from "@/components/operator/TenantIdentifier"
import { CreateIncidentDialog } from "@/features/incidents/components/CreateIncidentDialog"
import { incidentStatusLabel } from "@/features/incidents/formatters"
import {
  OperatorActionsSection,
  parseApprovalIdFromItemId,
} from "@/features/operatorActions/components/OperatorActionsSection"
import { ApiError } from "@/api/client"

import {
  categoryLabel,
  formatAgeHours,
  formatDetectedAt,
  panelSeverityLabel,
  signalStateLabel,
} from "./formatters"
import { useNeedsHelpItemQuery } from "./queries"

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid min-w-0 gap-1 md:grid-cols-[10rem_1fr]">
      <dt className="text-label text-text-muted">{label}</dt>
      <dd className="break-words text-body text-text-primary">{value}</dd>
    </div>
  )
}

export function NeedsHelpDetailPage() {
  const { itemId } = useParams<{ itemId: string }>()
  const [searchParams] = useSearchParams()
  const tenantId = searchParams.get("tenant_id") ?? undefined
  const [createIncidentOpen, setCreateIncidentOpen] = useState(false)
  const { data, isLoading, isError, error } = useNeedsHelpItemQuery(itemId, tenantId)

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Ärendedetalj" description="Laddar problembeskrivning…" />
        <LoadingState label="Laddar ärende…" rows={6} />
      </div>
    )
  }

  if (isError || !data) {
    const is404 = error instanceof ApiError && error.status === 404
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Ärendedetalj" />
        <ErrorState
          title={is404 ? "Ärendet hittades inte" : "Kunde inte ladda ärende"}
          description={
            is404
              ? "Det finns inget aktivt ärende med det angivna ID:t."
              : "Ärendedetaljen kunde inte hämtas just nu."
          }
          recommendedAction={
            is404 ? "Gå tillbaka till kön." : "Försök uppdatera sidan."
          }
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
        <Link
          to="/needs-help"
          className="self-start text-body text-text-primary underline"
        >
          Tillbaka till Behöver hjälp
        </Link>
      </div>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title={data.title}
        description={`${data.customer_name} · ${categoryLabel(data.category)}`}
        actions={
          <Link
            to={data.link}
            className="inline-flex max-w-full shrink-0 min-h-11 items-center rounded-md border border-border bg-page px-4 text-body text-text-primary"
          >
            Öppna kund
          </Link>
        }
      />

      <section className="min-w-0 rounded-lg border border-border bg-surface p-4">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <SeverityBadge variant={data.severity_badge} />
          <span className="text-body text-text-secondary">
            {panelSeverityLabel(data.severity)}
          </span>
        </div>
        <dl className="space-y-3">
          <DetailRow label="Kund" value={data.customer_name} />
          <div className="grid min-w-0 gap-1 md:grid-cols-[10rem_1fr]">
            <dt className="text-label text-text-muted">Tenant</dt>
            <dd>
              <TenantIdentifier tenantId={data.tenant_id} />
            </dd>
          </div>
          <DetailRow label="Kategori" value={categoryLabel(data.category)} />
          <DetailRow label="Källtyp" value={data.source_type || "—"} />
          <DetailRow label="Upptäckt" value={formatDetectedAt(data.detected_at)} />
          <DetailRow label="Ålder" value={formatAgeHours(data.age_hours)} />
          <DetailRow label="Påverkan" value={data.impact || "—"} />
          <DetailRow
            label="Säker retry"
            value={signalStateLabel(data.safe_retry_available)}
          />
          <DetailRow
            label="Extern åtgärd kan ha skett"
            value={signalStateLabel(data.external_action_may_have_occurred)}
          />
          <DetailRow
            label="Rekommenderad åtgärd"
            value={data.recommended_action || "—"}
          />
          {data.runbook ? (
            <DetailRow label="Runbook" value={data.runbook.label} />
          ) : null}
        </dl>
      </section>

      <OperatorActionsSection
        tenantId={data.tenant_id}
        tenantLabel={data.customer_name}
        actions={data.available_actions ?? []}
        approvalId={parseApprovalIdFromItemId(data.id)}
      />

      <section className="min-w-0 rounded-lg border border-border bg-surface p-4">
        <h2 className="text-heading-3 text-text-primary">Incidenthantering</h2>
        <p className="mt-2 text-body-small text-text-muted">
          Skapa eller koppla till en intern incident utan extern påverkan.
        </p>
        {data.recommended_incident_action && (
          <button
            type="button"
            className="mt-4 rounded-md border border-border bg-page px-4 py-2 text-body text-text-primary"
            onClick={() => setCreateIncidentOpen(true)}
          >
            Skapa incident från detta problem
          </button>
        )}
        {data.linked_incidents?.open?.length ? (
          <div className="mt-4">
            <h3 className="text-label text-text-muted">Öppna incidenter</h3>
            <ul className="mt-2 space-y-2">
              {data.linked_incidents.open.map((incident) => (
                <li key={incident.incident_id}>
                  <Link
                    to={`/incidents/${encodeURIComponent(incident.incident_id)}`}
                    className="text-body text-text-primary underline"
                  >
                    {incident.title} ({panelSeverityLabel(incident.severity)} ·{" "}
                    {incidentStatusLabel(incident.status as never)})
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {data.linked_incidents?.closed?.length ? (
          <div className="mt-4">
            <h3 className="text-label text-text-muted">Stängda incidenter</h3>
            <ul className="mt-2 space-y-2">
              {data.linked_incidents.closed.map((incident) => (
                <li key={incident.incident_id}>
                  <Link
                    to={`/incidents/${encodeURIComponent(incident.incident_id)}`}
                    className="text-body text-text-secondary underline"
                  >
                    {incident.title} ({panelSeverityLabel(incident.severity)} ·{" "}
                    {incidentStatusLabel(incident.status as never)})
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {data.recommended_incident_action && (
        <CreateIncidentDialog
          open={createIncidentOpen}
          onClose={() => setCreateIncidentOpen(false)}
          prefill={{
            title: data.recommended_incident_action.prefill_title,
            severity: data.recommended_incident_action.prefill_severity,
            tenantId: data.recommended_incident_action.tenant_id,
            signalId: data.recommended_incident_action.signal_id,
          }}
        />
      )}

      <Link
        to="/needs-help"
        className="self-start text-body text-text-primary underline"
      >
        Tillbaka till kön
      </Link>
    </div>
  )
}
