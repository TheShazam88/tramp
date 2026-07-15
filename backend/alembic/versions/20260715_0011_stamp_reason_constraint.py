"""Install the TRAMP-Stamp reason constraint for upgraded databases."""

from __future__ import annotations

from alembic import op

revision = "20260715_0011"
down_revision = "20260715_0010"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "ck_tramp_stamp_ledger_reason"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{CONSTRAINT_NAME}'
                  AND conrelid = 'tramp_stamp_ledger'::regclass
            ) THEN
                ALTER TABLE tramp_stamp_ledger
                ADD CONSTRAINT {CONSTRAINT_NAME}
                CHECK (reason = 'live_booking_completed');
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE tramp_stamp_ledger "
        "DROP CONSTRAINT IF EXISTS ck_tramp_stamp_ledger_reason"
    )
