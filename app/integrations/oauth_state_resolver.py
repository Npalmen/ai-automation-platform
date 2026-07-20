"""Resolve OAuth callback state to the correct persistence table."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.admin.onboarding.models import OnboardingOAuthStateRecord
from app.integrations.oauth_state_models import IntegrationOAuthStateRecord


def lookup_oauth_state_source(db: Session, state_id: str) -> str | None:
    """
    Return which OAuth state table owns this opaque state_id.

    DB lookup only — no opaque-string heuristics (DEC-032).
    """
    if not state_id or not state_id.strip():
        return None
    sid = state_id.strip()
    integration = (
        db.query(IntegrationOAuthStateRecord)
        .filter(IntegrationOAuthStateRecord.state_id == sid)
        .first()
    )
    if integration is not None:
        if getattr(integration, "invitation_id", None):
            return "invite"
        return "integration"
    onboarding = (
        db.query(OnboardingOAuthStateRecord.state_id)
        .filter(OnboardingOAuthStateRecord.state_id == sid)
        .first()
    )
    if onboarding is not None:
        return "onboarding"
    return None
