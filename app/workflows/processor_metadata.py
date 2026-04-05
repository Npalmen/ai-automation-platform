from app.domain.workflows.enums import JobType

PROCESSOR_METADATA = {
    JobType.INVOICE: {
        "label": "Invoice Intake",
        "description": "Extraherar fakturadata"
    },
    JobType.CLASSIFICATION: {
        "label": "Classification",
        "description": "Klassificerar inkommande ärenden"
    },
    JobType.ENTITY_EXTRACTION: {
        "label": "Entity Extraction",
        "description": "Extraherar strukturerad data"
    },
}