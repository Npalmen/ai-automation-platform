import { SETTINGS_TABS } from "../constants"
import type { SettingsTab } from "../types"

type Props = {
  activeTab: SettingsTab
  onTabChange: (tab: SettingsTab) => void
  dirtyTabs: Set<string>
}

export function SettingsNavigation({ activeTab, onTabChange, dirtyTabs }: Props) {
  return (
    <nav aria-label="Inställningsdomäner" className="min-w-0">
      <ul className="flex flex-col gap-1 md:flex-row md:flex-wrap">
        {SETTINGS_TABS.map((tab) => {
          const isActive = tab.id === activeTab
          const isDirty = dirtyTabs.has(tab.id)
          return (
            <li key={tab.id} className="min-w-0">
              <button
                type="button"
                onClick={() => onTabChange(tab.id)}
                aria-current={isActive ? "page" : undefined}
                className={`min-h-11 w-full rounded-md px-3 py-2 text-left text-label transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 md:w-auto ${
                  isActive
                    ? "bg-surface-subtle font-medium text-text-primary"
                    : "text-text-secondary hover:bg-surface-subtle hover:text-text-primary"
                }`}
              >
                <span>{tab.label}</span>
                {isDirty ? (
                  <span className="ml-2 text-caption text-status-warning" aria-label="Osparade ändringar">
                    •
                  </span>
                ) : null}
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
