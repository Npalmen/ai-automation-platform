from dataclasses import dataclass

from app.domain.workflows.enums import JobType


@dataclass(frozen=True)
class WorkflowDefinition:
    base_steps: tuple[JobType, ...]
    post_classification_steps: dict[JobType, tuple[JobType, ...]]


DEFAULT_WORKFLOW = WorkflowDefinition(
    base_steps=(
        JobType.INTAKE,
        JobType.CLASSIFICATION,
    ),
    post_classification_steps={
        JobType.INVOICE: (
            JobType.ENTITY_EXTRACTION,
            JobType.INVOICE,
            JobType.POLICY,
            JobType.HUMAN_HANDOFF,
        ),
        JobType.LEAD: (
            JobType.ENTITY_EXTRACTION,
            JobType.LEAD,
            JobType.POLICY,
            JobType.HUMAN_HANDOFF,
        ),
        JobType.CUSTOMER_INQUIRY: (
            JobType.ENTITY_EXTRACTION,
            JobType.CUSTOMER_INQUIRY,
            JobType.POLICY,
            JobType.HUMAN_HANDOFF,
        ),
        JobType.UNKNOWN: (
            JobType.POLICY,
            JobType.HUMAN_HANDOFF,
        ),
    },
)


def get_base_steps() -> tuple[JobType, ...]:
    return DEFAULT_WORKFLOW.base_steps


def get_post_classification_steps(job_type: JobType) -> tuple[JobType, ...]:
    return DEFAULT_WORKFLOW.post_classification_steps.get(
        job_type,
        DEFAULT_WORKFLOW.post_classification_steps[JobType.UNKNOWN],
    )