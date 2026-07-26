import type { PartialError } from "@/customer/types/overview"

type OverviewPartialErrorProps = {
  errors: PartialError[]
}

export function OverviewPartialError({ errors }: OverviewPartialErrorProps) {
  if (errors.length === 0) return null

  return (
    <div
      className="rounded-lg border border-status-warning/30 bg-status-warning/5 p-4"
      role="alert"
    >
      <h2 className="text-section-title text-text-primary">
        Delar av översikten kunde inte visas
      </h2>
      <ul className="mt-2 space-y-2">
        {errors.map((error, index) => (
          <li key={`${error.section}-${index}`} className="text-body text-text-secondary">
            {error.message}
          </li>
        ))}
      </ul>
    </div>
  )
}
