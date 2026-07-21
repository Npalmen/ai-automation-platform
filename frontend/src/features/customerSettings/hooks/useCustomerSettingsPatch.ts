import { useMutation, useQueryClient } from "@tanstack/react-query"

import { ApiError } from "@/api/client"

import { patchCustomerSettingsDomain } from "../api"
import { CUSTOMER_SETTINGS_QUERY_KEY } from "./useCustomerSettingsQuery"
import type { ConflictState, CustomerSettingsPatchRequest } from "../types"

type PatchArgs = {
  tenantId: string
  domain: string
  body: CustomerSettingsPatchRequest
}

type PatchResult = {
  response: Awaited<ReturnType<typeof patchCustomerSettingsDomain>>
  conflict: ConflictState | null
}

export function useCustomerSettingsPatch() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ tenantId: id, domain, body }: PatchArgs): Promise<PatchResult> => {
      try {
        const response = await patchCustomerSettingsDomain(id, domain, body)
        return { response, conflict: null }
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          const detail = error.body as { config_version?: number; message?: string }
          return {
            response: null as never,
            conflict: {
              serverConfigVersion: Number(detail?.config_version ?? body.expected_config_version),
              message:
                typeof detail?.message === "string"
                  ? detail.message
                  : "Konfigurationen har ändrats av någon annan.",
            },
          }
        }
        throw error
      }
    },
    onSuccess: (result, variables) => {
      if (result.conflict) return
      queryClient.setQueryData(
        [...CUSTOMER_SETTINGS_QUERY_KEY, variables.tenantId],
        (current: unknown) => {
          if (!current || typeof current !== "object") return current
          const aggregate = current as Record<string, unknown>
          const domains = { ...(aggregate.domains as Record<string, unknown>) }
          domains[variables.domain] = result.response.payload
          return {
            ...aggregate,
            config_version: result.response.config_version,
            domains,
          }
        },
      )
      void queryClient.invalidateQueries({
        queryKey: [...CUSTOMER_SETTINGS_QUERY_KEY, variables.tenantId],
      })
    },
  })
}
