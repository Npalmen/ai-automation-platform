import { useMutation } from "@tanstack/react-query"

import { previewCustomerSettingsDomain } from "../api"
import type { CustomerSettingsPreviewResponse } from "../types"

type PreviewArgs = {
  tenantId: string
  domain: string
  payload: Record<string, unknown>
}

export function useCustomerSettingsPreview() {
  return useMutation({
    mutationFn: ({ tenantId, domain, payload }: PreviewArgs) =>
      previewCustomerSettingsDomain(tenantId, domain, payload),
  })
}

export type { CustomerSettingsPreviewResponse }
