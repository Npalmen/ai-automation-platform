import type { ReactNode } from "react"

type WorkQueueToolbarProps = {
  children: ReactNode
}

export function WorkQueueToolbar({ children }: WorkQueueToolbarProps) {
  return (
    <div className="mb-4 flex flex-wrap gap-3 rounded-lg border border-border bg-surface p-4">
      {children}
    </div>
  )
}
