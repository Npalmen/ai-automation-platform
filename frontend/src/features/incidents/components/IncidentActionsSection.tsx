import { useState } from "react"

import { ActionDialog } from "@/components/operator/ActionDialog"

import {
  formatIncidentError,
  useChangeIncidentStatusMutation,
} from "../mutations"
import { parseStatusActionId } from "../formatters"
import type { AvailableIncidentAction, IncidentDetail } from "../types"

type IncidentActionsSectionProps = {
  incident: IncidentDetail
  writable: boolean
}

export function IncidentActionsSection({
  incident,
  writable,
}: IncidentActionsSectionProps) {
  const [activeAction, setActiveAction] = useState<AvailableIncidentAction | null>(
    null,
  )
  const [reason, setReason] = useState("")
  const [resolutionSummary, setResolutionSummary] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const mutation = useChangeIncidentStatusMutation(incident.incident_id)

  const statusActions = incident.available_actions.filter((action) =>
    action.action_id.startsWith("incident.status."),
  )

  const targetStatus = activeAction
    ? parseStatusActionId(activeAction.action_id)
    : null
  const needsResolution =
    targetStatus === "resolved" || targetStatus === "closed"
  const canSubmit =
    reason.trim().length > 0 &&
    confirmed &&
    (!needsResolution || resolutionSummary.trim().length > 0)

  function closeDialog() {
    if (mutation.isPending) return
    setActiveAction(null)
    setReason("")
    setResolutionSummary("")
    setConfirmed(false)
    mutation.reset()
  }

  return (
    <section className="flex min-w-0 flex-col gap-3">
      <h2 className="text-heading-3 text-text-primary">Åtgärder</h2>
      <div className="flex flex-wrap gap-2">
        {statusActions.map((action) => (
          <button
            key={action.action_id}
            type="button"
            className="rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary disabled:opacity-50"
            disabled={!writable || !action.allowed}
            title={action.blocked_reason ?? undefined}
            onClick={() => setActiveAction(action)}
          >
            {action.label}
          </button>
        ))}
      </div>
      {!writable && (
        <p className="text-body-small text-text-muted">
          Incidenten är stängd och kan inte ändras.
        </p>
      )}

      <ActionDialog
        open={activeAction !== null}
        title={activeAction?.label ?? "Ändra status"}
        consequence="Ändrar incidentens interna status utan extern påverkan."
        primaryLabel="Bekräfta"
        loading={mutation.isPending}
        primaryDisabled={!canSubmit}
        error={mutation.isError ? formatIncidentError(mutation.error) : undefined}
        onConfirm={() => {
          if (!targetStatus) return
          mutation.mutate(
            {
              target_status: targetStatus,
              reason: reason.trim(),
              resolution_summary: needsResolution
                ? resolutionSummary.trim()
                : null,
              expected_version: incident.version,
              confirmation: true,
            },
            { onSuccess: () => closeDialog() },
          )
        }}
        onClose={closeDialog}
      >
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-label text-text-muted">Anledning</span>
            <textarea
              className="min-h-20 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          {needsResolution && (
            <label className="flex flex-col gap-1">
              <span className="text-label text-text-muted">Sammanfattning</span>
              <textarea
                className="min-h-24 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"
                value={resolutionSummary}
                onChange={(e) => setResolutionSummary(e.target.value)}
              />
            </label>
          )}
          <label className="flex items-start gap-2 text-body text-text-primary">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            <span>Jag bekräftar statusändringen.</span>
          </label>
        </div>
      </ActionDialog>
    </section>
  )
}
