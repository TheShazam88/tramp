"""Serialize booking attempts and track pending ticketing."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260710_0005"
down_revision = "20260710_0004"
branch_labels = None
depends_on = None


def _require_unique_idempotency_keys() -> None:
    duplicates = op.get_bind().execute(
        sa.text(
            """
            SELECT idempotency_key, count(*) AS duplicate_count
            FROM booking_attempts
            GROUP BY idempotency_key
            HAVING count(*) > 1
            ORDER BY idempotency_key
            LIMIT 10
            """
        )
    )
    rows = list(duplicates)
    if not rows:
        return

    detail = ", ".join(f"{key!r} ({count} rows)" for key, count in rows)
    raise RuntimeError(
        "Duplicate booking attempt idempotency keys prevent migration: "
        f"{detail}. Resolve the duplicate audit rows manually; no history was deleted."
    )


def upgrade() -> None:
    _require_unique_idempotency_keys()
    op.execute(
        "ALTER TYPE booking_attempt_status "
        "ADD VALUE IF NOT EXISTS 'PENDING_TICKETING' AFTER 'REVALIDATED'"
    )
    op.drop_index(
        "ix_booking_attempts_idempotency_key",
        table_name="booking_attempts",
    )
    op.create_unique_constraint(
        "uq_booking_attempts_idempotency_key",
        "booking_attempts",
        ["idempotency_key"],
    )


def downgrade() -> None:
    pending_count = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM booking_attempts "
            "WHERE status::text = 'PENDING_TICKETING'"
        )
    )
    if pending_count:
        raise RuntimeError(
            "Cannot downgrade booking attempt claims while pending-ticketing attempts exist."
        )

    op.drop_constraint(
        "uq_booking_attempts_idempotency_key",
        "booking_attempts",
        type_="unique",
    )
    op.create_index(
        "ix_booking_attempts_idempotency_key",
        "booking_attempts",
        ["idempotency_key"],
    )
    op.execute(
        "ALTER TABLE booking_attempts "
        "ALTER COLUMN status TYPE text USING status::text"
    )
    op.execute("DROP TYPE booking_attempt_status")
    op.execute(
        "CREATE TYPE booking_attempt_status AS ENUM "
        "('STARTED', 'REVALIDATED', 'BOOKED', 'FAILED')"
    )
    op.execute(
        "ALTER TABLE booking_attempts "
        "ALTER COLUMN status TYPE booking_attempt_status "
        "USING status::booking_attempt_status"
    )
