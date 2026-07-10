"""Add the TRAMP-Stamp ledger."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260710_0004"
down_revision = "20260630_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Early 0003 databases stored enum member names, while the current ORM stores values.
    # Rebuild these two types so existing rows remain readable without retaining aliases.
    op.execute(
        "ALTER TABLE notification_deliveries "
        "ALTER COLUMN transport TYPE text USING transport::text, "
        "ALTER COLUMN status TYPE text USING status::text"
    )
    op.execute("DROP TYPE notification_transport")
    op.execute("DROP TYPE notification_delivery_status")
    op.execute(
        "CREATE TYPE notification_transport AS ENUM "
        "('log_only', 'smtp_dev', 'telegram_bot')"
    )
    op.execute(
        "CREATE TYPE notification_delivery_status AS ENUM "
        "('pending', 'sent', 'failed')"
    )
    op.execute(
        "ALTER TABLE notification_deliveries "
        "ALTER COLUMN transport TYPE notification_transport "
        "USING lower(transport)::notification_transport, "
        "ALTER COLUMN status TYPE notification_delivery_status "
        "USING lower(status)::notification_delivery_status"
    )

    op.create_table(
        "tramp_stamp_ledger",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "meta_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "amount = 1",
            name=op.f("ck_tramp_stamp_ledger_single_stamp"),
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "booking_id",
            name="uq_tramp_stamp_ledger_booking_id",
        ),
    )
    op.create_index(
        "ix_tramp_stamp_ledger_user_id",
        "tramp_stamp_ledger",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tramp_stamp_ledger_user_id",
        table_name="tramp_stamp_ledger",
    )
    op.drop_table("tramp_stamp_ledger")
