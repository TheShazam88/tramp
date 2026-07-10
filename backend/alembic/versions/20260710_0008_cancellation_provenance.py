"""Add reversible cancellation provenance and effect links."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260710_0008"
down_revision = "20260710_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    booking_status = postgresql.ENUM(name="booking_status", create_type=False)
    watch_status = postgresql.ENUM(name="trip_watch_status", create_type=False)

    op.add_column("cancellations", sa.Column("provider", sa.String(length=64), nullable=True))
    op.add_column(
        "cancellations",
        sa.Column("provider_correlation_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "cancellations",
        sa.Column(
            "provider_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "cancellations",
        sa.Column("execution_simulated", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "cancellations",
        sa.Column("prior_booking_status", booking_status, nullable=True),
    )
    op.add_column(
        "cancellations",
        sa.Column("prior_watch_status", watch_status, nullable=True),
    )

    op.add_column(
        "spend_ledger",
        sa.Column("cancellation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_spend_ledger_cancellation_id_cancellations"),
        "spend_ledger",
        "cancellations",
        ["cancellation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_spend_ledger_cancellation_id"),
        "spend_ledger",
        ["cancellation_id"],
        unique=False,
    )

    op.add_column(
        "notification_deliveries",
        sa.Column("cancellation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_notification_deliveries_cancellation_id_cancellations"),
        "notification_deliveries",
        "cancellations",
        ["cancellation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_notification_deliveries_cancellation_id"),
        "notification_deliveries",
        ["cancellation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notification_deliveries_cancellation_id"),
        table_name="notification_deliveries",
    )
    op.drop_constraint(
        op.f("fk_notification_deliveries_cancellation_id_cancellations"),
        "notification_deliveries",
        type_="foreignkey",
    )
    op.drop_column("notification_deliveries", "cancellation_id")

    op.drop_index(
        op.f("ix_spend_ledger_cancellation_id"),
        table_name="spend_ledger",
    )
    op.drop_constraint(
        op.f("fk_spend_ledger_cancellation_id_cancellations"),
        "spend_ledger",
        type_="foreignkey",
    )
    op.drop_column("spend_ledger", "cancellation_id")

    op.drop_column("cancellations", "prior_watch_status")
    op.drop_column("cancellations", "prior_booking_status")
    op.drop_column("cancellations", "execution_simulated")
    op.drop_column("cancellations", "provider_payload_json")
    op.drop_column("cancellations", "provider_correlation_id")
    op.drop_column("cancellations", "provider")
