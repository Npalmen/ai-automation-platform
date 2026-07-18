import type { EffectiveRouteRow, RoutingPreviewRow } from "./types"

export function hasUnsavedRoutingDraft(
  saved: Record<string, string | null> | undefined,
  local: Record<string, string | null>,
): boolean {
  const savedDraft = saved ?? {}
  const savedKeys = new Set(Object.keys(savedDraft))
  const localKeys = new Set(Object.keys(local))
  if (savedKeys.size !== localKeys.size) return true
  for (const key of localKeys) {
    if ((savedDraft[key] ?? null) !== (local[key] ?? null)) return true
  }
  return false
}

export type RoutingPreviewDisplayRow = RoutingPreviewRow & {
  platform_default: string | null
  tenant_override: string | null
  uses_fallback: boolean
}

export function mergeRoutingPreviewRows(
  preview: RoutingPreviewRow[],
  effectiveRoutes: EffectiveRouteRow[] | undefined,
): RoutingPreviewDisplayRow[] {
  const byType = new Map((effectiveRoutes ?? []).map((row) => [row.service_type, row]))
  return preview.map((row) => {
    const effective = byType.get(row.service_type)
    return {
      ...row,
      platform_default: effective?.platform_default ?? null,
      tenant_override: effective?.override ?? null,
      uses_fallback: row.source === "fallback_manual_review",
    }
  })
}

export function routingSourceLabel(source: string): string {
  if (source === "platform_default") return "Plattformsstandard"
  if (source === "tenant_override") return "Tenant-override"
  if (source === "fallback_manual_review") return "Fallback (manual review)"
  return source
}
