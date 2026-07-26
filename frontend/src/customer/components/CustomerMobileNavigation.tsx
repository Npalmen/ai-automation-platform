import { useEffect, useRef, useState } from "react"
import { NavLink, useLocation } from "react-router-dom"

import { CustomerSidebar } from "@/customer/components/CustomerSidebar"
import {
  CUSTOMER_NAV_ITEMS,
  MOBILE_MORE_NAV,
  MOBILE_PRIMARY_NAV,
} from "@/customer/routes/navConfig"
import { cn } from "@/lib/utils"

export function CustomerMobileNavigation() {
  const [moreOpen, setMoreOpen] = useState(false)
  const location = useLocation()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const moreTriggerRef = useRef<HTMLButtonElement>(null)

  const moreActive = MOBILE_MORE_NAV.some((item) =>
    item.end
      ? location.pathname === item.to
      : location.pathname.startsWith(item.to),
  )

  function closeMoreMenu() {
    setMoreOpen(false)
    moreTriggerRef.current?.focus()
  }

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (moreOpen && !dialog.open) {
      dialog.showModal()
    }
    if (!moreOpen && dialog.open) {
      dialog.close()
    }
  }, [moreOpen])

  return (
    <>
      <nav
        aria-label="Mobilnavigation"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-page pb-[env(safe-area-inset-bottom,0px)] md:hidden"
      >
        <ul className="grid grid-cols-5">
          {MOBILE_PRIMARY_NAV.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-14 flex-col items-center justify-center gap-1 px-1 text-caption font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand",
                    isActive
                      ? "text-brand"
                      : "text-text-secondary hover:text-text-primary",
                  )
                }
              >
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
          <li>
            <button
              ref={moreTriggerRef}
              type="button"
              className={cn(
                "flex min-h-14 w-full flex-col items-center justify-center gap-1 px-1 text-caption font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand",
                moreActive
                  ? "text-brand"
                  : "text-text-secondary hover:text-text-primary",
              )}
              aria-expanded={moreOpen}
              aria-haspopup="dialog"
              onClick={() => setMoreOpen(true)}
            >
              Mer
            </button>
          </li>
        </ul>
      </nav>

      <dialog
        ref={dialogRef}
        className="m-0 h-full max-h-none w-full max-w-none rounded-none border-0 bg-page p-0 md:hidden"
        aria-label="Fler val"
        onCancel={closeMoreMenu}
        onClose={() => setMoreOpen(false)}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h2 className="text-section-title text-text-primary">Mer</h2>
            <button
              type="button"
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              aria-label="Stäng meny"
              onClick={closeMoreMenu}
            >
              <span aria-hidden>✕</span>
            </button>
          </div>
          <div className="flex-1 overflow-auto p-4">
            <CustomerSidebar
              items={MOBILE_MORE_NAV}
              onNavigate={closeMoreMenu}
            />
          </div>
        </div>
      </dialog>
    </>
  )
}

export function CustomerTabletDrawer({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className={cn(
        "m-0 h-full max-h-none w-72 max-w-[85vw] rounded-none border-0 border-r border-border bg-page p-0 md:max-lg:block lg:hidden",
        !open && "hidden",
      )}
      aria-label="Navigation"
      onCancel={onClose}
      onClose={onClose}
    >
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="text-section-title text-text-primary">Meny</p>
          <button
            type="button"
            className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md border border-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            aria-label="Stäng meny"
            onClick={onClose}
          >
            <span aria-hidden>✕</span>
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4">
          <CustomerSidebar
            items={CUSTOMER_NAV_ITEMS}
            onNavigate={onClose}
          />
        </div>
      </div>
    </dialog>
  )
}
