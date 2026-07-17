import type { SeverityVariant } from "@/design/types"
import { cn } from "@/lib/utils"

const SEVERITY_STYLES = {
  P1: {
    className: "border-status-critical bg-status-critical/10 text-status-critical",
    label: "P1",
  },
  P2: {
    className: "border-status-danger bg-status-danger/10 text-status-danger",
    label: "P2",
  },
  P3: {
    className: "border-status-warning bg-status-warning/10 text-status-warning",
    label: "P3",
  },
  P4: {
    className:
      "border-status-information bg-status-information/10 text-status-information",
    label: "P4",
  },
} satisfies Record<SeverityVariant, { className: string; label: string }>

type SeverityBadgeProps = {
  variant: SeverityVariant
  className?: string
}

export function SeverityBadge({ variant, className }: SeverityBadgeProps) {
  const style = SEVERITY_STYLES[variant]

  return (
    <span
      className={cn(
        "inline-flex min-h-[1.75rem] items-center rounded-md border px-2 py-0.5 text-label font-semibold",
        style.className,
        className,
      )}
      aria-label={`Allvarlighetsgrad ${style.label}`}
    >
      {style.label}
    </span>
  )
}
