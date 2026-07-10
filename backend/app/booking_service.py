from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.bookings import BookingResponse, CancellationResponse
from app.approval_service import consume_approval_token, verify_approval_token
from app.calendar_service import push_booking_to_calendar, remove_booking_from_calendar
from app.config import KeyUnlockMode, get_settings
from app.db.models import (
    AuditLog,
    Booking,
    BookingAttempt,
    BookingAttemptStatus,
    BookingStatus,
    Cancellation,
    CancellationStatus,
    Deal,
    DealStatus,
    Disruption,
    PaymentMethod,
    SpendLedger,
    TripWatch,
    TripWatchStatus,
    User,
)
from app.deal_service import get_owned_deal_record
from app.disruption_service import list_disruptions_for_booking
from app.integrations.service import (
    get_booking_connector,
    get_mock_data_enabled,
    payload_is_simulated,
    provider_is_simulated,
)
from app.notification_service import (
    list_notification_deliveries_for_booking,
    queue_notification,
)
from app.scheduler.celery_app import celery_app
from app.security.key_provider import get_key_provider
from app.security.tokens import SignedTokenService
from app.security.totp import verify_totp_code
from app.service_errors import AuthenticationError, ConflictError


def approve_and_book(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    approval_token: str,
    totp_code: str,
    master_key_passphrase: str,
    payment_method_id: UUID,
    idempotency_key: str,
    token_service: SignedTokenService,
) -> BookingResponse:
    mock_data_enabled = get_mock_data_enabled(db=db)
    deal = get_owned_deal_record(db=db, user=user, deal_id=deal_id)
    watch = _get_owned_watch_for_deal(db=db, user=user, deal=deal)
    booking_attempt = BookingAttempt(
        deal_id=deal.id,
        watch_id=watch.id,
        idempotency_key=idempotency_key,
        status=BookingAttemptStatus.STARTED,
        request_payload_json={
            "payment_method_id": str(payment_method_id),
            "watch_id": str(watch.id),
        },
        started_at=datetime.now(UTC),
    )
    db.add(booking_attempt)
    db.flush()

    existing_by_key = db.scalar(select(Booking).where(Booking.idempotency_key == idempotency_key))
    if existing_by_key is not None:
        if existing_by_key.deal_id != deal.id:
            raise ConflictError("Idempotency key is already bound to another booking.")
        return serialize_booking(db=db, user=user, booking=existing_by_key, idempotent_replay=True)

    existing_booking = db.scalar(select(Booking).where(Booking.deal_id == deal.id))
    if existing_booking is not None:
        raise ConflictError("This deal has already been booked.")

    if deal.status != DealStatus.PROPOSED:
        raise ConflictError("Only proposed deals can be booked.")

    _require_step_up_auth(
        user=user,
        totp_code=totp_code,
        master_key_passphrase=master_key_passphrase,
    )
    verify_approval_token(deal=deal, user=user, token=approval_token, token_service=token_service)
    payment_method = _get_owned_payment_method_or_404(
        db=db,
        user=user,
        payment_method_id=payment_method_id,
    )
    _revalidate_deal_before_booking(deal=deal)
    booking_attempt.status = BookingAttemptStatus.REVALIDATED
    db.add(booking_attempt)

    booked_at = datetime.now(UTC)
    try:
        provider_result = get_booking_connector(db=db).book_deal(
            deal=deal,
            watch=watch,
            payment_method=payment_method,
            booked_at=booked_at,
        )
    except Exception as exc:  # noqa: BLE001
        booking_attempt.status = BookingAttemptStatus.FAILED
        booking_attempt.error_text = str(exc)
        booking_attempt.finished_at = datetime.now(UTC)
        db.add(booking_attempt)
        db.commit()
        raise ConflictError(f"Booking connector failed: {exc}") from exc

    if not mock_data_enabled and (
        provider_is_simulated(provider_result.provider)
        or payload_is_simulated(provider_result.provider_payload)
    ):
        booking_attempt.status = BookingAttemptStatus.FAILED
        booking_attempt.error_text = (
            "Live booking is unavailable while mock data is disabled."
        )
        booking_attempt.finished_at = datetime.now(UTC)
        booking_attempt.response_payload_json = provider_result.provider_payload
        db.add(booking_attempt)
        db.commit()
        raise ConflictError("Live booking is unavailable while mock data is disabled.")

    booking = Booking(
        deal_id=deal.id,
        provider=provider_result.provider,
        provider_booking_ref=provider_result.provider_booking_ref,
        provider_correlation_id=provider_result.provider_correlation_id,
        status=BookingStatus(provider_result.status),
        idempotency_key=idempotency_key,
        amount_charged=provider_result.amount_charged,
        currency=provider_result.currency,
        documents_json=provider_result.documents,
        loyalty_attached_json=provider_result.loyalty_attached,
        loyalty_manual_followup=provider_result.loyalty_manual_followup,
        ticketing_state=provider_result.ticketing_state,
        booked_at=provider_result.booked_at,
        error_text=provider_result.error_text,
    )
    db.add(booking)
    db.flush()
    booking_attempt.booking_id = booking.id
    booking_attempt.provider = provider_result.provider
    booking_attempt.provider_correlation_id = provider_result.provider_correlation_id
    booking_attempt.response_payload_json = provider_result.provider_payload
    booking_attempt.status = BookingAttemptStatus.BOOKED
    booking_attempt.finished_at = datetime.now(UTC)

    db.add(
        SpendLedger(
            user_id=user.id,
            watch_id=watch.id,
            booking_id=booking.id,
            amount=provider_result.amount_charged,
            currency=provider_result.currency,
            booked_at=provider_result.booked_at,
        )
    )

    notification_deliveries = queue_notification(
        db=db,
        user=user,
        message_type="booking.booked",
        subject="TRAMP booking confirmed",
        body=f"Your booking for deal {deal.id} has been confirmed.",
        booking=booking,
        deal=deal,
    )

    calendar_detail = "Calendar sync not attempted."
    try:
        calendar_result = push_booking_to_calendar(db=db, booking=booking, deal=deal, watch=watch)
        calendar_detail = f"Calendar sync complete via {calendar_result.get('transport', 'local-safe')}."
    except Exception as exc:  # noqa: BLE001
        calendar_detail = f"Calendar sync failed: {exc}"
    booking.calendar_detail = calendar_detail

    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action="booking.booked",
            target=f"deal:{deal.id}",
            amount=provider_result.amount_charged,
            currency=provider_result.currency,
            at=provider_result.booked_at,
            meta_json={
                "booking_id": str(booking.id),
                "watch_id": str(watch.id),
                "payment_method_id": str(payment_method.id),
                "provider_booking_ref": provider_result.provider_booking_ref,
                "provider_correlation_id": provider_result.provider_correlation_id,
                "idempotency_key": idempotency_key,
                "ticketing_state": provider_result.ticketing_state,
                "calendar_detail": calendar_detail,
            },
        )
    )

    consume_approval_token(deal=deal)
    deal.status = DealStatus.BOOKED
    watch.status = TripWatchStatus.FULFILLED
    db.add_all([deal, watch, booking, booking_attempt])
    db.commit()
    db.refresh(booking)
    _enqueue_notification_tasks(notification_deliveries)
    return serialize_booking(db=db, user=user, booking=booking)


def list_bookings(*, db: Session, user: User) -> list[BookingResponse]:
    mock_data_enabled = get_mock_data_enabled(db=db)
    bookings = list(
        db.scalars(
            select(Booking)
            .join(Deal, Deal.id == Booking.deal_id)
            .join(TripWatch, TripWatch.id == Deal.watch_id)
            .where(TripWatch.user_id == user.id)
            .order_by(Booking.booked_at.desc(), Booking.id.desc())
        )
    )
    if not mock_data_enabled:
        bookings = [booking for booking in bookings if not _booking_is_simulated(db=db, booking=booking)]
    return [serialize_booking(db=db, user=user, booking=booking) for booking in bookings]


def get_booking(*, db: Session, user: User, booking_id: UUID) -> BookingResponse:
    booking = _get_owned_booking_or_404(db=db, user=user, booking_id=booking_id)
    return serialize_booking(db=db, user=user, booking=booking)


def cancel_booking(
    *,
    db: Session,
    user: User,
    booking_id: UUID,
    reason: str | None,
) -> CancellationResponse:
    booking = _get_owned_booking_or_404(db=db, user=user, booking_id=booking_id)
    if not get_mock_data_enabled(db=db) and _booking_is_simulated(db=db, booking=booking):
        raise ConflictError("Live cancellation is unavailable while mock data is disabled.")
    deal = get_owned_deal_record(db=db, user=user, deal_id=booking.deal_id)
    watch = _get_owned_watch_for_deal(db=db, user=user, deal=deal)

    existing = _latest_cancellation_for_booking(db=db, booking=booking)
    if existing is not None:
        return serialize_cancellation(existing, idempotent_replay=True)

    requested_at = datetime.now(UTC)
    provider_result = get_booking_connector(db=db).cancel_booking(
        booking=booking,
        deal=deal,
        reason=reason,
        requested_at=requested_at,
    )
    cancellation = Cancellation(
        booking_id=booking.id,
        reason=reason,
        refund_expected=provider_result.refund_expected,
        refund_received=provider_result.refund_received,
        currency=provider_result.currency,
        status=provider_result.status,
        requested_at=requested_at,
        resolved_at=provider_result.resolved_at,
    )
    db.add(cancellation)
    db.flush()

    if provider_result.status == CancellationStatus.REFUNDED:
        booking.status = BookingStatus.CANCELLED
        watch.status = TripWatchStatus.ACTIVE
        try:
            calendar_result = remove_booking_from_calendar(db=db, booking=booking, deal=deal)
            booking.calendar_detail = f"Calendar unwind complete via {calendar_result.get('transport', 'local-safe')}."
        except Exception as exc:  # noqa: BLE001
            booking.calendar_detail = f"Calendar unwind failed: {exc}"
        if provider_result.refund_received > 0:
            db.add(
                SpendLedger(
                    user_id=user.id,
                    watch_id=watch.id,
                    booking_id=booking.id,
                    amount=provider_result.refund_received * Decimal("-1"),
                    currency=provider_result.currency,
                    booked_at=provider_result.resolved_at or requested_at,
                )
            )
        action = "booking.cancelled"
    else:
        action = "booking.cancellation_denied"

    notification_deliveries = queue_notification(
        db=db,
        user=user,
        message_type="booking.cancelled"
        if provider_result.status == CancellationStatus.REFUNDED
        else "booking.cancellation_denied",
        subject="TRAMP cancellation update",
        body=f"Cancellation state for booking {booking.provider_booking_ref or booking.id}: {provider_result.status.value}.",
        booking=booking,
        deal=deal,
    )

    db.add_all([booking, watch, cancellation])
    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action=action,
            target=f"booking:{booking.id}",
            amount=provider_result.refund_received,
            currency=provider_result.currency,
            at=provider_result.resolved_at or requested_at,
            meta_json={
                "deal_id": str(deal.id),
                "watch_id": str(watch.id),
                "cancellation_id": str(cancellation.id),
                "reason": reason,
                "status": provider_result.status.value,
                "provider_correlation_id": provider_result.provider_correlation_id,
            },
        )
    )
    db.commit()
    db.refresh(cancellation)
    _enqueue_notification_tasks(notification_deliveries)
    return serialize_cancellation(cancellation)


def serialize_booking(
    *,
    db: Session,
    user: User,
    booking: Booking,
    idempotent_replay: bool = False,
) -> BookingResponse:
    deal = get_owned_deal_record(db=db, user=user, deal_id=booking.deal_id)
    cancellation = _latest_cancellation_for_booking(db=db, booking=booking)
    disruptions = list_disruptions_for_booking(db=db, booking_id=booking.id)
    deliveries = list_notification_deliveries_for_booking(db=db, booking_id=booking.id)
    return BookingResponse(
        id=str(booking.id),
        deal_id=str(booking.deal_id),
        watch_id=str(deal.watch_id),
        provider=booking.provider,
        provider_booking_ref=booking.provider_booking_ref,
        status=booking.status,
        idempotency_key=booking.idempotency_key,
        amount_charged=booking.amount_charged,
        currency=booking.currency,
        documents=booking.documents_json,
        loyalty_attached=booking.loyalty_attached_json,
        loyalty_manual_followup=booking.loyalty_manual_followup,
        booked_at=booking.booked_at,
        error_text=booking.error_text,
        provider_correlation_id=booking.provider_correlation_id,
        ticketing_state=booking.ticketing_state,
        calendar_event_id=booking.calendar_event_id,
        calendar_detail=booking.calendar_detail,
        cancellation=serialize_cancellation(cancellation) if cancellation else None,
        disruptions=[
            {
                "id": str(disruption.id),
                "booking_id": str(disruption.booking_id),
                "type": disruption.type,
                "status": disruption.status,
                "detail": disruption.detail_json,
                "detected_at": disruption.detected_at,
                "notified_at": disruption.notified_at,
                "resolved_at": disruption.resolved_at,
            }
            for disruption in disruptions
        ],
        notifications=[
            {
                "id": str(delivery.id),
                "channel": delivery.channel,
                "transport": delivery.transport.value,
                "destination": delivery.destination,
                "message_type": delivery.message_type,
                "status": delivery.status,
                "attempted_at": delivery.attempted_at,
                "delivered_at": delivery.delivered_at,
                "error_text": delivery.error_text,
            }
            for delivery in deliveries
        ],
        idempotent_replay=idempotent_replay,
    )


def serialize_cancellation(
    cancellation: Cancellation,
    *,
    idempotent_replay: bool = False,
) -> CancellationResponse:
    return CancellationResponse(
        id=str(cancellation.id),
        booking_id=str(cancellation.booking_id),
        reason=cancellation.reason,
        refund_expected=cancellation.refund_expected,
        refund_received=cancellation.refund_received,
        currency=cancellation.currency,
        status=cancellation.status,
        requested_at=cancellation.requested_at,
        resolved_at=cancellation.resolved_at,
        idempotent_replay=idempotent_replay,
    )


def _require_step_up_auth(*, user: User, totp_code: str, master_key_passphrase: str | None) -> None:
    if not user.totp_secret or not verify_totp_code(secret=user.totp_secret, code=totp_code):
        raise AuthenticationError("Invalid TOTP code.")
    _validate_master_key_passphrase(master_key_passphrase)


def _validate_master_key_passphrase(passphrase: str | None) -> None:
    settings = get_settings()
    provider = get_key_provider()
    if settings.key_unlock_mode == KeyUnlockMode.MASTER_KEY:
        expected = (
            settings.booking_master_key_passphrase.get_secret_value()
            if settings.booking_master_key_passphrase
            else settings.app_secret.get_secret_value()
        )
        if not passphrase or not secrets.compare_digest(passphrase, expected):
            raise AuthenticationError("Invalid master key passphrase.")
        key_material = provider.get_key(passphrase=passphrase)
    else:
        key_material = provider.get_key(passphrase=None)
    key_material.zeroize()


def _revalidate_deal_before_booking(*, deal: Deal) -> None:
    if deal.expires_at and deal.expires_at < datetime.now(UTC):
        raise ConflictError("This deal expired and must be searched again before booking.")


def _enqueue_notification_tasks(deliveries) -> None:
    for delivery in deliveries:
        celery_app.send_task("travel_watch.send_notification_delivery", args=[str(delivery.id)])


def _get_owned_payment_method_or_404(
    *,
    db: Session,
    user: User,
    payment_method_id: UUID,
) -> PaymentMethod:
    payment_method = db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id == payment_method_id,
            PaymentMethod.user_id == user.id,
        )
    )
    if payment_method is None:
        raise LookupError("Payment method not found.")
    return payment_method


def _get_owned_booking_or_404(*, db: Session, user: User, booking_id: UUID) -> Booking:
    booking = db.scalar(
        select(Booking)
        .join(Deal, Deal.id == Booking.deal_id)
        .join(TripWatch, TripWatch.id == Deal.watch_id)
        .where(Booking.id == booking_id, TripWatch.user_id == user.id)
    )
    if booking is None or (
        not get_mock_data_enabled(db=db) and _booking_is_simulated(db=db, booking=booking)
    ):
        raise LookupError("Booking not found.")
    return booking


def _booking_is_simulated(*, db: Session, booking: Booking) -> bool:
    if provider_is_simulated(booking.provider):
        return True
    attempt_payload = db.scalar(
        select(BookingAttempt.response_payload_json)
        .where(BookingAttempt.booking_id == booking.id)
        .order_by(BookingAttempt.started_at.desc(), BookingAttempt.id.desc())
        .limit(1)
    )
    return payload_is_simulated(attempt_payload)


def _get_owned_watch_for_deal(*, db: Session, user: User, deal: Deal) -> TripWatch:
    watch = db.scalar(
        select(TripWatch).where(
            TripWatch.id == deal.watch_id,
            TripWatch.user_id == user.id,
        )
    )
    if watch is None:
        raise LookupError("Watch not found.")
    return watch


def _latest_cancellation_for_booking(*, db: Session, booking: Booking) -> Cancellation | None:
    return db.scalar(
        select(Cancellation)
        .where(Cancellation.booking_id == booking.id)
        .order_by(Cancellation.requested_at.desc(), Cancellation.id.desc())
        .limit(1)
    )
