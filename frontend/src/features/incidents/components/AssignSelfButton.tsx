import { useState } from "react"

import { ActionDialog } from "@/components/operator/ActionDialog"

import {
  formatIncidentError,
  useAssignSelfMutation,
} from "../mutations"
import type { IncidentDetail } from "../types"

type AssignSelfButtonProps = {
  incident: IncidentDetail
  disabled?: boolean
}

export function AssignSelfButton({ incident, disabled }: AssignSelfButtonProps) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const mutation = useAssignSelfMutation(incident.incident_id)

  const canSubmit = reason.trim().length > 0 && confirmed

  return (
    <>
      <button
        type="button"
        className="rounded-md border border-border bg-surface px-3 py-2 text-body text-text-primary disabled:opacity-50"
        disabled={disabled || mutation.isPending}
        onClick={() => setOpen(true)}
      >
        Tilldela mig
      </button>
      <ActionDialog
        open={open}
        title="Tilldela mig"
        consequence="Du blir ansvarig operatör för incidenten."
        primaryLabel="Tilldela mig"
        loading={mutation.isPending}
        primaryDisabled={!canSubmit}
        error={mutation.isError ? formatIncidentError(mutation.error) : undefined}
        onConfirm={() =>
          mutation.mutate(
            {
              expected_version: incident.version,
              reason: reason.trim(),
              confirmation: true,
            },
            { onSuccess: () => setOpen(false) },
          )
        }
        onClose={() => setOpen(false)}
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
          <label className="flex items-start gap-2 text-body text-text-primary">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            <span>Jag bekräftar tilldelningen.</span>
          </label>
        </div>
      </ActionDialog>
    </>
  )
}
