import {
  cloneOverview,
  createOverviewFixture,
  type OverviewMockScenario,
} from "@/customer/features/overview/overviewFixtures"
import {
  cloneActivityItem,
  getActivityItemsForScenario,
  getActivityPartialErrors,
  type ActivityMockScenario,
} from "@/customer/features/activity/activityFixtures"
import { buildActivityListResponse } from "@/customer/features/activity/activityMockLogic"
import {
  buildWorkItemDetail,
  cloneWorkItemDetail,
  EMPTY_TIMELINE_WORK_ITEM_ID,
} from "@/customer/features/work-detail/workDetailFixtures"
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
  activityScenario?: ActivityMockScenario
}

export function createMockDataSource(
  options: MockDataSourceOptions | OverviewMockScenario = "populated",
): WorkspaceDataSource {
  const resolved =
    typeof options === "string"
      ? {
          overviewScenario: options,
          queueScenario: options as QueueMockScenario,
          activityScenario: options as ActivityMockScenario,
        }
      : {
          overviewScenario: options.overviewScenario ?? "populated",
          queueScenario: options.queueScenario ?? "populated",
          activityScenario: options.activityScenario ?? "populated",
        }

  const { overviewScenario, queueScenario, activityScenario } = resolved

  function allWorkItems() {
    const items = getWorkItemsForScenario(queueScenario).map(cloneWorkItem)
    if (queueScenario === "empty_timeline") {
      const emptyItem = items.find(
        (item) => item.work_item_id === EMPTY_TIMELINE_WORK_ITEM_ID,
      )
      if (!emptyItem) {
        items.push({
          work_item_id: EMPTY_TIMELINE_WORK_ITEM_ID,
          type: "needs_help",
          title: "Ärende utan historik ännu",
          customer_name: "Test Kund",
          customer_email: "test@fiktivmail.se",
          customer_status: "new",
          customer_status_label: "Ny",
          priority_rank: 5,
          priority_label: null,
          summary: "Ett ärende utan registrerad historik i förhandsläget.",
          created_at: "2026-07-26T10:00:00+02:00",
          updated_at: "2026-07-26T10:00:00+02:00",
        })
      }
    }
    return items
  }

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

      return buildWorkItemListResponse(
        allWorkItems(),
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

    async getWorkItem(workItemId) {
      if (queueScenario === "full_error") {
        throw new Error("Kunde inte hämta arbetsobjektet i förhandsläget")
      }
      if (queueScenario === "delayed") {
        return new Promise(() => {})
      }
      if (queueScenario === "not_found") {
        return null
      }

      const item = allWorkItems().find(
        (candidate) => candidate.work_item_id === workItemId,
      )
      if (!item) return null

      return cloneWorkItemDetail(buildWorkItemDetail(item))
    },

    async listActivity(params) {
      if (activityScenario === "full_error") {
        throw new Error("Kunde inte hämta aktiviteten i förhandsläget")
      }
      if (activityScenario === "delayed") {
        return new Promise(() => {})
      }

      const items = getActivityItemsForScenario(activityScenario).map(
        cloneActivityItem,
      )
      return buildActivityListResponse(
        items,
        params,
        getActivityPartialErrors(activityScenario),
      )
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
