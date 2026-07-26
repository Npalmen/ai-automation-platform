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

export const mockDataSource: WorkspaceDataSource = {
  async getContext() {
    return MOCK_CONTEXT
  },

  async getOverview() {
    return {
      last_updated_at: new Date().toISOString(),
      summary: {
        cases_handled_today: 0,
        waiting_for_decision: 0,
        waiting_for_customer: 0,
        needs_help: 0,
        failed_today: 0,
      },
      priority_work_items: [],
      partial_errors: [],
    }
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
