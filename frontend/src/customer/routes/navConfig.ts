export type CustomerNavItem = {
  to: string
  label: string
  end?: boolean
  mobilePrimary?: boolean
}

export const CUSTOMER_NAV_ITEMS: readonly CustomerNavItem[] = [
  { to: "/", label: "Översikt", end: true, mobilePrimary: true },
  { to: "/leads", label: "Leads", mobilePrimary: true },
  { to: "/support", label: "Kundfrågor", mobilePrimary: true },
  { to: "/approvals", label: "Godkännanden", mobilePrimary: true },
  { to: "/needs-help", label: "Behöver hjälp" },
  { to: "/activity", label: "Aktivitet" },
]

export const MOBILE_PRIMARY_NAV = CUSTOMER_NAV_ITEMS.filter(
  (item) => item.mobilePrimary,
)

export const MOBILE_MORE_NAV = CUSTOMER_NAV_ITEMS.filter(
  (item) => !item.mobilePrimary,
)
