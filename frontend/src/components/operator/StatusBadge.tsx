import type { StatusVariant } from "@/design/types"
import { cn } from "@/lib/utils"

const STATUS_STYLES = {
  healthy: {
    dotClassName: "bg-status-success",
    label: "Frisk",
  },
  warning: {
    dotClassName: "bg-status-warning",
    label: "Varning",
  },
  failed: {
    dotClassName: "bg-status-danger",
    label: "Fel",
  },
  critical: {
    dotClassName: "bg-status-critical",
    label: "Kritiskt",
  },
  paused: {
    dotClassName: "bg-status-paused",
    label: "Pausad",
  },
  unknown: {
    dotClassName: "bg-status-unknown",
    label: "Okänd",
  },
} satisfies Record<StatusVariant, { dotClassName: string; label: string }>

type StatusBadgeProps = {
  variant: StatusVariant
  label?: string
  className?: string
}

export function StatusBadge({ variant, label, className }: StatusBadgeProps) {
  const style = STATUS_STYLES[variant]
  const text = label ?? style.label

  return (
    <span
      className={cn(
        "inline-flex min-h-[1.75rem] min-w-0 items-center gap-2 rounded-full border border-border bg-surface px-2.5 py-0.5 text-label text-text-primary",
        className,
      )}
      aria-label={`Status: ${text}`}
    >
      <span
        className={cn("h-2 w-2 shrink-0 rounded-full", style.dotClassName)}
        aria-hidden="true"
      />
      <span className="truncate">{text}</span>
    </span>
  )
}
