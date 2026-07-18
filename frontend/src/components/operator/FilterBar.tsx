import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type FilterBarProps = {
  children: ReactNode
  className?: string
}

export function FilterBar({ children, className }: FilterBarProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col flex-wrap items-stretch gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:flex-wrap sm:items-end",
        className,
      )}
      role="search"
    >
      {children}
    </div>
  )
}

type FilterFieldProps = {
  label: string
  htmlFor: string
  children: ReactNode
  className?: string
}

export function FilterField({
  label,
  htmlFor,
  children,
  className,
}: FilterFieldProps) {
  return (
    <div className={cn("flex min-w-0 flex-1 flex-col gap-1 sm:min-w-[min(100%,12rem)]", className)}>
      <label htmlFor={htmlFor} className="text-label text-text-secondary">
        {label}
      </label>
      {children}
    </div>
  )
}
