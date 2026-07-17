import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { ActionDialog } from "@/components/operator/ActionDialog"
import { ErrorState } from "@/components/operator/ErrorState"
import { LoadingState } from "@/components/operator/LoadingState"
import { PageHeader } from "@/components/operator/PageHeader"
import { SeverityBadge } from "@/components/operator/SeverityBadge"
import { StatusBadge } from "@/components/operator/StatusBadge"
import { ApiError } from "@/api/client"
import { useAuth } from "@/features/auth/AuthProvider"
import { isRoleAllowed } from "@/features/auth/permissions"

import {
  alertSeverityBadge,
  alertSeverityLabel,
  alertStatusLabel,
  formatAgeHours,
  formatTimestamp,
  isAlertWritable,
} from "./formatters"
import {
  formatAlertError,
  useAcknowledgeAlertMutation,
  useResolveAlertMutation,
} from "./mutations"
import { useAlertDetailQuery } from "./queries"

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[10rem_1fr]">
      <dt className="text-label text-text-muted">{label}</dt>
      <dd className="break-words text-body text-text-primary">{value}</dd>
    </div>
  )
}

export function AlertDetailPage() {
  const { alertId } = useParams<{ alertId: string }>()
  const { auth } = useAuth()
  const { data, isLoading, isError, error } = useAlertDetailQuery(alertId)
  const [ackOpen, setAckOpen] = useState(false)
  const [resolveOpen, setResolveOpen] = useState(false)
  const [reason, setReason] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const acknowledgeMutation = useAcknowledgeAlertMutation(alertId ?? "")
  const resolveMutation = useResolveAlertMutation(alertId ?? "")

  const canWrite =
    auth.status === "authenticated" &&
    isRoleAllowed(auth.operator.role, ["operations", "admin"])
  const writable = data ? isAlertWritable(data.status) && canWrite : false

  if (isLoading) {
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Larmdetalj" description="Laddar larm…" />
        <LoadingState label="Laddar larm…" rows={6} />
      </div>
    )
  }

  if (isError || !data) {
    const is404 = error instanceof ApiError && error.status === 404
    return (
      <div className="flex min-w-0 flex-col gap-6">
        <PageHeader title="Larmdetalj" />
        <ErrorState
          title={is404 ? "Larmet hittades inte" : "Kunde inte ladda larm"}
          description={
            is404
              ? "Det finns inget larm med det angivna ID:t."
              : "Larmdetaljen kunde inte hämtas just nu."
          }
          recommendedAction={
            is404 ? "Gå tillbaka till listan." : "Försök uppdatera sidan."
          }
          technicalDetails={error instanceof Error ? error.message : undefined}
        />
        <Link
          to="/alerts"
          className="self-start text-body text-text-primary underline"
        >
          Tillbaka till larm
        </Link>
      </div>
    )
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <PageHeader
        title={data.title}
        description={data.summary}
        actions={
          writable ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary"
                onClick={() => setAckOpen(true)}
              >
                Bekräfta
              </button>
              <button
                type="button"
                className="rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary"
                onClick={() => setResolveOpen(true)}
              >
                Lös
              </button>
            </div>
          ) : undefined
        }
      />

      <section className="flex flex-wrap items-center gap-3">
        <SeverityBadge variant={alertSeverityBadge(data.severity)} />
        <StatusBadge
          variant={data.status === "resolved" ? "paused" : "warning"}
          label={alertStatusLabel(data.status)}
        />
        <span className="text-body-small text-text-muted">
          {alertSeverityLabel(data.severity)} · {data.alert_type_label}
        </span>
      </section>

      <section className="rounded-lg border border-border bg-surface p-4">
        <h2 className="mb-3 text-heading-3 text-text-primary">Detaljer</h2>
        <dl className="space-y-3">
          <DetailRow label="Kund" value={data.tenant_id ?? "Plattform"} />
          <DetailRow label="Jobb" value={data.related_job_id ?? "—"} />
          <DetailRow label="Ålder" value={formatAgeHours(data.age_hours)} />
          <DetailRow
            label="Första detektering"
            value={formatTimestamp(data.first_detected_at)}
          />
          <DetailRow
            label="Senast detekterad"
            value={formatTimestamp(data.last_detected_at)}
          />
          <DetailRow
            label="Antal gånger"
            value={String(data.occurrence_count)}
          />
          {data.recommended_action ? (
            <DetailRow label="Rekommenderad åtgärd" value={data.recommended_action} />
          ) : null}
          {data.runbook_ref ? (
            <DetailRow label="Runbook" value={data.runbook_ref} />
          ) : null}
        </dl>
      </section>

      <Link
        to="/alerts"
        className="self-start text-body text-text-primary underline"
      >
        Tillbaka till larm
      </Link>

      <ActionDialog
        open={ackOpen}
        title="Bekräfta larm"
        consequence="Markerar larmet som bekräftat utan att lösa det."
        primaryLabel="Bekräfta"
        loading={acknowledgeMutation.isPending}
        primaryDisabled={!confirmed}
        error={
          acknowledgeMutation.isError
            ? formatAlertError(acknowledgeMutation.error)
            : undefined
        }
        onClose={() => {
          if (acknowledgeMutation.isPending) return
          setAckOpen(false)
          setReason("")
          setConfirmed(false)
          acknowledgeMutation.reset()
        }}
        onConfirm={() => {
          void acknowledgeMutation.mutateAsync(
            { version: data.version, reason: reason.trim() || undefined },
            {
              onSuccess: () => {
                setAckOpen(false)
                setReason("")
                setConfirmed(false)
              },
            },
          )
        }}
      >
        <label className="flex items-center gap-2 text-body text-text-primary">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          Jag bekräftar att jag har tagit del av larmet.
        </label>
      </ActionDialog>

      <ActionDialog
        open={resolveOpen}
        title="Lös larm"
        consequence="Markerar larmet som löst. Det kan återöppnas om signalen återkommer."
        primaryLabel="Lös"
        loading={resolveMutation.isPending}
        primaryDisabled={!confirmed || reason.trim().length < 3}
        error={
          resolveMutation.isError ? formatAlertError(resolveMutation.error) : undefined
        }
        onClose={() => {
          if (resolveMutation.isPending) return
          setResolveOpen(false)
          setReason("")
          setConfirmed(false)
          resolveMutation.reset()
        }}
        onConfirm={() => {
          void resolveMutation.mutateAsync(
            { version: data.version, reason: reason.trim() },
            {
              onSuccess: () => {
                setResolveOpen(false)
                setReason("")
                setConfirmed(false)
              },
            },
          )
        }}
      >
        <label className="flex flex-col gap-1">
          <span className="text-label text-text-muted">Anledning</span>
          <textarea
            className="min-h-24 w-full rounded-md border border-border bg-page px-3 py-2 text-body text-text-primary"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-body text-text-primary">
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          Jag bekräftar att larmet är hanterat.
        </label>
      </ActionDialog>
    </div>
  )
}
