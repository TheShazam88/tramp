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
