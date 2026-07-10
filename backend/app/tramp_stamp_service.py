from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingStatus, Deal, TrampStampLedger, User
from app.integrations.service import (
    payload_is_simulated,
    provider_is_simulated,
    source_is_simulated,
)


def stamp_balance(*, db: Session, user_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(TrampStampLedger.amount), 0)).where(
                TrampStampLedger.user_id == user_id
            )
        )
        or 0
    )


def award_for_live_booking(
    *,
    db: Session,
    user: User,
    booking: Booking,
    deal: Deal,
    provider_payload: dict[str, object] | None,
) -> int:
    if booking.status not in {BookingStatus.TICKETED, BookingStatus.BOOKED}:
        return 0
    if source_is_simulated(deal.source):
        return 0
    if provider_is_simulated(booking.provider) or payload_is_simulated(provider_payload):
        return 0
    existing = db.scalar(
        select(TrampStampLedger).where(TrampStampLedger.booking_id == booking.id)
    )
    if existing is not None:
        return 0

    db.add(
        TrampStampLedger(
            user_id=user.id,
            booking_id=booking.id,
            amount=1,
            reason="live_booking_completed",
            awarded_at=datetime.now(UTC),
            meta_json={
                "deal_id": str(deal.id),
                "watch_id": str(deal.watch_id),
                "provider": booking.provider,
            },
        )
    )
    return 1
