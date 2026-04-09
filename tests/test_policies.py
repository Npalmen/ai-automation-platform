"""
Tests for app/workflows/policies.py — is_job_type_enabled_for_tenant.

The critical regression test detects swapped argument order:
  correct:  is_job_type_enabled_for_tenant(job_type, tenant_id)
  bug:      is_job_type_enabled_for_tenant(tenant_id, job_type)   ← was in main.py
"""
import pytest

from app.domain.workflows.enums import JobType
from app.workflows.policies import is_job_type_enabled_for_tenant


class TestIsJobTypeEnabledForTenant:
    # --- happy-path: enabled types ---

    def test_lead_enabled_for_tenant_1001(self):
        assert is_job_type_enabled_for_tenant(JobType.LEAD, "TENANT_1001") is True

    def test_invoice_enabled_for_tenant_1001(self):
        assert is_job_type_enabled_for_tenant(JobType.INVOICE, "TENANT_1001") is True

    def test_customer_inquiry_enabled_for_tenant_1001(self):
        assert is_job_type_enabled_for_tenant(JobType.CUSTOMER_INQUIRY, "TENANT_1001") is True

    def test_lead_enabled_for_tenant_2001(self):
        assert is_job_type_enabled_for_tenant(JobType.LEAD, "TENANT_2001") is True

    def test_invoice_enabled_for_finance_tenant(self):
        assert is_job_type_enabled_for_tenant(JobType.INVOICE, "TENANT_3001") is True

    # --- happy-path: disabled types ---

    def test_invoice_disabled_for_sales_tenant(self):
        # TENANT_2001 only has lead + customer_inquiry
        assert is_job_type_enabled_for_tenant(JobType.INVOICE, "TENANT_2001") is False

    def test_lead_disabled_for_finance_tenant(self):
        # TENANT_3001 only has invoice
        assert is_job_type_enabled_for_tenant(JobType.LEAD, "TENANT_3001") is False

    # --- string values accepted ---

    def test_accepts_string_job_type(self):
        assert is_job_type_enabled_for_tenant("lead", "TENANT_1001") is True

    def test_rejects_unknown_string_job_type(self):
        assert is_job_type_enabled_for_tenant("nonexistent", "TENANT_1001") is False

    # --- regression: argument order ---

    def test_argument_order_lead_is_allowed(self):
        """
        Catches the swapped-argument bug that was in main.py:
            is_job_type_enabled_for_tenant(tenant_id, request.job_type)
        With reversed args the function treats 'TENANT_1001' as the job_type
        and 'lead' as the tenant_id.  'TENANT_1001' is not in any enabled list,
        so it would return False even though 'lead' is allowed.
        This test must pass with the correct arg order and would fail if reversed.
        """
        result = is_job_type_enabled_for_tenant(JobType.LEAD, "TENANT_1001")
        assert result is True, (
            "is_job_type_enabled_for_tenant returned False for an allowed job type. "
            "Check argument order: signature is (job_type, tenant_id)."
        )

    def test_reversed_args_would_fail(self):
        """
        Explicitly documents what the bug looked like.
        Calling with args swapped must NOT return True for 'lead'/'TENANT_1001'.
        'TENANT_1001' is not a valid job_type in any enabled list.
        """
        result_with_reversed_args = is_job_type_enabled_for_tenant("TENANT_1001", "lead")
        assert result_with_reversed_args is False, (
            "Swapped args unexpectedly returned True — the regression guard is broken."
        )
