from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    UUID as SQLUUID,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import conv

from app.db.base import Base, CreatedTimestampMixin, UpdatedTimestampMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class NotificationChannel(StrEnum):
    INHERIT = "inherit"
    EMAIL = "email"
    TELEGRAM = "telegram"
    BOTH = "both"


class IntegrationEnvironment(StrEnum):
    OFF = "off"
    TEST = "test"
    LIVE = "live"


class TravelerRelationship(StrEnum):
    SELF = "self"
    PARTNER = "partner"
    CHILD = "child"
    OTHER = "other"


class SeatPreference(StrEnum):
    AISLE = "aisle"
    WINDOW = "window"
    EXTRA_LEGROOM = "extra_legroom"
    NO_PREFERENCE = "no_pref"


class ProgramType(StrEnum):
    AIRLINE = "airline"
    HOTEL = "hotel"
    CAR = "car"
    ALLIANCE = "alliance"


class Alliance(StrEnum):
    STAR = "star"
    ONEWORLD = "oneworld"
    SKYTEAM = "skyteam"
    NONE = "none"


class TripWatchStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    FULFILLED = "fulfilled"


class TripMode(StrEnum):
    FLIGHTS_THEN_HOTELS = "flights_then_hotels"
    FLIGHTS_ONLY = "flights_only"
    HOTELS_ONLY = "hotels_only"


class DestinationMode(StrEnum):
    FIXED = "fixed"
    FLEXIBLE = "flexible"


class RefreshInterval(StrEnum):
    DAILY = "daily"
    SIX_HOURS = "6h"
    HOURLY = "hourly"


class AutoBookMode(StrEnum):
    ALWAYS_CONFIRM = "always_confirm"
    AUTO_UNDER_X = "auto_under_X"


class ObservationKind(StrEnum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    CAR = "car"


class PriceScopeType(StrEnum):
    ROUTE_CABIN = "route_cabin"
    HOTEL_AREA = "hotel_area"


class SuppressedAttributeType(StrEnum):
    AIRLINE = "airline"
    HOTEL_PROPERTY = "hotel_property"
    HOTEL_CHAIN = "hotel_chain"
    AREA_CLUSTER = "area_cluster"
    ROUTING_TRAIT = "routing_trait"


class DealFraming(StrEnum):
    MAX_LUXURY = "max_luxury"
    BEST_VALUE = "best_value"
    CHEAPEST_OK = "cheapest_ok"


class DealStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    BOOKED = "booked"
    FAILED = "failed"
    REJECTED = "rejected"


class FeedbackSignalType(StrEnum):
    VALUE = "value"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    AMBIGUOUS = "ambiguous"


class BookingStatus(StrEnum):
    PENDING_TICKETING = "pending_ticketing"
    TICKETED = "ticketed"
    BOOKED = "booked"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CancellationStatus(StrEnum):
    REQUESTED = "requested"
    PROCESSING = "processing"
    REFUNDED = "refunded"
    DENIED = "denied"


class BookingAttemptStatus(StrEnum):
    STARTED = "started"
    REVALIDATED = "revalidated"
    PENDING_TICKETING = "pending_ticketing"
    BOOKED = "booked"
    FAILED = "failed"


class NotificationTransport(StrEnum):
    LOG_ONLY = "log_only"
    SMTP_DEV = "smtp_dev"
    TELEGRAM_BOT = "telegram_bot"


class NotificationDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class DisruptionType(StrEnum):
    SCHEDULE_CHANGE = "schedule_change"
    CANCELLATION = "cancellation"
    BETTER_DEAL = "better_deal"
    MANUAL_TEST = "manual_test"


class DisruptionStatus(StrEnum):
    NEW = "new"
    NOTIFIED = "notified"
    RESOLVED = "resolved"


class User(UUIDPrimaryKeyMixin, CreatedTimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        nullable=False,
        default=UserRole.USER,
    )
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_notify_channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"),
        nullable=False,
        default=NotificationChannel.EMAIL,
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    global_max_auto_book_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    weekly_max_spend: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    weekly_max_bookings: Mapped[int | None] = mapped_column(Integer)
    annual_travel_budget: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    annual_budget_currency: Mapped[str | None] = mapped_column(String(3))
    google_calendar_token_ref: Mapped[str | None] = mapped_column(String(255))


class IntegrationCredentialProfile(UUIDPrimaryKeyMixin, UpdatedTimestampMixin, Base):
    __tablename__ = "integration_credential_profiles"
    __table_args__ = (
        UniqueConstraint(
            "provider_key",
            "label",
            name="uq_integration_credential_profiles_provider_label",
        ),
    )

    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), ForeignKey("users.id"))


class PlatformIntegration(UUIDPrimaryKeyMixin, UpdatedTimestampMixin, Base):
    __tablename__ = "platform_integrations"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    credential_profile_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("integration_credential_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    environment: Mapped[IntegrationEnvironment] = mapped_column(
        Enum(IntegrationEnvironment, name="integration_environment"),
        nullable=False,
        default=IntegrationEnvironment.TEST,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feature_flags_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_by: Mapped[UUID | None] = mapped_column(SQLUUID(as_uuid=True), ForeignKey("users.id"))


class Traveler(UUIDPrimaryKeyMixin, CreatedTimestampMixin, Base):
    __tablename__ = "travelers"

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    traveler_relationship: Mapped[TravelerRelationship] = mapped_column(
        "relationship",
        Enum(TravelerRelationship, name="traveler_relationship"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    legal_first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    legal_last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dob: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(32))
    nationality: Mapped[str] = mapped_column(String(2), nullable=False)
    residency_country: Mapped[str | None] = mapped_column(String(2))
    passport_number_enc: Mapped[str | None] = mapped_column(Text)
    passport_country: Mapped[str | None] = mapped_column(String(2))
    passport_expiry: Mapped[date | None] = mapped_column(Date)
    known_traveler_number: Mapped[str | None] = mapped_column(String(64))
    redress_number: Mapped[str | None] = mapped_column(String(64))
    seat_pref: Mapped[SeatPreference] = mapped_column(
        Enum(SeatPreference, name="seat_preference"),
        nullable=False,
        default=SeatPreference.NO_PREFERENCE,
    )
    meal_pref: Mapped[str | None] = mapped_column(String(64))
    accessibility_needs: Mapped[str | None] = mapped_column(Text)
    infant_on_lap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class LoyaltyAccount(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "loyalty_accounts"
    __table_args__ = (
        UniqueConstraint(
            "traveler_id",
            "program_type",
            "program_code",
            name="uq_loyalty_accounts_program",
        ),
    )

    traveler_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("travelers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    program_type: Mapped[ProgramType] = mapped_column(
        Enum(ProgramType, name="program_type"),
        nullable=False,
    )
    program_code: Mapped[str] = mapped_column(String(32), nullable=False)
    alliance: Mapped[Alliance] = mapped_column(
        Enum(Alliance, name="alliance"),
        nullable=False,
        default=Alliance.NONE,
    )
    account_number: Mapped[str] = mapped_column(String(128), nullable=False)
    status_tier: Mapped[str | None] = mapped_column(String(64))
    preferred_earning_for_alliance: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )


class TravelerGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "traveler_groups"

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    traveler_ids: Mapped[list[UUID]] = mapped_column(ARRAY(SQLUUID(as_uuid=True)), nullable=False)


class UserPreference(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_user_preferences_user_id"),)

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    home_airports: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))
    default_cabin: Mapped[str | None] = mapped_column(String(32))
    default_luxury_vs_savings: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    preferred_airlines: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))
    avoided_airlines: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))
    preferred_alliances: Mapped[list[str] | None] = mapped_column(ARRAY(String(16)))
    preferred_hotel_brands: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))
    avoided_hotel_brands: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)))
    default_hotel_min_rating: Mapped[float | None] = mapped_column(Float)
    avoid_redeye: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_max_layover_minutes: Mapped[int | None] = mapped_column(Integer)
    default_min_connection_minutes: Mapped[int | None] = mapped_column(Integer)
    default_outbound_window_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    default_return_window_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prefer_refundable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seat_auto_select: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_notify_channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="preferences_notification_channel"),
        nullable=False,
        default=NotificationChannel.INHERIT,
    )
    quiet_hours_start: Mapped[time | None] = mapped_column(Time)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time)


class TripTemplate(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "trip_templates"

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    watch_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class PaymentMethod(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payment_methods"

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(64))
    last4: Mapped[str | None] = mapped_column(String(4))
    encrypted_blob: Mapped[str] = mapped_column(Text, nullable=False)
    provider_token: Mapped[str | None] = mapped_column(String(255))
    billing_address_enc: Mapped[str | None] = mapped_column(Text)


class TripWatch(UUIDPrimaryKeyMixin, CreatedTimestampMixin, UpdatedTimestampMixin, Base):
    __tablename__ = "trip_watches"

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[TripWatchStatus] = mapped_column(
        Enum(TripWatchStatus, name="trip_watch_status"),
        nullable=False,
        default=TripWatchStatus.ACTIVE,
    )
    trip_mode: Mapped[TripMode] = mapped_column(
        Enum(TripMode, name="trip_mode"),
        nullable=False,
        default=TripMode.FLIGHTS_THEN_HOTELS,
    )
    traveler_group_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("traveler_groups.id", ondelete="SET NULL"),
    )
    origin_iatas: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))
    destination_iatas: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))
    destination_mode: Mapped[DestinationMode] = mapped_column(
        Enum(DestinationMode, name="destination_mode"),
        nullable=False,
        default=DestinationMode.FIXED,
    )
    flexible_region: Mapped[str | None] = mapped_column(String(64))
    flexible_theme: Mapped[str | None] = mapped_column(String(64))
    depart_date_from: Mapped[date | None] = mapped_column(Date)
    depart_date_to: Mapped[date | None] = mapped_column(Date)
    return_date_from: Mapped[date | None] = mapped_column(Date)
    return_date_to: Mapped[date | None] = mapped_column(Date)
    trip_min_nights: Mapped[int | None] = mapped_column(Integer)
    trip_max_nights: Mapped[int | None] = mapped_column(Integer)
    cabin_class: Mapped[str | None] = mapped_column(String(32))
    max_stops: Mapped[int | None] = mapped_column(Integer)
    max_layover_minutes: Mapped[int | None] = mapped_column(Integer)
    min_connection_minutes: Mapped[int | None] = mapped_column(Integer)
    preferred_airlines: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)))
    preferred_alliances: Mapped[list[str] | None] = mapped_column(ARRAY(String(16)))
    avoid_redeye: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outbound_earliest_depart: Mapped[time | None] = mapped_column(Time)
    outbound_latest_depart: Mapped[time | None] = mapped_column(Time)
    outbound_arrive_by: Mapped[time | None] = mapped_column(Time)
    return_earliest_depart: Mapped[time | None] = mapped_column(Time)
    return_latest_depart: Mapped[time | None] = mapped_column(Time)
    return_arrive_by: Mapped[time | None] = mapped_column(Time)
    flight_budget_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    hotel_budget_per_night_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    max_total_trip_spend: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    budget_currency: Mapped[str | None] = mapped_column(String(3))
    ideal_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    glide_start_days: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    glide_end_days: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    quality_floor: Mapped[int] = mapped_column(Integer, nullable=False, default=40)
    luxury_vs_savings: Mapped[float] = mapped_column(Float, nullable=False, default=0.6)
    hotel_min_rating: Mapped[float | None] = mapped_column(Float)
    hotel_area_lat: Mapped[float | None] = mapped_column(Float)
    hotel_area_lng: Mapped[float | None] = mapped_column(Float)
    hotel_radius_km: Mapped[float | None] = mapped_column(Float)
    prefer_refundable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    loyalty_weighting: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    value_target: Mapped[float | None] = mapped_column(Float)
    band_tolerance: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    value_pressure: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    include_airbnb: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    airbnb_disclosure_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_interval: Mapped[RefreshInterval] = mapped_column(
        Enum(RefreshInterval, name="refresh_interval"),
        nullable=False,
        default=RefreshInterval.DAILY,
    )
    notify_channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="watch_notification_channel"),
        nullable=False,
        default=NotificationChannel.INHERIT,
    )
    want_car: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_book_mode: Mapped[AutoBookMode] = mapped_column(
        Enum(AutoBookMode, name="auto_book_mode"),
        nullable=False,
        default=AutoBookMode.ALWAYS_CONFIRM,
    )


class WatchTraveler(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "watch_travelers"
    __table_args__ = (UniqueConstraint("watch_id", "traveler_id", name="uq_watch_travelers_pair"),)

    watch_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    traveler_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("travelers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class PriceObservation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "price_observations"

    watch_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[ObservationKind] = mapped_column(
        Enum(ObservationKind, name="observation_kind"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


class PriceStat(UUIDPrimaryKeyMixin, UpdatedTimestampMixin, Base):
    __tablename__ = "price_stats"

    scope_type: Mapped[PriceScopeType] = mapped_column(
        Enum(PriceScopeType, name="price_scope_type"),
        nullable=False,
    )
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    month_bucket: Mapped[date] = mapped_column(Date, nullable=False)
    p10: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    p25: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    median: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    p75: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    volatility: Mapped[float | None] = mapped_column(Float)
    sample_n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SuppressedAttribute(UUIDPrimaryKeyMixin, CreatedTimestampMixin, Base):
    __tablename__ = "suppressed_attributes"

    watch_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attr_type: Mapped[SuppressedAttributeType] = mapped_column(
        Enum(SuppressedAttributeType, name="suppressed_attribute_type"),
        nullable=False,
    )
    attr_value: Mapped[str] = mapped_column(String(255), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class RejectedFingerprint(UUIDPrimaryKeyMixin, CreatedTimestampMixin, Base):
    __tablename__ = "rejected_fingerprints"
    __table_args__ = (
        UniqueConstraint(
            "watch_id",
            "fingerprint_hash",
            name="uq_rejected_fingerprints_watch_fingerprint",
        ),
    )

    watch_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False)


class Deal(UUIDPrimaryKeyMixin, CreatedTimestampMixin, Base):
    __tablename__ = "deals"

    watch_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    quality_index: Mapped[float | None] = mapped_column(Float)
    value_score: Mapped[float | None] = mapped_column(Float)
    price_percentile: Mapped[float | None] = mapped_column(Float)
    timing_advice: Mapped[str | None] = mapped_column(String(255))
    framing: Mapped[DealFraming] = mapped_column(
        Enum(DealFraming, name="deal_framing"),
        nullable=False,
        default=DealFraming.BEST_VALUE,
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    summary_text: Mapped[str | None] = mapped_column(Text)
    coverage_report_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    validation_warnings_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    loyalty_plan_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    offer_ref: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus, name="deal_status"),
        nullable=False,
        default=DealStatus.PROPOSED,
    )
    rejected_reason: Mapped[str | None] = mapped_column(String(255))
    confirm_token_hash: Mapped[str | None] = mapped_column(String(255))
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class DealFeedback(UUIDPrimaryKeyMixin, CreatedTimestampMixin, Base):
    __tablename__ = "deal_feedback"

    watch_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deal_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rejected_value_score: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(String(255))
    signal_type: Mapped[FeedbackSignalType] = mapped_column(
        Enum(FeedbackSignalType, name="feedback_signal_type"),
        nullable=False,
    )
    action_taken_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Booking(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("deal_id", name="uq_bookings_deal_id"),)

    deal_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_booking_ref: Mapped[str | None] = mapped_column(String(255))
    provider_correlation_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"),
        nullable=False,
        default=BookingStatus.PENDING_TICKETING,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    amount_charged: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    documents_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    loyalty_attached_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    loyalty_manual_followup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ticketing_state: Mapped[str | None] = mapped_column(String(64))
    calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    calendar_detail: Mapped[str | None] = mapped_column(Text)
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_text: Mapped[str | None] = mapped_column(Text)


class BookingAttempt(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "booking_attempts"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_booking_attempts_idempotency_key",
        ),
    )

    deal_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        index=True,
    )
    watch_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[BookingAttemptStatus] = mapped_column(
        Enum(BookingAttemptStatus, name="booking_attempt_status"),
        nullable=False,
        default=BookingAttemptStatus.STARTED,
    )
    provider: Mapped[str | None] = mapped_column(String(64))
    provider_correlation_id: Mapped[str | None] = mapped_column(String(255))
    request_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_text: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Cancellation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cancellations"

    booking_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(String(255))
    refund_expected: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    refund_received: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    status: Mapped[CancellationStatus] = mapped_column(
        Enum(CancellationStatus, name="cancellation_status"),
        nullable=False,
        default=CancellationStatus.REQUESTED,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SpendLedger(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "spend_ledger"

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    watch_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("trip_watches.id", ondelete="SET NULL"),
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TrampStampLedger(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tramp_stamp_ledger"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_tramp_stamp_ledger_booking_id"),
        CheckConstraint(
            "amount = 1",
            name=conv("ck_tramp_stamp_ledger_single_stamp"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Disruption(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "disruptions"

    booking_id: Mapped[UUID] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[DisruptionType] = mapped_column(
        Enum(DisruptionType, name="disruption_type"),
        nullable=False,
    )
    detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[DisruptionStatus] = mapped_column(
        Enum(DisruptionStatus, name="disruption_status"),
        nullable=False,
        default=DisruptionStatus.NEW,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDelivery(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notification_deliveries"

    user_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="SET NULL"),
        index=True,
    )
    disruption_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("disruptions.id", ondelete="SET NULL"),
        index=True,
    )
    deal_id: Mapped[UUID | None] = mapped_column(
        SQLUUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="SET NULL"),
        index=True,
    )
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    transport: Mapped[NotificationTransport] = mapped_column(
        Enum(
            NotificationTransport,
            name="notification_transport",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    destination: Mapped[str | None] = mapped_column(String(320))
    message_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        Enum(
            NotificationDeliveryStatus,
            name="notification_delivery_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=NotificationDeliveryStatus.PENDING,
    )
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_text: Mapped[str | None] = mapped_column(Text)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_log"

    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
