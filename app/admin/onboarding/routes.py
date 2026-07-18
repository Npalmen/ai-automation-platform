"""FastAPI routes for operator onboarding (Kapitel 9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.admin.onboarding.errors import (
    OnboardingAuditError,
    OnboardingConflictError,
    OnboardingNotFoundError,
    OnboardingStaleActivationPlanError,
    OnboardingStaleReadinessError,
    OnboardingValidationError,
    OnboardingVersionConflictError,
)
from app.admin.onboarding.registry_presenter import present_registries
from app.admin.onboarding.registry_schemas import ActivationPlanResponse, OnboardingRegistriesResponse
from app.admin.onboarding.schemas import (
    ActivateRequest,
    ActivateResponse,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    AutomationPatchRequest,
    CancelRequest,
    ConnectIntegrationRequest,
    ExternalRoutingStepResponse,
    IdentityPatchRequest,
    IntegrationStatusResponse,
    IntegrationsStepResponse,
    ModulesPatchRequest,
    OnboardingCreateRequest,
    OnboardingListResponse,
    OnboardingSessionResponse,
    ReadinessResponse,
    RoutingPreviewResponse,
    Slice2aStepResponse,
    StepDetailResponse,
)
from app.admin.onboarding.draft_schemas import (
    DataStartPatchRequest,
    RoutingPatchRequest,
    RoutingResetRequest,
    ServiceProfilePatchRequest,
)
from app.admin.onboarding.integration_draft_schemas import (
    ExternalRoutingPatchRequest,
    ExternalRoutingResetRequest,
    IntegrationsPatchRequest,
    IntegrationActionRequest,
)
from app.admin.onboarding.slice2b_external_routing_service import (
    get_external_routing_step,
    patch_external_routing_step,
    preview_external_routing,
    reset_external_routing,
)
from app.admin.onboarding.slice2b_integrations_service import (
    connect_integration,
    get_integration_status,
    get_integrations_step,
    local_unlink_integration,
    patch_integrations_step,
    replace_connection_integration,
    unrequest_integration,
    verify_integration,
)
from app.admin.onboarding.slice2a_service import (
    get_data_start_step,
    get_routing_step,
    get_service_profile_step,
    patch_data_start_step,
    patch_routing_step,
    patch_service_profile_step,
    preview_routing,
    reset_routing_overrides,
)
from app.admin.onboarding.service import (
    activate_onboarding_session,
    cancel_onboarding_session,
    create_onboarding_api_key,
    create_onboarding_session,
    get_activation_plan,
    get_onboarding_session,
    get_step_detail,
    list_onboarding_sessions,
    patch_automation,
    patch_identity,
    patch_modules,
    run_readiness,
)
from app.core.admin_auth import (
    require_admin_api_key,
    require_operator_role,
    resolve_authenticated_operator,
)
from app.core.admin_session import require_same_origin
from app.core.settings import Settings, get_settings
from app.api.dependencies import get_db

router = APIRouter(prefix="/admin/onboarding", tags=["admin"])

_OPERATOR_WRITE_ROLES = frozenset({"operations", "admin"})
_OPERATOR_READ_ROLES = frozenset({"read_only", "operations", "admin"})
_ADMIN_ROLES = frozenset({"admin"})


def _run_onboarding_action(handler):
    try:
        return handler()
    except OnboardingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OnboardingVersionConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except OnboardingStaleReadinessError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except OnboardingStaleActivationPlanError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except OnboardingConflictError as exc:
        detail: dict = {"code": exc.code, "message": str(exc)}
        if exc.session_id:
            detail["session_id"] = exc.session_id
        raise HTTPException(status_code=409, detail=detail) from exc
    except OnboardingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OnboardingAuditError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("", response_model=OnboardingListResponse)
def admin_list_onboarding_sessions(
    request: Request,
    open_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return list_onboarding_sessions(db, open_only=open_only, limit=limit, settings=settings)


@router.get("/registries", response_model=OnboardingRegistriesResponse)
def admin_get_onboarding_registries(
    request: Request,
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return present_registries()


@router.post("", response_model=OnboardingSessionResponse, status_code=201)
def admin_create_onboarding_session(
    body: OnboardingCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: create_onboarding_session(
            db,
            operator=operator,
            company_name=body.company_name,
            slug=body.slug,
            org_number=body.org_number,
            primary_contact=body.primary_contact,
            contact_email=body.contact_email,
            phone=body.phone,
            timezone=body.timezone,
            language=body.language,
            settings=settings,
        )
    )


@router.get("/{session_id}/activation-plan", response_model=ActivationPlanResponse)
def admin_get_activation_plan(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_activation_plan(db, session_id, settings=settings)
    )


@router.get("/{session_id}", response_model=OnboardingSessionResponse)
def admin_get_onboarding_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_onboarding_session(db, session_id, settings=settings)
    )


@router.patch("/{session_id}/identity", response_model=OnboardingSessionResponse)
def admin_patch_onboarding_identity(
    session_id: str,
    body: IdentityPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_identity(
            db,
            session_id=session_id,
            operator=operator,
            payload=body.model_dump(exclude={"version"}, exclude_none=True),
            expected_version=body.version,
            settings=settings,
        )
    )


@router.patch("/{session_id}/modules", response_model=OnboardingSessionResponse)
def admin_patch_onboarding_modules(
    session_id: str,
    body: ModulesPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_modules(
            db,
            session_id=session_id,
            operator=operator,
            capabilities=body.capabilities,
            integrations=body.integrations,
            expected_version=body.version,
            settings=settings,
        )
    )


@router.patch("/{session_id}/automation", response_model=OnboardingSessionResponse)
def admin_patch_onboarding_automation(
    session_id: str,
    body: AutomationPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_automation(
            db,
            session_id=session_id,
            operator=operator,
            preset_key=body.preset_key,
            preset_version=body.preset_version,
            expected_version=body.version,
            settings=settings,
        )
    )


@router.get("/{session_id}/service-profile", response_model=Slice2aStepResponse)
def admin_get_service_profile_step(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_service_profile_step(db, session_id, settings=settings)
    )


@router.patch("/{session_id}/service-profile", response_model=OnboardingSessionResponse)
def admin_patch_service_profile_step(
    session_id: str,
    body: ServiceProfilePatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_service_profile_step(
            db,
            session_id=session_id,
            operator=operator,
            body=body,
            settings=settings,
        )
    )


@router.get("/{session_id}/routing", response_model=Slice2aStepResponse)
def admin_get_routing_step(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_routing_step(db, session_id, settings=settings)
    )


@router.patch("/{session_id}/routing", response_model=OnboardingSessionResponse)
def admin_patch_routing_step(
    session_id: str,
    body: RoutingPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_routing_step(
            db,
            session_id=session_id,
            operator=operator,
            body=body,
            settings=settings,
        )
    )


@router.post("/{session_id}/routing-preview", response_model=RoutingPreviewResponse)
def admin_preview_routing(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: preview_routing(db, session_id, settings=settings)
    )


@router.post("/{session_id}/routing-reset", response_model=Slice2aStepResponse)
def admin_reset_routing(
    session_id: str,
    body: RoutingResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: reset_routing_overrides(
            db,
            session_id=session_id,
            operator=operator,
            body=body,
            settings=settings,
        )
    )


@router.get("/{session_id}/data-start", response_model=Slice2aStepResponse)
def admin_get_data_start_step(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_data_start_step(db, session_id, settings=settings)
    )


@router.patch("/{session_id}/data-start", response_model=OnboardingSessionResponse)
def admin_patch_data_start_step(
    session_id: str,
    body: DataStartPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_data_start_step(
            db,
            session_id=session_id,
            operator=operator,
            body=body,
            settings=settings,
        )
    )


@router.get("/{session_id}/integrations", response_model=IntegrationsStepResponse)
def admin_get_integrations_step(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_integrations_step(db, session_id, settings=settings)
    )


@router.patch("/{session_id}/integrations", response_model=OnboardingSessionResponse)
def admin_patch_integrations_step(
    session_id: str,
    body: IntegrationsPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_integrations_step(
            db,
            session_id=session_id,
            operator=operator,
            body=body,
            settings=settings,
        )
    )


@router.post("/{session_id}/integrations/{integration_key}/connect")
def admin_connect_integration(
    session_id: str,
    integration_key: str,
    body: ConnectIntegrationRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: connect_integration(
            db,
            session_id=session_id,
            operator=operator,
            integration_key=integration_key,
            settings=settings,
            redirect_target=body.redirect_target,
        )
    )


@router.get("/{session_id}/integrations/{integration_key}/status", response_model=IntegrationStatusResponse)
def admin_integration_status(
    session_id: str,
    integration_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_integration_status(db, session_id, integration_key, settings=settings)
    )


@router.post("/{session_id}/integrations/{integration_key}/verify", response_model=IntegrationStatusResponse)
def admin_verify_integration(
    session_id: str,
    integration_key: str,
    body: IntegrationActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    _ = body
    return _run_onboarding_action(
        lambda: verify_integration(
            db,
            session_id=session_id,
            operator=operator,
            integration_key=integration_key,
            settings=settings,
        )
    )


@router.post("/{session_id}/integrations/{integration_key}/unrequest", response_model=OnboardingSessionResponse)
def admin_unrequest_integration(
    session_id: str,
    integration_key: str,
    body: IntegrationActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: unrequest_integration(
            db,
            session_id=session_id,
            operator=operator,
            integration_key=integration_key,
            body=body,
            settings=settings,
        )
    )


@router.post("/{session_id}/integrations/{integration_key}/local-unlink", response_model=OnboardingSessionResponse)
def admin_local_unlink_integration(
    session_id: str,
    integration_key: str,
    body: IntegrationActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: local_unlink_integration(
            db,
            session_id=session_id,
            operator=operator,
            integration_key=integration_key,
            body=body,
            settings=settings,
        )
    )


@router.post("/{session_id}/integrations/{integration_key}/replace-connection")
def admin_replace_connection_integration(
    session_id: str,
    integration_key: str,
    body: ConnectIntegrationRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: replace_connection_integration(
            db,
            session_id=session_id,
            operator=operator,
            integration_key=integration_key,
            body=IntegrationActionRequest(version=body.version),
            settings=settings,
            redirect_target=body.redirect_target,
        )
    )


@router.get("/{session_id}/external-routing", response_model=ExternalRoutingStepResponse)
def admin_get_external_routing(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: get_external_routing_step(db, session_id, settings=settings)
    )


@router.patch("/{session_id}/external-routing", response_model=OnboardingSessionResponse)
def admin_patch_external_routing(
    session_id: str,
    body: ExternalRoutingPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: patch_external_routing_step(
            db,
            session_id=session_id,
            operator=operator,
            body=body,
            settings=settings,
        )
    )


@router.post("/{session_id}/external-routing-preview", response_model=RoutingPreviewResponse)
def admin_external_routing_preview(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    return _run_onboarding_action(
        lambda: preview_external_routing(db, session_id, settings=settings)
    )


@router.post("/{session_id}/external-routing-reset", response_model=OnboardingSessionResponse)
def admin_external_routing_reset(
    session_id: str,
    body: ExternalRoutingResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: reset_external_routing(
            db,
            session_id=session_id,
            operator=operator,
            body=body,
            settings=settings,
        )
    )


@router.get("/{session_id}/steps/{step_key}", response_model=StepDetailResponse)
def admin_get_onboarding_step(
    session_id: str,
    step_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_api_key),
    x_admin_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
):
    resolve_authenticated_operator(request, x_admin_api_key)
    if step_key not in ("integrations",):
        raise HTTPException(status_code=404, detail=f"Unknown read-only step '{step_key}'.")
    return _run_onboarding_action(
        lambda: get_step_detail(db, session_id, step_key, settings=settings)
    )


@router.post("/{session_id}/readiness", response_model=ReadinessResponse)
def admin_run_onboarding_readiness(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: run_readiness(
            db,
            session_id=session_id,
            operator=operator,
            settings=settings,
        )
    )


@router.post("/{session_id}/activate", response_model=ActivateResponse)
def admin_activate_onboarding_session(
    session_id: str,
    body: ActivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_ADMIN_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: activate_onboarding_session(
            db,
            session_id=session_id,
            operator=operator,
            reason=body.reason,
            confirmation_phrase=body.confirmation_phrase,
            expected_version=body.version,
            readiness_check_version=body.readiness_check_version,
            plan_hash=body.plan_hash,
            acknowledged_warning_ids=body.acknowledged_warning_ids,
            settings=settings,
        )
    )


@router.post("/{session_id}/cancel", response_model=OnboardingSessionResponse)
def admin_cancel_onboarding_session(
    session_id: str,
    body: CancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    settings: Settings = Depends(get_settings),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: cancel_onboarding_session(
            db,
            session_id=session_id,
            operator=operator,
            reason=body.reason,
            expected_version=body.version,
            settings=settings,
        )
    )


@router.post("/{session_id}/api-key", response_model=ApiKeyCreateResponse)
def admin_create_onboarding_api_key(
    session_id: str,
    body: ApiKeyCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_ADMIN_ROLES)),
):
    require_same_origin(request)
    return _run_onboarding_action(
        lambda: create_onboarding_api_key(
            db,
            session_id=session_id,
            operator=operator,
            reason=body.reason,
            confirmation=body.confirmation,
            expected_version=body.version,
        )
    )
