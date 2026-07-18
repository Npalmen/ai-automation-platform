import { useEffect, useRef, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

type ActionDialogProps = {
  open: boolean
  title: string
  consequence: string
  primaryLabel: string
  cancelLabel?: string
  loading?: boolean
  primaryDisabled?: boolean
  error?: string
  onConfirm: () => void
  onClose: () => void
  children?: ReactNode
}

export function ActionDialog({
  open,
  title,
  consequence,
  primaryLabel,
  cancelLabel = "Avbryt",
  loading = false,
  primaryDisabled = false,
  error,
  onConfirm,
  onClose,
  children,
}: ActionDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const triggerRef = useRef<HTMLElement | null>(null)

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

  if (!open) return null

  return (
    <dialog
      ref={dialogRef}
      className={cn(
        "m-0 max-h-[90vh] w-[min(100vw-2rem,32rem)] max-w-none rounded-lg border border-border bg-surface p-0 shadow-lg",
        "backdrop:bg-transparent",
      )}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClose={() => {
        triggerRef.current?.focus()
        onClose()
      }}
      onClick={(event) => {
        if (event.target === dialogRef.current) {
          onClose()
        }
      }}
    >
      <div className="flex max-h-[90vh] flex-col">
        <div className="space-y-2 border-b border-border p-4">
          <h2 className="text-section-title text-text-primary">{title}</h2>
          <p className="break-words text-body text-text-secondary">
            {consequence}
          </p>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
        {error ? (
          <p className="px-4 text-body-small text-status-danger" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex flex-col-reverse gap-2 border-t border-border p-4 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button type="button" onClick={onConfirm} disabled={loading || primaryDisabled}>
            {loading ? "Arbetar…" : primaryLabel}
          </Button>
        </div>
      </div>
    </dialog>
  )
}
