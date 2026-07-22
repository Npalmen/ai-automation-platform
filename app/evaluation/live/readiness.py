"""Readiness checks for validate-config (offline and Gmail read-only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import PYTEST_MARKER_EXPR
from app.evaluation.live.safety import (
    require_gmail_eval_enabled,
    require_tenant_allowed,
    validate_config_readiness,
)
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.policies import is_integration_enabled_for_tenant
from app.integrations.service import get_integration_connection_config

_READ_ONLY_GMAIL_ACTIONS = frozenset({"get_profile", "list_labels"})


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _looks_like_email(value: str) -> bool:
    normalized = _normalize_email(value)
    if normalized.count("@") != 1:
        return False
    local, domain = normalized.split("@", 1)
    return bool(local) and "." in domain


def _normalized_recipient_allowlist(config: LiveEvalConfig) -> frozenset[str]:
    return frozenset(
        email for email in (_normalize_email(item) for item in config.recipient_emails) if email
    )


def _validate_gmail_account_identity(
    *,
    connection_user_id: str,
    profile_email: str,
    recipient_allowlist: frozenset[str],
) -> list[str]:
    issues: list[str] = []
    selector = connection_user_id.strip()
    selector_lower = selector.lower()

    if not profile_email or "@" not in profile_email:
        issues.append("Gmail profile email is missing")
        return issues

    if profile_email not in recipient_allowlist:
        issues.append("Gmail profile email does not match LIVE_EVAL_RECIPIENT_EMAILS")
        return issues

    if selector_lower == "me":
        return issues

    if _looks_like_email(selector):
        if _normalize_email(selector) != profile_email:
            issues.append("Gmail profile email does not match configured connection user_id")
        return issues

    if selector:
        issues.append("configured connection user_id is not a valid Gmail selector or email address")

    return issues


@dataclass
class ReadinessReport:
    ready: bool
    issues: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)


def run_offline_readiness_checks(
    config: LiveEvalConfig | None = None,
) -> ReadinessReport:
    config = config or get_live_eval_config()
    issues = validate_config_readiness(config)
    checks: dict[str, Any] = {
        "mode": "offline",
        "pytest_marker_expr": PYTEST_MARKER_EXPR,
        "intake_label": config.intake_label,
        "env_fingerprint": config.env_fingerprint,
        "filter_contract": (
            "Operator must configure Gmail filter: from allowlisted sender "
            f"→ apply label:{config.intake_label} (verified in 2F.2)"
        ),
    }
    return ReadinessReport(ready=not issues, issues=issues, checks=checks)


def run_gmail_readiness_checks(
    db: Session,
    tenant_id: str,
    *,
    config: LiveEvalConfig | None = None,
) -> ReadinessReport:
    """Read-only Gmail verification via app-side OAuth (no send/modify/LLM)."""
    config = config or get_live_eval_config()
    issues = list(validate_config_readiness(config))
    checks: dict[str, Any] = {"mode": "gmail_read_only", "tenant_id": tenant_id}

    try:
        require_gmail_eval_enabled(config)
        require_tenant_allowed(tenant_id, config)
    except Exception as exc:
        issues.append(str(exc))
        return ReadinessReport(ready=False, issues=issues, checks=checks)

    if not is_integration_enabled_for_tenant(
        tenant_id, IntegrationType.GOOGLE_MAIL, db=db
    ):
        issues.append("Gmail integration is not enabled for tenant")

    label_name = config.intake_label
    intake_query = f"label:{label_name} is:unread"
    checks["intake_query"] = intake_query

    try:
        connection_config = get_integration_connection_config(
            tenant_id=tenant_id,
            integration_type=IntegrationType.GOOGLE_MAIL,
            db=db,
        )
        connection_user_id = str(connection_config.get("user_id") or "").strip()
        checks["connection_user_id"] = connection_user_id.lower() or None
        if not str(connection_config.get("access_token") or "").strip():
            issues.append("Gmail OAuth access_token is missing")

        adapter = get_integration_adapter(
            integration_type=IntegrationType.GOOGLE_MAIL,
            connection_config=connection_config,
        )

        profile_result = adapter.execute_action(action="get_profile", payload={})
        profile_email = _normalize_email(profile_result.get("email_address"))
        checks["gmail_profile_email"] = profile_email or None
        issues.extend(
            _validate_gmail_account_identity(
                connection_user_id=connection_user_id,
                profile_email=profile_email,
                recipient_allowlist=_normalized_recipient_allowlist(config),
            )
        )

        labels_result = adapter.execute_action(action="list_labels", payload={})
        labels = labels_result.get("labels") or []
        checks["label_count"] = len(labels)
        label_names = {str(item.get("name") or "") for item in labels}
        checks["label_present"] = label_name in label_names
        if label_name not in label_names:
            issues.append(f"Gmail label {label_name!r} not found")

        query_token = f"label:{label_name}".replace(" ", "").lower()
        if query_token not in intake_query.replace(" ", "").lower():
            issues.append("intake query missing configured label token")
    except Exception as exc:
        issues.append(f"gmail readiness failed: {exc}")

    checks["allowed_adapter_actions"] = sorted(_READ_ONLY_GMAIL_ACTIONS)
    checks["filter_contract"] = (
        "Operator must configure Gmail filter to apply "
        f"label:{label_name} (full filter test in 2F.2)"
    )
    return ReadinessReport(ready=not issues, issues=issues, checks=checks)
