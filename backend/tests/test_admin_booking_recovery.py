from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app import booking_recovery_service
from app.api.deps import require_admin
from app.api.routes import admin as admin_routes
from app.booking_recovery_service import (
    BOOKING_RECOVERY_CONFIRMATION,
    recover_unresolved_booking_attempt,
)
from app.db.models import (
    AuditLog,
    Booking,
    BookingAttempt,
    BookingAttemptStatus,
    BookingStatus,
    Deal,
    DealStatus,
    User,
    UserRole,
)


class _RecoverySession:
    def __init__(self, scalar_results: list[object | None]) -> None:
        self.scalar_results = list(scalar_results)
        self.added: list[object] = []
        self.commits = 0

    def scalar(self, _statement):
        return self.scalar_results.pop(0) if self.scalar_results else None

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1


def _admin() -> User:
    return User(
        id=uuid4(),
        email="admin@example.com",
        password_hash="hashed",
        role=UserRole.ADMIN,
    )


def _attempt(*, deal_id, recovery_required: bool = True) -> BookingAttempt:
    return BookingAttempt(
        id=uuid4(),
        deal_id=deal_id,
        watch_id=uuid4(),
        idempotency_key="ambiguous-booking-attempt",
        status=BookingAttemptStatus.REVALIDATED,
        recovery_required=recovery_required,
        started_at=datetime.now(UTC),
    )


def _deal(*, deal_id) -> Deal:
    return Deal(
        id=deal_id,
        watch_id=uuid4(),
        kind="flight",
        source="live-duffel",
        total_price=640,
        currency="USD",
        fingerprint_hash="admin-recovery-deal",
        status=DealStatus.FAILED,
    )


def test_admin_recovery_marks_unresolved_attempt_failed_and_releases_deal() -> None:
    deal_id = uuid4()
    attempt = _attempt(deal_id=deal_id)
    deal = _deal(deal_id=deal_id)
    db = _RecoverySession([attempt, deal, attempt, None])

    result = recover_unresolved_booking_attempt(
        db=db,
        actor=_admin(),
        idempotency_key=attempt.idempotency_key,
        confirmation=BOOKING_RECOVERY_CONFIRMATION,
    )

    assert result.booking_exists is False
    assert result.deal_status == DealStatus.PROPOSED.value
    assert attempt.status == BookingAttemptStatus.FAILED
    assert attempt.recovery_required is False
    assert attempt.finished_at is not None
    assert deal.status == DealStatus.PROPOSED
    assert db.commits == 1
    audit = next(item for item in db.added if isinstance(item, AuditLog))
    assert audit.action == "booking_attempt.recovered_as_failed"
    assert audit.meta_json["booking_fabricated"] is False


def test_admin_recovery_never_reopens_deal_when_booking_exists() -> None:
    deal_id = uuid4()
    attempt = _attempt(deal_id=deal_id)
    deal = _deal(deal_id=deal_id)
    deal.status = DealStatus.BOOKED
    booking = Booking(
        id=uuid4(),
        deal_id=deal.id,
        provider="duffel",
        status=BookingStatus.TICKETED,
        idempotency_key="existing-booking",
    )
    db = _RecoverySession([attempt, deal, attempt, booking])

    result = recover_unresolved_booking_attempt(
        db=db,
        actor=_admin(),
        idempotency_key=attempt.idempotency_key,
        confirmation=BOOKING_RECOVERY_CONFIRMATION,
    )

    assert result.booking_exists is True
    assert result.booking_id == str(booking.id)
    assert deal.status == DealStatus.BOOKED
    assert attempt.status == BookingAttemptStatus.FAILED
    assert attempt.recovery_required is False


def test_admin_recovery_takes_exclusive_lock_then_locks_deal_before_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deal_id = uuid4()
    attempt = _attempt(deal_id=deal_id)
    deal = _deal(deal_id=deal_id)
    lock_calls: list[str] = []
    query_order: list[tuple[type[object], bool]] = []

    class LockOrderSession:
        added: list[object] = []

        def scalar(self, statement):
            entity = statement.column_descriptions[0]["entity"]
            query_order.append((entity, statement._for_update_arg is not None))
            if entity is BookingAttempt:
                return attempt
            if entity is Deal:
                return deal
            return None

        def add(self, value: object) -> None:
            self.added.append(value)

        def commit(self) -> None:
            return None

    monkeypatch.setattr(
        booking_recovery_service,
        "acquire_activity_maintenance_lock",
        lambda _db: lock_calls.append("exclusive"),
        raising=False,
    )

    recover_unresolved_booking_attempt(
        db=LockOrderSession(),
        actor=_admin(),
        idempotency_key=attempt.idempotency_key,
        confirmation=BOOKING_RECOVERY_CONFIRMATION,
    )

    assert lock_calls == ["exclusive"]
    assert query_order == [
        (BookingAttempt, False),
        (Deal, True),
        (BookingAttempt, True),
        (Booking, False),
    ]


def test_admin_recovery_requires_confirmation_and_unresolved_state() -> None:
    deal_id = uuid4()
    attempt = _attempt(deal_id=deal_id, recovery_required=False)
    attempt.status = BookingAttemptStatus.BOOKED

    with pytest.raises(ValueError, match=BOOKING_RECOVERY_CONFIRMATION):
        recover_unresolved_booking_attempt(
            db=_RecoverySession([]),
            actor=_admin(),
            idempotency_key=attempt.idempotency_key,
            confirmation="recover",
        )

    with pytest.raises(ValueError, match="not unresolved"):
        recover_unresolved_booking_attempt(
            db=_RecoverySession([attempt]),
            actor=_admin(),
            idempotency_key=attempt.idempotency_key,
            confirmation=BOOKING_RECOVERY_CONFIRMATION,
        )


def test_admin_recovery_endpoint_is_admin_only() -> None:
    route = next(
        route
        for route in admin_routes.router.routes
        if route.path
        == "/booking-attempts/{idempotency_key}/recover-failed"
    )

    assert require_admin in {
        dependency.call for dependency in route.dependant.dependencies
    }
