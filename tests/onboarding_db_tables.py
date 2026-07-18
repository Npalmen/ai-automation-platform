"""SQLite table list for onboarding integration tests."""

from __future__ import annotations

from app.admin.onboarding.models import (
    OnboardingIntegrationVerificationRecord,
    OnboardingOAuthStateRecord,
    OnboardingSessionRecord,
    OnboardingStepDraftRecord,
    OnboardingStepStateRecord,
    TenantResourceBindingRecord,
)
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def onboarding_sqlite_tables() -> list:
    return [
        TenantConfigRecord.__table__,
        OnboardingSessionRecord.__table__,
        OnboardingStepStateRecord.__table__,
        OnboardingStepDraftRecord.__table__,
        OnboardingIntegrationVerificationRecord.__table__,
        OnboardingOAuthStateRecord.__table__,
        TenantResourceBindingRecord.__table__,
        OAuthCredentialRecord.__table__,
        AuditEventRecord.__table__,
        TenantApiKeyRecord.__table__,
    ]
