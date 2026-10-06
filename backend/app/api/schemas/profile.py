# ruff: noqa: E501
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import (
    Alliance,
    NotificationChannel,
    ProgramType,
    SeatPreference,
    TravelerRelationship,
)


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_optional_upper(value: str | None) -> str | None:
    stripped = _strip_or_none(value)
    return stripped.upper() if stripped else None


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


class BillingAddressModel(BaseModel):
    line1: str = Field(min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=120)
    region: str | None = Field(default=None, max_length=120)
    postal_code: str = Field(min_length=1, max_length=32)
    country: str = Field(min_length=2, max_length=2)

    @field_validator("line1", "city", "postal_code")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("line2", "region")
    @classmethod
    def validate_optional_strings(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        return value.strip().upper()


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    email: str
    role: str
    onboarding_completed: bool
    default_notify_channel: NotificationChannel
    telegram_chat_id: str | None
    totp_enabled: bool
    global_max_auto_book_amount: Decimal | None
    weekly_max_spend: Decimal | None
    weekly_max_bookings: int | None
    annual_travel_budget: Decimal | None
    annual_budget_currency: str | None


class UserSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_notify_channel: NotificationChannel | None = None
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    global_max_auto_book_amount: Decimal | None = None
    weekly_max_spend: Decimal | None = None
    weekly_max_bookings: int | None = Field(default=None, ge=0)
    annual_travel_budget: Decimal | None = None
    annual_budget_currency: str | None = Field(default=None, min_length=3, max_length=3)

    @field_validator("telegram_chat_id")
    @classmethod
    def validate_telegram_chat_id(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("annual_budget_currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return _normalize_optional_upper(value)


class PreferenceWindowModel(BaseModel):
    start: str | None = None
    end: str | None = None
    arrive_by: str | None = None


class UserPreferenceResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    home_airports: list[str]
    default_cabin: str | None
    default_luxury_vs_savings: float
    preferred_airlines: list[str]
    avoided_airlines: list[str]
    preferred_alliances: list[str]
    preferred_hotel_brands: list[str]
    avoided_hotel_brands: list[str]
    default_hotel_min_rating: float | None
    avoid_redeye: bool
    default_max_layover_minutes: int | None
    default_min_connection_minutes: int | None
    default_outbound_window: dict[str, Any] | None
    default_return_window: dict[str, Any] | None
    prefer_refundable: bool
    seat_auto_select: bool
    default_notify_channel: NotificationChannel
    quiet_hours_start: time | None
    quiet_hours_end: time | None
    quiet_hours_timezone: str | None = None


class UserPreferenceUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home_airports: list[str] | None = None
    default_cabin: str | None = Field(default=None, max_length=32)
    default_luxury_vs_savings: float | None = Field(default=None, ge=0, le=1)
    preferred_airlines: list[str] | None = None
    avoided_airlines: list[str] | None = None
    preferred_alliances: list[str] | None = None
    preferred_hotel_brands: list[str] | None = None
    avoided_hotel_brands: list[str] | None = None
    default_hotel_min_rating: float | None = Field(default=None, ge=0, le=5)
    avoid_redeye: bool | None = None
    default_max_layover_minutes: int | None = Field(default=None, ge=0)
    default_min_connection_minutes: int | None = Field(default=None, ge=0)
    default_outbound_window: PreferenceWindowModel | dict[str, Any] | None = None
    default_return_window: PreferenceWindowModel | dict[str, Any] | None = None
    prefer_refundable: bool | None = None
    seat_auto_select: bool | None = None
    default_notify_channel: NotificationChannel | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    quiet_hours_timezone: str | None = None

    @field_validator("quiet_hours_timezone")
    @classmethod
    def validate_quiet_hours_timezone(cls, value: str | None) -> str | None:
        name = _strip_or_none(value)
        if name is None:
            return None
        try:
            ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Choose a valid IANA timezone.") from exc
        return name

    @field_validator("home_airports", "preferred_airlines", "avoided_airlines")
    @classmethod
    def normalize_code_lists(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_list(value, uppercase=True)

    @field_validator("preferred_alliances", "preferred_hotel_brands", "avoided_hotel_brands")
    @classmethod
    def normalize_text_lists(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_list(value)

    @field_validator("default_cabin")
    @classmethod
    def validate_default_cabin(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class LoyaltyProgramModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_type: ProgramType = ProgramType.AIRLINE
    program_code: str = Field(min_length=1, max_length=32)
    account_number: str = Field(min_length=1, max_length=128)
    alliance: Alliance | None = None
    status_tier: str | None = Field(default=None, max_length=64)
    is_favorite: bool = False

    @field_validator("program_code", "account_number", "status_tier")
    @classmethod
    def validate_strings(cls, value: str | None) -> str | None:
        stripped = _strip_or_none(value)
        if value is not None and stripped is None:
            raise ValueError("Value may not be blank.")
        return stripped

    @field_validator("program_code")
    @classmethod
    def normalize_program_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("account_number")
    @classmethod
    def normalize_account_number(cls, value: str) -> str:
        return value.strip()


class LoyaltyProgramResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    program_type: ProgramType
    program_code: str
    account_number: str
    alliance: Alliance
    status_tier: str | None
    is_favorite: bool


class TravelerBase(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    traveler_relationship: TravelerRelationship
    display_name: str = Field(min_length=1, max_length=120)
    legal_first_name: str = Field(min_length=1, max_length=120)
    legal_last_name: str = Field(min_length=1, max_length=120)
    dob: date
    gender: str | None = Field(default=None, max_length=32)
    nationality: str = Field(min_length=2, max_length=2)
    residency_country: str | None = Field(default=None, min_length=2, max_length=2)
    passport_number: str | None = Field(default=None, max_length=64)
    passport_country: str | None = Field(default=None, min_length=2, max_length=2)
    passport_expiry: date | None = None
    known_traveler_number: str | None = Field(default=None, max_length=64)
    redress_number: str | None = Field(default=None, max_length=64)
    seat_pref: SeatPreference = SeatPreference.NO_PREFERENCE
    meal_pref: str | None = Field(default=None, max_length=64)
    accessibility_needs: str | None = None
    infant_on_lap: bool = False
    loyalty_program_code: str | None = Field(default=None, max_length=32)
    loyalty_account_number: str | None = Field(default=None, max_length=128)
    loyalty_alliance: Alliance | None = None
    loyalty_status_tier: str | None = Field(default=None, max_length=64)
    preferred_earning_for_alliance: bool = False
    loyalty_programs: list[LoyaltyProgramModel] = Field(default_factory=list)

    @field_validator(
        "display_name",
        "legal_first_name",
        "legal_last_name",
        "passport_number",
        "known_traveler_number",
        "redress_number",
        "meal_pref",
        "gender",
        "loyalty_program_code",
        "loyalty_account_number",
        "loyalty_status_tier",
    )
    @classmethod
    def validate_strings(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("accessibility_needs")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("nationality", "residency_country", "passport_country")
    @classmethod
    def validate_country_codes(cls, value: str | None) -> str | None:
        return _normalize_optional_upper(value)

    @model_validator(mode="after")
    def validate_passport_fields(self) -> TravelerBase:
        passport_fields = [self.passport_number, self.passport_country, self.passport_expiry]
        populated_fields = sum(value is not None for value in passport_fields)
        if populated_fields not in {0, 3}:
            raise ValueError(
                "passport_number, passport_country, and passport_expiry must be provided together."
            )

        loyalty_fields = [self.loyalty_program_code, self.loyalty_account_number]
        populated_loyalty_fields = sum(value is not None for value in loyalty_fields)
        if populated_loyalty_fields not in {0, 2}:
            raise ValueError(
                "loyalty_program_code and loyalty_account_number must be provided together."
            )
        if self.loyalty_programs:
            if populated_loyalty_fields:
                raise ValueError(
                    "Use loyalty_programs for multiple loyalty accounts or the legacy single loyalty fields, not both."
                )
            favorite_count = sum(program.is_favorite for program in self.loyalty_programs)
            if favorite_count > 1:
                raise ValueError("Only one loyalty program may be marked as favorite.")
            seen_program_codes: set[tuple[str, ProgramType]] = set()
            for program in self.loyalty_programs:
                unique_key = (program.program_code, program.program_type)
                if unique_key in seen_program_codes:
                    raise ValueError(
                        "Duplicate loyalty program codes are not allowed for one traveler."
                    )
                seen_program_codes.add(unique_key)
        elif populated_loyalty_fields == 2:
            self.loyalty_programs = [
                LoyaltyProgramModel(
                    program_code=self.loyalty_program_code,
                    account_number=self.loyalty_account_number,
                    alliance=self.loyalty_alliance,
                    status_tier=self.loyalty_status_tier,
                    is_favorite=self.preferred_earning_for_alliance,
                )
            ]
        return self


class TravelerCreateRequest(TravelerBase):
    model_config = ConfigDict(extra="forbid")


class TravelerUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    traveler_relationship: TravelerRelationship | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    legal_first_name: str | None = Field(default=None, min_length=1, max_length=120)
    legal_last_name: str | None = Field(default=None, min_length=1, max_length=120)
    dob: date | None = None
    gender: str | None = Field(default=None, max_length=32)
    nationality: str | None = Field(default=None, min_length=2, max_length=2)
    residency_country: str | None = Field(default=None, min_length=2, max_length=2)
    passport_number: str | None = Field(default=None, max_length=64)
    passport_country: str | None = Field(default=None, min_length=2, max_length=2)
    passport_expiry: date | None = None
    known_traveler_number: str | None = Field(default=None, max_length=64)
    redress_number: str | None = Field(default=None, max_length=64)
    seat_pref: SeatPreference | None = None
    meal_pref: str | None = Field(default=None, max_length=64)
    accessibility_needs: str | None = None
    infant_on_lap: bool | None = None
    loyalty_program_code: str | None = Field(default=None, max_length=32)
    loyalty_account_number: str | None = Field(default=None, max_length=128)
    loyalty_alliance: Alliance | None = None
    loyalty_status_tier: str | None = Field(default=None, max_length=64)
    preferred_earning_for_alliance: bool | None = None
    loyalty_programs: list[LoyaltyProgramModel] | None = None

    @field_validator(
        "display_name",
        "legal_first_name",
        "legal_last_name",
        "passport_number",
        "known_traveler_number",
        "redress_number",
        "meal_pref",
        "gender",
        "loyalty_program_code",
        "loyalty_account_number",
        "loyalty_status_tier",
    )
    @classmethod
    def validate_strings(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("accessibility_needs")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("nationality", "residency_country", "passport_country")
    @classmethod
    def validate_country_codes(cls, value: str | None) -> str | None:
        return _normalize_optional_upper(value)

    @model_validator(mode="after")
    def validate_loyalty_payload(self) -> TravelerUpdateRequest:
        populated_legacy = [
            self.loyalty_program_code,
            self.loyalty_account_number,
        ]
        populated_legacy_count = sum(value is not None for value in populated_legacy)
        if self.loyalty_programs is not None:
            if populated_legacy_count:
                raise ValueError(
                    "Use loyalty_programs for multiple loyalty accounts or the legacy single loyalty fields, not both."
                )
            favorite_count = sum(program.is_favorite for program in self.loyalty_programs)
            if favorite_count > 1:
                raise ValueError("Only one loyalty program may be marked as favorite.")
            seen_program_codes: set[tuple[str, ProgramType]] = set()
            for program in self.loyalty_programs:
                unique_key = (program.program_code, program.program_type)
                if unique_key in seen_program_codes:
                    raise ValueError(
                        "Duplicate loyalty program codes are not allowed for one traveler."
                    )
                seen_program_codes.add(unique_key)
        elif populated_legacy_count == 1:
            raise ValueError(
                "loyalty_program_code and loyalty_account_number must be provided together."
            )
        return self


class TravelerResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    traveler_relationship: TravelerRelationship
    display_name: str
    legal_first_name: str
    legal_last_name: str
    dob: date
    gender: str | None
    nationality: str
    residency_country: str | None
    passport_number: str | None
    passport_country: str | None
    passport_expiry: date | None
    known_traveler_number: str | None
    redress_number: str | None
    seat_pref: SeatPreference
    meal_pref: str | None
    accessibility_needs: str | None
    infant_on_lap: bool
    loyalty_program_code: str | None
    loyalty_account_number: str | None
    loyalty_alliance: Alliance | None
    loyalty_status_tier: str | None
    preferred_earning_for_alliance: bool
    loyalty_programs: list[LoyaltyProgramResponse]
    created_at: datetime


class TravelerGroupCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    traveler_ids: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return value.strip()


class TravelerGroupUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    traveler_ids: list[str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class TravelerGroupResponse(BaseModel):
    id: str
    name: str
    traveler_ids: list[str]


class PaymentMethodCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=64)
    cardholder_name: str = Field(min_length=1, max_length=120)
    card_number: str = Field(min_length=12, max_length=32)
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2000, le=3000)
    provider_token: str | None = Field(default=None, max_length=255)
    billing_address: BillingAddressModel | None = None

    @field_validator("label", "brand", "cardholder_name", "provider_token")
    @classmethod
    def validate_strings(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("card_number")
    @classmethod
    def validate_card_number(cls, value: str) -> str:
        digits_only = "".join(character for character in value if character.isdigit())
        if len(digits_only) < 12:
            raise ValueError("Card number must contain at least 12 digits.")
        return digits_only


class PaymentMethodUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(default=None, min_length=1, max_length=120)
    brand: str | None = Field(default=None, max_length=64)
    cardholder_name: str | None = Field(default=None, min_length=1, max_length=120)
    card_number: str | None = Field(default=None, min_length=12, max_length=32)
    exp_month: int | None = Field(default=None, ge=1, le=12)
    exp_year: int | None = Field(default=None, ge=2000, le=3000)
    provider_token: str | None = Field(default=None, max_length=255)
    billing_address: BillingAddressModel | None = None

    @field_validator("label", "brand", "cardholder_name", "provider_token")
    @classmethod
    def validate_strings(cls, value: str | None) -> str | None:
        return _strip_or_none(value)

    @field_validator("card_number")
    @classmethod
    def validate_card_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        digits_only = "".join(character for character in value if character.isdigit())
        if len(digits_only) < 12:
            raise ValueError("Card number must contain at least 12 digits.")
        return digits_only


class PaymentMethodResponse(BaseModel):
    id: str
    label: str
    brand: str | None
    last4: str | None
    cardholder_name: str | None
    exp_month: int | None
    exp_year: int | None
    provider_token: str | None
    billing_address: BillingAddressModel | None


class TripTemplateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    watch_payload: dict[str, Any]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return value.strip()


class TripTemplateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    watch_payload: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _strip_or_none(value)


class TripTemplateResponse(BaseModel):
    id: str
    name: str
    watch_payload: dict[str, Any]


class HouseholdWorkspaceSummaryResponse(BaseModel):
    traveler_count: int
    traveler_group_count: int
    payment_method_count: int
    template_count: int
    passport_gap_count: int
    has_self_traveler: bool
    has_payment_method: bool
    totp_enabled: bool
    setup_warnings: list[str]
    readiness_label: str


class TrampStampHistoryItemResponse(BaseModel):
    id: str
    booking_id: str
    awarded_at: datetime
    provider: str
    route: str
    amount: int


class ProfileSummaryResponse(BaseModel):
    tramp_stamp_balance: int
    tramp_stamp_history: list[TrampStampHistoryItemResponse] = Field(default_factory=list)
    settings: UserSettingsResponse
    preferences: UserPreferenceResponse
    travelers: list[TravelerResponse]
    traveler_groups: list[TravelerGroupResponse]
    payment_methods: list[PaymentMethodResponse]
    trip_templates: list[TripTemplateResponse]
    household_summary: HouseholdWorkspaceSummaryResponse


class OnboardingCompletionResponse(BaseModel):
    onboarding_completed: bool
