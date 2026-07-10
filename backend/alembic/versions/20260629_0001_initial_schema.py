"""Create the original Travel Watch schema."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260629_0001"
down_revision = None
branch_labels = None
depends_on = None

ENUM_VALUES: dict[str, tuple[str, ...]] = {
    "user_role": ("ADMIN", "USER"),
    "notification_channel": ("INHERIT", "EMAIL", "TELEGRAM", "BOTH"),
    "integration_environment": ("TEST", "LIVE"),
    "traveler_relationship": ("SELF", "PARTNER", "CHILD", "OTHER"),
    "seat_preference": ("AISLE", "WINDOW", "EXTRA_LEGROOM", "NO_PREFERENCE"),
    "program_type": ("AIRLINE", "HOTEL", "CAR", "ALLIANCE"),
    "alliance": ("STAR", "ONEWORLD", "SKYTEAM", "NONE"),
    "preferences_notification_channel": ("INHERIT", "EMAIL", "TELEGRAM", "BOTH"),
    "trip_watch_status": ("ACTIVE", "PAUSED", "FULFILLED"),
    "trip_mode": ("FLIGHTS_THEN_HOTELS", "FLIGHTS_ONLY", "HOTELS_ONLY"),
    "destination_mode": ("FIXED", "FLEXIBLE"),
    "refresh_interval": ("DAILY", "SIX_HOURS", "HOURLY"),
    "watch_notification_channel": ("INHERIT", "EMAIL", "TELEGRAM", "BOTH"),
    "auto_book_mode": ("ALWAYS_CONFIRM", "AUTO_UNDER_X"),
    "observation_kind": ("FLIGHT", "HOTEL", "CAR"),
    "price_scope_type": ("ROUTE_CABIN", "HOTEL_AREA"),
    "suppressed_attribute_type": (
        "AIRLINE",
        "HOTEL_PROPERTY",
        "HOTEL_CHAIN",
        "AREA_CLUSTER",
        "ROUTING_TRAIT",
    ),
    "deal_framing": ("MAX_LUXURY", "BEST_VALUE", "CHEAPEST_OK"),
    "deal_status": ("PROPOSED", "CONFIRMED", "EXPIRED", "BOOKED", "FAILED", "REJECTED"),
    "feedback_signal_type": ("VALUE", "PREFERENCE", "CONSTRAINT", "AMBIGUOUS"),
    "booking_status": (
        "PENDING_TICKETING",
        "TICKETED",
        "BOOKED",
        "CANCEL_PENDING",
        "CANCELLED",
        "FAILED",
    ),
    "cancellation_status": ("REQUESTED", "PROCESSING", "REFUNDED", "DENIED"),
}

INDEXES: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("ix_users_email", "users", ("email",), True),
    ("ix_travelers_user_id", "travelers", ("user_id",), False),
    ("ix_loyalty_accounts_traveler_id", "loyalty_accounts", ("traveler_id",), False),
    ("ix_traveler_groups_user_id", "traveler_groups", ("user_id",), False),
    ("ix_trip_templates_user_id", "trip_templates", ("user_id",), False),
    ("ix_payment_methods_user_id", "payment_methods", ("user_id",), False),
    ("ix_trip_watches_user_id", "trip_watches", ("user_id",), False),
    ("ix_watch_travelers_watch_id", "watch_travelers", ("watch_id",), False),
    ("ix_watch_travelers_traveler_id", "watch_travelers", ("traveler_id",), False),
    ("ix_price_observations_watch_id", "price_observations", ("watch_id",), False),
    (
        "ix_price_observations_fingerprint_hash",
        "price_observations",
        ("fingerprint_hash",),
        False,
    ),
    ("ix_price_stats_scope_key", "price_stats", ("scope_key",), False),
    (
        "ix_suppressed_attributes_watch_id",
        "suppressed_attributes",
        ("watch_id",),
        False,
    ),
    (
        "ix_rejected_fingerprints_watch_id",
        "rejected_fingerprints",
        ("watch_id",),
        False,
    ),
    ("ix_deals_watch_id", "deals", ("watch_id",), False),
    ("ix_deals_fingerprint_hash", "deals", ("fingerprint_hash",), False),
    ("ix_deal_feedback_watch_id", "deal_feedback", ("watch_id",), False),
    ("ix_deal_feedback_deal_id", "deal_feedback", ("deal_id",), False),
    ("ix_bookings_deal_id", "bookings", ("deal_id",), False),
    ("ix_cancellations_booking_id", "cancellations", ("booking_id",), False),
    ("ix_spend_ledger_user_id", "spend_ledger", ("user_id",), False),
)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUM_VALUES[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_name in ENUM_VALUES:
        _enum(enum_name).create(bind, checkfirst=False)

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("totp_secret", sa.String(length=255), nullable=True),
        sa.Column("role", _enum("user_role"), nullable=False),
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False),
        sa.Column(
            "default_notify_channel",
            _enum("notification_channel"),
            nullable=False,
        ),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
        sa.Column("global_max_auto_book_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("weekly_max_spend", sa.Numeric(12, 2), nullable=True),
        sa.Column("weekly_max_bookings", sa.Integer(), nullable=True),
        sa.Column("annual_travel_budget", sa.Numeric(12, 2), nullable=True),
        sa.Column("annual_budget_currency", sa.String(length=3), nullable=True),
        sa.Column("google_calendar_token_ref", sa.String(length=255), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "platform_integrations",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=False),
        sa.Column(
            "environment",
            _enum("integration_environment"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "feature_flags_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_platform_integrations_key"),
    )
    op.create_table(
        "travelers",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "relationship",
            _enum("traveler_relationship"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("legal_first_name", sa.String(length=120), nullable=False),
        sa.Column("legal_last_name", sa.String(length=120), nullable=False),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column("nationality", sa.String(length=2), nullable=False),
        sa.Column("residency_country", sa.String(length=2), nullable=True),
        sa.Column("passport_number_enc", sa.Text(), nullable=True),
        sa.Column("passport_country", sa.String(length=2), nullable=True),
        sa.Column("passport_expiry", sa.Date(), nullable=True),
        sa.Column("known_traveler_number", sa.String(length=64), nullable=True),
        sa.Column("redress_number", sa.String(length=64), nullable=True),
        sa.Column("seat_pref", _enum("seat_preference"), nullable=False),
        sa.Column("meal_pref", sa.String(length=64), nullable=True),
        sa.Column("accessibility_needs", sa.Text(), nullable=True),
        sa.Column("infant_on_lap", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "loyalty_accounts",
        sa.Column("traveler_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_type", _enum("program_type"), nullable=False),
        sa.Column("program_code", sa.String(length=32), nullable=False),
        sa.Column("alliance", _enum("alliance"), nullable=False),
        sa.Column("account_number", sa.String(length=128), nullable=False),
        sa.Column("status_tier", sa.String(length=64), nullable=True),
        sa.Column("preferred_earning_for_alliance", sa.Boolean(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["traveler_id"],
            ["travelers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "traveler_id",
            "program_type",
            "program_code",
            name="uq_loyalty_accounts_program",
        ),
    )
    op.create_table(
        "traveler_groups",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "traveler_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "home_airports",
            postgresql.ARRAY(sa.String(length=8)),
            nullable=True,
        ),
        sa.Column("default_cabin", sa.String(length=32), nullable=True),
        sa.Column("default_luxury_vs_savings", sa.Float(), nullable=False),
        sa.Column(
            "preferred_airlines",
            postgresql.ARRAY(sa.String(length=8)),
            nullable=True,
        ),
        sa.Column(
            "avoided_airlines",
            postgresql.ARRAY(sa.String(length=8)),
            nullable=True,
        ),
        sa.Column(
            "preferred_alliances",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=True,
        ),
        sa.Column(
            "preferred_hotel_brands",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=True,
        ),
        sa.Column(
            "avoided_hotel_brands",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=True,
        ),
        sa.Column("default_hotel_min_rating", sa.Float(), nullable=True),
        sa.Column("avoid_redeye", sa.Boolean(), nullable=False),
        sa.Column("default_max_layover_minutes", sa.Integer(), nullable=True),
        sa.Column("default_min_connection_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "default_outbound_window_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "default_return_window_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("prefer_refundable", sa.Boolean(), nullable=False),
        sa.Column("seat_auto_select", sa.Boolean(), nullable=False),
        sa.Column(
            "default_notify_channel",
            _enum("preferences_notification_channel"),
            nullable=False,
        ),
        sa.Column("quiet_hours_start", sa.Time(), nullable=True),
        sa.Column("quiet_hours_end", sa.Time(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
    )
    op.create_table(
        "trip_templates",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "watch_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "payment_methods",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("brand", sa.String(length=64), nullable=True),
        sa.Column("last4", sa.String(length=4), nullable=True),
        sa.Column("encrypted_blob", sa.Text(), nullable=False),
        sa.Column("provider_token", sa.String(length=255), nullable=True),
        sa.Column("billing_address_enc", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trip_watches",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", _enum("trip_watch_status"), nullable=False),
        sa.Column("trip_mode", _enum("trip_mode"), nullable=False),
        sa.Column(
            "traveler_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "origin_iatas",
            postgresql.ARRAY(sa.String(length=8)),
            nullable=True,
        ),
        sa.Column(
            "destination_iatas",
            postgresql.ARRAY(sa.String(length=8)),
            nullable=True,
        ),
        sa.Column("destination_mode", _enum("destination_mode"), nullable=False),
        sa.Column("flexible_region", sa.String(length=64), nullable=True),
        sa.Column("flexible_theme", sa.String(length=64), nullable=True),
        sa.Column("depart_date_from", sa.Date(), nullable=True),
        sa.Column("depart_date_to", sa.Date(), nullable=True),
        sa.Column("return_date_from", sa.Date(), nullable=True),
        sa.Column("return_date_to", sa.Date(), nullable=True),
        sa.Column("trip_min_nights", sa.Integer(), nullable=True),
        sa.Column("trip_max_nights", sa.Integer(), nullable=True),
        sa.Column("cabin_class", sa.String(length=32), nullable=True),
        sa.Column("max_stops", sa.Integer(), nullable=True),
        sa.Column("max_layover_minutes", sa.Integer(), nullable=True),
        sa.Column("min_connection_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "preferred_airlines",
            postgresql.ARRAY(sa.String(length=8)),
            nullable=True,
        ),
        sa.Column(
            "preferred_alliances",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=True,
        ),
        sa.Column("avoid_redeye", sa.Boolean(), nullable=False),
        sa.Column("outbound_earliest_depart", sa.Time(), nullable=True),
        sa.Column("outbound_latest_depart", sa.Time(), nullable=True),
        sa.Column("outbound_arrive_by", sa.Time(), nullable=True),
        sa.Column("return_earliest_depart", sa.Time(), nullable=True),
        sa.Column("return_latest_depart", sa.Time(), nullable=True),
        sa.Column("return_arrive_by", sa.Time(), nullable=True),
        sa.Column("flight_budget_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("hotel_budget_per_night_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("max_total_trip_spend", sa.Numeric(12, 2), nullable=True),
        sa.Column("budget_currency", sa.String(length=3), nullable=True),
        sa.Column("ideal_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("glide_start_days", sa.Integer(), nullable=False),
        sa.Column("glide_end_days", sa.Integer(), nullable=False),
        sa.Column("quality_floor", sa.Integer(), nullable=False),
        sa.Column("luxury_vs_savings", sa.Float(), nullable=False),
        sa.Column("hotel_min_rating", sa.Float(), nullable=True),
        sa.Column("hotel_area_lat", sa.Float(), nullable=True),
        sa.Column("hotel_area_lng", sa.Float(), nullable=True),
        sa.Column("hotel_radius_km", sa.Float(), nullable=True),
        sa.Column("prefer_refundable", sa.Boolean(), nullable=False),
        sa.Column("loyalty_weighting", sa.Float(), nullable=False),
        sa.Column("value_target", sa.Float(), nullable=True),
        sa.Column("band_tolerance", sa.Float(), nullable=False),
        sa.Column("value_pressure", sa.Float(), nullable=False),
        sa.Column("include_airbnb", sa.Boolean(), nullable=False),
        sa.Column(
            "airbnb_disclosure_ack_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("refresh_interval", _enum("refresh_interval"), nullable=False),
        sa.Column(
            "notify_channel",
            _enum("watch_notification_channel"),
            nullable=False,
        ),
        sa.Column("want_car", sa.Boolean(), nullable=False),
        sa.Column("auto_book_mode", _enum("auto_book_mode"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["traveler_group_id"],
            ["traveler_groups.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "watch_travelers",
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("traveler_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["traveler_id"],
            ["travelers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["trip_watches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "watch_id",
            "traveler_id",
            name="uq_watch_travelers_pair",
        ),
    )
    op.create_table(
        "price_observations",
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", _enum("observation_kind"), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("fingerprint_hash", sa.String(length=128), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["trip_watches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "price_stats",
        sa.Column("scope_type", _enum("price_scope_type"), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("month_bucket", sa.Date(), nullable=False),
        sa.Column("p10", sa.Numeric(12, 2), nullable=True),
        sa.Column("p25", sa.Numeric(12, 2), nullable=True),
        sa.Column("median", sa.Numeric(12, 2), nullable=True),
        sa.Column("p75", sa.Numeric(12, 2), nullable=True),
        sa.Column("volatility", sa.Float(), nullable=True),
        sa.Column("sample_n", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "suppressed_attributes",
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attr_type",
            _enum("suppressed_attribute_type"),
            nullable=False,
        ),
        sa.Column("attr_value", sa.String(length=255), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["trip_watches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rejected_fingerprints",
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=128), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["trip_watches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "watch_id",
            "fingerprint_hash",
            name="uq_rejected_fingerprints_watch_fingerprint",
        ),
    )
    op.create_table(
        "deals",
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("quality_index", sa.Float(), nullable=True),
        sa.Column("value_score", sa.Float(), nullable=True),
        sa.Column("price_percentile", sa.Float(), nullable=True),
        sa.Column("timing_advice", sa.String(length=255), nullable=True),
        sa.Column("framing", _enum("deal_framing"), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=128), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column(
            "coverage_report_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "validation_warnings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "loyalty_plan_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("offer_ref", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _enum("deal_status"), nullable=False),
        sa.Column("rejected_reason", sa.String(length=255), nullable=True),
        sa.Column("confirm_token_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["trip_watches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "deal_feedback",
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rejected_value_score", sa.Float(), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column(
            "signal_type",
            _enum("feedback_signal_type"),
            nullable=False,
        ),
        sa.Column(
            "action_taken_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["trip_watches.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bookings",
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_booking_ref", sa.String(length=255), nullable=True),
        sa.Column("status", _enum("booking_status"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("amount_charged", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "documents_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "loyalty_attached_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("loyalty_manual_followup", sa.Boolean(), nullable=False),
        sa.Column("calendar_event_id", sa.String(length=255), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id", name="uq_bookings_deal_id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_bookings_idempotency_key",
        ),
    )
    op.create_table(
        "cancellations",
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("refund_expected", sa.Numeric(12, 2), nullable=True),
        sa.Column("refund_received", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("status", _enum("cancellation_status"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "spend_ledger",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["trip_watches.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_log",
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "meta_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    for index_name, table_name, columns, unique in INDEXES:
        op.create_index(
            op.f(index_name),
            table_name,
            list(columns),
            unique=unique,
        )


def downgrade() -> None:
    for index_name, table_name, _columns, _unique in reversed(INDEXES):
        op.drop_index(op.f(index_name), table_name=table_name)

    op.drop_table("audit_log")
    op.drop_table("spend_ledger")
    op.drop_table("cancellations")
    op.drop_table("bookings")
    op.drop_table("deal_feedback")
    op.drop_table("deals")
    op.drop_table("rejected_fingerprints")
    op.drop_table("suppressed_attributes")
    op.drop_table("price_stats")
    op.drop_table("price_observations")
    op.drop_table("watch_travelers")
    op.drop_table("trip_watches")
    op.drop_table("payment_methods")
    op.drop_table("trip_templates")
    op.drop_table("user_preferences")
    op.drop_table("loyalty_accounts")
    op.drop_table("travelers")
    op.drop_table("traveler_groups")
    op.drop_table("platform_integrations")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_name in reversed(ENUM_VALUES):
        _enum(enum_name).drop(bind, checkfirst=False)
