import { Outlet } from "react-router-dom"
import { createBrowserRouter } from "react-router-dom"

import { AppShell } from "@/components/operator/AppShell"
import { AuthProvider } from "@/features/auth/AuthProvider"
import { LoginPage } from "@/features/auth/LoginPage"
import { RequireAuth } from "@/features/auth/RequireAuth"
import { RequireRole } from "@/features/auth/RequireRole"
import { DesignReferencePage } from "@/pages/DesignReferencePage"
import { FoundationPage } from "@/pages/FoundationPage"
import { NotFoundPage } from "@/pages/NotFoundPage"
import { CustomerDetailPage } from "@/features/customers/CustomerDetailPage"
import { CustomersListPage } from "@/features/customers/CustomersListPage"
import { NeedsHelpDetailPage } from "@/features/needsHelp/NeedsHelpDetailPage"
import { NeedsHelpQueuePage } from "@/features/needsHelp/NeedsHelpQueuePage"
import { IncidentDetailPage } from "@/features/incidents/IncidentDetailPage"
import { IncidentsPage } from "@/features/incidents/IncidentsPage"
import { AlertDetailPage } from "@/features/alerts/AlertDetailPage"
import { AlertsPage } from "@/features/alerts/AlertsPage"
import { OperatorDigestsPage } from "@/features/alerts/OperatorDigestsPage"
import { UsagePage } from "@/features/usage/UsagePage"
import { SystemPage } from "@/features/systemStatus/SystemPage"
import { OverviewPage } from "@/features/overview/OverviewPage"

function AppRoot() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  )
}

function ProtectedShell() {
  return (
    <RequireAuth>
      <AppShell />
    </RequireAuth>
  )
}

export const router = createBrowserRouter(
  [
    {
      element: <AppRoot />,
      children: [
        {
          path: "login",
          element: <LoginPage />,
        },
        {
          element: <ProtectedShell />,
          children: [
            {
              index: true,
              element: <OverviewPage />,
            },
            {
              path: "needs-help",
              children: [
                { index: true, element: <NeedsHelpQueuePage /> },
                { path: ":itemId", element: <NeedsHelpDetailPage /> },
              ],
            },
            {
              path: "customers",
              children: [
                { index: true, element: <CustomersListPage /> },
                { path: ":tenantId", element: <CustomerDetailPage /> },
              ],
            },
            {
              path: "incidents",
              children: [
                { index: true, element: <IncidentsPage /> },
                { path: ":incidentId", element: <IncidentDetailPage /> },
              ],
            },
            {
              path: "alerts",
              children: [
                { index: true, element: <AlertsPage /> },
                { path: ":alertId", element: <AlertDetailPage /> },
              ],
            },
            {
              path: "digests",
              element: <OperatorDigestsPage />,
            },
            {
              path: "usage",
              element: <UsagePage />,
            },
            {
              path: "system",
              element: (
                <RequireRole allowedRoles={["operations", "admin"]}>
                  <SystemPage />
                </RequireRole>
              ),
            },
            {
              path: "foundation",
              element: (
                <RequireRole allowedRoles={["admin"]}>
                  <FoundationPage />
                </RequireRole>
              ),
            },
            {
              path: "design-reference",
              element: (
                <RequireRole allowedRoles={["admin"]}>
                  <DesignReferencePage />
                </RequireRole>
              ),
            },
            {
              path: "*",
              element: <NotFoundPage />,
            },
          ],
        },
      ],
    },
  ],
  {
    basename: "/ops",
  },
)
