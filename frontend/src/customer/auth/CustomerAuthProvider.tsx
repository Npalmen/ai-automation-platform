import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from "react"

import { mockDataSource } from "@/customer/api/mockDataSource"
import type {
  CustomerAuthState,
  WorkspaceDataSource,
} from "@/customer/api/types"
import { DEFAULT_FEATURE_FLAGS } from "@/customer/types/workspace"

type CustomerAuthContextValue = {
  auth: CustomerAuthState
  dataSource: WorkspaceDataSource
}

const CustomerAuthContext = createContext<CustomerAuthContextValue | null>(null)

const PREVIEW_AUTH: CustomerAuthState = {
  role: "customer_viewer",
  mode: "preview",
  connected: false,
  context: {
    tenant_id: "MOCK_TENANT_001",
    company_name: "Exempel El & Service AB",
    contact_name: "Anna Svensson",
    contact_email: "anna@exempel-el.se",
    support_email: "support@exempel-el.se",
    language: "sv",
    region: "SE",
    workspace_mode: "preview",
    feature_flags: DEFAULT_FEATURE_FLAGS,
  },
}

type CustomerAuthProviderProps = {
  children: ReactNode
}

export function CustomerAuthProvider({ children }: CustomerAuthProviderProps) {
  const value = useMemo<CustomerAuthContextValue>(
    () => ({
      auth: PREVIEW_AUTH,
      dataSource: mockDataSource,
    }),
    [],
  )

  return (
    <CustomerAuthContext.Provider value={value}>
      {children}
    </CustomerAuthContext.Provider>
  )
}

export function useCustomerAuth(): CustomerAuthContextValue {
  const context = useContext(CustomerAuthContext)
  if (!context) {
    throw new Error("useCustomerAuth must be used within CustomerAuthProvider")
  }
  return context
}

export function useFeatureFlags() {
  return useCustomerAuth().auth.context.feature_flags
}
