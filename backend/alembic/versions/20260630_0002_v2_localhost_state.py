"""Add V2 localhost state tables and booking fields."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260630_0002"
down_revision = "20260629_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE integration_environment "
        "ADD VALUE IF NOT EXISTS 'OFF' BEFORE 'TEST'"
    )

    booking_attempt_status_type = sa.Enum(
        "STARTED",
        "REVALIDATED",
        "BOOKED",
        "FAILED",
        name="booking_attempt_status",
    )
    booking_attempt_status = postgresql.ENUM(
        "STARTED",
        "REVALIDATED",
        "BOOKED",
        "FAILED",
        name="booking_attempt_status",
        create_type=False,
    )
    notification_transport_type = sa.Enum(
        "log_only",
        "smtp_dev",
        "telegram_bot",
        name="notification_transport",
    )
    notification_transport = postgresql.ENUM(
        "log_only",
        "smtp_dev",
        "telegram_bot",
        name="notification_transport",
        create_type=False,
    )
    notification_delivery_status_type = sa.Enum(
        "pending",
        "sent",
        "failed",
        name="notification_delivery_status",
    )
    notification_delivery_status = postgresql.ENUM(
        "pending",
        "sent",
        "failed",
        name="notification_delivery_status",
        create_type=False,
    )
    disruption_type_type = sa.Enum(
        "SCHEDULE_CHANGE",
        "CANCELLATION",
        "BETTER_DEAL",
        "MANUAL_TEST",
        name="disruption_type",
    )
    disruption_type = postgresql.ENUM(
        "SCHEDULE_CHANGE",
        "CANCELLATION",
        "BETTER_DEAL",
        "MANUAL_TEST",
        name="disruption_type",
        create_type=False,
    )
    disruption_status_type = sa.Enum(
        "NEW",
        "NOTIFIED",
        "RESOLVED",
        name="disruption_status",
    )
    disruption_status = postgresql.ENUM(
        "NEW",
        "NOTIFIED",
        "RESOLVED",
        name="disruption_status",
        create_type=False,
    )

    bind = op.get_bind()
    booking_attempt_status_type.create(bind, checkfirst=True)
    notification_transport_type.create(bind, checkfirst=True)
    notification_delivery_status_type.create(bind, checkfirst=True)
    disruption_type_type.create(bind, checkfirst=True)
    disruption_status_type.create(bind, checkfirst=True)

    op.add_column(
        "bookings",
        sa.Column("provider_correlation_id", sa.String(length=255), nullable=True),
    )
    op.add_column("bookings", sa.Column("ticketing_state", sa.String(length=64), nullable=True))
    op.add_column("bookings", sa.Column("calendar_detail", sa.Text(), nullable=True))

    op.create_table(
        "booking_attempts",
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("watch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", booking_attempt_status, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_correlation_id", sa.String(length=255), nullable=True),
        sa.Column("request_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["watch_id"], ["trip_watches.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_booking_attempts_deal_id", "booking_attempts", ["deal_id"])
    op.create_index("ix_booking_attempts_booking_id", "booking_attempts", ["booking_id"])
    op.create_index("ix_booking_attempts_watch_id", "booking_attempts", ["watch_id"])
    op.create_index("ix_booking_attempts_idempotency_key", "booking_attempts", ["idempotency_key"])

    op.create_table(
        "disruptions",
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", disruption_type, nullable=False),
        sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", disruption_status, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_disruptions_booking_id", "disruptions", ["booking_id"])

    op.create_table(
        "notification_deliveries",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("disruption_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("transport", notification_transport, nullable=False),
        sa.Column("destination", sa.String(length=320), nullable=True),
        sa.Column("message_type", sa.String(length=120), nullable=False),
        sa.Column("status", notification_delivery_status, nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["disruption_id"], ["disruptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    op.create_index(
        "ix_notification_deliveries_booking_id",
        "notification_deliveries",
        ["booking_id"],
    )
    op.create_index(
        "ix_notification_deliveries_disruption_id",
        "notification_deliveries",
        ["disruption_id"],
    )
    op.create_index("ix_notification_deliveries_deal_id", "notification_deliveries", ["deal_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_deliveries_deal_id", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_disruption_id", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_booking_id", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_user_id", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")

    op.drop_index("ix_disruptions_booking_id", table_name="disruptions")
    op.drop_table("disruptions")

    op.drop_index("ix_booking_attempts_idempotency_key", table_name="booking_attempts")
    op.drop_index("ix_booking_attempts_watch_id", table_name="booking_attempts")
    op.drop_index("ix_booking_attempts_booking_id", table_name="booking_attempts")
    op.drop_index("ix_booking_attempts_deal_id", table_name="booking_attempts")
    op.drop_table("booking_attempts")

    op.drop_column("bookings", "calendar_detail")
    op.drop_column("bookings", "ticketing_state")
    op.drop_column("bookings", "provider_correlation_id")

    bind = op.get_bind()
    sa.Enum(name="notification_delivery_status").drop(bind, checkfirst=True)
    sa.Enum(name="notification_transport").drop(bind, checkfirst=True)
    sa.Enum(name="disruption_status").drop(bind, checkfirst=True)
    sa.Enum(name="disruption_type").drop(bind, checkfirst=True)
    sa.Enum(name="booking_attempt_status").drop(bind, checkfirst=True)
