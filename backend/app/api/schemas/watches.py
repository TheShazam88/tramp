# ruff: noqa: E501
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import (
    AutoBookMode,
    DealFraming,
    DestinationMode,
    NotificationChannel,
    ObservationKind,
    RefreshInterval,
    TripMode,
    TripWatchStatus,
)


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_list(value: list[str] | None, *, uppercase: bool = False) -> list[str] | None:
    if value is None:
        return None

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        stripped = item.strip()
        if not stripped:
            continue
        normalized_item = stripped.upper() if uppercase else stripped
        if normalized_item not in seen:
            seen.add(normalized_item)
            normalized.append(normalized_item)
    return normalized


def _normalize_code(value: str | None) -> str | None:
    stripped = _strip_or_none(value)
    return stripped.upper() if stripped else None


class WatchBaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    trip_mode: TripMode = TripMode.FLIGHTS_THEN_HOTELS
    traveler_group_id: str | None = None
    traveler_ids: list[str] = Field(default_factory=list)
    origin_iatas: list[str] = Field(default_factory=list)
    destination_iatas: list[str] = Field(default_factory=list)
    destination_mode: DestinationMode = DestinationMode.FIXED
    flexible_region: str | None = Field(default=None, max_length=64)
    flexible_theme: str | None = Field(default=None, max_length=64)
    depart_date_from: date | None = None
    depart_date_to: date | None = None
    return_date_from: date | None = None
    return_date_to: date | None = None
    trip_min_nights: int | None = Field(default=None, ge=1, le=90)
    trip_max_nights: int | None = Field(default=None, ge=1, le=90)
    cabin_class: str | None = Field(default=None, max_length=32)
    max_stops: int | None = Field(default=None, ge=0, le=4)
    max_layover_minutes: int | None = Field(default=None, ge=0)
    min_connection_minutes: int | None = Field(default=None, ge=0)
    preferred_airlines: list[str] = Field(default_factory=list)
    preferred_alliances: list[str] = Field(default_factory=list)
    avoid_redeye: bool = False
    outbound_earliest_depart: time | None = None
    outbound_latest_depart: time | None = None
    outbound_arrive_by: time | None = None
    return_earliest_depart: time | None = None
    return_latest_depart: time | None = None
    return_arrive_by: time | None = None
    flight_budget_max: Decimal | None = None
    hotel_budget_per_night_max: Decimal | None = None
    max_total_trip_spend: Decimal | None = None
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    ideal_price: Decimal | None = None
    glide_start_days: int = 42
    glide_end_days: int = 3
    quality_floor: int = Field(default=40, ge=0, le=100)
    luxury_vs_savings: float = Field(default=0.6, ge=0, le=1)
    hotel_min_rating: float | None = Field(default=None, ge=0, le=5)
    hotel_area_lat: float | None = None
    hotel_area_lng: float | None = None
    hotel_radius_km: float | None = Field(default=None, ge=0)
    prefer_refundable: bool = False
    loyalty_weighting: float = Field(default=0.0, ge=0, le=1)
    value_target: float | None = Field(default=None, ge=0, le=100)
    band_tolerance: float = Field(default=0.10, ge=0, le=1)
    value_pressure: float = Field(default=0.0, ge=0, le=1)
    include_airbnb: bool = False
    refresh_interval: RefreshInterval = RefreshInterval.DAILY
    notify_channel: NotificationChannel = NotificationChannel.INHERIT
    want_car: bool = False
    auto_book_mode: AutoBookMode = AutoBookMode.ALWAYS_CONFIRM

    @field_validator("traveler_group_id")
    @classmethod
    def validate_traveler_group_id(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("origin_iatas", "destination_iatas", "preferred_airlines")
    @classmethod
    def normalize_code_lists(cls, value: list[str]) -> list[str]:
        return _normalize_list(value, uppercase=True) or []

    @field_validator("preferred_alliances")
    @classmethod
    def normalize_text_lists(cls, value: list[str]) -> list[str]:
        return _normalize_list(value) or []

    @field_validator("traveler_ids")
    @classmethod
    def normalize_traveler_ids(cls, value: list[str]) -> list[str]:
        return _normalize_list(value) or []

    @field_validator("flexible_region", "flexible_theme", "cabin_class")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("budget_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return _normalize_code(value)

    @model_validator(mode="after")
    def validate_ranges(self) -> WatchBaseRequest:
        if self.glide_end_days > self.glide_start_days:
            raise ValueError("glide_end_days cannot be greater than glide_start_days.")

        if self.trip_min_nights is not None and self.trip_max_nights is not None:
            if self.trip_min_nights > self.trip_max_nights:
                raise ValueError("trip_min_nights cannot be greater than trip_max_nights.")

        if self.destination_mode == DestinationMode.FIXED and not self.destination_iatas:
            raise ValueError("destination_iatas are required when destination_mode is fixed.")

        if self.destination_mode == DestinationMode.FLEXIBLE:
            if not self.flexible_region and not self.flexible_theme:
                raise ValueError(
                    "flexible_region or flexible_theme is required when destination_mode is flexible."
                )

        if (
            self.depart_date_from
            and self.depart_date_to
            and self.depart_date_from > self.depart_date_to
        ):
            raise ValueError("depart_date_from cannot be after depart_date_to.")

        if (
            self.return_date_from
            and self.return_date_to
            and self.return_date_from > self.return_date_to
        ):
            raise ValueError("return_date_from cannot be after return_date_to.")

        return self


class WatchCreateRequest(WatchBaseRequest):
    pass


class WatchUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    status: TripWatchStatus | None = None
    trip_mode: TripMode | None = None
    traveler_group_id: str | None = None
    traveler_ids: list[str] | None = None
    origin_iatas: list[str] | None = None
    destination_iatas: list[str] | None = None
    destination_mode: DestinationMode | None = None
    flexible_region: str | None = Field(default=None, max_length=64)
    flexible_theme: str | None = Field(default=None, max_length=64)
    depart_date_from: date | None = None
    depart_date_to: date | None = None
    return_date_from: date | None = None
    return_date_to: date | None = None
    trip_min_nights: int | None = Field(default=None, ge=1, le=90)
    trip_max_nights: int | None = Field(default=None, ge=1, le=90)
    cabin_class: str | None = Field(default=None, max_length=32)
    max_stops: int | None = Field(default=None, ge=0, le=4)
    max_layover_minutes: int | None = Field(default=None, ge=0)
    min_connection_minutes: int | None = Field(default=None, ge=0)
    preferred_airlines: list[str] | None = None
    preferred_alliances: list[str] | None = None
    avoid_redeye: bool | None = None
    outbound_earliest_depart: time | None = None
    outbound_latest_depart: time | None = None
    outbound_arrive_by: time | None = None
    return_earliest_depart: time | None = None
    return_latest_depart: time | None = None
    return_arrive_by: time | None = None
    flight_budget_max: Decimal | None = None
    hotel_budget_per_night_max: Decimal | None = None
    max_total_trip_spend: Decimal | None = None
    budget_currency: str | None = Field(default=None, min_length=3, max_length=3)
    ideal_price: Decimal | None = None
    glide_start_days: int | None = Field(default=None, ge=0)
    glide_end_days: int | None = Field(default=None, ge=0)
    quality_floor: int | None = Field(default=None, ge=0, le=100)
    luxury_vs_savings: float | None = Field(default=None, ge=0, le=1)
    hotel_min_rating: float | None = Field(default=None, ge=0, le=5)
    hotel_area_lat: float | None = None
    hotel_area_lng: float | None = None
    hotel_radius_km: float | None = Field(default=None, ge=0)
    prefer_refundable: bool | None = None
    loyalty_weighting: float | None = Field(default=None, ge=0, le=1)
    value_target: float | None = Field(default=None, ge=0, le=100)
    band_tolerance: float | None = Field(default=None, ge=0, le=1)
    value_pressure: float | None = Field(default=None, ge=0, le=1)
    include_airbnb: bool | None = None
    refresh_interval: RefreshInterval | None = None
    notify_channel: NotificationChannel | None = None
    want_car: bool | None = None
    auto_book_mode: AutoBookMode | None = None

    @field_validator("traveler_group_id")
    @classmethod
    def validate_traveler_group_id(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("origin_iatas", "destination_iatas", "preferred_airlines")
    @classmethod
    def normalize_code_lists(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_list(value, uppercase=True)

    @field_validator("preferred_alliances", "traveler_ids")
    @classmethod
    def normalize_text_lists(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_list(value)

    @field_validator("flexible_region", "flexible_theme", "cabin_class")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("budget_currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        return _normalize_code(value)


class DashboardHighlightResponse(BaseModel):
    label: str
    value: str
    note: str


class ReadinessResolutionResponse(BaseModel):
    code: str
    label: str
    path: str


class ReadinessResponse(BaseModel):
    score: int
    label: str
    blockers: list[str]
    warnings: list[str]
    resolutions: list[ReadinessResolutionResponse] = Field(default_factory=list)


class SemanticBadgeResponse(BaseModel):
    label: str
    tone: str


class CtaActionResponse(BaseModel):
    key: str
    label: str
    tone: str
    enabled: bool = True
    detail: str | None = None


class WatchDashboardCardResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    route: str
    dates: str
    travelers: str
    cabin: str
    status: TripWatchStatus
    framing: str
    best_now: str = Field(serialization_alias="bestNow")
    insight: str
    cadence: str
    deal_id: str | None = None
    current_deal_status: str | None = None
    search_label: str | None = None
    readiness: ReadinessResponse | None = None
    badges: list[SemanticBadgeResponse] = Field(default_factory=list)
    cta_actions: list[CtaActionResponse] = Field(default_factory=list)


class WatchDashboardResponse(BaseModel):
    highlights: list[DashboardHighlightResponse]
    watches: list[WatchDashboardCardResponse]


class WatchCurrentDealResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    kind: str
    framing: DealFraming
    total_price: Decimal
    currency: str
    quality_index: float | None
    value_score: float | None
    price_percentile: float | None
    timing_advice: str | None
    summary_text: str | None
    status: str
    created_at: datetime
    readiness: ReadinessResponse | None = None
    badges: list[SemanticBadgeResponse] = Field(default_factory=list)


class WatchResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    status: TripWatchStatus
    trip_mode: TripMode
    destination_mode: DestinationMode
    traveler_group_id: str | None
    traveler_group_name: str | None
    traveler_ids: list[str]
    traveler_names: list[str]
    origin_iatas: list[str]
    destination_iatas: list[str]
    flexible_region: str | None
    flexible_theme: str | None
    depart_date_from: date | None
    depart_date_to: date | None
    return_date_from: date | None
    return_date_to: date | None
    trip_min_nights: int | None
    trip_max_nights: int | None
    cabin_class: str | None
    max_stops: int | None
    max_layover_minutes: int | None
    min_connection_minutes: int | None
    preferred_airlines: list[str]
    preferred_alliances: list[str]
    avoid_redeye: bool
    flight_budget_max: Decimal | None
    hotel_budget_per_night_max: Decimal | None
    max_total_trip_spend: Decimal | None
    budget_currency: str | None
    ideal_price: Decimal | None
    glide_start_days: int
    glide_end_days: int
    quality_floor: int
    luxury_vs_savings: float
    hotel_min_rating: float | None
    prefer_refundable: bool
    loyalty_weighting: float
    value_target: float | None
    band_tolerance: float
    value_pressure: float
    include_airbnb: bool
    refresh_interval: RefreshInterval
    notify_channel: NotificationChannel
    want_car: bool
    auto_book_mode: AutoBookMode
    route: str
    dates_label: str
    travelers_label: str
    cabin_label: str
    cadence_label: str
    observation_count: int
    deal_count: int
    latest_observed_at: datetime | None
    current_deal: WatchCurrentDealResponse | None
    readiness: ReadinessResponse | None = None
    badges: list[SemanticBadgeResponse] = Field(default_factory=list)
    cta_actions: list[CtaActionResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class WatchDraftGroupResponse(BaseModel):
    id: str
    name: str
    traveler_ids: list[str]


class WatchDraftResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str
    traveler_groups: list[WatchDraftGroupResponse] = Field(serialization_alias="travelerGroups")
    selected_group_id: str | None = Field(serialization_alias="selectedGroupId")
    selected_group_name: str = Field(serialization_alias="selectedGroup")
    origins: str
    destination: str
    date_window: str = Field(serialization_alias="dateWindow")
    stay_length: str = Field(serialization_alias="stayLength")
    flight_budget: str = Field(serialization_alias="flightBudget")
    hotel_budget: str = Field(serialization_alias="hotelBudget")
    luxury_vs_savings: float = Field(serialization_alias="luxuryVsSavings")
    options: list[str]
    watch_defaults: dict[str, Any] = Field(serialization_alias="watchDefaults")


class ValidationWarningResponse(BaseModel):
    code: str
    severity: str
    message: str
    traveler_name: str | None = None


class LoyaltyPlanEntryResponse(BaseModel):
    traveler_name: str
    program_code: str
    alliance: str
    note: str


class CoverageReportResponse(BaseModel):
    confidence: str
    searched_sources: list[str]
    gaps: list[str]
    notes: list[str]


class NormalizedOfferResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    fingerprint_hash: str
    kind: ObservationKind
    source: str
    title: str
    total_price: Decimal
    currency: str
    quality_index: float
    value_score: float | None
    price_percentile: float | None
    timing_advice: str | None
    attributes: list[str]


class SearchNowDealResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    kind: str
    source: str
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
    status: str
    readiness: ReadinessResponse | None = None
    badges: list[SemanticBadgeResponse] = Field(default_factory=list)


class SearchNowResponse(BaseModel):
    observed_at: datetime
    observations_created: int
    deals_upserted: int
    coverage_report: CoverageReportResponse
    offers: list[NormalizedOfferResponse]
    proposed_deals: list[SearchNowDealResponse]
