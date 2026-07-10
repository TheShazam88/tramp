from __future__ import annotations

from datetime import UTC, datetime, time

from app.db.models import Booking, Deal, TripWatch
from app.integrations.service import get_calendar_connector


def push_booking_to_calendar(*, db, booking: Booking, deal: Deal, watch: TripWatch) -> dict[str, object]:
    connector = get_calendar_connector(db=db, allow_disabled=True)
    starts_at = _watch_start_datetime(watch)
    ends_at = _watch_end_datetime(watch)
    route = " -> ".join((watch.origin_iatas or []) + (watch.destination_iatas or []))
    result = connector.create_event(
        title=f"TRAMP trip · {route or deal.kind}",
        starts_at=starts_at,
        ends_at=ends_at,
        description=deal.summary_text or "Booked via TRAMP.",
        metadata={
            "booking_id": str(booking.id),
            "deal_id": str(deal.id),
            "watch_id": str(watch.id),
        },
    )
    booking.calendar_event_id = str(result.get("event_id") or "") or None
    return result


def remove_booking_from_calendar(*, db, booking: Booking, deal: Deal) -> dict[str, object]:
    if not booking.calendar_event_id:
        return {"skipped": True, "reason": "No calendar event to remove."}
    connector = get_calendar_connector(db=db, allow_disabled=True)
    return connector.cancel_event(
        event_id=booking.calendar_event_id,
        metadata={
            "booking_id": str(booking.id),
            "deal_id": str(deal.id),
        },
    )


def _watch_start_datetime(watch: TripWatch) -> datetime:
    if watch.depart_date_from:
        return datetime.combine(watch.depart_date_from, time(hour=9), tzinfo=UTC)
    return datetime.now(UTC)


def _watch_end_datetime(watch: TripWatch) -> datetime | None:
    if watch.return_date_to:
        return datetime.combine(watch.return_date_to, time(hour=18), tzinfo=UTC)
    if watch.depart_date_to:
        return datetime.combine(watch.depart_date_to, time(hour=18), tzinfo=UTC)
    return None
