import type { CustomerStatus } from "@/customer/types/overview"
import {
  WORK_QUEUE_STATUS_FILTERS,
  type StatusFilterOption,
} from "@/customer/features/work-queues/workQueueConstants"

type WorkQueueStatusFilterProps = {
  value: CustomerStatus | "all"
  onChange: (value: CustomerStatus | "all") => void
  options?: StatusFilterOption[]
}

export function WorkQueueStatusFilter({
  value,
  onChange,
  options = WORK_QUEUE_STATUS_FILTERS,
}: WorkQueueStatusFilterProps) {
  return (
    <div className="min-w-0">
      <label
        htmlFor="work-queue-status-filter"
        className="mb-1 block text-body-small font-medium text-text-primary"
      >
        Status
      </label>
      <select
        id="work-queue-status-filter"
        className="min-h-11 w-full min-w-[10rem] rounded-md border border-border bg-surface px-3 text-body text-text-primary"
        value={value}
        onChange={(event) =>
          onChange(event.target.value as CustomerStatus | "all")}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
