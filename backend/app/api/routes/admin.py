# ruff: noqa: B008
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.admin_activity_service import (
    execute_test_data_purge,
    preview_test_data_purge,
)
from app.api.deps import require_admin
from app.api.schemas.integrations import (
    AdminBookingAttemptRecoveryRequest,
    AdminBookingAttemptRecoveryResponse,
    AdminCredentialProfileCreateRequest,
    AdminCredentialProfileResponse,
    AdminCredentialProfileUpdateRequest,
    AdminIntegrationCategoryResponse,
    AdminIntegrationConnectionTestResponse,
    AdminIntegrationResponse,
    AdminIntegrationsSummaryResponse,
    AdminIntegrationUpdateRequest,
    AdminRuntimeSettingsResponse,
    AdminRuntimeSettingsUpdateRequest,
    AdminTestDataPurgeRequest,
    AdminTestDataPurgeResponse,
)
from app.booking_recovery_service import recover_unresolved_booking_attempt
from app.config import get_settings
from app.db.models import User
from app.db.session import get_db_session
from app.integrations.service import (
    create_credential_profile,
    delete_credential_profile,
    get_integration,
    get_mock_data_enabled,
    list_credential_profiles,
    list_integration_categories,
    list_integrations,
    live_inventory_available,
    set_mock_data_enabled,
    test_connection,
    update_credential_profile,
    update_integration,
)

router = APIRouter()


def _map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _to_response(resolved: object) -> AdminIntegrationResponse:
    return AdminIntegrationResponse.model_validate(asdict(resolved))


def _summary_response(
    *, db: Session, category: str | None = None
) -> AdminIntegrationsSummaryResponse:
    items = list_integrations(db=db, category=category)
    enabled_flags = []
    health_notes = []
    for item in items:
        if item.enabled and item.environment.value != "off":
            enabled_flags.extend(
                [
                    {
                        "label": definition.label,
                        "enabled": item.feature_flags.get(definition.key, False),
                    }
                    for definition in item.feature_flag_definitions
                ]
            )
        health_notes.append(
            f"{item.label}: {item.environment.value} / "
            f"{'enabled' if item.enabled else 'disabled'} / {item.credential_source}"
        )
    provider_keys = sorted(
        {
            provider_key
            for item in items
            for provider_key in item.compatible_profile_provider_keys
            if provider_key
        }
    )
    return AdminIntegrationsSummaryResponse(
        categories=[
            AdminIntegrationCategoryResponse.model_validate(payload)
            for payload in list_integration_categories()
        ],
        providers=[_to_response(item) for item in items],
        credential_profiles=[
            AdminCredentialProfileResponse.model_validate(asdict(profile))
            for profile in list_credential_profiles(db=db, provider_keys=provider_keys or None)
        ],
        feature_flags=enabled_flags,
        health_notes=health_notes,
        runtime_settings=_runtime_settings_response(db),
    )


def _runtime_settings_response(db: Session) -> AdminRuntimeSettingsResponse:
    settings = get_settings()
    mock_data_enabled = get_mock_data_enabled(db=db)
    live_available = live_inventory_available(db=db)
    return AdminRuntimeSettingsResponse(
        mock_data_enabled=mock_data_enabled,
        live_inventory_available=live_available,
        current_inventory_mode=(
            "live" if live_available else "mock" if mock_data_enabled else "empty"
        ),
        key_unlock_mode=settings.key_unlock_mode.value,
        master_key_source=settings.master_key_source.value,
    )


@router.post(
    "/booking-attempts/{idempotency_key}/recover-failed",
    response_model=AdminBookingAttemptRecoveryResponse,
)
def recover_booking_attempt_record(
    idempotency_key: str,
    payload: AdminBookingAttemptRecoveryRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminBookingAttemptRecoveryResponse:
    try:
        result = recover_unresolved_booking_attempt(
            db=db,
            actor=current_user,
            idempotency_key=idempotency_key,
            confirmation=payload.confirmation,
        )
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc
    return AdminBookingAttemptRecoveryResponse.model_validate(asdict(result))


@router.get("/test-data/purge-preview", response_model=AdminTestDataPurgeResponse)
def preview_test_data_purge_record(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminTestDataPurgeResponse:
    try:
        plan = preview_test_data_purge(db=db)
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return AdminTestDataPurgeResponse(
        dry_run=True,
        deleted_counts=plan.deleted_counts,
        reset_watch_count=plan.reset_watch_count,
        plan_digest=plan.plan_digest,
        warnings=list(plan.warnings),
        unreverted_feedback_count=plan.unreverted_feedback_count,
        unknown_cancellation_count=plan.unknown_cancellation_count,
    )


@router.post("/test-data/purge", response_model=AdminTestDataPurgeResponse)
def purge_test_data_record(
    payload: AdminTestDataPurgeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminTestDataPurgeResponse:
    try:
        result = execute_test_data_purge(
            db=db,
            actor=current_user,
            confirmation=payload.confirmation,
            preview_digest=payload.plan_digest,
        )
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return AdminTestDataPurgeResponse(
        dry_run=False,
        deleted_counts=result.deleted_counts,
        reset_watch_count=result.reset_watch_count,
        plan_digest=result.plan_digest,
        warnings=list(result.warnings),
        unreverted_feedback_count=result.unreverted_feedback_count,
        unknown_cancellation_count=result.unknown_cancellation_count,
    )


@router.get("/integrations", response_model=AdminIntegrationsSummaryResponse)
async def list_integration_records(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminIntegrationsSummaryResponse:
    return _summary_response(db=db)


@router.get(
    "/integrations/categories/{category_key}", response_model=AdminIntegrationsSummaryResponse
)
async def get_integration_category(
    category_key: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminIntegrationsSummaryResponse:
    return _summary_response(db=db, category=category_key)


@router.get("/integrations/{integration_key}", response_model=AdminIntegrationResponse)
async def get_integration_record(
    integration_key: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminIntegrationResponse:
    try:
        return _to_response(get_integration(db=db, key=integration_key))
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.patch("/integrations/{integration_key}", response_model=AdminIntegrationResponse)
async def update_integration_record(
    integration_key: str,
    payload: AdminIntegrationUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminIntegrationResponse:
    try:
        resolved = update_integration(
            db=db,
            actor=current_user,
            key=integration_key,
            enabled=payload.enabled,
            environment=payload.environment,
            feature_flags=payload.feature_flags,
            credentials=payload.credentials,
            credential_profile_id=payload.credential_profile_id,
            fields_set=payload.model_fields_set,
        )
        return _to_response(resolved)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.post(
    "/integrations/{integration_key}/test-connection",
    response_model=AdminIntegrationConnectionTestResponse,
)
async def test_integration_record(
    integration_key: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminIntegrationConnectionTestResponse:
    try:
        result = test_connection(db=db, key=integration_key, actor=current_user)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc
    return AdminIntegrationConnectionTestResponse(
        checked_at=result.checked_at,
        ok=result.ok,
        connector=result.connector,
        message=result.message,
        detail=result.detail,
        warnings=result.warnings,
    )


@router.patch("/runtime-settings", response_model=AdminRuntimeSettingsResponse)
async def update_runtime_settings(
    payload: AdminRuntimeSettingsUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminRuntimeSettingsResponse:
    set_mock_data_enabled(
        db=db,
        actor=current_user,
        enabled=payload.mock_data_enabled,
    )
    return _runtime_settings_response(db)


@router.post("/credential-profiles", response_model=AdminCredentialProfileResponse)
async def create_credential_profile_record(
    payload: AdminCredentialProfileCreateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminCredentialProfileResponse:
    try:
        profile = create_credential_profile(
            db=db,
            actor=current_user,
            provider_key=payload.provider_key,
            label=payload.label,
            credentials=payload.credentials,
        )
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc
    return AdminCredentialProfileResponse.model_validate(asdict(profile))


@router.patch("/credential-profiles/{profile_id}", response_model=AdminCredentialProfileResponse)
async def update_credential_profile_record(
    profile_id: str,
    payload: AdminCredentialProfileUpdateRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> AdminCredentialProfileResponse:
    try:
        profile = update_credential_profile(
            db=db,
            actor=current_user,
            profile_id=profile_id,
            label=payload.label,
            credentials=payload.credentials,
        )
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc
    return AdminCredentialProfileResponse.model_validate(asdict(profile))


@router.delete("/credential-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential_profile_record(
    profile_id: str,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db_session),
) -> None:
    try:
        delete_credential_profile(db=db, profile_id=profile_id)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc
