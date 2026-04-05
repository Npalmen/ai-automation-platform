from collections.abc import Callable

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.classification_processor import process_classification_job
from app.workflows.processors.customer_inquiry_processor import process_customer_inquiry_job
from app.workflows.processors.decisioning_processor import process_decisioning_job
from app.workflows.processors.entity_extraction_processor import process_entity_extraction_job
from app.workflows.processors.human_handoff_processor import process_human_handoff_job
from app.workflows.processors.intake_processor import process_universal_intake_job
from app.workflows.processors.invoice_processor import process_invoice_job
from app.workflows.processors.lead_processor import process_lead_job
from app.workflows.processors.policy_processor import process_policy_job
from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job

Processor = Callable[[Job], Job]


PROCESSOR_REGISTRY: dict[JobType, Processor] = {
    JobType.INTAKE: process_universal_intake_job,
    JobType.CLASSIFICATION: process_classification_job,
    JobType.ENTITY_EXTRACTION: process_entity_extraction_job,
    JobType.DECISIONING: process_decisioning_job,
    JobType.INVOICE: process_invoice_job,
    JobType.LEAD: process_lead_job,
    JobType.CUSTOMER_INQUIRY: process_customer_inquiry_job,
    JobType.POLICY: process_policy_job,
    JobType.HUMAN_HANDOFF: process_human_handoff_job,
    JobType.ACTION_DISPATCH: process_action_dispatch_job,
}