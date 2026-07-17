import { useState } from "react"

import { ActionDialog } from "@/components/operator/ActionDialog"

import { formatIncidentError, useCreateIncidentMutation } from "../mutations"
import type { IncidentCreatePayload, PanelSeverity } from "../types"

type CreateIncidentDialogProps = {
  open: boolean
  onClose: () => void
  onCreated?: (incidentId: string) => void
  prefill?: {
    title?: string
    severity?: PanelSeverity
    tenantId?: string
    signalId?: string
  }
}

const inputClassName =
  "min-h-11 w-full rounded-md border border-border bg-page px-3 text-body text-text-primary"

export function CreateIncidentDialog({
  open,
  onClose,
  onCreated,
  prefill,
}: CreateIncidentDialogProps) {
  const [title, setTitle] = useState(prefill?.title ?? "")
  const [description, setDescription] = useState("")
  const [severity, setSeverity] = useState<PanelSeverity>(
    prefill?.severity ?? "warning",
  )
  const [reason, setReason] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const mutation = useCreateIncidentMutation()

  const signalLinks =
    prefill?.tenantId && prefill?.signalId
      ? [{ tenant_id: prefill.tenantId, signal_id: prefill.signalId }]
      : []

  const canSubmit =
    title.trim().length > 0 && reason.trim().length > 0 && confirmed

  function handleClose() {
    if (mutation.isPending) return
    mutation.reset()
    onClose()
  }

  function handleSubmit() {
    const payload: IncidentCreatePayload = {
      title: title.trim(),
      description: description.trim() || null,
      severity,
      tenant_ids: prefill?.tenantId ? [prefill.tenantId] : [],
      signal_links: signalLinks,
      reason: reason.trim(),
      confirmation: true,
    }
    mutation.mutate(payload, {
      onSuccess: (data) => {
        onCreated?.(data.incident_id)
        handleClose()
      },
    })
  }

  return (
    <ActionDialog
      open={open}
      title="Skapa incident"
      consequence="Skapar ett internt operatörsärende utan extern påverkan."
      primaryLabel="Skapa incident"
      loading={mutation.isPending}
      primaryDisabled={!canSubmit}
      error={mutation.isError ? formatIncidentError(mutation.error) : undefined}
      onConfirm={handleSubmit}
      onClose={handleClose}
    >
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1">
          <span className="text-label text-text-muted">Titel</span>
          <input
            className={inputClassName}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-label text-text-muted">Beskrivning</span>
          <textarea
            className={`${inputClassName} min-h-24`}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-label text-text-muted">Allvarlighetsgrad</span>
          <select
            className={inputClassName}
            value={severity}
            onChange={(e) => setSeverity(e.target.value as PanelSeverity)}
          >
            <option value="critical">Kritisk</option>
            <option value="failed">Fel</option>
            <option value="warning">Varning</option>
            <option value="information">Information</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-label text-text-muted">Anledning</span>
          <textarea
            className={`${inputClassName} min-h-20`}
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
          <span>Jag bekräftar att jag vill skapa incidenten.</span>
        </label>
      </div>
    </ActionDialog>
  )
}
