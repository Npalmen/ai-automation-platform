import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type CriticalActionDialogProps = {
  open: boolean
  title: string
  consequence: string
  reasonLabel?: string
  confirmationLabel?: string
  primaryLabel: string
  cancelLabel?: string
  loading?: boolean
  error?: string
  onConfirm: (reason: string) => void
  onClose: () => void
}

export function CriticalActionDialog({
  open,
  title,
  consequence,
  reasonLabel = "Anledning (obligatorisk)",
  confirmationLabel = "Jag förstår konsekvenserna och vill fortsätta",
  primaryLabel,
  cancelLabel = "Avbryt",
  loading = false,
  error,
  onConfirm,
  onClose,
}: CriticalActionDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)
  const [reason, setReason] = useState("")
  const [confirmed, setConfirmed] = useState(false)

  const canConfirm = reason.trim().length > 0 && confirmed && !loading

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (open) {
      triggerRef.current = document.activeElement as HTMLElement | null
      if (!dialog.open) {
        dialog.showModal()
      }
      return
    }

    if (dialog.open) {
      dialog.close()
    }
  }, [open])

  const handleClose = () => {
    setReason("")
    setConfirmed(false)
    onClose()
  }

  if (!open) return null

  return (
    <dialog
      ref={dialogRef}
      className={cn(
        "m-0 max-h-[90vh] w-[min(100vw-1rem,40rem)] max-w-none rounded-lg border-2 border-status-critical bg-surface p-0 shadow-lg",
      )}
      onCancel={(event) => {
        event.preventDefault()
        handleClose()
      }}
      onClose={() => {
        triggerRef.current?.focus()
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) {
          event.stopPropagation()
        }
      }}
    >
      <div className="flex max-h-[90vh] flex-col">
        <div className="space-y-2 border-b border-border p-4">
          <p className="text-label font-semibold uppercase tracking-wide text-status-critical">
            Kritisk åtgärd
          </p>
          <h2 className="text-section-title text-text-primary">{title}</h2>
          <p className="break-words text-body text-text-secondary">
            {consequence}
          </p>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <label className="block space-y-2">
            <span className="text-label text-text-primary">{reasonLabel}</span>
            <textarea
              className="min-h-[5rem] w-full rounded-md border border-input bg-surface px-3 py-2 text-body text-text-primary"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
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
              {confirmationLabel}
            </span>
          </label>
        </div>
        {error ? (
          <p className="px-4 text-body-small text-status-danger" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex flex-col-reverse gap-2 border-t border-border p-4 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={handleClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            type="button"
            disabled={!canConfirm}
            onClick={() => onConfirm(reason.trim())}
          >
            {loading ? "Arbetar…" : primaryLabel}
          </Button>
        </div>
      </div>
    </dialog>
  )
}
