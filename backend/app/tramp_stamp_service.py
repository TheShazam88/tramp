from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_writer_lock
from app.db.models import (
    Booking,
    BookingStatus,
    Deal,
    DestinationMode,
    TrampStampLedger,
    TripWatch,
    User,
)
from app.integrations.service import (
    payload_is_simulated,
    provider_is_simulated,
    source_is_simulated,
)


def list_stamp_history(*, db: Session, user_id: UUID) -> list[dict[str, object]]:
    rows = db.execute(
        select(TrampStampLedger, Booking, TripWatch)
        .join(Booking, Booking.id == TrampStampLedger.booking_id)
        .join(Deal, Deal.id == Booking.deal_id)
        .join(TripWatch, TripWatch.id == Deal.watch_id)
        .where(TrampStampLedger.user_id == user_id)
        .order_by(TrampStampLedger.awarded_at.desc(), TrampStampLedger.id.desc())
    ).all()
    return [
        {
            "id": str(stamp.id),
            "booking_id": str(stamp.booking_id),
            "awarded_at": stamp.awarded_at,
            "provider": booking.provider or "Provider",
            "route": _stamp_route(watch),
            "amount": stamp.amount,
        }
        for stamp, booking, watch in rows
    ]


def _stamp_route(watch: TripWatch) -> str:
    origin = (watch.origin_iatas or ["Origin"])[0]
    if watch.destination_mode == DestinationMode.FLEXIBLE:
        destination = watch.flexible_region or watch.flexible_theme or "Flexible"
    else:
        destination = (watch.destination_iatas or ["Destination"])[0]
    return f"{origin} to {destination}"


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
    execution_simulated: bool | None,
) -> int:
    acquire_activity_writer_lock(db)
    if booking.status not in {BookingStatus.TICKETED, BookingStatus.BOOKED}:
        return 0
    if execution_simulated is not False:
        return 0
    if source_is_simulated(deal.source):
        return 0
    if provider_is_simulated(booking.provider) or payload_is_simulated(provider_payload):
        return 0
    inserted_id = db.scalar(
        insert(TrampStampLedger)
        .values(
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
        .on_conflict_do_nothing(
            constraint="uq_tramp_stamp_ledger_booking_id",
        )
        .returning(TrampStampLedger.id)
    )
    return int(inserted_id is not None)
