"""Store the timezone used to interpret quiet hours."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261006_0012"
down_revision = "20260715_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("quiet_hours_timezone", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "quiet_hours_timezone")
