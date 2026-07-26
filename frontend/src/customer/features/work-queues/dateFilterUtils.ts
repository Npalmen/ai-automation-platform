const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/

export function parseDateOnly(value: string | undefined): Date | null {
  if (!value) return null
  const match = DATE_ONLY_PATTERN.exec(value.trim())
  if (!match) return null

  const year = Number(match[1])
  const month = Number(match[2]) - 1
  const day = Number(match[3])
  const date = new Date(year, month, day)

  if (
    date.getFullYear() !== year
    || date.getMonth() !== month
    || date.getDate() !== day
  ) {
    return null
  }

  return date
}

export function toDateOnlyString(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

export function getCreatedDateOnly(createdAt: string): Date | null {
  const parsed = new Date(createdAt)
  if (Number.isNaN(parsed.getTime())) return null
  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate())
}

export function isDateRangeInvalid(from?: string, to?: string): boolean {
  const fromDate = parseDateOnly(from)
  const toDate = parseDateOnly(to)
  if (!fromDate || !toDate) return false
  return fromDate.getTime() > toDate.getTime()
}

export function matchesCreatedDateRange(
  createdAt: string,
  from?: string,
  to?: string,
): boolean {
  const createdDate = getCreatedDateOnly(createdAt)
  if (!createdDate) return false

  const fromDate = parseDateOnly(from)
  const toDate = parseDateOnly(to)

  if (fromDate && createdDate.getTime() < fromDate.getTime()) {
    return false
  }

  if (toDate && createdDate.getTime() > toDate.getTime()) {
    return false
  }

  return true
}
