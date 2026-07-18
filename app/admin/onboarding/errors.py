from __future__ import annotations


class OnboardingError(Exception):
    """Base onboarding error."""


class OnboardingNotFoundError(OnboardingError):
    pass


class OnboardingConflictError(OnboardingError):
    def __init__(self, message: str, *, code: str = "conflict", session_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.session_id = session_id


class OnboardingValidationError(OnboardingError):
    pass


class OnboardingVersionConflictError(OnboardingConflictError):
    def __init__(self):
        super().__init__("Session version conflict.", code="version_conflict")


class OnboardingStaleReadinessError(OnboardingConflictError):
    def __init__(self):
        super().__init__(
            "Readiness snapshot is stale. Re-run readiness before activating.",
            code="stale_readiness",
        )


class OnboardingStaleActivationPlanError(OnboardingConflictError):
    def __init__(self):
        super().__init__(
            "Activation plan is stale. Reload the activation plan before activating.",
            code="stale_activation_plan",
        )


class OnboardingAuditError(OnboardingError):
    pass


class OnboardingResourceConflictError(OnboardingConflictError):
    def __init__(self, message: str):
        super().__init__(message, code="resource_already_bound")
