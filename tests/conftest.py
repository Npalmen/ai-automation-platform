"""Shared pytest fixtures."""

import os

import pytest

from app.core.rate_limit import reset_rate_limits_for_tests


def _running_monday_live_tier(config: pytest.Config) -> bool:
    markexpr = (getattr(config.option, "markexpr", None) or "").replace(" ", "")
    if markexpr == "monday_live":
        return True
    return os.environ.get("RUN_MONDAY_LIVE_TESTS", "").strip().lower() == "yes"


def pytest_configure(config: pytest.Config) -> None:
    if _running_monday_live_tier(config) and not os.environ.get("MONDAY_API_KEY", "").strip():
        raise pytest.UsageError(
            "monday_live tier requires MONDAY_API_KEY (set RUN_MONDAY_LIVE_TESTS=yes for explicit opt-in)"
        )


@pytest.fixture(autouse=True)
def _reset_rate_limits_between_tests():
    """Prevent cross-test flakiness from K11 in-memory login rate limits."""
    reset_rate_limits_for_tests()
    yield
    reset_rate_limits_for_tests()


@pytest.fixture
def lifespan_client():
    """FastAPI TestClient that runs app startup/shutdown (schema provisioning)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client
