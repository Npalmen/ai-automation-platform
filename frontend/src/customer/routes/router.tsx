import { createBrowserRouter, Navigate } from "react-router-dom"

import { ForbiddenPage } from "@/customer/auth/ForbiddenPage"
import { PreviewLoginPage } from "@/customer/auth/PreviewLoginPage"
import { ActivityPage } from "@/customer/features/activity/ActivityPage"
import { ApprovalsPage } from "@/customer/features/approvals/ApprovalsPage"
import { LeadsPage } from "@/customer/features/leads/LeadsPage"
import { NeedsHelpPage } from "@/customer/features/needs-help/NeedsHelpPage"
import { OverviewPage } from "@/customer/features/overview/OverviewPage"
import { SearchPage } from "@/customer/features/search/SearchPage"
import { SupportPage } from "@/customer/features/support/SupportPage"
import { WorkDetailPage } from "@/customer/features/work-detail/WorkDetailPage"
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
          element: <ActivityPage />,
        },
        {
          path: "search",
          element: <SearchPage />,
        },
        {
          path: "work/:workItemId",
          element: <WorkDetailPage />,
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
