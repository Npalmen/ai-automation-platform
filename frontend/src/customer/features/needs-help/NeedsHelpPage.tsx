import { WorkItemsQueuePage } from "@/customer/features/work-queues/WorkItemsQueuePage"

const NEEDS_HELP_CONFIG = {
  title: "Behöver hjälp",
  description:
    "Ärenden där systemet har stoppat hellre än att agera osäkert. Kontrollera uppgifterna innan ärendet hanteras vidare.",
  itemType: "needs_help" as const,
  emptyTitle: "Inget behöver mänsklig hjälp just nu.",
  emptyDescription:
    "När systemet behöver er hjälp visas ärendena här. Just nu finns inget som matchar dina filter.",
}

export function NeedsHelpPage() {
  return <WorkItemsQueuePage config={NEEDS_HELP_CONFIG} />
}
