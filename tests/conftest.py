"""Shared pytest fixtures."""

import pytest

from app.core.rate_limit import reset_rate_limits_for_tests


@pytest.fixture(autouse=True)
def _reset_rate_limits_between_tests():
    """Prevent cross-test flakiness from K11 in-memory login rate limits."""
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()
