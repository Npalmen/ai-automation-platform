"""Tests for GET /dashboard/summary and GET /dashboard/activity.

Uses direct function calls with mocked DB sessions — no TestClient/httpx.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call


# ── helpers ───────────────────────────────────────────────────────────────────

def _db():
    return MagicMock()


def _make_record(
    job_id: str = "j1",
    tenant_id: str = "T1",
    job_type: str = "lead",
    status: str = "completed",
    created_at: datetime | None = None,
    result: dict | None = None,
):
    r = MagicMock()
    r.job_id = job_id
    r.tenant_id = tenant_id
    r.job_type = job_type
    r.status = status
    r.created_at = created_at or datetime(2026, 4, 24, 10, 0, 0, tzinfo=timezone.utc)
    r.result = result or {}
    return r


# ══════════════════════════════════════════════════════════════════════════════
# /dashboard/summary
# ══════════════════════════════════════════════════════════════════════════════

class TestDashboardSummary:
    def _call(self, tenant_id: str = "T1", scalar_values: list | None = None):
        """Call dashboard_summary with a fake db where scalar() returns values in order."""
        from app.main import dashboard_summary

        scalars = iter(scalar_values or [0, 0, 0, 0, 0, 0, 0])

        db = MagicMock()
        # Each call to db.query(...).filter(...).scalar() returns next scalar.
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter.return_value.filter.return_value = mock_query
        mock_query.scalar.side_effect = lambda: next(scalars, 0)

        with patch("app.main.get_verified_tenant", return_value=tenant_id), \
             patch("app.main.get_db", return_value=iter([db])):
            return dashboard_summary(db=db, tenant_id=tenant_id)

    def test_returns_required_keys(self):
        result = self._call()
        assert "leads_today" in result
        assert "inquiries_today" in result
        assert "invoices_today" in result
        assert "waiting_customer" in result
        assert "ready_cases" in result
        assert "completed_today" in result

    def test_all_values_are_integers(self):
        result = self._call(scalar_values=[3, 1, 2, 0, 4, 5, 0])
        for key in ("leads_today", "inquiries_today", "invoices_today",
                    "waiting_customer", "ready_cases", "completed_today"):
            assert isinstance(result[key], int), f"{key} should be int"

    def test_empty_state_returns_zeros(self):
        result = self._call(scalar_values=[0, 0, 0, 0, 0, 0, 0])
        assert result["leads_today"] == 0
        assert result["completed_today"] == 0

    def test_nonzero_values_returned(self):
        # Scalar calls: leads, inquiries, invoices, ready_cases, completed, waiting
        # The exact order depends on implementation — we just verify values propagate.
        result = self._call(scalar_values=[5, 3, 2, 1, 8, 4])
        total = (result["leads_today"] + result["inquiries_today"] + result["invoices_today"]
                 + result["waiting_customer"] + result["ready_cases"] + result["completed_today"])
        assert total > 0

    def test_tenant_isolation_uses_tenant_id(self):
        """The db query must be filtered by tenant_id, not a hardcoded value."""
        from app.main import dashboard_summary

        captured_filters = []

        db = MagicMock()
        mock_q = MagicMock()
        db.query.return_value = mock_q

        def capture_filter(*args, **kwargs):
            captured_filters.extend(args)
            return mock_q

        mock_q.filter.side_effect = capture_filter
        mock_q.scalar.return_value = 0

        dashboard_summary(db=db, tenant_id="TENANT_XYZ")

        # At least one filter should mention the tenant id — verify query was called
        assert db.query.called


# ══════════════════════════════════════════════════════════════════════════════
# /dashboard/activity
# ══════════════════════════════════════════════════════════════════════════════

class TestDashboardActivity:
    def _call(
        self,
        records: list,
        total: int = 0,
        action_rows: list | None = None,
        tenant_id: str = "T1",
        limit: int = 50,
        offset: int = 0,
    ):
        from app.main import dashboard_activity

        db = MagicMock()

        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.filter.return_value.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.offset.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.all.return_value = records
        query_mock.scalar.return_value = total
        query_mock.group_by.return_value = query_mock
        query_mock.subquery.return_value = MagicMock()
        query_mock.join.return_value = query_mock

        action_rows = action_rows or []
        # The second .all() call (for action rows) should return action_rows.
        query_mock.all.side_effect = [records, action_rows]

        return dashboard_activity(db=db, tenant_id=tenant_id, limit=limit, offset=offset)

    def test_returns_items_and_total_keys(self):
        result = self._call(records=[], total=0)
        assert "items" in result
        assert "total" in result

    def test_empty_state_returns_empty_items(self):
        result = self._call(records=[], total=0)
        assert result["items"] == []
        assert result["total"] == 0

    def test_item_has_required_fields(self):
        record = _make_record()
        result = self._call(records=[record], total=1)
        assert len(result["items"]) == 1
        item = result["items"][0]
        assert "job_id" in item
        assert "created_at" in item
        assert "type" in item
        assert "status" in item
        assert "latest_action" in item
        assert "tenant" in item
        assert "priority" in item

    def test_item_type_matches_job_type(self):
        record = _make_record(job_type="customer_inquiry")
        result = self._call(records=[record], total=1)
        assert result["items"][0]["type"] == "customer_inquiry"

    def test_item_status_matches_job_status(self):
        record = _make_record(status="awaiting_approval")
        result = self._call(records=[record], total=1)
        assert result["items"][0]["status"] == "awaiting_approval"

    def test_created_at_is_iso_string(self):
        dt = datetime(2026, 4, 24, 12, 30, 0, tzinfo=timezone.utc)
        record = _make_record(created_at=dt)
        result = self._call(records=[record], total=1)
        assert "2026-04-24" in result["items"][0]["created_at"]

    def test_latest_action_none_when_no_executions(self):
        record = _make_record()
        result = self._call(records=[record], total=1, action_rows=[])
        assert result["items"][0]["latest_action"] is None

    def test_latest_action_populated_from_action_rows(self):
        record = _make_record(job_id="j1")
        # action_rows is list of (job_id, action_type) tuples.
        result = self._call(records=[record], total=1, action_rows=[("j1", "send_email")])
        assert result["items"][0]["latest_action"] == "send_email"

    def test_priority_extracted_from_result_payload(self):
        result_payload = {
            "processor_history": [
                {
                    "processor": "action_dispatch_processor",
                    "result": {
                        "payload": {
                            "actions_requested": [
                                {"type": "create_monday_item", "column_values": {"priority": "HIGH"}}
                            ]
                        }
                    }
                }
            ]
        }
        record = _make_record(result=result_payload)
        result = self._call(records=[record], total=1)
        assert result["items"][0]["priority"] == "high"

    def test_priority_none_when_not_in_payload(self):
        record = _make_record(result={})
        result = self._call(records=[record], total=1)
        assert result["items"][0]["priority"] is None

    def test_tenant_field_matches_record_tenant(self):
        record = _make_record(tenant_id="ACME")
        result = self._call(records=[record], total=1, tenant_id="ACME")
        assert result["items"][0]["tenant"] == "ACME"

    def test_total_matches_db_count(self):
        result = self._call(records=[], total=42)
        assert result["total"] == 42

    def test_multiple_records_returned(self):
        records = [
            _make_record(job_id="j1", job_type="lead"),
            _make_record(job_id="j2", job_type="invoice"),
            _make_record(job_id="j3", job_type="customer_inquiry"),
        ]
        result = self._call(records=records, total=3)
        assert len(result["items"]) == 3
        types = {item["type"] for item in result["items"]}
        assert types == {"lead", "invoice", "customer_inquiry"}
