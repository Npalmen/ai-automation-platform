import type { ReactNode } from "react"

type WorkQueueToolbarProps = {
  children: ReactNode
}

export function WorkQueueToolbar({ children }: WorkQueueToolbarProps) {
  return (
    <div className="mb-4 grid gap-3 rounded-lg border border-border bg-surface p-4 sm:grid-cols-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
      {children}
    </div>
  )
}
