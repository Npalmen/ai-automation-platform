"""Evaluation harness errors and exit codes."""


class HarnessError(Exception):
    """Infrastructure or contract error in the harness itself."""


class ScenarioValidationError(HarnessError):
    pass


class FixtureAIError(HarnessError):
    pass


class SafetyViolation(Exception):
    """Absolute safety gate failure."""

    def __init__(self, gate_id: str, message: str):
        self.gate_id = gate_id
        super().__init__(f"[{gate_id}] {message}")


class QualityFailure(Exception):
    """Quality metric gate failure."""

    def __init__(self, metric: str, message: str):
        self.metric = metric
        super().__init__(f"[{metric}] {message}")


class BaselineRegression(Exception):
    """Regression vs approved baseline."""

    def __init__(self, details: list[str]):
        self.details = details
        super().__init__("; ".join(details))


# Exit codes
EXIT_PASS = 0
EXIT_FAIL_SAFETY = 1
EXIT_FAIL_QUALITY = 2
EXIT_FAIL_HARNESS = 3
EXIT_FAIL_READINESS = 10
EXIT_BASELINE_REGRESSION = 21
