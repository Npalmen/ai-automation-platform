import type { PartialError } from "@/customer/types/overview"

export type ListResponse<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
  partial_errors: PartialError[]
}
