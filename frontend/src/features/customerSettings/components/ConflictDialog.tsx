import { Button } from "@/components/ui/button"

type Props = {
  open: boolean
  message: string
  serverConfigVersion: number
  onReload: () => void
  onCancel: () => void
}

export function ConflictDialog({
  open,
  message,
  serverConfigVersion,
  onReload,
  onCancel,
}: Props) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="conflict-dialog-title"
    >
      <div className="w-full max-w-lg rounded-lg border border-border bg-surface p-4 shadow-lg">
        <h2 id="conflict-dialog-title" className="text-section-title text-text-primary">
          Konfigurationen har ändrats
        </h2>
        <p className="mt-2 text-body text-text-secondary">{message}</p>
        <p className="mt-2 text-body-small text-text-secondary">
          Serverns aktuella version är {serverConfigVersion}. Dina osparade ändringar sparas inte automatiskt
          över den nya versionen.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" onClick={onReload}>
            Ladda om senaste version
          </Button>
          <Button type="button" variant="outline" onClick={onCancel}>
            Avbryt
          </Button>
        </div>
      </div>
    </div>
  )
}
