"""Gate cancellations with signed approval and idempotency state."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260715_0010"
down_revision = "20260710_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bookings",
        sa.Column("cancellation_token_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "cancellations",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_cancellations_idempotency_key",
        "cancellations",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_cancellations_idempotency_key",
        "cancellations",
        type_="unique",
    )
    op.drop_column("cancellations", "idempotency_key")
    op.drop_column("bookings", "cancellation_token_hash")
