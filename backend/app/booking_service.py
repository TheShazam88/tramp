from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
    get_calendar_connector,
    get_integration,
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
from app.tramp_stamp_service import award_for_live_booking, stamp_balance

logger = logging.getLogger(__name__)
IDEMPOTENCY_CLAIM_CONSTRAINT = "uq_booking_attempts_idempotency_key"
COMPLETED_BOOKING_STATUSES = {BookingStatus.TICKETED, BookingStatus.BOOKED}


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
    existing_replay = _get_owned_booking_replay(
        db=db,
        user=user,
        deal_id=deal.id,
        idempotency_key=idempotency_key,
    )
    if existing_replay is not None:
        return serialize_booking(
            db=db,
            user=user,
            booking=existing_replay,
            idempotent_replay=True,
        )

    watch = _get_owned_watch_for_deal(db=db, user=user, deal=deal)
    booking_connector = get_booking_connector(db=db)
    calendar_connector = get_calendar_connector(db=db, allow_disabled=True)
    notification_integration = get_integration(db=db, key="notifications")
    claimed_deal_id = deal.id
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

    claim = _persist_booking_claim(
        db=db,
        user=user,
        deal=deal,
        watch=watch,
        payment_method_id=payment_method_id,
        idempotency_key=idempotency_key,
    )
    if isinstance(claim, BookingResponse):
        return claim
    booking_attempt = claim

    deal = _lock_deal_for_booking(db=db, deal_id=claimed_deal_id)
    existing_by_key = db.scalar(
        select(Booking).where(Booking.idempotency_key == idempotency_key)
    )
    if existing_by_key is not None:
        if existing_by_key.deal_id != deal.id:
            _commit_failed_booking_attempt(
                db=db,
                booking_attempt=booking_attempt,
                error_text="Idempotency key is already bound to another booking.",
                client_message="Idempotency key is already bound to another booking.",
            )
        booking_attempt.booking_id = existing_by_key.id
        booking_attempt.status = BookingAttemptStatus.BOOKED
        booking_attempt.finished_at = datetime.now(UTC)
        db.add(booking_attempt)
        db.commit()
        return serialize_booking(
            db=db,
            user=user,
            booking=existing_by_key,
            idempotent_replay=True,
        )

    existing_booking = db.scalar(select(Booking).where(Booking.deal_id == deal.id))
    if existing_booking is not None:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text="This deal has already been booked.",
            client_message="This deal has already been booked.",
        )

    if deal.status != DealStatus.PROPOSED:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text="Only proposed deals can be booked.",
            client_message="Only proposed deals can be booked.",
        )

    booking_attempt.status = BookingAttemptStatus.REVALIDATED
    db.add(booking_attempt)

    booked_at = datetime.now(UTC)
    try:
        provider_result = booking_connector.book_deal(
            deal=deal,
            watch=watch,
            payment_method=payment_method,
            booked_at=booked_at,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        booking_attempt.status = BookingAttemptStatus.FAILED
        booking_attempt.error_text = str(exc)
        booking_attempt.finished_at = datetime.now(UTC)
        db.add(booking_attempt)
        db.commit()
        raise ConflictError(f"Booking connector failed: {exc}") from exc

    booking_attempt.provider = provider_result.provider
    booking_attempt.provider_booking_ref = provider_result.provider_booking_ref
    booking_attempt.provider_correlation_id = provider_result.provider_correlation_id
    booking_attempt.response_payload_json = provider_result.provider_payload
    booking_attempt.finished_at = datetime.now(UTC)

    execution_simulated = getattr(provider_result, "simulated", None)
    if execution_simulated is not True and execution_simulated is not False:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text="Booking provider omitted explicit execution provenance.",
            client_message=(
                "Booking provider must supply explicit execution provenance; "
                "the booking was not finalized."
            ),
        )

    if not mock_data_enabled and (
        execution_simulated
        or provider_is_simulated(provider_result.provider)
        or payload_is_simulated(provider_result.provider_payload)
    ):
        booking_attempt.status = BookingAttemptStatus.FAILED
        booking_attempt.error_text = (
            "Live booking is unavailable while mock data is disabled."
        )
        db.add(booking_attempt)
        db.commit()
        raise ConflictError("Live booking is unavailable while mock data is disabled.")

    try:
        provider_status = BookingStatus(provider_result.status)
    except ValueError:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=f"Unsupported provider booking status: {provider_result.status!r}.",
            client_message="Booking provider returned an unsupported status.",
        )

    if provider_status == BookingStatus.FAILED:
        error_text = provider_result.error_text or "Booking provider reported a failed status."
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=error_text,
            client_message=error_text,
        )

    if provider_status == BookingStatus.PENDING_TICKETING:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=(
                "Provider returned pending ticketing, but automatic finalization "
                "is unavailable; manual recovery is required."
            ),
            client_message=(
                "Booking is pending with the provider, but automatic finalization "
                "is unavailable. Manual recovery is required."
            ),
        )

    if provider_status not in COMPLETED_BOOKING_STATUSES:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=f"Unsupported provider booking status: {provider_status.value}.",
            client_message="Booking provider returned an unsupported status.",
        )

    effective_booked_at = provider_result.booked_at or booked_at
    booking = Booking(
        deal_id=deal.id,
        provider=provider_result.provider,
        provider_booking_ref=provider_result.provider_booking_ref,
        provider_correlation_id=provider_result.provider_correlation_id,
        status=provider_status,
        idempotency_key=idempotency_key,
        amount_charged=provider_result.amount_charged,
        currency=provider_result.currency,
        documents_json=provider_result.documents,
        loyalty_attached_json=provider_result.loyalty_attached,
        loyalty_manual_followup=provider_result.loyalty_manual_followup,
        ticketing_state=provider_result.ticketing_state,
        booked_at=effective_booked_at,
        error_text=provider_result.error_text,
    )
    db.add(booking)
    db.flush()
    booking_attempt.booking_id = booking.id
    booking_attempt.status = BookingAttemptStatus.BOOKED

    db.add(
        SpendLedger(
            user_id=user.id,
            watch_id=watch.id,
            booking_id=booking.id,
            amount=provider_result.amount_charged,
            currency=provider_result.currency,
            booked_at=effective_booked_at,
        )
    )
    message_type = "booking.booked"
    notification_subject = "TRAMP booking confirmed"
    notification_body = f"Your booking for deal {deal.id} has been confirmed."
    calendar_detail = "Calendar sync not attempted."
    try:
        calendar_result = push_booking_to_calendar(
            db=db,
            booking=booking,
            deal=deal,
            watch=watch,
            connector=calendar_connector,
        )
        calendar_transport = calendar_result.get("transport", "local-safe")
        calendar_detail = f"Calendar sync complete via {calendar_transport}."
    except Exception as exc:  # noqa: BLE001
        calendar_detail = f"Calendar sync failed: {exc}"
    audit_action = "booking.booked"
    deal.status = DealStatus.BOOKED
    watch.status = TripWatchStatus.FULFILLED

    notification_deliveries = queue_notification(
        db=db,
        user=user,
        message_type=message_type,
        subject=notification_subject,
        body=notification_body,
        booking=booking,
        deal=deal,
        integration=notification_integration,
    )
    booking.calendar_detail = calendar_detail

    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action=audit_action,
            target=f"deal:{deal.id}",
            amount=provider_result.amount_charged,
            currency=provider_result.currency,
            at=effective_booked_at,
            meta_json={
                "booking_id": str(booking.id),
                "watch_id": str(watch.id),
                "payment_method_id": str(payment_method.id),
                "provider_booking_ref": provider_result.provider_booking_ref,
                "provider_correlation_id": provider_result.provider_correlation_id,
                "idempotency_key": idempotency_key,
                "ticketing_state": provider_result.ticketing_state,
                "booking_status": provider_status.value,
                "calendar_detail": calendar_detail,
            },
        )
    )

    consume_approval_token(deal=deal)
    db.add_all([deal, watch, booking, booking_attempt])
    stamps_awarded = award_for_live_booking(
        db=db,
        user=user,
        booking=booking,
        deal=deal,
        provider_payload=provider_result.provider_payload,
        execution_simulated=execution_simulated,
    )
    response = serialize_booking(
        db=db,
        user=user,
        booking=booking,
        tramp_stamps_awarded=stamps_awarded,
    )
    db.commit()
    _enqueue_notification_tasks(notification_deliveries)
    return response


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
        bookings = [
            booking
            for booking in bookings
            if not _booking_is_simulated(db=db, booking=booking)
        ]
    current_stamp_balance = stamp_balance(db=db, user_id=user.id)
    return [
        serialize_booking(
            db=db,
            user=user,
            booking=booking,
            tramp_stamp_balance=current_stamp_balance,
        )
        for booking in bookings
    ]


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
            calendar_transport = calendar_result.get("transport", "local-safe")
            booking.calendar_detail = f"Calendar unwind complete via {calendar_transport}."
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
        body=(
            "Cancellation state for booking "
            f"{booking.provider_booking_ref or booking.id}: {provider_result.status.value}."
        ),
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
    tramp_stamps_awarded: int = 0,
    tramp_stamp_balance: int | None = None,
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
                "transport": (
                    delivery.transport.value
                    if hasattr(delivery.transport, "value")
                    else str(delivery.transport)
                ),
                "destination": delivery.destination,
                "message_type": delivery.message_type,
                "status": delivery.status,
                "attempted_at": delivery.attempted_at,
                "delivered_at": delivery.delivered_at,
                "error_text": delivery.error_text,
            }
            for delivery in deliveries
        ],
        tramp_stamps_awarded=tramp_stamps_awarded,
        tramp_stamp_balance=(
            stamp_balance(db=db, user_id=user.id)
            if tramp_stamp_balance is None
            else tramp_stamp_balance
        ),
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


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _persist_booking_claim(
    *,
    db: Session,
    user: User,
    deal: Deal,
    watch: TripWatch,
    payment_method_id: UUID,
    idempotency_key: str,
) -> BookingAttempt | BookingResponse:
    claim_deal_id = deal.id
    existing_attempt = db.scalar(
        select(BookingAttempt).where(
            BookingAttempt.idempotency_key == idempotency_key
        )
    )
    if existing_attempt is not None:
        return _resolve_claim_conflict(
            db=db,
            user=user,
            deal_id=claim_deal_id,
            idempotency_key=idempotency_key,
            cause=None,
        )

    booking_attempt = BookingAttempt(
        deal_id=claim_deal_id,
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
    try:
        db.commit()
    except IntegrityError as exc:
        constraint_name = _integrity_constraint_name(exc)
        db.rollback()
        if constraint_name != IDEMPOTENCY_CLAIM_CONSTRAINT:
            raise
        return _resolve_claim_conflict(
            db=db,
            user=user,
            deal_id=claim_deal_id,
            idempotency_key=idempotency_key,
            cause=exc,
        )
    return booking_attempt


def _resolve_claim_conflict(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    idempotency_key: str,
    cause: BaseException | None,
) -> BookingResponse:
    existing = db.scalar(
        select(Booking).where(Booking.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.deal_id != deal_id:
            raise ConflictError(
                "Idempotency key is already bound to another booking."
            ) from cause
        return serialize_booking(
            db=db,
            user=user,
            booking=existing,
            idempotent_replay=True,
        )

    attempt = db.scalar(
        select(BookingAttempt).where(
            BookingAttempt.idempotency_key == idempotency_key
        )
    )
    if attempt is not None and attempt.deal_id != deal_id:
        raise ConflictError(
            "Idempotency key is already bound to another booking attempt."
        ) from cause
    attempt_status = attempt.status.value if attempt is not None else "unknown"
    raise ConflictError(
        "This idempotency key already has an "
        f"{attempt_status} booking attempt without a completed booking. "
        "Automatic provider retry is disabled; manual recovery is required."
    ) from cause


def _lock_deal_for_booking(*, db: Session, deal_id: UUID) -> Deal:
    deal = db.scalar(
        select(Deal)
        .where(Deal.id == deal_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if deal is None:
        raise LookupError("Deal not found.")
    return deal


def _commit_failed_booking_attempt(
    *,
    db: Session,
    booking_attempt: BookingAttempt,
    error_text: str,
    client_message: str,
) -> NoReturn:
    booking_attempt.status = BookingAttemptStatus.FAILED
    booking_attempt.error_text = error_text
    booking_attempt.finished_at = booking_attempt.finished_at or datetime.now(UTC)
    db.add(booking_attempt)
    db.commit()
    raise ConflictError(client_message)


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
        try:
            celery_app.send_task(
                "travel_watch.send_notification_delivery",
                args=[str(delivery.id)],
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to enqueue notification delivery %s; delivery remains pending.",
                delivery.id,
            )


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


def _get_owned_booking_replay(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    idempotency_key: str,
) -> Booking | None:
    return db.scalar(
        select(Booking)
        .join(Deal, Deal.id == Booking.deal_id)
        .join(TripWatch, TripWatch.id == Deal.watch_id)
        .where(
            Booking.idempotency_key == idempotency_key,
            Booking.deal_id == deal_id,
            TripWatch.user_id == user.id,
        )
    )


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
