import { WorkItemsQueuePage } from "@/customer/features/work-queues/WorkItemsQueuePage"

const SUPPORT_CONFIG = {
  title: "Kundfrågor",
  description:
    "Frågor och supportärenden från era kunder — med tydlig status och senaste händelse.",
  itemType: "support" as const,
  emptyTitle: "Inga kundfrågor matchar ditt val.",
  emptyDescription:
    "Nya kundfrågor visas här när de behöver hanteras. Just nu finns inget som matchar dina filter.",
}

export function SupportPage() {
  return <WorkItemsQueuePage config={SUPPORT_CONFIG} />
}
