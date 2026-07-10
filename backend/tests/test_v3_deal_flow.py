from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("APP_SECRET", "test-master-secret-with-more-than-32-bytes")
os.environ.setdefault("BOOKING_MASTER_KEY_PASSPHRASE", "test-master-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PUBLIC_BASE_URL", "https://tramp.test")

from app.approval_service import issue_approval_token
from app.config import get_settings
from app.db.models import (
    Deal,
    DealStatus,
    DestinationMode,
    NotificationChannel,
    SuppressedAttribute,
    SuppressedAttributeType,
    TripMode,
    TripWatch,
    User,
)
from app.deal_service import confirm_deal_intent, create_approval_token, reject_deal
from app.security.tokens import SignedTokenService
from app.service_errors import ConflictError
from app.watch_service import _queue_deal_notifications


class FakeSession:
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []
        self.committed = False
        self.refreshed: list[object] = []

    def scalar(self, *_args, **_kwargs):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, value: object) -> None:
        self.refreshed.append(value)


def _build_user() -> User:
    return User(
        id=uuid4(),
        email="traveler@example.com",
        password_hash="hashed-password",
        totp_secret="JBSWY3DPEHPK3PXP",
        default_notify_channel=NotificationChannel.EMAIL,
    )


def _build_watch(*, user: User) -> TripWatch:
    return TripWatch(
        id=uuid4(),
        user_id=user.id,
        trip_mode=TripMode.FLIGHTS_THEN_HOTELS,
        destination_mode=DestinationMode.FIXED,
        origin_iatas=["HND"],
        destination_iatas=["SIN"],
        depart_date_from=date(2027, 4, 12),
        return_date_to=date(2027, 4, 19),
        cabin_class="business",
        budget_currency="USD",
        prefer_refundable=True,
        want_car=False,
        glide_start_days=42,
        glide_end_days=3,
        quality_floor=40,
        luxury_vs_savings=0.6,
        loyalty_weighting=0.0,
        band_tolerance=0.10,
        value_pressure=0.0,
        notify_channel=NotificationChannel.EMAIL,
    )


def _build_deal(*, watch: TripWatch) -> Deal:
    return Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="mock-amadeus",
        total_price=Decimal("420.00"),
        currency="USD",
        fingerprint_hash="flight-fingerprint",
        status=DealStatus.PROPOSED,
        value_score=88.0,
        quality_index=90.0,
        summary_text="Lowest 12% seen in the last 90 days.",
        payload_json={
            "airline_code": "NH",
            "supplier": "ANA",
            "layover_minutes": 95,
            "hotel_name": "Singapore Harbor Grand",
            "hotel_chain": "Marriott",
            "area_cluster": "Marina Bay",
        },
    )


def test_confirm_deal_intent_consumes_token_and_marks_confirmed(monkeypatch) -> None:
    user = _build_user()
    watch = _build_watch(user=user)
    deal = _build_deal(watch=watch)
    token_service = SignedTokenService()
    signed = issue_approval_token(deal=deal, user=user, token_service=token_service)
    db = FakeSession()

    monkeypatch.setattr("app.deal_service.get_owned_deal_record", lambda **_kwargs: deal)
    monkeypatch.setattr("app.deal_service.verify_totp_code", lambda **_kwargs: True)

    response = confirm_deal_intent(
        db=db,
        user=user,
        deal_id=deal.id,
        token=signed.token,
        totp_code="123456",
        token_service=token_service,
    )

    assert response.status == "confirmed"
    assert deal.status == DealStatus.CONFIRMED
    assert deal.confirm_token_hash is None
    assert db.committed is True


def test_approval_token_requires_proposed_deal(monkeypatch) -> None:
    user = _build_user()
    watch = _build_watch(user=user)
    deal = _build_deal(watch=watch)
    deal.status = DealStatus.REJECTED
    db = FakeSession()
    monkeypatch.setattr("app.deal_service.get_owned_deal_record", lambda **_kwargs: deal)

    with pytest.raises(ConflictError, match="Only proposed deals"):
        create_approval_token(
            db=db,
            user=user,
            deal_id=deal.id,
            token_service=SignedTokenService(),
        )


def test_reject_deal_wrong_airline_adds_suppression_and_feedback(monkeypatch) -> None:
    user = _build_user()
    watch = _build_watch(user=user)
    deal = _build_deal(watch=watch)
    db = FakeSession(scalar_results=[None, None])

    monkeypatch.setattr("app.deal_service.get_owned_deal_record", lambda **_kwargs: deal)
    monkeypatch.setattr("app.deal_service.get_owned_watch_for_deal", lambda **_kwargs: watch)

    response = reject_deal(
        db=db,
        user=user,
        deal_id=deal.id,
        reason="wrong_airline",
    )

    suppressed = [item for item in db.added if isinstance(item, SuppressedAttribute)]
    assert response.status == "rejected"
    assert deal.status == DealStatus.REJECTED
    assert suppressed
    assert suppressed[0].attr_type == SuppressedAttributeType.AIRLINE
    assert suppressed[0].attr_value == "NH"


def test_repeated_rejection_cannot_change_watch_preferences_again(monkeypatch) -> None:
    user = _build_user()
    watch = _build_watch(user=user)
    deal = _build_deal(watch=watch)
    deal.status = DealStatus.REJECTED
    db = FakeSession()
    monkeypatch.setattr("app.deal_service.get_owned_deal_record", lambda **_kwargs: deal)

    with pytest.raises(ConflictError, match="Only proposed deals"):
        reject_deal(
            db=db,
            user=user,
            deal_id=deal.id,
            reason="too_pricey",
        )

    assert watch.value_pressure == 0.0


def test_reject_deal_too_pricey_increases_value_pressure(monkeypatch) -> None:
    user = _build_user()
    watch = _build_watch(user=user)
    deal = _build_deal(watch=watch)
    db = FakeSession(scalar_results=[None])

    monkeypatch.setattr("app.deal_service.get_owned_deal_record", lambda **_kwargs: deal)
    monkeypatch.setattr("app.deal_service.get_owned_watch_for_deal", lambda **_kwargs: watch)

    response = reject_deal(
        db=db,
        user=user,
        deal_id=deal.id,
        reason="too_pricey",
    )

    assert response.action_taken == {
        "reason": "too_pricey",
        "fingerprint_recorded": True,
        "value_pressure": 0.1,
    }
    assert watch.value_pressure == 0.1


def test_queue_deal_notifications_builds_signed_review_link(monkeypatch) -> None:
    user = _build_user()
    watch = _build_watch(user=user)
    deal = _build_deal(watch=watch)
    db = FakeSession(scalar_results=[None])
    captured: dict[str, object] = {}

    get_settings.cache_clear()

    def _capture_queue_notification(**kwargs):
        captured.update(kwargs)
        return [SimpleNamespace(id=uuid4())]

    monkeypatch.setattr("app.watch_service.queue_notification", _capture_queue_notification)

    deliveries = _queue_deal_notifications(
        db=db,
        user=user,
        watch=watch,
        deals=[deal],
    )

    assert deliveries
    assert deal.confirm_token_hash
    assert captured["message_type"] == "deal.proposed"
    assert "approvalToken=" in str(captured["body"])
    assert f"/deals/{deal.id}" in str(captured["body"])
    assert f"watchId={watch.id}" in str(captured["body"])
