import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import { CustomerApp } from "@/customer/app/App"
import { CustomerAuthProvider } from "@/customer/auth/CustomerAuthProvider"
import { CustomerErrorBoundary } from "@/customer/components/CustomerErrorBoundary"
import "@/styles/globals.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <CustomerErrorBoundary>
      <CustomerAuthProvider>
        <CustomerApp />
      </CustomerAuthProvider>
    </CustomerErrorBoundary>
  </StrictMode>,
)
