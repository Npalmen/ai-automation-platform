import { useEffect, useId, useRef, useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  ENVIRONMENT_LABELS,
  ROLE_LABELS,
  isRoleAllowed,
} from "@/features/auth/permissions"
import { useAuth } from "@/features/auth/AuthProvider"
import type { Role } from "@/features/auth/types"
import { cn } from "@/lib/utils"

type NavItem = {
  to: string
  label: string
  end?: boolean
  allowedRoles: readonly Role[]
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Översikt", end: true, allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/needs-help", label: "Behöver hjälp", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/customers", label: "Kunder", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/incidents", label: "Incidenter", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/usage", label: "Användning", allowedRoles: ["read_only", "operations", "admin"] },
  { to: "/system", label: "System", allowedRoles: ["operations", "admin"] },
]

function EnvironmentBadge({ environment }: { environment: "local" | "test" | "production" }) {
  const label = ENVIRONMENT_LABELS[environment]
  return (
    <Badge
      variant="outline"
      className={cn(
        "whitespace-nowrap",
        environment === "production"
          ? "border-border text-text-primary"
          : "border-status-information/40 text-text-secondary",
      )}
    >
      {label}
    </Badge>
  )
}

function SidebarNav({
  items,
  onNavigate,
}: {
  items: NavItem[]
  onNavigate?: () => void
}) {
  return (
    <nav aria-label="Huvudnavigation" className="space-y-1">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex min-h-11 items-center rounded-md px-3 text-body font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              isActive
                ? "bg-surface-subtle text-text-primary"
                : "text-text-secondary hover:bg-surface-subtle hover:text-text-primary",
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell() {
  const { auth, logout } = useAuth()
  const location = useLocation()
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const drawerRef = useRef<HTMLDivElement>(null)
  const mainId = useId()
  const [mobileOpen, setMobileOpen] = useState(false)

  const operator = auth.status === "authenticated" ? auth.operator : null
  const environment = auth.status === "authenticated" ? auth.environment : null
  const visibleNavItems =
    operator === null
      ? []
      : NAV_ITEMS.filter((item) =>
          isRoleAllowed(operator.role, item.allowedRoles),
        )

  useEffect(() => {
    // Close mobile navigation after client-side route changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional UX reset on navigation
    setMobileOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!mobileOpen) {
      document.body.style.overflow = ""
      return
    }

    document.body.style.overflow = "hidden"
    const firstLink = drawerRef.current?.querySelector<HTMLElement>("a")
    firstLink?.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault()
        setMobileOpen(false)
        menuButtonRef.current?.focus()
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = ""
    }
  }, [mobileOpen])

  if (auth.status !== "authenticated" || operator === null || environment === null) {
    return null
  }

  return (
    <div className="min-h-screen bg-page text-text-primary">
      <a
        href={`#${mainId}`}
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2"
      >
        Hoppa till huvudinnehåll
      </a>

      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-border bg-surface md:sticky md:top-0 md:flex md:h-screen md:flex-col">
          <div className="border-b border-border px-4 py-4">
            <p className="text-label font-semibold uppercase tracking-wide text-text-secondary">
              Krowolf Ops
            </p>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-4">
            <SidebarNav items={visibleNavItems} />
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-border bg-surface">
            <div className="flex min-h-14 items-center gap-3 px-4 py-2 sm:px-6">
              <Button
                ref={menuButtonRef}
                type="button"
                variant="outline"
                size="sm"
                className="min-h-11 min-w-11 md:hidden"
                aria-expanded={mobileOpen}
                aria-controls="mobile-navigation"
                onClick={() => setMobileOpen((open) => !open)}
              >
                <span className="sr-only">Öppna meny</span>
                <span aria-hidden="true">☰</span>
              </Button>

              <div className="min-w-0 flex-1">
                <p className="truncate text-body font-medium text-text-primary md:hidden">
                  Krowolf Ops
                </p>
              </div>

              <div className="flex min-w-0 items-center gap-2 sm:gap-3">
                <EnvironmentBadge environment={environment} />
                <div className="hidden min-w-0 text-right sm:block">
                  <p className="truncate text-body font-medium">
                    {operator.display_name}
                  </p>
                  <p className="truncate text-caption text-text-secondary">
                    {ROLE_LABELS[operator.role]}
                  </p>
                </div>
                <Badge variant="outline" className="sm:hidden">
                  {ROLE_LABELS[operator.role]}
                </Badge>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11"
                  onClick={() => void logout()}
                >
                  Logga ut
                </Button>
              </div>
            </div>
          </header>

          <main
            id={mainId}
            className="min-w-0 flex-1 px-4 py-6 sm:px-6"
          >
            <Outlet />
          </main>
        </div>
      </div>

      {mobileOpen ? (
        <div className="fixed inset-0 z-40 md:hidden" role="presentation">
          <button
            type="button"
            aria-label="Stäng meny"
            className="absolute inset-0 bg-black/40"
            onClick={() => {
              setMobileOpen(false)
              menuButtonRef.current?.focus()
            }}
          />
          <div
            id="mobile-navigation"
            ref={drawerRef}
            className="absolute left-0 top-0 flex h-full w-[min(100%,18rem)] flex-col border-r border-border bg-surface shadow-lg"
            role="dialog"
            aria-modal="true"
            aria-label="Mobilnavigation"
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-4">
              <p className="text-label font-semibold uppercase tracking-wide text-text-secondary">
                Meny
              </p>
              <Button
                type="button"
                variant="ghost"
                className="min-h-11 min-w-11"
                onClick={() => {
                  setMobileOpen(false)
                  menuButtonRef.current?.focus()
                }}
              >
                Stäng
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto px-3 py-4">
              <SidebarNav
                items={visibleNavItems}
                onNavigate={() => setMobileOpen(false)}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
