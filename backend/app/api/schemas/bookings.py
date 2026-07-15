from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import (
    BookingAttemptStatus,
    BookingStatus,
    CancellationProvenance,
    CancellationStatus,
    DisruptionStatus,
    DisruptionType,
    NotificationDeliveryStatus,
)


class ApproveBookingRequest(BaseModel):
    deal_id: str
    approval_token: str = Field(min_length=32)
    totp_code: str = Field(min_length=6, max_length=6)
    master_key_passphrase: str | None = Field(default=None, min_length=1, max_length=512)
    payment_method_id: str
    idempotency_key: str = Field(min_length=8, max_length=255)

    @field_validator("totp_code")
    @classmethod
    def validate_totp_code(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("TOTP code must be numeric.")
        return value


class BookingConflictDetail(BaseModel):
    code: str
    message: str
    safe_to_retry: bool = False


class CancellationCreateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)
    approval_token: str = Field(min_length=32)
    totp_code: str = Field(min_length=6, max_length=6)
    master_key_passphrase: str | None = Field(default=None, min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=8, max_length=255)

    @field_validator("totp_code")
    @classmethod
    def validate_totp_code(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("TOTP code must be numeric.")
        return value


class CancellationApprovalTokenResponse(BaseModel):
    booking_id: str
    token: str
    expires_at: datetime


class CancellationResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    booking_id: str
    reason: str | None
    refund_expected: Decimal | None
    refund_received: Decimal | None
    currency: str | None
    status: CancellationStatus
    provider: str | None = None
    execution_simulated: bool | None = None
    provenance: CancellationProvenance = CancellationProvenance.UNKNOWN
    requested_at: datetime
    resolved_at: datetime | None
    idempotent_replay: bool = False


class NotificationDeliveryResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    channel: str
    transport: str
    destination: str | None
    message_type: str
    status: NotificationDeliveryStatus
    attempted_at: datetime
    delivered_at: datetime | None
    error_text: str | None


class DisruptionResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    booking_id: str
    type: DisruptionType
    status: DisruptionStatus
    detail: dict[str, Any] | None
    detected_at: datetime
    notified_at: datetime | None
    resolved_at: datetime | None


class BookingResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    deal_id: str
    watch_id: str
    provider: str
    provider_booking_ref: str | None
    status: BookingStatus
    idempotency_key: str
    amount_charged: Decimal | None
    currency: str | None
    documents: dict[str, Any] | None
    loyalty_attached: dict[str, Any] | None
    loyalty_manual_followup: bool
    booked_at: datetime | None
    error_text: str | None
    provider_correlation_id: str | None = None
    ticketing_state: str | None = None
    calendar_event_id: str | None = None
    calendar_detail: str | None = None
    cancellation: CancellationResponse | None
    disruptions: list[DisruptionResponse] = Field(default_factory=list)
    notifications: list[NotificationDeliveryResponse] = Field(default_factory=list)
    tramp_stamps_awarded: int = 0
    tramp_stamp_balance: int = 0
    idempotent_replay: bool = False


class BookingListResponse(BaseModel):
    items: list[BookingResponse]


class BookingAttemptReconciliationResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    idempotency_key: str
    deal_id: str
    payment_method_id: str
    status: BookingAttemptStatus
    code: str
    message: str
    safe_to_retry: bool
    recovery_required: bool
    booking: BookingResponse | None = None
    started_at: datetime
    finished_at: datetime | None = None
