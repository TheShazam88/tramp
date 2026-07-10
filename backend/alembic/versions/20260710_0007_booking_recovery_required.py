"""Persist fail-safe booking recovery state."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260710_0007"
down_revision = "20260710_0006"
branch_labels = None
depends_on = None

INDEX_NAME = "ux_booking_attempts_unresolved_deal"
ACTIVE_PREDICATE = (
    "status IN ('STARTED', 'REVALIDATED') OR recovery_required IS TRUE"
)
LEGACY_PREDICATE = "status IN ('STARTED', 'REVALIDATED')"


def _require_unique_active_deals() -> None:
    duplicates = op.get_bind().execute(
        sa.text(
            """
            SELECT
                deal_id,
                count(*) AS duplicate_count,
                array_agg(idempotency_key ORDER BY started_at, id) AS attempt_keys
            FROM booking_attempts
            WHERE status IN ('STARTED', 'REVALIDATED')
               OR recovery_required IS TRUE
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
        "Duplicate active booking recovery attempts prevent migration: "
        f"{detail}. Resolve the conflicting states manually; no audit data was deleted."
    )


def upgrade() -> None:
    op.add_column(
        "booking_attempts",
        sa.Column(
            "recovery_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE booking_attempts
            SET recovery_required = TRUE
            WHERE response_payload_json->>'conflict_code'
                IN ('pending_ticketing', 'provider_failed')
            """
        )
    )
    op.drop_index(INDEX_NAME, table_name="booking_attempts")
    _require_unique_active_deals()
    op.create_index(
        INDEX_NAME,
        "booking_attempts",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="booking_attempts")
    op.create_index(
        INDEX_NAME,
        "booking_attempts",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text(LEGACY_PREDICATE),
    )
    op.drop_column("booking_attempts", "recovery_required")
