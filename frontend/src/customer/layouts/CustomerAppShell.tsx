import { useState, useRef } from "react"
import { Outlet } from "react-router-dom"

import { CustomerHeader } from "@/customer/components/CustomerHeader"
import {
  CustomerMobileNavigation,
  CustomerTabletDrawer,
} from "@/customer/components/CustomerMobileNavigation"
import { CustomerSidebar } from "@/customer/components/CustomerSidebar"
import { SkipToContentLink } from "@/customer/components/SkipToContentLink"
import { useRouteFocus } from "@/customer/hooks/useRouteFocus"
import { CUSTOMER_NAV_ITEMS } from "@/customer/routes/navConfig"
import { cn } from "@/lib/utils"

export function CustomerAppShell() {
  const [tabletMenuOpen, setTabletMenuOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)

  useRouteFocus()

  function closeTabletMenu() {
    setTabletMenuOpen(false)
    menuButtonRef.current?.focus()
  }

  return (
    <div className="min-h-screen bg-page">
      <SkipToContentLink />
      <CustomerHeader
        showMenuButton
        menuButtonRef={menuButtonRef}
        onOpenMenu={() => setTabletMenuOpen(true)}
      />

      <div className="mx-auto flex w-full max-w-7xl">
        <aside
          className={cn(
            "hidden shrink-0 border-r border-border bg-surface-subtle/40 lg:block",
            sidebarCollapsed ? "w-16" : "w-60",
          )}
          aria-label="Sidomeny"
        >
          <div className="sticky top-14 flex h-[calc(100vh-3.5rem)] flex-col p-4">
            <div className="mb-4 hidden lg:flex lg:justify-end">
              <button
                type="button"
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border text-text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                aria-label={
                  sidebarCollapsed ? "Expandera sidomeny" : "Minimera sidomeny"
                }
                onClick={() => setSidebarCollapsed((value) => !value)}
              >
                {sidebarCollapsed ? "»" : "«"}
              </button>
            </div>
            <CustomerSidebar
              items={CUSTOMER_NAV_ITEMS}
              collapsed={sidebarCollapsed}
            />
          </div>
        </aside>

        <main
          id="main-content"
          className="min-w-0 flex-1 pb-[calc(6rem+env(safe-area-inset-bottom,0px))] md:pb-6"
          tabIndex={-1}
        >
          <Outlet />
        </main>
      </div>

      <CustomerMobileNavigation />
      <CustomerTabletDrawer
        open={tabletMenuOpen}
        onClose={closeTabletMenu}
      />
    </div>
  )
}
