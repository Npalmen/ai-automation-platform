import { createBrowserRouter, Navigate } from "react-router-dom"

import { ForbiddenPage } from "@/customer/auth/ForbiddenPage"
import { PreviewLoginPage } from "@/customer/auth/PreviewLoginPage"
import { RoutePlaceholder } from "@/customer/components/RoutePlaceholder"
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
          element: (
            <RoutePlaceholder
              title="Översikt"
              description="Din dagliga överblick över vad som hänt och vad som behöver uppmärksamhet."
            />
          ),
        },
        {
          path: "leads",
          element: (
            <RoutePlaceholder
              title="Leads"
              description="Inkommande förfrågningar och prioriterade affärsmöjligheter."
            />
          ),
        },
        {
          path: "support",
          element: (
            <RoutePlaceholder
              title="Kundfrågor"
              description="Supportärenden och frågor från era kunder."
            />
          ),
        },
        {
          path: "approvals",
          element: (
            <RoutePlaceholder
              title="Godkännanden"
              description="Beslut som väntar på dig — visas read-only i förhandsläget."
            />
          ),
        },
        {
          path: "needs-help",
          element: (
            <RoutePlaceholder
              title="Behöver hjälp"
              description="Ärenden där en människa behöver ta över."
            />
          ),
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
