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
          <div className="max-w-lg">
            <ErrorState
              title="Något gick fel"
              description="Arbetsytan kunde inte visas. Ladda om sidan och försök igen."
            />
            <button
              type="button"
              className="mt-4 inline-flex min-h-11 items-center rounded-md border border-border bg-surface px-4 text-body font-medium text-text-primary hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              onClick={() => window.location.reload()}
            >
              Ladda om sidan
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
