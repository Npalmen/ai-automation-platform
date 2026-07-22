import { StatusBadge } from "@/components/operator/StatusBadge"
import { Button } from "@/components/ui/button"

import { autoActionLabel } from "../formatters"
import type { CustomerSettingsPreviewResponse } from "../types"

type Props = {
  open: boolean
  preview: CustomerSettingsPreviewResponse | null
  isLoading: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConsequencePreview({
  open,
  preview,
  isLoading,
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null

  const hasBlocking = Boolean(preview?.blocking?.length)
  const canConfirm = preview && preview.valid && !isLoading

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="preview-dialog-title"
    >
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-surface p-4 shadow-lg">
        <h2 id="preview-dialog-title" className="text-section-title text-text-primary">
          Förhandsgranskning av ändringar
        </h2>
        <p className="mt-1 text-body-small text-text-secondary">
          Detta är en read-only förhandsgranskning. Inget sparas förrän du bekräftar.
        </p>

        {isLoading ? <p className="mt-4 text-body">Beräknar konsekvenser…</p> : null}

        {preview && !isLoading ? (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge
                variant={preview.valid ? (hasBlocking ? "warning" : "healthy") : "critical"}
                label={
                  !preview.valid
                    ? "Ogiltig konfiguration"
                    : hasBlocking
                      ? "Giltig men inte redo"
                      : "Giltig"
                }
              />
              {preview.credential_preservation ? (
                <StatusBadge variant="healthy" label="Credentials bevaras" />
              ) : null}
            </div>

            {preview.blocking.length > 0 ? (
              <section>
                <h3 className="text-body font-medium text-text-primary">Blockerare efter save</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-body-small text-text-secondary">
                  {preview.blocking.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <p className="mt-2 text-body-small text-status-warning">
                  Tenant blir not_ready och automation körs fail-closed tills readiness uppfylls.
                </p>
              </section>
            ) : null}

            {preview.warnings.length > 0 ? (
              <section>
                <h3 className="text-body font-medium text-text-primary">Varningar</h3>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-body-small text-text-secondary">
                  {preview.warnings.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>
            ) : null}

            {preview.readiness_domains_affected.length > 0 ? (
              <section>
                <h3 className="text-body font-medium text-text-primary">Readiness påverkas</h3>
                <p className="mt-1 text-body-small text-text-secondary">
                  {preview.readiness_domains_affected.join(", ")}
                </p>
              </section>
            ) : null}

            {preview.automation_projection?.auto_actions ? (
              <section>
                <h3 className="text-body font-medium text-text-primary">Beräknad automation</h3>
                <ul className="mt-2 space-y-1 text-body-small text-text-secondary">
                  {Object.entries(preview.automation_projection.auto_actions).map(([key, value]) => (
                    <li key={key}>
                      {key}: {autoActionLabel(value)}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" disabled={!canConfirm} onClick={onConfirm}>
            Bekräfta och spara
          </Button>
          <Button type="button" variant="outline" onClick={onCancel}>
            Avbryt
          </Button>
        </div>
      </div>
    </div>
  )
}
