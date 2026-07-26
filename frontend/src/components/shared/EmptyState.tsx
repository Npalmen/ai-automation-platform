import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type EmptyStateProps = {
  title: string
  description: string
  action?: ReactNode
  className?: string
}

export function EmptyState({
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-3 rounded-lg border border-dashed border-border bg-surface-subtle p-6",
        className,
      )}
    >
      <h2 className="text-section-title text-text-primary">{title}</h2>
      <p className="break-words text-body text-text-secondary">{description}</p>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  )
}
