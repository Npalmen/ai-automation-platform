from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_APPROVAL = "awaiting_approval"
    MANUAL_REVIEW = "manual_review"
    COMPLETED = "completed"
    FAILED = "failed"