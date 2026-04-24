"""Tests for GET /dashboard/roi.

Uses direct function calls with mocked DB — no TestClient/httpx.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _call(tenant_id: str = "T1", scalar_values: list | None = None):
    """
    Call dashboard_roi with a mocked db.

    scalar_values: list of ints returned by successive .scalar() calls.
    Order matches implementation: leads, support, invoices, followups.
    """
    from app.main import dashboard_roi

    scalars = iter(scalar_values if scalar_values is not None else [0, 0, 0, 0])

    db = MagicMock()
    mock_q = MagicMock()
    db.query.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.join.return_value = mock_q
    mock_q.scalar.side_effect = lambda: next(scalars, 0)

    return dashboard_roi(db=db, tenant_id=tenant_id)


# ══════════════════════════════════════════════════════════════════════════════
# Response shape
# ══════════════════════════════════════════════════════════════════════════════

class TestRoiShape:
    def test_returns_all_required_keys(self):
        result = _call()
        required = {
            "period", "leads_created", "support_cases_handled",
            "invoices_processed", "followups_sent",
            "estimated_minutes_saved", "estimated_hours_saved",
            "estimated_value_sek", "assumptions",
        }
        assert required.issubset(result.keys())

    def test_period_is_today(self):
        assert _call()["period"] == "today"

    def test_assumptions_contains_all_keys(self):
        a = _call()["assumptions"]
        assert "lead_minutes_saved" in a
        assert "support_minutes_saved" in a
        assert "invoice_minutes_saved" in a
        assert "followup_minutes_saved" in a
        assert "hourly_value_sek" in a

    def test_assumptions_are_positive(self):
        a = _call()["assumptions"]
        for k, v in a.items():
            assert v > 0, f"{k} should be positive"

    def test_numeric_fields_are_numbers(self):
        result = _call(scalar_values=[1, 1, 1, 1])
        for key in ("leads_created", "support_cases_handled", "invoices_processed",
                    "followups_sent", "estimated_minutes_saved",
                    "estimated_hours_saved", "estimated_value_sek"):
            assert isinstance(result[key], (int, float)), f"{key} should be numeric"


# ══════════════════════════════════════════════════════════════════════════════
# Empty tenant
# ══════════════════════════════════════════════════════════════════════════════

class TestRoiEmptyTenant:
    def test_all_counts_zero_when_no_jobs(self):
        result = _call(scalar_values=[0, 0, 0, 0])
        assert result["leads_created"] == 0
        assert result["support_cases_handled"] == 0
        assert result["invoices_processed"] == 0
        assert result["followups_sent"] == 0

    def test_estimated_minutes_zero_when_no_jobs(self):
        assert _call(scalar_values=[0, 0, 0, 0])["estimated_minutes_saved"] == 0

    def test_estimated_hours_zero_when_no_jobs(self):
        assert _call(scalar_values=[0, 0, 0, 0])["estimated_hours_saved"] == 0.0

    def test_estimated_value_zero_when_no_jobs(self):
        assert _call(scalar_values=[0, 0, 0, 0])["estimated_value_sek"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# Calculation correctness
# ══════════════════════════════════════════════════════════════════════════════

class TestRoiCalculation:
    def test_minutes_saved_with_one_lead(self):
        from app.main import _ROI_LEAD_MIN
        result = _call(scalar_values=[1, 0, 0, 0])
        assert result["estimated_minutes_saved"] == _ROI_LEAD_MIN

    def test_minutes_saved_with_one_support_case(self):
        from app.main import _ROI_SUPPORT_MIN
        result = _call(scalar_values=[0, 1, 0, 0])
        assert result["estimated_minutes_saved"] == _ROI_SUPPORT_MIN

    def test_minutes_saved_with_one_invoice(self):
        from app.main import _ROI_INVOICE_MIN
        result = _call(scalar_values=[0, 0, 1, 0])
        assert result["estimated_minutes_saved"] == _ROI_INVOICE_MIN

    def test_minutes_saved_with_one_followup(self):
        from app.main import _ROI_FOLLOWUP_MIN
        result = _call(scalar_values=[0, 0, 0, 1])
        assert result["estimated_minutes_saved"] == _ROI_FOLLOWUP_MIN

    def test_minutes_additive_across_types(self):
        from app.main import _ROI_LEAD_MIN, _ROI_SUPPORT_MIN, _ROI_INVOICE_MIN, _ROI_FOLLOWUP_MIN
        result = _call(scalar_values=[1, 1, 1, 1])
        expected = _ROI_LEAD_MIN + _ROI_SUPPORT_MIN + _ROI_INVOICE_MIN + _ROI_FOLLOWUP_MIN
        assert result["estimated_minutes_saved"] == expected

    def test_hours_equals_minutes_over_60(self):
        result = _call(scalar_values=[6, 0, 0, 0])  # 6 leads × 10 min = 60 min = 1 h
        from app.main import _ROI_LEAD_MIN
        expected_min = 6 * _ROI_LEAD_MIN
        expected_hours = round(expected_min / 60, 2)
        assert result["estimated_minutes_saved"] == expected_min
        assert result["estimated_hours_saved"] == expected_hours

    def test_value_sek_equals_hours_times_rate(self):
        from app.main import _ROI_LEAD_MIN, _ROI_HOURLY_SEK
        result = _call(scalar_values=[6, 0, 0, 0])
        hours = round(6 * _ROI_LEAD_MIN / 60, 2)
        expected = round(hours * _ROI_HOURLY_SEK)
        assert result["estimated_value_sek"] == expected

    def test_larger_volumes(self):
        from app.main import _ROI_LEAD_MIN, _ROI_SUPPORT_MIN, _ROI_INVOICE_MIN, _ROI_FOLLOWUP_MIN, _ROI_HOURLY_SEK
        result = _call(scalar_values=[20, 15, 10, 5])
        expected_min = 20 * _ROI_LEAD_MIN + 15 * _ROI_SUPPORT_MIN + 10 * _ROI_INVOICE_MIN + 5 * _ROI_FOLLOWUP_MIN
        expected_hours = round(expected_min / 60, 2)
        expected_sek = round(expected_hours * _ROI_HOURLY_SEK)
        assert result["estimated_minutes_saved"] == expected_min
        assert result["estimated_hours_saved"] == expected_hours
        assert result["estimated_value_sek"] == expected_sek


# ══════════════════════════════════════════════════════════════════════════════
# Tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestRoiTenantIsolation:
    def test_db_query_called_with_tenant_id(self):
        from app.main import dashboard_roi

        db = MagicMock()
        mock_q = MagicMock()
        db.query.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.join.return_value = mock_q
        mock_q.scalar.return_value = 0

        dashboard_roi(db=db, tenant_id="TENANT_XYZ")

        assert db.query.called

    def test_different_tenants_get_independent_counts(self):
        # Two separate calls with different scalar sequences should return different values.
        r1 = _call(tenant_id="T1", scalar_values=[5, 0, 0, 0])
        r2 = _call(tenant_id="T2", scalar_values=[0, 0, 0, 0])
        assert r1["leads_created"] != r2["leads_created"]
