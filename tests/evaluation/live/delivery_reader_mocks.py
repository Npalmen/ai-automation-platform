"""Shared mocks for delivery mailbox reader resolution in tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.evaluation.live.delivery_mailbox_reader import (
    CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
    DeliveryMailboxReaderResolution,
    TenantIntegrationDeliveryReader,
)


def tenant_adapter_reader_resolution(adapter: MagicMock) -> DeliveryMailboxReaderResolution:
    return DeliveryMailboxReaderResolution(
        reader=TenantIntegrationDeliveryReader(adapter),
        credential_source=CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
        mailbox_identity_redacted="re…@eval.test",
        source_allowed=True,
        source_matches_readiness=True,
        blockers=[],
    )
