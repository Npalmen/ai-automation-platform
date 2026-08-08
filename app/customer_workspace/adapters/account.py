"""Workspace context adapter."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.customer_workspace.read_sources import build_account_context
from app.customer_workspace.schemas import FeatureFlags, WorkspaceContextResponse


def get_workspace_context(db: Session, tenant_id: str) -> WorkspaceContextResponse:
    account = build_account_context(db, tenant_id)
    return WorkspaceContextResponse(
        tenant_id=account["tenant_id"],
        company_name=account["company_name"],
        contact_name=account["contact_name"],
        contact_email=account["contact_email"],
        support_email=account["support_email"],
        language=account["language"],
        region=account["region"],
        feature_flags=FeatureFlags(),
    )
