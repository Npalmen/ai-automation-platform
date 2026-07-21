import { Button } from "@/components/ui/button"

type Props = {
  canSave: boolean
  canPreview: boolean
  isDirty: boolean
  isSaving: boolean
  isPreviewing: boolean
  saveLabel?: string
  onSave: () => void
  onPreview?: () => void
  onReset: () => void
  feedback?: { type: "success" | "error"; message: string } | null
}

export function SaveBar({
  canSave,
  canPreview,
  isDirty,
  isSaving,
  isPreviewing,
  saveLabel = "Spara ändringar",
  onSave,
  onPreview,
  onReset,
  feedback,
}: Props) {
  if (!canSave && !isDirty) {
    return null
  }

  return (
    <div className="sticky bottom-0 z-10 mt-4 rounded-lg border border-border bg-surface p-4 shadow-sm">
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          {isDirty ? (
            <p className="text-body-small text-text-primary">Du har osparade ändringar i denna flik.</p>
          ) : (
            <p className="text-body-small text-text-secondary">Inga osparade ändringar.</p>
          )}
          {feedback ? (
            <p
              className={`mt-1 text-body-small ${
                feedback.type === "success" ? "text-status-healthy" : "text-status-critical"
              }`}
              role="status"
            >
              {feedback.message}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {canSave ? (
            <Button type="button" variant="outline" size="sm" disabled={!isDirty || isSaving} onClick={onReset}>
              Återställ
            </Button>
          ) : null}
          {canPreview && onPreview ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!isDirty || isPreviewing || isSaving}
              onClick={onPreview}
            >
              {isPreviewing ? "Förhandsgranskar…" : "Förhandsgranska"}
            </Button>
          ) : null}
          {canSave ? (
            <Button type="button" size="sm" disabled={!isDirty || isSaving} onClick={onSave}>
              {isSaving ? "Sparar…" : saveLabel}
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
