from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_writer_lock
from app.db.models import (
    AuditLog,
    Booking,
    BookingAttempt,
    BookingAttemptStatus,
    Deal,
    DealStatus,
    User,
)

BOOKING_RECOVERY_CONFIRMATION = "MARK ATTEMPT FAILED"


@dataclass(frozen=True, slots=True)
class BookingAttemptRecoveryResult:
    idempotency_key: str
    attempt_status: str
    recovery_required: bool
    deal_id: str
    deal_status: str
    booking_exists: bool
    booking_id: str | None


def recover_unresolved_booking_attempt(
    *,
    db: Session,
    actor: User,
    idempotency_key: str,
    confirmation: str,
) -> BookingAttemptRecoveryResult:
    if confirmation != BOOKING_RECOVERY_CONFIRMATION:
        raise ValueError(
            f"Confirmation must exactly match {BOOKING_RECOVERY_CONFIRMATION}."
        )

    acquire_activity_writer_lock(db)
    attempt = db.scalar(
        select(BookingAttempt)
        .where(BookingAttempt.idempotency_key == idempotency_key)
        .with_for_update()
    )
    if attempt is None:
        raise LookupError("Booking attempt not found.")
    if (
        attempt.status
        not in {
            BookingAttemptStatus.STARTED,
            BookingAttemptStatus.REVALIDATED,
        }
        and not attempt.recovery_required
    ):
        raise ValueError("Booking attempt is not unresolved.")

    booking_conditions = [Booking.deal_id == attempt.deal_id]
    if attempt.booking_id is not None:
        booking_conditions.append(Booking.id == attempt.booking_id)
    booking = db.scalar(
        select(Booking)
        .where(or_(*booking_conditions))
        .order_by(Booking.booked_at.desc().nullslast(), Booking.id.desc())
        .limit(1)
    )
    deal = db.scalar(
        select(Deal).where(Deal.id == attempt.deal_id).with_for_update()
    )
    if deal is None:
        raise LookupError("Deal not found.")

    recovered_at = datetime.now(UTC)
    attempt.status = BookingAttemptStatus.FAILED
    attempt.recovery_required = False
    attempt.finished_at = attempt.finished_at or recovered_at
    attempt.error_text = (
        "Administratively marked failed after explicit unresolved-attempt recovery."
    )
    attempt.response_payload_json = {
        **(attempt.response_payload_json or {}),
        "conflict_code": "admin_recovered",
        "safe_to_retry": False,
        "admin_recovered": True,
    }
    if booking is None:
        deal.status = DealStatus.PROPOSED

    db.add(attempt)
    db.add(deal)
    db.add(
        AuditLog(
            actor=f"admin:{actor.id}",
            action="booking_attempt.recovered_as_failed",
            target=f"booking_attempt:{attempt.id}",
            at=recovered_at,
            meta_json={
                "idempotency_key": attempt.idempotency_key,
                "deal_id": str(deal.id),
                "booking_exists": booking is not None,
                "booking_id": str(booking.id) if booking else None,
                "booking_fabricated": False,
                "deal_reopened": booking is None,
                "confirmation": BOOKING_RECOVERY_CONFIRMATION,
            },
        )
    )
    db.commit()

    deal_status = (
        deal.status.value if hasattr(deal.status, "value") else str(deal.status)
    )
    attempt_status = (
        attempt.status.value
        if hasattr(attempt.status, "value")
        else str(attempt.status)
    )
    return BookingAttemptRecoveryResult(
        idempotency_key=attempt.idempotency_key,
        attempt_status=attempt_status,
        recovery_required=attempt.recovery_required,
        deal_id=str(deal.id),
        deal_status=deal_status,
        booking_exists=booking is not None,
        booking_id=str(booking.id) if booking else None,
    )
