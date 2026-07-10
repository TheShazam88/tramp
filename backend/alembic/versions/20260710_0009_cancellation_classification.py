"""Classify cancellation provenance without guessing legacy live activity."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260710_0009"
down_revision = "20260710_0008"
branch_labels = None
depends_on = None

SIMULATED_COMPONENT_PATTERN = r"(^|\+)[[:space:]]*(mock-|local-safe-|off-)"


def upgrade() -> None:
    provenance_enum = postgresql.ENUM(
        "simulated",
        "live",
        "unknown",
        name="cancellation_provenance",
    )
    provenance_enum.create(op.get_bind(), checkfirst=False)
    op.add_column("cancellations", sa.Column("provenance", provenance_enum, nullable=True))

    op.get_bind().execute(
        sa.text(
            """
            UPDATE cancellations AS cancellation
            SET provenance = CASE
                WHEN cancellation.execution_simulated IS TRUE
                  OR lower(COALESCE(cancellation.provider, '')) ~ :simulated_pattern
                  OR cancellation.provider_payload_json->'simulated' = 'true'::jsonb
                  OR lower(COALESCE(booking.provider, '')) ~ :simulated_pattern
                  OR lower(COALESCE(deal.source, '')) ~ :simulated_pattern
                  OR EXISTS (
                      SELECT 1
                      FROM booking_attempts AS attempt
                      WHERE (
                          attempt.booking_id = booking.id
                          OR (
                              attempt.booking_id IS NULL
                              AND attempt.deal_id = booking.deal_id
                          )
                      )
                        AND (
                            attempt.request_payload_json->'simulated' = 'true'::jsonb
                            OR attempt.response_payload_json->'simulated' = 'true'::jsonb
                        )
                  )
                THEN 'simulated'::cancellation_provenance
                WHEN cancellation.execution_simulated IS FALSE
                THEN 'live'::cancellation_provenance
                ELSE 'unknown'::cancellation_provenance
            END
            FROM bookings AS booking
            JOIN deals AS deal ON deal.id = booking.deal_id
            WHERE cancellation.booking_id = booking.id
            """
        ),
        {"simulated_pattern": SIMULATED_COMPONENT_PATTERN},
    )
    op.alter_column(
        "cancellations",
        "provenance",
        existing_type=provenance_enum,
        nullable=False,
        server_default="unknown",
    )


def downgrade() -> None:
    op.drop_column("cancellations", "provenance")
    postgresql.ENUM(
        "simulated",
        "live",
        "unknown",
        name="cancellation_provenance",
    ).drop(op.get_bind(), checkfirst=False)
