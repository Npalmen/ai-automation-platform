import type { AiCostBlock, AiUsageBlock, NotMeasuredValue, UsageDays } from "./types"

export function periodLabel(days: UsageDays): string {
  if (days === 7) return "Senaste 7 dagarna"
  if (days === 90) return "Senaste 90 dagarna"
  return "Senaste 30 dagarna"
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString("sv-SE", {
    dateStyle: "medium",
    timeStyle: "short",
  })
}

export function formatPercentageChange(value: number | null | undefined): string {
  if (value == null) return "—"
  const sign = value > 0 ? "+" : ""
  return `${sign}${value.toFixed(1)} %`
}

export function formatComparisonTrend(
  _current: number,
  previous: number,
  percentageChange: number | null,
): string {
  if (previous === 0) {
    return `Föregående period: ${previous} (ingen procentuell förändring)`
  }
  return `Föregående period: ${previous} (${formatPercentageChange(percentageChange)})`
}

export function formatNotMeasured(block: NotMeasuredValue): string {
  return `Ej mätt — ${block.reason}`
}

export function formatAiUsageStatus(block: AiUsageBlock): string {
  if (block.status === "not_measured") {
    return block.reason ?? "Ej mätt"
  }
  return "Uppmätt"
}

export function formatAiCostStatus(block: AiCostBlock): string {
  if (block.status === "unknown") {
    return block.reason ?? "Okänd kostnad"
  }
  if (block.amount == null) {
    return "Ej mätt"
  }
  const currency = block.currency ?? ""
  return `${block.amount} ${currency}`.trim()
}

/** Short label for tenant table rows — never repeats long data-quality explanations. */
export function formatAiCostTableCell(block: AiCostBlock): string {
  if (block.status === "unknown" || block.amount == null) {
    return "Ej mätt"
  }
  const currency = block.currency ?? ""
  return `${block.amount} ${currency}`.trim()
}

export function formatOperatorBurdenTableCell(
  operatorActions: number,
  openManualReviews: number,
  pendingApprovals: number,
): string {
  return `${operatorActions} åtg · ${openManualReviews} MR · ${pendingApprovals} godk.`
}

export function formatNullableNumber(value: number | null | undefined): string {
  if (value == null) return "—"
  return String(value)
}

export function tenantStatusLabel(status: string): string {
  if (status === "active") return "Aktiv"
  if (status === "inactive") return "Inaktiv"
  return "Okänd"
}

export function attentionStatusLabel(status: string): string {
  if (status === "healthy") return "Frisk"
  if (status === "warning") return "Varning"
  if (status === "failed") return "Fel"
  if (status === "paused") return "Pausad"
  if (status === "critical") return "Kritisk"
  return "Okänd"
}

export function proxyTimestampNote(): string {
  return "Baserat på updated_at (proxy), inte exakt sluttid."
}
