from collections.abc import Callable

from app.domain.workflows.models import Job
from app.domain.workflows.enums import JobType
from app.workflows.processors.invoice_processor import process_invoice_job
from app.workflows.processors.email_processor import process_email_job
from app.workflows.processors.contract_processor import process_contract_job
from app.workflows.processors.classification_processor import process_classification_job
from app.workflows.processors.intake_processor import process_intake_job
from app.workflows.processors.entity_extraction_processor import process_entity_extraction_job

Processor = Callable[[Job], Job]


PROCESSOR_REGISTRY: dict[JobType, Processor] = {
    JobType.INTAKE: process_intake_job,
    JobType.INVOICE: process_invoice_job,
    JobType.EMAIL: process_email_job,
    JobType.CONTRACT: process_contract_job,
    JobType.CLASSIFICATION: process_classification_job,
    JobType.ENTITY_EXTRACTION: process_entity_extraction_job,
}