import {
  cloneOverview,
  createOverviewFixture,
  type OverviewMockScenario,
} from "@/customer/features/overview/overviewFixtures"
import { DEFAULT_FEATURE_FLAGS } from "@/customer/types/workspace"

import type { WorkspaceDataSource } from "./types"

const MOCK_CONTEXT = {
  tenant_id: "MOCK_TENANT_001",
  company_name: "Exempel El & Service AB",
  contact_name: "Anna Svensson",
  contact_email: "anna@exempel-el.se",
  support_email: "support@exempel-el.se",
  language: "sv",
  region: "SE",
  workspace_mode: "preview" as const,
  feature_flags: DEFAULT_FEATURE_FLAGS,
}

export function createMockDataSource(
  overviewScenario: OverviewMockScenario = "populated",
): WorkspaceDataSource {
  return {
    async getContext() {
      return MOCK_CONTEXT
    },

    async getOverview() {
      const result = createOverviewFixture(overviewScenario)
      if (result === "full_error") {
        throw new Error("Kunde inte hämta översikten i förhandsläget")
      }
      if (result === "loading") {
        return new Promise(() => {})
      }
      return cloneOverview(result)
    },

    async getWorkItems() {
      return { items: [], total: 0 }
    },

    async getWorkItemDetail() {
      return null
    },

    async getApprovals() {
      return { items: [], total: 0 }
    },

    async getActivity() {
      return { items: [], total: 0 }
    },

    async getHealth() {
      return {
        overall_status: "preview",
        message: "Förhandsvisning — inga riktiga kopplingar",
        systems: {},
      }
    },
  }
}

export const mockDataSource = createMockDataSource("populated")
