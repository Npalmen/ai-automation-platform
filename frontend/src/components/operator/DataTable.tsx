import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

import { EmptyState } from "./EmptyState"
import { ErrorState } from "./ErrorState"
import { LoadingState } from "./LoadingState"

export type DataTableColumn<T> = {
  key: string
  header: string
  className?: string
  render: (row: T) => ReactNode
}

type DataTableProps<T> = {
  columns: DataTableColumn<T>[]
  rows: T[]
  getRowKey: (row: T) => string
  onRowClick?: (row: T) => void
  loading?: boolean
  error?: Error | null
  emptyTitle?: string
  emptyDescription?: string
  mobileCard?: (row: T) => ReactNode
  className?: string
}

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  onRowClick,
  loading = false,
  error = null,
  emptyTitle = "Inga rader att visa",
  emptyDescription = "Det finns inget innehåll som matchar filtren.",
  mobileCard,
  className,
}: DataTableProps<T>) {
  if (loading) {
    return <LoadingState label="Laddar lista…" rows={5} className={className} />
  }

  if (error) {
    return (
      <ErrorState
        title="Kunde inte ladda listan"
        description="Listan kunde inte hämtas just nu."
        recommendedAction="Försök uppdatera sidan."
        technicalDetails={error.message}
        className={className}
      />
    )
  }

  if (rows.length === 0) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        className={className}
      />
    )
  }

  return (
    <div className={cn("min-w-0", className)}>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-0 border-collapse text-left text-body">
          <thead>
            <tr className="border-b border-border">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(
                    "px-3 py-2 text-label font-medium text-text-secondary",
                    column.className,
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={getRowKey(row)}
                className={cn(
                  "border-b border-border",
                  onRowClick
                    ? "cursor-pointer hover:bg-surface-subtle focus-within:bg-surface-subtle"
                    : undefined,
                )}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault()
                          onRowClick(row)
                        }
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn("px-3 py-3 align-top", column.className)}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-3 md:hidden">
        {rows.map((row) => (
          <div key={getRowKey(row)}>
            {mobileCard ? (
              mobileCard(row)
            ) : (
              <div className="rounded-lg border border-border bg-surface p-4">
                {columns.map((column) => (
                  <div key={column.key} className="mb-2 last:mb-0">
                    <p className="text-caption text-text-secondary">{column.header}</p>
                    <div className="text-body text-text-primary">{column.render(row)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
