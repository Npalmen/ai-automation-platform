import { autoActionLabel, schedulerLabel } from "../formatters"

type Props = {
  automation: Record<string, unknown>
  schedulerRunMode: string | null
  autoActions: Record<string, string>
  externalWrites: string[]
  canWrite: boolean
  onChange: (automation: Record<string, unknown>) => void
}

const PRESETS = [
  { key: "observe_only", label: "Endast observera" },
  { key: "prepare_only", label: "Endast förbered" },
  { key: "approval_first", label: "Godkännande först" },
  { key: "controlled_automation", label: "Kontrollerad automation" },
]

export function AutomationSettingsPanel({
  automation,
  schedulerRunMode,
  autoActions,
  externalWrites,
  canWrite,
  onChange,
}: Props) {
  const policy = (automation.policy ?? automation) as Record<string, unknown>
  const presetKey = String(policy.preset_key ?? "")
  const approvalFirst = Boolean(policy.approval_first)

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-body font-medium text-text-primary">Automation preset</h3>
        <select
          className="mt-2 w-full rounded-md border border-border bg-surface px-3 py-2 text-body"
          value={presetKey}
          disabled={!canWrite}
          onChange={(event) =>
            onChange({
              preset_key: event.target.value,
              preset_version: 1,
              approval_first: approvalFirst,
            })
          }
        >
          <option value="">Välj preset</option>
          {PRESETS.map((preset) => (
            <option key={preset.key} value={preset.key}>
              {preset.label}
            </option>
          ))}
        </select>
        <label className="mt-3 flex min-h-11 items-center gap-2">
          <input
            type="checkbox"
            checked={approvalFirst}
            disabled={!canWrite}
            onChange={(event) =>
              onChange({
                preset_key: presetKey,
                preset_version: 1,
                approval_first: event.target.checked,
              })
            }
          />
          <span className="text-body text-text-primary">Godkännande först-policy</span>
        </label>
      </section>

      <section className="rounded-md border border-border bg-page p-3">
        <h3 className="text-body font-medium text-text-primary">Skrivskyddad runtime</h3>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2">
          <div>
            <dt className="text-caption text-text-secondary">Scheduler</dt>
            <dd className="text-body text-text-primary">{schedulerLabel(schedulerRunMode)}</dd>
          </div>
          <div>
            <dt className="text-caption text-text-secondary">Externa writes</dt>
            <dd className="text-body text-text-primary">
              {externalWrites.length > 0 ? externalWrites.join(", ") : "Inga aktiverade"}
            </dd>
          </div>
        </dl>
        <h4 className="mt-3 text-body-small font-medium text-text-primary">Effektiva auto_actions</h4>
        <ul className="mt-2 space-y-1 text-body-small text-text-secondary">
          {Object.entries(autoActions).map(([key, value]) => (
            <li key={key}>
              {key}: {autoActionLabel(value)}
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
