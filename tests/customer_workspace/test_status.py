"""Unit tests for customer status normalization."""

from __future__ import annotations

import pytest

from app.customer_workspace.status import (
    customer_status_label,
    map_internal_status,
    map_job_type_to_work_item_type,
    priority_rank,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("pending", "new"),
        ("processing", "in_progress"),
        ("awaiting_approval", "waiting_for_decision"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
        ("manual_review", "needs_help"),
        ("bogus", "unknown"),
    ],
)
def test_map_internal_status(raw, expected):
    assert map_internal_status(raw) == expected


def test_pending_approval_overrides_status():
    assert map_internal_status("completed", has_pending_approval=True) == "waiting_for_decision"


def test_recommended_status_mapping():
    assert map_internal_status("processing", recommended_status="needs_customer_info") == "waiting_for_customer"


def test_unknown_status_label():
    assert customer_status_label("unknown") == "Okänd status"


@pytest.mark.parametrize(
    "priority,expected",
    [
        ("hot", 1),
        ("low", 4),
        (None, 50),
        ("weird", 50),
    ],
)
def test_priority_rank(priority, expected):
    assert priority_rank(priority) == expected


@pytest.mark.parametrize(
    "job_type,expected",
    [
        ("lead", "lead"),
        ("customer_inquiry", "support"),
        ("invoice", "support"),
    ],
)
def test_map_job_type(job_type, expected):
    assert map_job_type_to_work_item_type(job_type) == expected
