"""Decision trace errors."""

from __future__ import annotations


class DecisionTraceError(Exception):
    """Base class for decision trace failures."""


class ExternalWriteBlocked(DecisionTraceError):
    """External write blocked due to missing or invalid trace."""


class OperationConflict(DecisionTraceError):
    """Action payload conflicts with an existing operation fingerprint binding."""


class ReconciliationRequired(DecisionTraceError):
    """External execution outcome unknown — manual reconciliation required."""
