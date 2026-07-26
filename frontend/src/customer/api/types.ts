import type { ApprovalListParams, ApprovalListResponse } from "@/customer/types/approvals"
import type { WorkspaceOverview } from "@/customer/types/overview"
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
  getWorkItemDetail(workItemId: string): Promise<Record<string, unknown> | null>
  getActivity(): Promise<{ items: unknown[]; total: number }>
  getHealth(): Promise<Record<string, unknown>>
}

export type { CustomerAuthState, FeatureFlags, WorkspaceContext, WorkspaceMode }
