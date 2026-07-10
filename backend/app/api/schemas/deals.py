from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.api.schemas.watches import (
    CoverageReportResponse,
    CtaActionResponse,
    LoyaltyPlanEntryResponse,
    ReadinessResponse,
    SemanticBadgeResponse,
    ValidationWarningResponse,
)
from app.db.models import DealFraming


class StoredDealResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    watch_id: str
    booking_id: str | None
    kind: str
    source: str
    offer_ref: str | None
    total_price: Decimal
    currency: str
    quality_index: float | None
    value_score: float | None
    price_percentile: float | None
    timing_advice: str | None
    framing: DealFraming
    summary_text: str | None
    coverage_report: CoverageReportResponse | None
    validation_warnings: list[ValidationWarningResponse]
    loyalty_plan: list[LoyaltyPlanEntryResponse]
    payload: dict[str, Any] | None
    status: str
    expires_at: datetime | None
    created_at: datetime
    readiness: ReadinessResponse | None = None
    badges: list[SemanticBadgeResponse] = Field(default_factory=list)
    cta_actions: list[CtaActionResponse] = Field(default_factory=list)


class DealTimelinePointResponse(BaseModel):
    observed_at: datetime
    price: Decimal
    currency: str
    label: str
    source: str
    price_percentile: float | None = None


class DealTimelineResponse(BaseModel):
    current_price: Decimal | None
    currency: str | None
    target_price: Decimal | None
    glide_limit: Decimal | None
    trend_summary: str
    points: list[DealTimelinePointResponse]


class ApprovalTokenResponse(BaseModel):
    deal_id: str
    token: str
    expires_at: datetime


class ApprovalTokenVerifyRequest(BaseModel):
    token: str


class ApprovalTokenVerifyResponse(BaseModel):
    deal_id: str
    valid: bool
    expires_at: datetime


class DealIntentConfirmRequest(BaseModel):
    token: str
    totp_code: str


class DealIntentResponse(BaseModel):
    deal_id: str
    status: str
    detail: str
    action_taken: dict[str, Any] | None = None


class DealRejectRequest(BaseModel):
    reason: str
