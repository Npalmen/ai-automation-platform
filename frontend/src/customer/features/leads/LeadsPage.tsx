import { WorkItemsQueuePage } from "@/customer/features/work-queues/WorkItemsQueuePage"

const LEADS_CONFIG = {
  title: "Leads",
  description:
    "Inkommande affärsmöjligheter som systemet har samlat och prioriterat åt er.",
  itemType: "lead" as const,
  emptyTitle: "Inga leads matchar ditt val.",
  emptyDescription:
    "Nya leads visas här när de kommer in. Just nu finns inget som matchar dina filter.",
}

export function LeadsPage() {
  return <WorkItemsQueuePage config={LEADS_CONFIG} />
}
