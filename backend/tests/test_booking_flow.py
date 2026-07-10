from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.approval_service import consume_approval_token, issue_approval_token, verify_approval_token
from app.config import get_settings
from app.db.models import (
    Booking,
    CancellationStatus,
    Deal,
    DealStatus,
    DestinationMode,
    NotificationChannel,
    PaymentMethod,
    TripMode,
    TripWatch,
    User,
)
from app.security.tokens import SignedTokenService
from app.watch_mock_adapter import DeterministicMockAdapter


def _configure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET", "test-master-secret")
    monkeypatch.setenv("BOOKING_MASTER_KEY_PASSPHRASE", "test-master-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://travel-watch.test")
    get_settings.cache_clear()


def _build_user() -> User:
    return User(
        id=uuid4(),
        email="traveler@example.com",
        password_hash="hashed-password",
        totp_secret="BASE32SECRET234567",
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
        want_car=True,
        glide_start_days=42,
        glide_end_days=3,
        quality_floor=40,
        luxury_vs_savings=0.6,
        loyalty_weighting=0.0,
        band_tolerance=0.10,
        value_pressure=0.0,
    )


def test_approval_token_is_single_use_and_rotates(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch)
    token_service = SignedTokenService()
    user = _build_user()
    deal = Deal(
        id=uuid4(),
        watch_id=uuid4(),
        kind="flight",
        source="mock-duffel",
        total_price=Decimal("420.00"),
        currency="USD",
        fingerprint_hash="flight-fingerprint",
        status=DealStatus.PROPOSED,
    )

    first = issue_approval_token(deal=deal, user=user, token_service=token_service)
    first_hash = deal.confirm_token_hash
    claims = verify_approval_token(
        deal=deal,
        user=user,
        token=first.token,
        token_service=token_service,
    )
    assert claims["deal_id"] == str(deal.id)

    second = issue_approval_token(deal=deal, user=user, token_service=token_service)
    assert deal.confirm_token_hash != first_hash

    with pytest.raises(ValueError):
        verify_approval_token(deal=deal, user=user, token=first.token, token_service=token_service)

    verify_approval_token(deal=deal, user=user, token=second.token, token_service=token_service)
    consume_approval_token(deal=deal)

    with pytest.raises(ValueError):
        verify_approval_token(deal=deal, user=user, token=second.token, token_service=token_service)


def test_mock_booking_result_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch)
    user = _build_user()
    watch = _build_watch(user=user)
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="trip_bundle",
        source="mock-duffel+mock-booking",
        total_price=Decimal("640.00"),
        currency="USD",
        fingerprint_hash="bundle-fingerprint",
        status=DealStatus.PROPOSED,
        loyalty_plan_json=[
            {
                "traveler_name": "Alex",
                "program_code": "NH",
                "alliance": "star",
                "note": "Attach ANA number at ticketing.",
            }
        ],
        payload_json={
            "components": {
                "flight": {"refundable": True},
                "hotel": {"refundable": False},
                "car": {"refundable": True},
            }
        },
    )
    payment_method = PaymentMethod(
        id=uuid4(),
        user_id=user.id,
        label="Visa",
        encrypted_blob="encrypted",
        last4="4242",
    )
    adapter = DeterministicMockAdapter()
    booked_at = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)

    first = adapter.book_deal(
        deal=deal,
        watch=watch,
        payment_method=payment_method,
        booked_at=booked_at,
    )
    second = adapter.book_deal(
        deal=deal,
        watch=watch,
        payment_method=payment_method,
        booked_at=booked_at,
    )

    assert first == second
    assert first.provider_booking_ref.startswith("TB-")
    assert first.amount_charged == Decimal("640.00")

    booking = Booking(
        deal_id=deal.id,
        provider=first.provider,
        provider_booking_ref=first.provider_booking_ref,
        status=first.status,
        idempotency_key="booking-12345",
        amount_charged=first.amount_charged,
        currency=first.currency,
    )
    cancellation = adapter.cancel_booking(
        booking=booking,
        deal=deal,
        reason="Need to reschedule",
        requested_at=booked_at,
    )

    assert cancellation.status == CancellationStatus.REFUNDED
    assert cancellation.refund_received == Decimal("384.00")


def test_nonrefundable_mock_booking_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch)
    user = _build_user()
    watch = _build_watch(user=user)
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="hotel",
        source="mock-booking",
        total_price=Decimal("250.00"),
        currency="USD",
        fingerprint_hash="hotel-fingerprint",
        status=DealStatus.PROPOSED,
        payload_json={"refundable": False},
    )
    payment_method = PaymentMethod(
        id=uuid4(),
        user_id=user.id,
        label="Visa",
        encrypted_blob="encrypted",
        last4="1111",
    )
    adapter = DeterministicMockAdapter()
    booked_at = datetime(2026, 6, 29, 13, 0, tzinfo=UTC)
    booked = adapter.book_deal(
        deal=deal,
        watch=watch,
        payment_method=payment_method,
        booked_at=booked_at,
    )
    booking = Booking(
        deal_id=deal.id,
        provider=booked.provider,
        provider_booking_ref=booked.provider_booking_ref,
        status=booked.status,
        idempotency_key="booking-67890",
        amount_charged=booked.amount_charged,
        currency=booked.currency,
    )

    cancellation = adapter.cancel_booking(
        booking=booking,
        deal=deal,
        reason="Price dropped elsewhere",
        requested_at=booked_at,
    )

    assert cancellation.status == CancellationStatus.DENIED
    assert cancellation.refund_received == Decimal("0.00")
