import type {
  CustomerAuthState,
  FeatureFlags,
  WorkspaceContext,
  WorkspaceMode,
} from "@/customer/types/workspace"

export type WorkspaceDataSource = {
  getContext(): Promise<WorkspaceContext>
  getOverview(): Promise<Record<string, unknown>>
  getWorkItems(): Promise<{ items: unknown[]; total: number }>
  getWorkItemDetail(workItemId: string): Promise<Record<string, unknown> | null>
  getApprovals(): Promise<{ items: unknown[]; total: number }>
  getActivity(): Promise<{ items: unknown[]; total: number }>
  getHealth(): Promise<Record<string, unknown>>
}

export type { CustomerAuthState, FeatureFlags, WorkspaceContext, WorkspaceMode }
