import type { PartialError } from "@/customer/types/overview"

type WorkQueuePartialErrorProps = {
  errors: PartialError[]
}

export function WorkQueuePartialError({ errors }: WorkQueuePartialErrorProps) {
  if (errors.length === 0) return null

  return (
    <div
      className="rounded-lg border border-status-warning/30 bg-status-warning/5 p-4"
      role="alert"
    >
      <h2 className="text-section-title text-text-primary">
        Delar av listan kunde inte visas
      </h2>
      <ul className="mt-2 space-y-2">
        {errors.map((error, index) => (
          <li
            key={`${error.section}-${index}`}
            className="text-body text-text-secondary"
          >
            {error.message}
          </li>
        ))}
      </ul>
    </div>
  )
}
