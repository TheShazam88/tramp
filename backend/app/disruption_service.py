from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_maintenance_lock
from app.db.models import (
    AuditLog,
    Booking,
    Disruption,
    DisruptionStatus,
    DisruptionType,
    User,
)
from app.notification_service import queue_notification


def create_disruption(
    *,
    db: Session,
    booking: Booking,
    user: User,
    kind: DisruptionType = DisruptionType.MANUAL_TEST,
    detail: dict[str, object] | None = None,
) -> Disruption:
    acquire_activity_maintenance_lock(db)
    disruption = Disruption(
        booking_id=booking.id,
        type=kind,
        detail_json=detail or {"message": "Manual localhost disruption test."},
        status=DisruptionStatus.NEW,
        detected_at=datetime.now(UTC),
    )
    db.add(disruption)
    db.flush()
    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action="disruption.created",
            target=f"booking:{booking.id}",
            at=disruption.detected_at,
            meta_json={"disruption_id": str(disruption.id), "type": disruption.type.value},
        )
    )
    queue_notification(
        db=db,
        user=user,
        message_type="disruption.created",
        subject="TRAMP disruption alert",
        body=f"A disruption was recorded for booking {booking.provider_booking_ref or booking.id}.",
        booking=booking,
        disruption=disruption,
    )
    disruption.status = DisruptionStatus.NOTIFIED
    disruption.notified_at = datetime.now(UTC)
    db.add(disruption)
    db.commit()
    db.refresh(disruption)
    return disruption


def list_disruptions_for_booking(*, db: Session, booking_id: UUID) -> list[Disruption]:
    return list(
        db.scalars(
            select(Disruption)
            .where(Disruption.booking_id == booking_id)
            .order_by(Disruption.detected_at.desc(), Disruption.id.desc())
        )
    )


def resolve_disruption(*, db: Session, disruption_id: UUID, user: User) -> Disruption:
    acquire_activity_maintenance_lock(db)
    disruption = db.scalar(select(Disruption).where(Disruption.id == disruption_id))
    if disruption is None:
        raise LookupError("Disruption not found.")
    disruption.status = DisruptionStatus.RESOLVED
    disruption.resolved_at = datetime.now(UTC)
    db.add(disruption)
    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action="disruption.resolved",
            target=f"disruption:{disruption.id}",
            at=disruption.resolved_at,
            meta_json={"booking_id": str(disruption.booking_id)},
        )
    )
    db.commit()
    db.refresh(disruption)
    return disruption
