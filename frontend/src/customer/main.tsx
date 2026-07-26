import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { QueryClientProvider } from "@tanstack/react-query"

import { CustomerApp } from "@/customer/app/App"
import { customerQueryClient } from "@/customer/app/queryClient"
import { CustomerAuthProvider } from "@/customer/auth/CustomerAuthProvider"
import { CustomerErrorBoundary } from "@/customer/components/CustomerErrorBoundary"
import "@/styles/globals.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <CustomerErrorBoundary>
      <QueryClientProvider client={customerQueryClient}>
        <CustomerAuthProvider>
          <CustomerApp />
        </CustomerAuthProvider>
      </QueryClientProvider>
    </CustomerErrorBoundary>
  </StrictMode>,
)
