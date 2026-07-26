import {
  cloneOverview,
  createOverviewFixture,
  type OverviewMockScenario,
} from "@/customer/features/overview/overviewFixtures"
import {
  cloneApproval,
  cloneWorkItem,
  getApprovalsForScenario,
  getQueuePartialErrors,
  getWorkItemsForScenario,
  type QueueMockScenario,
} from "@/customer/features/work-queues/workQueueFixtures"
import {
  buildApprovalListResponse,
  buildWorkItemListResponse,
} from "@/customer/features/work-queues/workQueueMockLogic"
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

export type MockDataSourceOptions = {
  overviewScenario?: OverviewMockScenario
  queueScenario?: QueueMockScenario
}

export function createMockDataSource(
  options: MockDataSourceOptions | OverviewMockScenario = "populated",
): WorkspaceDataSource {
  const resolved =
    typeof options === "string"
      ? { overviewScenario: options, queueScenario: options as QueueMockScenario }
      : {
          overviewScenario: options.overviewScenario ?? "populated",
          queueScenario: options.queueScenario ?? "populated",
        }

  const { overviewScenario, queueScenario } = resolved

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

    async listWorkItems(params) {
      if (queueScenario === "full_error") {
        throw new Error("Kunde inte hämta arbetslistan i förhandsläget")
      }
      if (queueScenario === "delayed") {
        return new Promise(() => {})
      }

      const items = getWorkItemsForScenario(queueScenario).map(cloneWorkItem)
      return buildWorkItemListResponse(
        items,
        params,
        getQueuePartialErrors(queueScenario),
      )
    },

    async listApprovals(params) {
      if (queueScenario === "full_error") {
        throw new Error("Kunde inte hämta godkännanden i förhandsläget")
      }
      if (queueScenario === "delayed") {
        return new Promise(() => {})
      }

      const items = getApprovalsForScenario(queueScenario).map(cloneApproval)
      return buildApprovalListResponse(
        items,
        params,
        getQueuePartialErrors(queueScenario),
      )
    },

    async getWorkItemDetail() {
      return null
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
