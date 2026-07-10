"""Serialize booking attempts with a durable idempotency claim."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260710_0005"
down_revision = "20260710_0004"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_booking_attempts_idempotency_key"
TEMPORARY_INDEX_NAME = "ux_booking_attempts_idempotency_key_claim"
LEGACY_INDEX_NAME = "ix_booking_attempts_idempotency_key"


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


def _constraint_exists() -> bool:
    return bool(
        op.get_bind().scalar(
            sa.text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = :constraint_name
                      AND conrelid = 'booking_attempts'::regclass
                )
                """
            ),
            {"constraint_name": CONSTRAINT_NAME},
        )
    )


def _rebuild_temporary_unique_index() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                f'DROP INDEX CONCURRENTLY IF EXISTS "{TEMPORARY_INDEX_NAME}"'
            )
        )
        op.execute(
            sa.text(
                f'CREATE UNIQUE INDEX CONCURRENTLY "{TEMPORARY_INDEX_NAME}" '
                "ON booking_attempts (idempotency_key)"
            )
        )


def _drop_temporary_index() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                f'DROP INDEX CONCURRENTLY IF EXISTS "{TEMPORARY_INDEX_NAME}"'
            )
        )


def upgrade() -> None:
    _require_unique_idempotency_keys()
    op.execute(
        "ALTER TABLE booking_attempts "
        "ADD COLUMN IF NOT EXISTS provider_booking_ref VARCHAR(255)"
    )
    if not _constraint_exists():
        _rebuild_temporary_unique_index()
        op.execute(
            sa.text(
                f'ALTER TABLE booking_attempts ADD CONSTRAINT "{CONSTRAINT_NAME}" '
                f'UNIQUE USING INDEX "{TEMPORARY_INDEX_NAME}"'
            )
        )
    else:
        _drop_temporary_index()
    op.execute(sa.text(f'DROP INDEX IF EXISTS "{LEGACY_INDEX_NAME}"'))


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(
            CONSTRAINT_NAME,
            "booking_attempts",
            type_="unique",
        )
    with op.get_context().autocommit_block():
        op.execute(
            sa.text(
                f'DROP INDEX CONCURRENTLY IF EXISTS "{TEMPORARY_INDEX_NAME}"'
            )
        )
        op.execute(
            sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{LEGACY_INDEX_NAME}"')
        )
        op.execute(
            sa.text(
                f'CREATE INDEX CONCURRENTLY "{LEGACY_INDEX_NAME}" '
                "ON booking_attempts (idempotency_key)"
            )
        )
    op.execute(
        "ALTER TABLE booking_attempts "
        "DROP COLUMN IF EXISTS provider_booking_ref"
    )
