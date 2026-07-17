import { useState } from "react"
import type { UseMutationResult } from "@tanstack/react-query"

import { ActionDialog } from "@/components/operator/ActionDialog"
import { Button } from "@/components/ui/button"

import { getActionPresentation } from "../actionRegistry"
import { formatOperatorActionError } from "../mutations"
import type {
  AvailableActionMeta,
  OperatorActionRequest,
  OperatorActionResponse,
} from "../types"
import { ActionResultState, responseIsSuccess } from "./ActionResultState"

type OperatorActionDialogProps = {
  open: boolean
  action: AvailableActionMeta
  tenantLabel: string
  onClose: () => void
  mutation: UseMutationResult<
    OperatorActionResponse,
    unknown,
    Omit<OperatorActionRequest, "idempotency_key">,
    unknown
  >
}

export function OperatorActionDialog({
  open,
  action,
  tenantLabel,
  onClose,
  mutation,
}: OperatorActionDialogProps) {
  const [reason, setReason] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const presentation = getActionPresentation(action.action_id)
  const canSubmit = reason.trim().length > 0 && confirmed && !mutation.isPending

  const handleClose = () => {
    setReason("")
    setConfirmed(false)
    mutation.reset()
    onClose()
  }

  const handleConfirm = () => {
    if (!canSubmit) return
    mutation.mutate(
      { reason: reason.trim(), confirmation: true },
      {
        onSuccess: (response) => {
          if (!responseIsSuccess(response)) {
            return
          }
        },
      },
    )
  }

  const errorMessage = mutation.isError
    ? formatOperatorActionError(mutation.error)
    : undefined

  const resultMessage =
    mutation.isSuccess && mutation.data
      ? mutation.data.message
      : null

  return (
    <ActionDialog
      open={open}
      title={action.label}
      consequence={`${presentation.consequence} Kund: ${tenantLabel}.`}
      primaryLabel={presentation.primaryLabel}
      loading={mutation.isPending}
      primaryDisabled={!canSubmit}
      error={errorMessage}
      onConfirm={handleConfirm}
      onClose={handleClose}
    >
      <div className="space-y-4">
        <label className="block space-y-2">
          <span className="text-label text-text-primary">Anledning (obligatorisk)</span>
          <textarea
            className="min-h-[5rem] w-full rounded-md border border-input bg-surface px-3 py-2 text-body text-text-primary"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            maxLength={500}
            required
          />
        </label>
        <label className="flex min-h-[2.75rem] items-start gap-3">
          <input
            type="checkbox"
            className="mt-1 h-4 w-4"
            checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)}
          />
          <span className="break-words text-body-small text-text-secondary">
            Jag förstår konsekvenserna och vill fortsätta
          </span>
        </label>
        {resultMessage ? (
          <ActionResultState
            status={mutation.data?.status ?? "completed"}
            message={resultMessage}
          />
        ) : null}
      </div>
    </ActionDialog>
  )
}

type OperatorActionButtonProps = {
  action: AvailableActionMeta
  onClick: () => void
}

export function OperatorActionButton({ action, onClick }: OperatorActionButtonProps) {
  const disabled = !action.allowed
  const title =
    action.blocked_reason === "insufficient_role"
      ? "Du saknar behörighet"
      : undefined

  return (
    <Button
      type="button"
      variant="outline"
      className="min-h-11 w-full justify-start sm:w-auto"
      disabled={disabled}
      title={title}
      onClick={onClick}
    >
      {action.label}
    </Button>
  )
}
