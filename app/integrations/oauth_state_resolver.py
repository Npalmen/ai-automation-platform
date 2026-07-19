"""Resolve OAuth callback state to the correct persistence table."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.admin.onboarding.models import OnboardingOAuthStateRecord
from app.integrations.oauth_state_models import IntegrationOAuthStateRecord


def lookup_oauth_state_source(db: Session, state_id: str) -> str | None:
    """
    Return which OAuth state table owns this opaque state_id.

    DB lookup replaces the previous opaque-string heuristic that incorrectly
    routed operator-panel integration states into the onboarding consumer.
    """
    if not state_id or not state_id.strip():
        return None
    sid = state_id.strip()
    integration = (
        db.query(IntegrationOAuthStateRecord.state_id)
        .filter(IntegrationOAuthStateRecord.state_id == sid)
        .first()
    )
    if integration is not None:
        return "integration"
    onboarding = (
        db.query(OnboardingOAuthStateRecord.state_id)
        .filter(OnboardingOAuthStateRecord.state_id == sid)
        .first()
    )
    if onboarding is not None:
        return "onboarding"
    return None
