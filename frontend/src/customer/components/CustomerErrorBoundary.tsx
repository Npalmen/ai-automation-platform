import { Component, type ErrorInfo, type ReactNode } from "react"

import { ErrorState } from "@/components/shared/ErrorState"

type CustomerErrorBoundaryProps = {
  children: ReactNode
}

type CustomerErrorBoundaryState = {
  hasError: boolean
}

export class CustomerErrorBoundary extends Component<
  CustomerErrorBoundaryProps,
  CustomerErrorBoundaryState
> {
  state: CustomerErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): CustomerErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Customer workspace error:", error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen items-center justify-center p-6">
          <ErrorState
            title="Något gick fel"
            description="Arbetsytan kunde inte visas. Ladda om sidan och försök igen."
          />
        </div>
      )
    }

    return this.props.children
  }
}
