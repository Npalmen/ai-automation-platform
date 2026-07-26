type WorkQueuePaginationProps = {
  page: number
  total: number
  limit: number
  onPageChange: (page: number) => void
}

export function WorkQueuePagination({
  page,
  total,
  limit,
  onPageChange,
}: WorkQueuePaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const isFirstPage = page <= 1
  const isLastPage = page >= totalPages || total === 0

  if (total <= limit) return null

  return (
    <nav
      className="flex flex-wrap items-center justify-between gap-3"
      aria-label="Sidnavigering"
    >
      <p className="text-body-small text-text-secondary">
        Sida {page} av {totalPages}
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-surface px-4 text-body font-medium text-text-primary hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => onPageChange(page - 1)}
          disabled={isFirstPage}
          aria-label="Föregående sida"
        >
          Föregående
        </button>
        <button
          type="button"
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border bg-surface px-4 text-body font-medium text-text-primary hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => onPageChange(page + 1)}
          disabled={isLastPage}
          aria-label="Nästa sida"
        >
          Nästa
        </button>
      </div>
    </nav>
  )
}
