import { RouterProvider } from "react-router-dom"

import { customerRouter } from "@/customer/routes/router"

export function CustomerApp() {
  return <RouterProvider router={customerRouter} />
}
