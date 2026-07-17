import { Outlet } from "react-router-dom"

export function FoundationLayout() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-1 px-4 py-4 sm:px-6">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Frontend foundation — intern, inte klar operatörspanel
          </p>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}
