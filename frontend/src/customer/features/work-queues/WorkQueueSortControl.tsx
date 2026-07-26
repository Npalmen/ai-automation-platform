import {
  WORK_QUEUE_SORT_OPTIONS,
  type WorkQueueSortOption,
} from "@/customer/features/work-queues/workQueueConstants"

type WorkQueueSortControlProps = {
  value: WorkQueueSortOption
  onChange: (option: WorkQueueSortOption) => void
}

export function WorkQueueSortControl({
  value,
  onChange,
}: WorkQueueSortControlProps) {
  const selectedId =
    WORK_QUEUE_SORT_OPTIONS.find(
      (option) => option.sort === value.sort && option.order === value.order,
    )?.id ?? WORK_QUEUE_SORT_OPTIONS[0].id

  return (
    <div className="min-w-0">
      <label
        htmlFor="work-queue-sort"
        className="mb-1 block text-body-small font-medium text-text-primary"
      >
        Sortering
      </label>
      <select
        id="work-queue-sort"
        className="min-h-11 w-full min-w-[10rem] rounded-md border border-border bg-surface px-3 text-body text-text-primary"
        value={selectedId}
        onChange={(event) => {
          const option = WORK_QUEUE_SORT_OPTIONS.find(
            (item) => item.id === event.target.value,
          )
          if (option) onChange(option)
        }}
      >
        {WORK_QUEUE_SORT_OPTIONS.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
