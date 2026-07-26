import { createBrowserRouter, Navigate } from "react-router-dom"

import { ForbiddenPage } from "@/customer/auth/ForbiddenPage"
import { PreviewLoginPage } from "@/customer/auth/PreviewLoginPage"
import { RoutePlaceholder } from "@/customer/components/RoutePlaceholder"
import { ApprovalsPage } from "@/customer/features/approvals/ApprovalsPage"
import { LeadsPage } from "@/customer/features/leads/LeadsPage"
import { NeedsHelpPage } from "@/customer/features/needs-help/NeedsHelpPage"
import { OverviewPage } from "@/customer/features/overview/OverviewPage"
import { SupportPage } from "@/customer/features/support/SupportPage"
import { CustomerAppShell } from "@/customer/layouts/CustomerAppShell"
import { NotFoundPage } from "@/customer/pages/NotFoundPage"

export const customerRouter = createBrowserRouter(
  [
    {
      path: "/login",
      element: <PreviewLoginPage />,
    },
    {
      path: "/forbidden",
      element: <ForbiddenPage />,
    },
    {
      element: <CustomerAppShell />,
      children: [
        {
          index: true,
          element: <OverviewPage />,
        },
        {
          path: "leads",
          element: <LeadsPage />,
        },
        {
          path: "support",
          element: <SupportPage />,
        },
        {
          path: "approvals",
          element: <ApprovalsPage />,
        },
        {
          path: "needs-help",
          element: <NeedsHelpPage />,
        },
        {
          path: "activity",
          element: (
            <RoutePlaceholder
              title="Aktivitet"
              description="Historik över vad systemet har gjort åt er."
            />
          ),
        },
        {
          path: "search",
          element: (
            <RoutePlaceholder
              title="Sökning"
              description="Sök bland leads, kundfrågor och andra arbetsobjekt."
            />
          ),
        },
        {
          path: "work/:workItemId",
          element: (
            <RoutePlaceholder
              title="Arbetsobjekt"
              description="Detaljvy för ett enskilt ärende."
            />
          ),
        },
        {
          path: "403-test",
          element: <Navigate to="/forbidden" replace />,
        },
        {
          path: "*",
          element: <NotFoundPage />,
        },
      ],
    },
  ],
  { basename: "/app" },
)
