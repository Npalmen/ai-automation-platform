import { NavLink } from "react-router-dom"

import type { CustomerNavItem } from "@/customer/routes/navConfig"
import { cn } from "@/lib/utils"

type CustomerSidebarProps = {
  items: readonly CustomerNavItem[]
  collapsed?: boolean
  onNavigate?: () => void
}

export function CustomerSidebar({
  items,
  collapsed = false,
  onNavigate,
}: CustomerSidebarProps) {
  return (
    <nav
      aria-label="Huvudnavigation"
      className={cn(
        "flex flex-col gap-1",
        collapsed ? "items-center" : "items-stretch",
      )}
    >
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex min-h-11 items-center rounded-md px-3 text-body font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
              collapsed ? "justify-center px-2" : "justify-start",
              isActive
                ? "bg-brand/10 text-brand"
                : "text-text-secondary hover:bg-surface-subtle hover:text-text-primary",
            )
          }
        >
          <span className={collapsed ? "sr-only" : undefined}>{item.label}</span>
          {collapsed ? (
            <span aria-hidden className="text-caption font-semibold">
              {item.label.slice(0, 1)}
            </span>
          ) : null}
        </NavLink>
      ))}
    </nav>
  )
}
