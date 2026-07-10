from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import booking_service
from app.api.routes import bookings as booking_routes
from app.api.routes.bookings import _map_service_error
from app.api.schemas import bookings as booking_schemas
from app.db.models import (
    Booking,
    BookingAttempt,
    BookingAttemptStatus,
    Deal,
    DealStatus,
    PaymentMethod,
    TripWatch,
    User,
)
from app.service_errors import ConflictError


class _RecordingSession:
    def __init__(self, scalar_results: list[object | None] | None = None) -> None:
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []
        self.commits = 0

    def scalar(self, _statement):
        return self.scalar_results.pop(0) if self.scalar_results else None

    def add(self, value: object) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1


def _attempt(
    *,
    user_id=None,
    deal_id=None,
    watch_id=None,
    payment_method_id=None,
    status: BookingAttemptStatus = BookingAttemptStatus.STARTED,
) -> BookingAttempt:
    user_id = user_id or uuid4()
    deal_id = deal_id or uuid4()
    watch_id = watch_id or uuid4()
    payment_method_id = payment_method_id or uuid4()
    return BookingAttempt(
        id=uuid4(),
        deal_id=deal_id,
        watch_id=watch_id,
        idempotency_key="attempt-key-123",
        status=status,
        request_payload_json={
            "user_id": str(user_id),
            "deal_id": str(deal_id),
            "watch_id": str(watch_id),
            "payment_method_id": str(payment_method_id),
        },
        started_at=datetime.now(UTC),
    )


def test_conflict_route_returns_structured_safe_detail() -> None:
    response = _map_service_error(
        ConflictError(
            "Refresh this deal before starting a new attempt.",
            code="deal_expired",
            safe_to_retry=True,
        )
    )

    assert response.status_code == 409
    assert response.detail == {
        "code": "deal_expired",
        "message": "Refresh this deal before starting a new attempt.",
        "safe_to_retry": True,
    }


def test_reconciliation_schema_exposes_only_sanitized_attempt_state() -> None:
    response = booking_schemas.BookingAttemptReconciliationResponse(
        idempotency_key="attempt-key-123",
        deal_id=str(uuid4()),
        payment_method_id=str(uuid4()),
        status=BookingAttemptStatus.FAILED,
        code="provider_failed",
        message="The provider could not confirm this booking. Manual recovery is required.",
        safe_to_retry=False,
        recovery_required=True,
        booking=None,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )

    assert response.code == "provider_failed"
    assert response.recovery_required is True
    assert "provider-secret" not in response.model_dump_json()


def test_reconciliation_route_uses_authenticated_user_without_approval_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=uuid4(), email="owner@example.com", password_hash="hashed")
    expected = booking_schemas.BookingAttemptReconciliationResponse(
        idempotency_key="attempt-key-123",
        deal_id=str(uuid4()),
        payment_method_id=str(uuid4()),
        status=BookingAttemptStatus.STARTED,
        code="attempt_in_progress",
        message="Booking attempt is processing.",
        safe_to_retry=False,
        recovery_required=False,
        booking=None,
        started_at=datetime.now(UTC),
    )
    calls: list[dict[str, object]] = []

    def reconcile(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(booking_routes, "reconcile_booking_attempt", reconcile)

    response = asyncio.run(
        booking_routes.reconcile_booking_attempt_record(
            idempotency_key="attempt-key-123",
            current_user=user,
            db=SimpleNamespace(),
        )
    )

    assert response is expected
    assert len(calls) == 1
    assert calls[0]["user"] is user
    assert calls[0]["idempotency_key"] == "attempt-key-123"


def test_reconciliation_is_user_scoped_and_hides_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=uuid4(), email="owner@example.com", password_hash="hashed")
    payment_method_id = uuid4()
    attempt = _attempt(
        user_id=user.id,
        payment_method_id=payment_method_id,
        status=BookingAttemptStatus.FAILED,
    )
    attempt.error_text = "provider-secret: card gateway timeout"
    attempt.recovery_required = True
    attempt.response_payload_json = {
        "conflict_code": "provider_failed",
        "safe_to_retry": False,
    }
    owner_db = _RecordingSession([attempt])

    response = booking_service.reconcile_booking_attempt(
        db=owner_db,
        user=user,
        idempotency_key=attempt.idempotency_key,
    )

    assert response.code == "provider_failed"
    assert response.safe_to_retry is False
    assert response.recovery_required is True
    assert "provider-secret" not in response.message

    other_user = User(id=uuid4(), email="other@example.com", password_hash="hashed")
    with pytest.raises(LookupError, match="Booking attempt not found"):
        booking_service.reconcile_booking_attempt(
            db=_RecordingSession([None]),
            user=other_user,
            idempotency_key=attempt.idempotency_key,
        )


def test_changed_payment_retry_is_rejected_before_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=uuid4(), email="owner@example.com", password_hash="hashed")
    watch = TripWatch(id=uuid4(), user_id=user.id)
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="live-provider",
        total_price=100,
        currency="USD",
        fingerprint_hash="fingerprint",
        status=DealStatus.PROPOSED,
    )
    original_payment = PaymentMethod(id=uuid4(), user_id=user.id, label="Original")
    changed_payment = PaymentMethod(id=uuid4(), user_id=user.id, label="Changed")
    attempt = _attempt(
        user_id=user.id,
        deal_id=deal.id,
        watch_id=watch.id,
        payment_method_id=original_payment.id,
    )
    db = _RecordingSession([attempt])
    provider_calls = 0

    def get_connector(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return SimpleNamespace()

    monkeypatch.setattr(booking_service, "get_mock_data_enabled", lambda **_: False)
    monkeypatch.setattr(booking_service, "get_owned_deal_record", lambda **_: deal)
    monkeypatch.setattr(booking_service, "get_booking_connector", get_connector)

    with pytest.raises(ConflictError) as exc_info:
        booking_service.approve_and_book(
            db=db,
            user=user,
            deal_id=deal.id,
            approval_token="unused",
            totp_code="000000",
            master_key_passphrase=None,
            payment_method_id=changed_payment.id,
            idempotency_key=attempt.idempotency_key,
            token_service=SimpleNamespace(),
        )

    assert exc_info.value.code == "idempotency_conflict"
    assert exc_info.value.safe_to_retry is False
    assert provider_calls == 0


def test_provider_failure_is_logged_but_client_message_is_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    attempt = _attempt(status=BookingAttemptStatus.REVALIDATED)
    db = _RecordingSession()
    raw_error = "provider-secret: processor response 51"

    with pytest.raises(ConflictError) as exc_info:
        booking_service._commit_failed_booking_attempt(
            db=db,
            booking_attempt=attempt,
            error_text=raw_error,
            client_message=(
                "The provider could not confirm this booking. Manual recovery is required."
            ),
            conflict_code="provider_failed",
            safe_to_retry=False,
            recovery_required=True,
        )

    assert raw_error in caplog.text
    assert raw_error not in str(exc_info.value)
    assert exc_info.value.code == "provider_failed"
    assert attempt.error_text == raw_error
    assert attempt.recovery_required is True
    assert attempt.response_payload_json == {
        "conflict_code": "provider_failed",
        "safe_to_retry": False,
    }


def test_definitive_pre_provider_failure_does_not_require_recovery() -> None:
    attempt = _attempt(status=BookingAttemptStatus.STARTED)
    db = _RecordingSession()

    with pytest.raises(ConflictError):
        booking_service._commit_failed_booking_attempt(
            db=db,
            booking_attempt=attempt,
            error_text="Deal was already booked before provider execution.",
            client_message="This deal has already been booked.",
            conflict_code="already_booked",
        )

    assert attempt.recovery_required is False


def test_booking_response_never_exposes_stored_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = User(id=uuid4(), email="owner@example.com", password_hash="hashed")
    booking = Booking(
        id=uuid4(),
        deal_id=uuid4(),
        provider="provider",
        status="ticketed",
        idempotency_key="attempt-key-123",
        loyalty_manual_followup=False,
        error_text="provider-secret: raw gateway response",
    )
    monkeypatch.setattr(
        booking_service,
        "get_owned_deal_record",
        lambda **_: SimpleNamespace(watch_id=uuid4()),
    )
    monkeypatch.setattr(booking_service, "_latest_cancellation_for_booking", lambda **_: None)
    monkeypatch.setattr(booking_service, "list_disruptions_for_booking", lambda **_: [])
    monkeypatch.setattr(
        booking_service,
        "list_notification_deliveries_for_booking",
        lambda **_: [],
    )
    monkeypatch.setattr(booking_service, "stamp_balance", lambda **_: 0)

    response = booking_service.serialize_booking(
        db=SimpleNamespace(),
        user=user,
        booking=booking,
    )

    assert response.error_text is None
    assert "provider-secret" not in response.model_dump_json()


@pytest.mark.parametrize(
    ("status", "stored_code", "safe_to_retry", "expected_code"),
    [
        (BookingAttemptStatus.STARTED, None, False, "attempt_in_progress"),
        (BookingAttemptStatus.REVALIDATED, None, False, "attempt_in_progress"),
        (BookingAttemptStatus.FAILED, "pending_ticketing", False, "pending_ticketing"),
        (BookingAttemptStatus.FAILED, "provider_failed", False, "provider_failed"),
        (BookingAttemptStatus.FAILED, "idempotency_conflict", False, "idempotency_conflict"),
        (BookingAttemptStatus.FAILED, "already_booked", False, "already_booked"),
        (BookingAttemptStatus.FAILED, "unknown", False, "conflict"),
    ],
)
def test_attempt_conflict_codes_are_stable(
    status: BookingAttemptStatus,
    stored_code: str | None,
    safe_to_retry: bool,
    expected_code: str,
) -> None:
    attempt = _attempt(status=status)
    if stored_code:
        attempt.response_payload_json = {
            "conflict_code": stored_code,
            "safe_to_retry": safe_to_retry,
        }

    code, message, actual_safe_to_retry = booking_service._attempt_conflict_state(attempt)

    assert code == expected_code
    assert message
    assert actual_safe_to_retry is safe_to_retry
