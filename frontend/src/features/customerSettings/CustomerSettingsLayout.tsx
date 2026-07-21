import type { ReactNode } from "react"

import { SettingsNavigation } from "./components/SettingsNavigation"
import { SettingsHeader } from "./components/SettingsHeader"
import type { CustomerSettingsAggregate } from "./types"
import type { SettingsTab } from "./types"

type Props = {
  data: CustomerSettingsAggregate
  roleLabel: string
  activeTab: SettingsTab
  dirtyTabs: Set<string>
  onTabChange: (tab: SettingsTab) => void
  children: ReactNode
  footer?: ReactNode
}

export function CustomerSettingsLayout({
  data,
  roleLabel,
  activeTab,
  dirtyTabs,
  onTabChange,
  children,
  footer,
}: Props) {
  return (
    <div className="flex min-w-0 flex-col gap-6">
      <SettingsHeader data={data} roleLabel={roleLabel} />
      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
        <aside className="min-w-0 rounded-lg border border-border bg-surface p-3">
          <SettingsNavigation activeTab={activeTab} dirtyTabs={dirtyTabs} onTabChange={onTabChange} />
        </aside>
        <section
          className="min-w-0 rounded-lg border border-border bg-surface p-4"
          aria-labelledby="settings-tab-heading"
        >
          {children}
          {footer}
        </section>
      </div>
    </div>
  )
}
