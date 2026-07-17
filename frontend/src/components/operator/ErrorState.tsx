import { useState } from "react"

import { cn } from "@/lib/utils"

type ErrorStateProps = {
  title: string
  description: string
  impact?: string
  recommendedAction?: string
  technicalDetails?: string
  className?: string
}

export function ErrorState({
  title,
  description,
  impact,
  recommendedAction,
  technicalDetails,
  className,
}: ErrorStateProps) {
  const [showDetails, setShowDetails] = useState(false)

  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-3 rounded-lg border border-status-danger/30 bg-status-danger/5 p-4",
        className,
      )}
      role="alert"
    >
      <h2 className="text-section-title text-text-primary">{title}</h2>
      <p className="break-words text-body text-text-secondary">{description}</p>
      {impact ? (
        <p className="break-words text-body-small text-text-secondary">
          <span className="font-medium">Påverkan:</span> {impact}
        </p>
      ) : null}
      {recommendedAction ? (
        <p className="break-words text-body-small text-text-primary">
          <span className="font-medium">Rekommenderad åtgärd:</span>{" "}
          {recommendedAction}
        </p>
      ) : null}
      {technicalDetails ? (
        <div className="min-w-0">
          <button
            type="button"
            className="text-body-small text-brand underline-offset-2 hover:underline"
            onClick={() => setShowDetails((value) => !value)}
          >
            {showDetails ? "Dölj tekniska detaljer" : "Visa tekniska detaljer"}
          </button>
          {showDetails ? (
            <pre className="mt-2 max-h-32 overflow-auto break-all rounded bg-surface p-2 font-mono text-caption text-text-muted">
              {technicalDetails}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
