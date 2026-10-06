from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import IntegrationEnvironment


class AdminIntegrationUpdateRequest(BaseModel):
    enabled: bool | None = None
    environment: IntegrationEnvironment | None = None
    feature_flags: dict[str, Any] | None = None
    credentials: dict[str, Any] | None = None
    credential_profile_id: str | None = None


class AdminIntegrationAcquisitionLinkResponse(BaseModel):
    label: str
    url: str


class AdminIntegrationAcquisitionGuideResponse(BaseModel):
    links: list[AdminIntegrationAcquisitionLinkResponse]
    account_requirements: list[str]
    steps: list[str]
    environment_notes: list[str]
    enables: list[str]


class AdminIntegrationResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    key: str
    label: str
    description: str
    category: str
    provider_key: str | None = None
    supports_shared_profile: bool
    compatible_profile_provider_keys: list[str]
    enabled: bool
    environment: IntegrationEnvironment
    runtime_connector: str
    feature_flags: dict[str, Any]
    credentials_masked: dict[str, Any]
    credential_source: str
    bootstrap_credentials_present: bool
    has_stored_credentials: bool
    updated_at: datetime | None
    updated_by: str | None
    credential_profile_id: str | None = None
    credential_profile_label: str | None = None
    credential_fields: list[dict[str, Any]]
    feature_flag_definitions: list[dict[str, Any]]
    validation_help: str | None
    guide: AdminIntegrationAcquisitionGuideResponse | None = None


class AdminIntegrationCategoryResponse(BaseModel):
    id: str
    title: str
    description: str


class AdminCredentialProfileCreateRequest(BaseModel):
    provider_key: str
    label: str
    credentials: dict[str, Any] | None = None


class AdminCredentialProfileUpdateRequest(BaseModel):
    label: str | None = None
    credentials: dict[str, Any] | None = None


class AdminCredentialProfileResponse(BaseModel):
    id: str
    provider_key: str
    label: str
    credentials_masked: dict[str, Any]
    updated_at: datetime | None
    updated_by: str | None
    usage_integration_keys: list[str]


class AdminIntegrationConnectionTestResponse(BaseModel):
    checked_at: datetime
    ok: bool
    connector: str
    message: str
    detail: dict[str, Any]
    warnings: list[str]


class AdminRuntimeSettingsResponse(BaseModel):
    mock_data_enabled: bool
    live_inventory_available: bool
    current_inventory_mode: str
    key_unlock_mode: str
    master_key_source: str


class AdminRuntimeSettingsUpdateRequest(BaseModel):
    mock_data_enabled: bool


class AdminTestDataPurgeRequest(BaseModel):
    confirmation: str
    plan_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class AdminTestDataPurgeResponse(BaseModel):
    dry_run: bool
    deleted_counts: dict[str, int]
    reset_watch_count: int
    plan_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    warnings: list[str]
    unreverted_feedback_count: int
    unknown_cancellation_count: int


class AdminBookingAttemptRecoveryRequest(BaseModel):
    confirmation: str


class AdminBookingAttemptRecoveryResponse(BaseModel):
    idempotency_key: str
    attempt_status: str
    recovery_required: bool
    deal_id: str
    deal_status: str
    booking_exists: bool
    booking_id: str | None


class AdminIntegrationsSummaryResponse(BaseModel):
    categories: list[AdminIntegrationCategoryResponse]
    providers: list[AdminIntegrationResponse]
    credential_profiles: list[AdminCredentialProfileResponse]
    feature_flags: list[dict[str, Any]]
    health_notes: list[str]
    runtime_settings: AdminRuntimeSettingsResponse
