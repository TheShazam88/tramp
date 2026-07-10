"""Enforce one unresolved booking attempt per deal."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260710_0006"
down_revision = "20260710_0005"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_booking_attempts_unresolved_deal"
UNRESOLVED_PREDICATE = "status IN ('STARTED', 'REVALIDATED')"


def _require_unique_unresolved_deals() -> None:
    duplicates = op.get_bind().execute(
        sa.text(
            """
            SELECT
                deal_id,
                count(*) AS duplicate_count,
                array_agg(idempotency_key ORDER BY started_at, id) AS attempt_keys
            FROM booking_attempts
            WHERE status IN ('STARTED', 'REVALIDATED')
            GROUP BY deal_id
            HAVING count(*) > 1
            ORDER BY deal_id
            LIMIT 10
            """
        )
    )
    rows = list(duplicates)
    if not rows:
        return

    detail = ", ".join(
        f"{deal_id} ({count} rows: {', '.join(keys[:5])})"
        for deal_id, count, keys in rows
    )
    raise RuntimeError(
        "Duplicate unresolved booking attempts prevent migration: "
        f"{detail}. Resolve the conflicting attempt states manually; no audit data was deleted."
    )


def upgrade() -> None:
    _require_unique_unresolved_deals()
    op.create_index(
        INDEX_NAME,
        "booking_attempts",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text(UNRESOLVED_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="booking_attempts")
