import type { FormEvent } from "react"
import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { useCustomerAuth } from "@/customer/auth/CustomerAuthProvider"
import { WorkspaceModeBadge } from "@/customer/components/WorkspaceModeBadge"
import { cn } from "@/lib/utils"

type CustomerHeaderProps = {
  onOpenMenu?: () => void
  showMenuButton?: boolean
}

export function CustomerHeader({
  onOpenMenu,
  showMenuButton = false,
}: CustomerHeaderProps) {
  const { auth } = useCustomerAuth()
  const navigate = useNavigate()
  const [query, setQuery] = useState("")

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) return
    navigate(`/search?q=${encodeURIComponent(trimmed)}`)
  }

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-page/95 backdrop-blur">
      <div className="flex min-h-14 items-center gap-3 px-4 py-2 md:px-6">
        {showMenuButton ? (
          <button
            type="button"
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border text-text-primary md:hidden"
            aria-label="Öppna meny"
            onClick={onOpenMenu}
          >
            <span aria-hidden>☰</span>
          </button>
        ) : null}

        <div className="min-w-0 flex-1">
          <p className="truncate text-body-small font-medium text-text-muted">
            Arbetsyta
          </p>
          <p className="truncate text-body font-semibold text-text-primary">
            {auth.context.company_name}
          </p>
        </div>

        <WorkspaceModeBadge className="hidden sm:inline-flex" />

        <form
          onSubmit={handleSearch}
          className="hidden min-w-0 flex-1 max-w-xs md:block"
          role="search"
        >
          <label htmlFor="workspace-search" className="sr-only">
            Sök i arbetsytan
          </label>
          <input
            id="workspace-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Sök…"
            className={cn(
              "h-11 w-full rounded-md border border-border bg-surface px-3 text-body",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
            )}
          />
        </form>

        <div
          className="hidden items-center gap-2 rounded-md bg-surface-subtle px-3 py-2 text-body-small text-text-secondary lg:flex"
          aria-label="Användarkontext"
        >
          <span className="font-medium text-text-primary">
            {auth.context.contact_name}
          </span>
          <span aria-hidden>·</span>
          <span>Läsbehörighet</span>
        </div>
      </div>

      <div className="border-t border-border px-4 py-2 md:hidden">
        <form onSubmit={handleSearch} role="search">
          <label htmlFor="workspace-search-mobile" className="sr-only">
            Sök i arbetsytan
          </label>
          <input
            id="workspace-search-mobile"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Sök i arbetsytan…"
            className="h-11 w-full rounded-md border border-border bg-surface px-3 text-body"
          />
        </form>
      </div>
    </header>
  )
}
