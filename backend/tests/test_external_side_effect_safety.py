from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import disruption_service, notification_service
from app.calendar_service import push_booking_to_calendar
from app.db.models import (
    Booking,
    BookingStatus,
    Deal,
    DealStatus,
    DestinationMode,
    DisruptionType,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTransport,
    TripMode,
    TripWatch,
    User,
)
from app.notification_service import queue_notification, send_notification_delivery


class _RecordingSession:
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []
        self.commits = 0

    def scalar(self, _statement):
        return self.scalar_results.pop(0) if self.scalar_results else None

    def add(self, value: object) -> None:
        self.added.append(value)

    def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = uuid4()

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, _value: object) -> None:
        return None


def _user() -> User:
    return User(
        id=uuid4(),
        email="traveler@example.com",
        password_hash="hashed",
        default_notify_channel=NotificationChannel.EMAIL,
    )


def _watch(*, user: User) -> TripWatch:
    return TripWatch(
        id=uuid4(),
        user_id=user.id,
        trip_mode=TripMode.FLIGHTS_ONLY,
        destination_mode=DestinationMode.FIXED,
        origin_iatas=["HND"],
        destination_iatas=["SIN"],
        depart_date_from=date(2027, 4, 12),
        return_date_to=date(2027, 4, 19),
    )


def _deal(*, watch: TripWatch) -> Deal:
    return Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="mock-duffel",
        total_price=640,
        currency="USD",
        fingerprint_hash="simulated-side-effect-safety",
        status=DealStatus.PROPOSED,
    )


def test_simulated_notification_is_recorded_as_log_only() -> None:
    user = _user()
    watch = _watch(user=user)
    deal = _deal(watch=watch)
    db = _RecordingSession()

    deliveries = queue_notification(
        db=db,
        user=user,
        message_type="deal.proposed",
        subject="Simulated deal",
        body="Local audit only.",
        deal=deal,
        simulated=True,
        integration=SimpleNamespace(credentials={"delivery_mode": "smtp_dev"}),
    )

    assert len(deliveries) == 1
    assert deliveries[0].transport == NotificationTransport.LOG_ONLY
    assert deliveries[0].status == NotificationDeliveryStatus.PENDING
    assert deliveries[0].payload_json["simulated"] is True
    assert deliveries[0].payload_json["external_side_effect_suppressed"] is True


def test_log_only_delivery_never_resolves_external_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    delivery = NotificationDelivery(
        id=uuid4(),
        user_id=user.id,
        channel=NotificationChannel.EMAIL.value,
        transport=NotificationTransport.LOG_ONLY,
        destination=user.email,
        message_type="deal.proposed",
        status=NotificationDeliveryStatus.PENDING,
        attempted_at=datetime.now(UTC),
        payload_json={
            "subject": "Simulated deal",
            "body": "Local audit only.",
            "force": True,
            "simulated": True,
            "external_side_effect_suppressed": True,
        },
    )
    db = _RecordingSession([delivery, user])

    def fail_if_resolved(**_kwargs):
        raise AssertionError("An external notification connector must not be resolved.")

    monkeypatch.setattr(
        notification_service,
        "get_notification_connector",
        fail_if_resolved,
    )

    result = send_notification_delivery(db=db, delivery_id=delivery.id)

    assert result.status == NotificationDeliveryStatus.SENT
    assert result.delivered_at is not None
    assert result.payload_json["response"]["transport"] == "log_only"
    assert result.payload_json["response"]["external_side_effect_suppressed"] is True
    assert db.commits == 1


def test_simulated_booking_calendar_sync_uses_local_audit_only() -> None:
    user = _user()
    watch = _watch(user=user)
    deal = _deal(watch=watch)
    booking = Booking(
        id=uuid4(),
        deal_id=deal.id,
        provider="mock-booking",
        status=BookingStatus.TICKETED,
        idempotency_key="simulated-calendar-booking",
    )

    class _FailingExternalConnector:
        def create_event(self, **_kwargs):
            raise AssertionError("A simulated booking must not call an external calendar.")

    result = push_booking_to_calendar(
        db=SimpleNamespace(),
        booking=booking,
        deal=deal,
        watch=watch,
        connector=_FailingExternalConnector(),
        simulated=True,
    )

    assert result["transport"] == "log_only"
    assert result["simulated"] is True
    assert result["external_side_effect_suppressed"] is True
    assert booking.calendar_event_id == f"logonly-{booking.id}"


def test_manual_disruption_test_forces_log_only_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    booking = Booking(
        id=uuid4(),
        deal_id=uuid4(),
        provider="duffel",
        provider_booking_ref="LIVE-BOOKING-1",
        status=BookingStatus.TICKETED,
        idempotency_key="live-booking-disruption-test",
    )
    captured: dict[str, object] = {}

    def capture_notification(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(disruption_service, "queue_notification", capture_notification)

    disruption = disruption_service.create_disruption(
        db=_RecordingSession(),
        booking=booking,
        user=user,
        kind=DisruptionType.MANUAL_TEST,
    )

    assert disruption.detail_json["simulated"] is True
    assert captured["simulated"] is True
