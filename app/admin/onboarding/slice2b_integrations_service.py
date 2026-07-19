"""Slice 2B onboarding integrations service (config-only drafts + server verification)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.onboarding.errors import OnboardingConflictError, OnboardingValidationError
from app.admin.onboarding.integration_draft_schemas import (
    GmailIntegrationConfig,
    GoogleSheetsIntegrationConfig,
    IntegrationActionRequest,
    IntegrationsDraftPayload,
    IntegrationsPatchRequest,
    MondayIntegrationConfig,
    VismaIntegrationConfig,
)
from app.admin.onboarding.integration_fingerprint import (
    build_gmail_label_query,
    fingerprint_gmail,
    fingerprint_google_sheets,
    fingerprint_monday,
    fingerprint_visma,
)
from app.admin.onboarding.integration_verification import IntegrationVerificationStore
from app.admin.onboarding.models import OPEN_SESSION_STATUSES
from app.admin.onboarding.audit_events import (
    INTEGRATION_CONFIGURATION_UPDATED,
    INTEGRATION_REQUESTED,
    INTEGRATION_VERIFICATION_FAILED,
    INTEGRATION_VERIFICATION_STARTED,
    INTEGRATION_VERIFICATION_SUCCEEDED,
    OAUTH_CONNECTION_STARTED,
    emit_onboarding_audit,
)
from app.admin.onboarding.oauth_state_service import create_oauth_state
from app.admin.onboarding.registries import INTEGRATIONS
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.resource_binding import (
    RESOURCE_SHEETS_SPREADSHEET,
    ResourceBindingService,
)
from app.admin.onboarding.steps import evaluate_integrations_step
from app.core.admin_session import OperatorIdentity
from app.core.settings import Settings
from app.integrations.google.sheets_auth import resolve_google_sheets_access_token
from app.integrations.google.sheets_client import GoogleSheetsClient
from app.integrations.monday.client import MondayClient
from app.integrations.google.oauth_service import get_auth_url_for_state as google_auth_url_for_state
from app.integrations.visma.oauth_service import (
    get_auth_url_for_state,
    refresh_access_token,
    test_connection,
)
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

_LABEL_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_CONNECTABLE = frozenset({"visma", "gmail"})
_ADMIN_UNLINK = frozenset({"visma", "gmail"})


def _session_ops():
    from app.admin.onboarding import service as onboarding_service

    return onboarding_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_integrations_draft(db: Session, session_id: str) -> IntegrationsDraftPayload:
    record = OnboardingRepository.get_draft(db, session_id, "integrations")
    return IntegrationsDraftPayload.model_validate((record.payload if record else {}) or {})


def _load_external_routing_draft(db: Session, session_id: str) -> dict:
    record = OnboardingRepository.get_draft(db, session_id, "external_routing")
    return (record.payload if record else {}) or {}


def _required_integration_keys(modules_payload: dict, draft: IntegrationsDraftPayload) -> set[str]:
    from app.admin.onboarding.steps import _required_integrations_for_capabilities

    caps = modules_payload.get("capabilities") or []
    required = _required_integrations_for_capabilities(caps)
    requested = set(draft.requested_integrations or modules_payload.get("integrations") or [])
    return required | requested


def _google_mail_oauth_row(db: Session, tenant_id: str) -> OAuthCredentialRecord | None:
    return (
        db.query(OAuthCredentialRecord)
        .filter(
            OAuthCredentialRecord.tenant_id == tenant_id,
            OAuthCredentialRecord.provider == "google_mail",
        )
        .first()
    )


def _visma_oauth_row(db: Session, tenant_id: str) -> OAuthCredentialRecord | None:
    return (
        db.query(OAuthCredentialRecord)
        .filter(
            OAuthCredentialRecord.tenant_id == tenant_id,
            OAuthCredentialRecord.provider == "visma",
        )
        .first()
    )


def _gmail_label_valid(slug: str) -> bool:
    s = slug.strip().lower()
    return bool(s and _LABEL_SLUG_RE.match(s))


def _monday_board_from_routing(external_routing: dict) -> tuple[str, str | None]:
    lead = (external_routing.get("targets") or {}).get("lead") or {}
    return str(lead.get("board_id") or "").strip(), lead.get("group_id")


def _integration_config_fingerprint(
    db: Session,
    *,
    session_id: str,
    integration_key: str,
    draft: IntegrationsDraftPayload,
    tenant: TenantConfigRecord,
    external_routing: dict,
) -> str | None:
    if integration_key == "gmail":
        if not draft.gmail.requested:
            return None
        return fingerprint_gmail(
            label_scope_slug=draft.gmail.label_scope_slug,
            tenant_slug=tenant.slug or "",
        )
    if integration_key == "visma":
        row = _visma_oauth_row(db, tenant.tenant_id)
        if row is None:
            return None
        return fingerprint_visma(connection_updated_at=row.updated_at or row.connected_at)
    if integration_key == "google_sheets":
        if not draft.google_sheets.spreadsheet_id:
            return None
        return fingerprint_google_sheets(
            spreadsheet_id=draft.google_sheets.spreadsheet_id,
            export_tabs=list(draft.google_sheets.export_tabs),
        )
    if integration_key == "monday":
        board_id, group_id = _monday_board_from_routing(external_routing)
        if not board_id:
            return None
        return fingerprint_monday(board_id=board_id, group_id=group_id)
    return None


def _compute_lifecycle(
    db: Session,
    *,
    session_id: str,
    integration_key: str,
    draft: IntegrationsDraftPayload,
    tenant: TenantConfigRecord,
    settings: Settings,
    external_routing: dict,
    required: bool,
) -> dict[str, Any]:
    integ = INTEGRATIONS.get(integration_key)
    if integ is None:
        return {
            "integration_key": integration_key,
            "lifecycle_status": "not_supported",
            "required": required,
        }

    verification = IntegrationVerificationStore.get(db, session_id, integration_key)
    fingerprint = _integration_config_fingerprint(
        db,
        session_id=session_id,
        integration_key=integration_key,
        draft=draft,
        tenant=tenant,
        external_routing=external_routing,
    )
    verified = IntegrationVerificationStore.is_verified_for_fingerprint(
        verification, expected_fingerprint=fingerprint or ""
    )

    connected = False
    configured = False
    lifecycle = "unknown"
    source_class = "declared"
    ownership = "not_verifiable"
    platform_credential = False

    if integration_key == "gmail":
        requested = draft.gmail.requested or required
        row = _google_mail_oauth_row(db, tenant.tenant_id)
        configured = requested and _gmail_label_valid(draft.gmail.label_scope_slug)
        platform_credential = row is not None or bool(settings.GOOGLE_MAIL_ACCESS_TOKEN)
        connected = row is not None or bool(settings.GOOGLE_MAIL_ACCESS_TOKEN)
        if configured and verified:
            lifecycle = "configured_not_running"
            source_class = (
                verification.source_class
                if verification
                else ("tenant_oauth" if row else "platform_env")
            )
        elif configured:
            lifecycle = "configured"
            source_class = "tenant_oauth" if row else "platform_env"
        elif connected:
            lifecycle = "connected"
            source_class = "tenant_oauth" if row else "platform_env"
        elif configured and not connected:
            lifecycle = "authorization_required"
        elif requested:
            lifecycle = "selected"
        else:
            lifecycle = "not_applicable"
    elif integration_key == "visma":
        requested = draft.visma.requested or required
        row = _visma_oauth_row(db, tenant.tenant_id)
        connected = row is not None
        configured = requested
        if verified:
            lifecycle = "verified"
            source_class = verification.source_class if verification else "externally_verified"
        elif connected:
            lifecycle = "connected"
        elif configured and not connected:
            lifecycle = "authorization_required"
        elif configured:
            lifecycle = "configured"
        elif requested:
            lifecycle = "selected"
        else:
            lifecycle = "not_applicable"
    elif integration_key == "google_sheets":
        requested = draft.google_sheets.requested or required
        configured = requested and bool(draft.google_sheets.spreadsheet_id.strip())
        connected = configured
        if verified:
            lifecycle = "verified"
            source_class = verification.source_class if verification else "externally_verified"
        elif connected:
            lifecycle = "connected"
        elif requested:
            lifecycle = "selected"
        else:
            lifecycle = "not_applicable"
    elif integration_key == "monday":
        requested = draft.monday.requested or required
        board_id, _ = _monday_board_from_routing(external_routing)
        configured = requested and bool(board_id)
        connected = bool(settings.MONDAY_API_KEY)
        platform_credential = connected
        if verified:
            lifecycle = "verified"
            source_class = verification.source_class if verification else "externally_verified"
        elif configured and connected:
            lifecycle = "connected"
        elif configured:
            lifecycle = "configured"
        elif requested:
            lifecycle = "selected"
        else:
            lifecycle = "not_applicable"

    freshness_hours = integ.freshness_max_hours if integ else None
    verified_at = verification.verified_at.isoformat() if verification and verification.verified_at else None
    verification_error = verification.error_code if verification and verification.verification_status == "failed" else None
    connection_status = "connected" if connected else ("disconnected" if requested else "not_requested")

    gmail_details: dict[str, Any] | None = None
    if integration_key == "gmail":
        gmail_details = {
            "label_query": "locally_verified" if configured else None,
            "platform_credential": "platform_level" if platform_credential else "missing",
            "tenant_mailbox_access": "not_verifiable",
            "live_intake": "configured_not_running" if configured else "not_verifiable",
            "capability_operational": False,
        }

    return {
        "integration_key": integration_key,
        "label": integ.label_sv,
        "required": required,
        "requested": integration_key in (draft.requested_integrations or []),
        "lifecycle_status": lifecycle,
        "connection_status": connection_status,
        "connected": connected,
        "configured": configured,
        "verified": verified,
        "verification_status": verification.verification_status if verification else "pending",
        "verified_at": verified_at,
        "freshness_max_hours": freshness_hours,
        "verification_error_code": verification_error,
        "source_class": source_class,
        "platform_credential": platform_credential,
        "ownership": ownership,
        "config_fingerprint": fingerprint,
        "limitation_ids": list(integ.limitation_ids),
        "lifecycle_cap": integ.lifecycle_cap,
        "gmail_classification": gmail_details,
    }


def _audit_verify_outcome(
    db: Session,
    *,
    tenant_id: str,
    operator: OperatorIdentity,
    session_id: str,
    integration_key: str,
    outcome: str,
    error_code: str | None = None,
    source_class: str | None = None,
) -> None:
    action = (
        INTEGRATION_VERIFICATION_SUCCEEDED
        if outcome == "succeeded"
        else INTEGRATION_VERIFICATION_FAILED
    )
    extra: dict[str, Any] = {"integration_key": integration_key}
    if error_code:
        extra["error_code"] = error_code
    if source_class:
        extra["source_class"] = source_class
    emit_onboarding_audit(
        db,
        tenant_id=tenant_id,
        action=action,
        status=outcome,
        details=_session_ops()._operator_audit_details(
            operator, session_id=session_id, extra=extra
        ),
    )


def _commit_or_audit_error(db: Session) -> None:
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from app.admin.onboarding.errors import OnboardingAuditError

        raise OnboardingAuditError("Audit could not be recorded.") from exc


def _sync_integrations_step_state(
    db: Session,
    *,
    session_id: str,
    tenant: TenantConfigRecord,
    settings: Settings,
    operator_id: str,
) -> None:
    modules = OnboardingRepository.get_draft(db, session_id, "modules")
    modules_payload = (modules.payload if modules else {}) or {}
    evaluation = evaluate_integrations_step(
        db,
        modules_draft=modules_payload,
        tenant=tenant,
        settings=settings,
        session_id=session_id,
    )
    OnboardingRepository.set_step_state(
        db,
        session_id=session_id,
        step_key="integrations",
        step_status=evaluation["step_status"],
        verification_level=evaluation["verification_level"],
        operator_id=operator_id,
    )


def get_integrations_step(
    db: Session,
    session_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    session = _session_ops()._get_session_or_raise(db, session_id)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    modules = OnboardingRepository.get_draft(db, session_id, "modules")
    modules_payload = (modules.payload if modules else {}) or {}
    draft = _load_integrations_draft(db, session_id)
    external_routing = _load_external_routing_draft(db, session_id)
    required_keys = _required_integration_keys(modules_payload, draft)

    items = [
        _compute_lifecycle(
            db,
            session_id=session_id,
            integration_key=key,
            draft=draft,
            tenant=tenant,
            settings=settings,
            external_routing=external_routing,
            required=key in required_keys,
        )
        for key in sorted(set(required_keys) | {i.key for i in INTEGRATIONS.values() if i.supported_in_current_slice})
        if key in INTEGRATIONS and INTEGRATIONS[key].supported_in_current_slice
    ]

    evaluation = evaluate_integrations_step(
        db,
        modules_draft=modules_payload,
        tenant=tenant,
        settings=settings,
        session_id=session_id,
    )
    return {
        "step_key": "integrations",
        "step_status": evaluation["step_status"],
        "verification_level": evaluation["verification_level"],
        "blocks_activation": evaluation["blocks_activation"],
        "integration_state_revision": session.integration_state_revision,
        "draft": draft.model_dump(),
        "integrations": items,
        "details": evaluation.get("details") or {},
    }


def patch_integrations_step(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    body: IntegrationsPatchRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    modules = OnboardingRepository.get_draft(db, session_id, "modules")
    modules_payload = (modules.payload if modules else {}) or {}
    current = _load_integrations_draft(db, session_id)

    gmail = body.gmail if body.gmail is not None else current.gmail
    visma = body.visma if body.visma is not None else current.visma
    sheets = body.google_sheets if body.google_sheets is not None else current.google_sheets
    monday = body.monday if body.monday is not None else current.monday
    requested = body.requested_integrations if body.requested_integrations is not None else current.requested_integrations

    if gmail.requested and not _gmail_label_valid(gmail.label_scope_slug):
        raise OnboardingValidationError("Gmail label_scope_slug is invalid.")

    draft = IntegrationsDraftPayload(
        requested_integrations=requested,
        gmail=gmail,
        visma=visma,
        google_sheets=sheets,
        monday=monday,
    )

    if sheets.spreadsheet_id.strip():
        ResourceBindingService.bind(
            db,
            resource_type=RESOURCE_SHEETS_SPREADSHEET,
            resource_id=sheets.spreadsheet_id.strip(),
            tenant_id=session.tenant_id,
            session_id=session.id,
            operator_id=operator["id"],
        )
        OnboardingRepository.bump_integration_state_revision(session)

    for key in ("gmail", "visma", "google_sheets", "monday"):
        IntegrationVerificationStore.invalidate(db, session_id=session_id, integration_key=key)

    OnboardingRepository.upsert_draft(
        db,
        session_id=session_id,
        step_key="integrations",
        payload=draft.model_dump(),
    )
    OnboardingRepository.bump_version(session, operator["id"])
    _sync_integrations_step_state(
        db, session_id=session_id, tenant=tenant, settings=settings, operator_id=operator["id"]
    )
    audit_action = (
        INTEGRATION_REQUESTED
        if body.requested_integrations is not None
        else INTEGRATION_CONFIGURATION_UPDATED
    )
    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=audit_action,
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator, session_id=session_id, extra={"requested_integrations": requested}
        ),
    )
    _session_ops()._add_audit_event_no_commit(
        db,
        tenant_id=session.tenant_id,
        action="onboarding.integrations_patched",
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator, session_id=session_id, extra={"requested_integrations": requested}
        ),
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from app.admin.onboarding.errors import OnboardingAuditError

        raise OnboardingAuditError("Audit could not be recorded.") from exc
    session = OnboardingRepository.get_session(db, session_id)
    return _session_ops()._build_session_response(db, session, settings=settings)


def connect_integration(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    integration_key: str,
    settings: Settings,
    redirect_target: str,
) -> dict[str, Any]:
    if integration_key not in _CONNECTABLE:
        raise OnboardingValidationError(f"Integration '{integration_key}' does not support connect.")
    session = _session_ops()._get_session_or_raise(db, session_id)
    _session_ops()._ensure_writable_session(session)
    if session.status not in OPEN_SESSION_STATUSES:
        raise OnboardingValidationError("Session is not writable.")

    if integration_key == "visma":
        if not settings.VISMA_CLIENT_ID or not settings.VISMA_REDIRECT_URI:
            raise OnboardingValidationError("Visma OAuth is not configured.")
        provider = "visma"
        state_id, _ = create_oauth_state(
            db,
            session=session,
            operator_id=operator["id"],
            provider=provider,
            redirect_target=redirect_target,
            settings=settings,
        )
        url = get_auth_url_for_state(state_id)
    elif integration_key == "gmail":
        if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
            raise OnboardingValidationError("Google OAuth is not configured.")
        provider = "google_mail"
        state_id, _ = create_oauth_state(
            db,
            session=session,
            operator_id=operator["id"],
            provider=provider,
            redirect_target=redirect_target,
            settings=settings,
        )
        url = google_auth_url_for_state(state_id)
    else:
        raise OnboardingValidationError(f"Integration '{integration_key}' does not support connect.")

    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=OAUTH_CONNECTION_STARTED,
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            extra={"provider": provider, "integration_key": integration_key},
        ),
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from app.admin.onboarding.errors import OnboardingAuditError

        raise OnboardingAuditError("Audit could not be recorded.") from exc
    return {"authorization_url": url, "provider": provider, "state_id": state_id}


def get_integration_status(
    db: Session,
    session_id: str,
    integration_key: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    session = _session_ops()._get_session_or_raise(db, session_id)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    modules = OnboardingRepository.get_draft(db, session_id, "modules")
    modules_payload = (modules.payload if modules else {}) or {}
    draft = _load_integrations_draft(db, session_id)
    external_routing = _load_external_routing_draft(db, session_id)
    required_keys = _required_integration_keys(modules_payload, draft)
    if integration_key not in INTEGRATIONS:
        raise OnboardingValidationError(f"Unknown integration '{integration_key}'.")
    return _compute_lifecycle(
        db,
        session_id=session_id,
        integration_key=integration_key,
        draft=draft,
        tenant=tenant,
        settings=settings,
        external_routing=external_routing,
        required=integration_key in required_keys,
    )


def verify_integration(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    integration_key: str,
    settings: Settings,
) -> dict[str, Any]:
    session = _session_ops()._get_session_or_raise(db, session_id)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    draft = _load_integrations_draft(db, session_id)
    external_routing = _load_external_routing_draft(db, session_id)

    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=INTEGRATION_VERIFICATION_STARTED,
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator, session_id=session_id, extra={"integration_key": integration_key}
        ),
    )

    if integration_key == "gmail":
        if not draft.gmail.requested and not _gmail_label_valid(draft.gmail.label_scope_slug):
            raise OnboardingValidationError("Gmail is not configured.")
        try:
            label_query = build_gmail_label_query(draft.gmail.label_scope_slug)
        except ValueError as exc:
            IntegrationVerificationStore.mark_failed(
                db,
                session_id=session_id,
                integration_key="gmail",
                source_class="declared",
                error_code="label_invalid",
            )
            emit_onboarding_audit(
                db,
                tenant_id=session.tenant_id,
                action=INTEGRATION_VERIFICATION_FAILED,
                status="failed",
                details=_session_ops()._operator_audit_details(
                    operator,
                    session_id=session_id,
                    extra={"integration_key": "gmail", "error_code": "label_invalid"},
                ),
            )
            try:
                db.commit()
            except Exception as exc:
                db.rollback()
                from app.admin.onboarding.errors import OnboardingAuditError

                raise OnboardingAuditError("Audit could not be recorded.") from exc
            raise OnboardingValidationError(str(exc)) from exc
        fp = fingerprint_gmail(
            label_scope_slug=draft.gmail.label_scope_slug,
            tenant_slug=tenant.slug or "",
        )
        rev = OnboardingRepository.bump_integration_state_revision(session)
        IntegrationVerificationStore.mark_verified(
            db,
            session_id=session_id,
            integration_key="gmail",
            source_class="locally_verified",
            operator_id=operator["id"],
            config_fingerprint=fp,
            integration_state_revision=rev,
            metadata={
                "label_query": label_query,
                "live_intake": "not_verifiable",
                "platform_credential": bool(settings.GOOGLE_MAIL_ACCESS_TOKEN),
            },
        )
        emit_onboarding_audit(
            db,
            tenant_id=session.tenant_id,
            action=INTEGRATION_VERIFICATION_SUCCEEDED,
            status="succeeded",
            details=_session_ops()._operator_audit_details(
                operator,
                session_id=session_id,
                extra={"integration_key": "gmail", "source_class": "locally_verified"},
            ),
        )
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            from app.admin.onboarding.errors import OnboardingAuditError

            raise OnboardingAuditError("Audit could not be recorded.") from exc
        return get_integration_status(db, session_id, "gmail", settings=settings)

    if integration_key == "visma":
        row = _visma_oauth_row(db, tenant.tenant_id)
        if row is None:
            IntegrationVerificationStore.mark_failed(
                db,
                session_id=session_id,
                integration_key="visma",
                source_class="declared",
                error_code="not_connected",
            )
            emit_onboarding_audit(
                db,
                tenant_id=session.tenant_id,
                action=INTEGRATION_VERIFICATION_FAILED,
                status="failed",
                details=_session_ops()._operator_audit_details(
                    operator,
                    session_id=session_id,
                    extra={"integration_key": "visma", "error_code": "not_connected"},
                ),
            )
            try:
                db.commit()
            except Exception as exc:
                db.rollback()
                from app.admin.onboarding.errors import OnboardingAuditError

                raise OnboardingAuditError("Audit could not be recorded.") from exc
            raise OnboardingValidationError("Visma is not connected. Run OAuth connect first.")
        access_token = row.access_token
        now = _utcnow()
        if row.expires_at and row.expires_at < now:
            if not row.refresh_token:
                IntegrationVerificationStore.mark_failed(
                    db,
                    session_id=session_id,
                    integration_key="visma",
                    source_class="declared",
                    error_code="token_expired",
                )
                db.commit()
                raise OnboardingValidationError("Visma token expired. Reconnect.")
            refreshed = refresh_access_token(row.refresh_token)
            OAuthCredentialRepository.upsert(
                db=db,
                tenant_id=tenant.tenant_id,
                provider="visma",
                access_token=refreshed["access_token"],
                refresh_token=refreshed.get("refresh_token"),
                expires_at=refreshed.get("expires_at"),
                scopes=refreshed.get("scopes") or row.scopes,
            )
            row = _visma_oauth_row(db, tenant.tenant_id)
            access_token = row.access_token if row else refreshed["access_token"]
        try:
            company = test_connection(access_token)
        except Exception:
            IntegrationVerificationStore.mark_failed(
                db,
                session_id=session_id,
                integration_key="visma",
                source_class="declared",
                error_code="api_read_failed",
            )
            db.commit()
            raise OnboardingValidationError("Visma API read failed.")
        fp = fingerprint_visma(connection_updated_at=row.updated_at or row.connected_at)
        rev = OnboardingRepository.bump_integration_state_revision(session)
        IntegrationVerificationStore.mark_verified(
            db,
            session_id=session_id,
            integration_key="visma",
            source_class="externally_verified",
            operator_id=operator["id"],
            config_fingerprint=fp,
            integration_state_revision=rev,
            metadata={"company_name": company.get("Name") if isinstance(company, dict) else None},
        )
        _audit_verify_outcome(
            db,
            tenant_id=session.tenant_id,
            operator=operator,
            session_id=session_id,
            integration_key="visma",
            outcome="succeeded",
            source_class="externally_verified",
        )
        _commit_or_audit_error(db)
        return get_integration_status(db, session_id, "visma", settings=settings)

    if integration_key == "google_sheets":
        spreadsheet_id = draft.google_sheets.spreadsheet_id.strip()
        if not spreadsheet_id:
            raise OnboardingValidationError("spreadsheet_id is required.")
        try:
            token = resolve_google_sheets_access_token({})
            client = GoogleSheetsClient(access_token=token)
            import requests

            meta_url = (
                f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
                "?fields=properties.title,sheets.properties.title"
            )
            response = requests.get(
                meta_url,
                headers=client._headers(),
                timeout=15,
            )
            if response.status_code != 200:
                raise RuntimeError(f"metadata {response.status_code}")
            meta = response.json()
        except Exception:
            IntegrationVerificationStore.mark_failed(
                db,
                session_id=session_id,
                integration_key="google_sheets",
                source_class="declared",
                error_code="metadata_read_failed",
            )
            db.commit()
            raise OnboardingValidationError("Could not read spreadsheet metadata.")
        tabs = [
            s.get("properties", {}).get("title")
            for s in meta.get("sheets", [])
            if s.get("properties", {}).get("title")
        ]
        fp = fingerprint_google_sheets(
            spreadsheet_id=spreadsheet_id,
            export_tabs=list(draft.google_sheets.export_tabs),
        )
        rev = OnboardingRepository.bump_integration_state_revision(session)
        IntegrationVerificationStore.mark_verified(
            db,
            session_id=session_id,
            integration_key="google_sheets",
            source_class="externally_verified",
            operator_id=operator["id"],
            config_fingerprint=fp,
            integration_state_revision=rev,
            metadata={
                "title": meta.get("properties", {}).get("title"),
                "tabs": tabs,
                "ownership": "not_verifiable",
            },
        )
        _audit_verify_outcome(
            db,
            tenant_id=session.tenant_id,
            operator=operator,
            session_id=session_id,
            integration_key="google_sheets",
            outcome="succeeded",
            source_class="externally_verified",
        )
        _commit_or_audit_error(db)
        return get_integration_status(db, session_id, "google_sheets", settings=settings)

    if integration_key == "monday":
        board_id, group_id = _monday_board_from_routing(external_routing)
        if not board_id:
            raise OnboardingValidationError("Monday board_id must be set in external routing.")
        if not settings.MONDAY_API_KEY:
            raise OnboardingValidationError("Platform Monday API key is not configured.")
        try:
            client = MondayClient(api_key=settings.MONDAY_API_KEY)
            boards = client.get_boards(limit=100)
            board = next((b for b in boards if str(b.get("id")) == board_id), None)
            if board is None:
                raise RuntimeError("board not found")
        except Exception:
            IntegrationVerificationStore.mark_failed(
                db,
                session_id=session_id,
                integration_key="monday",
                source_class="declared",
                error_code="board_read_failed",
            )
            db.commit()
            raise OnboardingValidationError("Could not read Monday board metadata.")
        fp = fingerprint_monday(board_id=board_id, group_id=group_id)
        rev = OnboardingRepository.bump_integration_state_revision(session)
        IntegrationVerificationStore.mark_verified(
            db,
            session_id=session_id,
            integration_key="monday",
            source_class="externally_verified",
            operator_id=operator["id"],
            config_fingerprint=fp,
            integration_state_revision=rev,
            metadata={
                "board_name": board.get("name"),
                "ownership": "not_verifiable",
            },
        )
        _audit_verify_outcome(
            db,
            tenant_id=session.tenant_id,
            operator=operator,
            session_id=session_id,
            integration_key="monday",
            outcome="succeeded",
            source_class="externally_verified",
        )
        _commit_or_audit_error(db)
        return get_integration_status(db, session_id, "monday", settings=settings)

    raise OnboardingValidationError(f"Verify not supported for '{integration_key}'.")


def unrequest_integration(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    integration_key: str,
    body: IntegrationActionRequest,
    settings: Settings,
):
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    draft = _load_integrations_draft(db, session_id)
    requested = [k for k in draft.requested_integrations if k != integration_key]
    patch = IntegrationsPatchRequest(
        version=session.version,
        requested_integrations=requested,
        gmail=GmailIntegrationConfig(requested=False) if integration_key == "gmail" else None,
        visma=VismaIntegrationConfig(requested=False) if integration_key == "visma" else None,
        google_sheets=GoogleSheetsIntegrationConfig(requested=False) if integration_key == "google_sheets" else None,
        monday=MondayIntegrationConfig(requested=False) if integration_key == "monday" else None,
    )
    ResourceBindingService.release_for_session(db, session_id=session_id)
    IntegrationVerificationStore.invalidate(db, session_id=session_id, integration_key=integration_key)
    return patch_integrations_step(
        db, session_id=session_id, operator=operator, body=patch, settings=settings
    )


def local_unlink_integration(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    integration_key: str,
    body: IntegrationActionRequest,
    settings: Settings,
):
    if integration_key in _ADMIN_UNLINK and operator["role"] != "admin":
        raise OnboardingValidationError("Local unlink for Visma requires admin role.")
    if integration_key == "visma" and not (body.reason or "").strip():
        raise OnboardingValidationError("Reason is required for local Visma unlink.")
    session = _session_ops()._lock_session(db, session_id, body.version)
    _session_ops()._ensure_writable_session(session)
    tenant = _session_ops()._get_tenant(db, session.tenant_id)
    draft = _load_integrations_draft(db, session_id)
    if integration_key == "visma":
        OAuthCredentialRepository.delete(db, tenant.tenant_id, "visma")
        draft = draft.model_copy(update={"visma": VismaIntegrationConfig(requested=draft.visma.requested)})
    elif integration_key == "google_sheets":
        draft = draft.model_copy(
            update={"google_sheets": GoogleSheetsIntegrationConfig(requested=draft.google_sheets.requested)}
        )
    IntegrationVerificationStore.invalidate(db, session_id=session_id, integration_key=integration_key)
    OnboardingRepository.bump_integration_state_revision(session)
    OnboardingRepository.upsert_draft(db, session_id=session_id, step_key="integrations", payload=draft.model_dump())
    OnboardingRepository.bump_version(session, operator["id"])
    _sync_integrations_step_state(
        db, session_id=session_id, tenant=tenant, settings=settings, operator_id=operator["id"]
    )
    emit_onboarding_audit(
        db,
        tenant_id=session.tenant_id,
        action=INTEGRATION_CONFIGURATION_UPDATED,
        status="succeeded",
        details=_session_ops()._operator_audit_details(
            operator,
            session_id=session_id,
            reason=body.reason,
            extra={"integration_key": integration_key, "action": "local_unlink"},
        ),
    )
    _commit_or_audit_error(db)
    session = OnboardingRepository.get_session(db, session_id)
    return _session_ops()._build_session_response(db, session, settings=settings)


def replace_connection_integration(
    db: Session,
    *,
    session_id: str,
    operator: OperatorIdentity,
    integration_key: str,
    body: IntegrationActionRequest,
    settings: Settings,
    redirect_target: str,
) -> dict[str, Any]:
    local_unlink_integration(
        db,
        session_id=session_id,
        operator=operator,
        integration_key=integration_key,
        body=body,
        settings=settings,
    )
    return connect_integration(
        db,
        session_id=session_id,
        operator=operator,
        integration_key=integration_key,
        settings=settings,
        redirect_target=redirect_target,
    )
