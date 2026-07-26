import type { ApprovalListParams, ApprovalListResponse } from "@/customer/types/approvals"
import type { ActivityListParams, ActivityListResponse } from "@/customer/types/activity"
import type { WorkspaceOverview } from "@/customer/types/overview"
import type { WorkItemDetail } from "@/customer/types/work-item-detail"
import type {
  WorkItemListParams,
  WorkItemListResponse,
} from "@/customer/types/work-items"
import type {
  CustomerAuthState,
  FeatureFlags,
  WorkspaceContext,
  WorkspaceMode,
} from "@/customer/types/workspace"

export type WorkspaceDataSource = {
  getContext(): Promise<WorkspaceContext>
  getOverview(): Promise<WorkspaceOverview>
  listWorkItems(params: WorkItemListParams): Promise<WorkItemListResponse>
  listApprovals(params: ApprovalListParams): Promise<ApprovalListResponse>
  getWorkItem(workItemId: string): Promise<WorkItemDetail | null>
  listActivity(params: ActivityListParams): Promise<ActivityListResponse>
  getHealth(): Promise<Record<string, unknown>>
}

export type { CustomerAuthState, FeatureFlags, WorkspaceContext, WorkspaceMode }
