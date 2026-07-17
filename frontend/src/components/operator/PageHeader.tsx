import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type PageHeaderProps = {
  title: string
  description?: string
  status?: ReactNode
  actions?: ReactNode
  className?: string
}

export function PageHeader({
  title,
  description,
  status,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "flex min-w-0 flex-col gap-3 border-b border-border pb-4 md:flex-row md:items-start md:justify-between",
        className,
      )}
    >
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <h1 className="text-page-title font-semibold text-text-primary">
            {title}
          </h1>
          {status}
        </div>
        {description ? (
          <p className="break-words text-body text-text-secondary">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex min-w-0 flex-wrap gap-2">{actions}</div>
      ) : null}
    </header>
  )
}
