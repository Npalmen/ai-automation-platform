import { useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"

export function NotFoundPage() {
  const navigate = useNavigate()

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <p className="break-words text-sm text-muted-foreground">
        The requested operator panel route does not exist.
      </p>
      <div>
        <Button
          variant="outline"
          type="button"
          onClick={() => navigate("/")}
        >
          Back to foundation
        </Button>
      </div>
    </div>
  )
}
