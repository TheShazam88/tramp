from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from typing import NoReturn
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_writer_lock
from app.api.schemas.bookings import (
    BookingAttemptReconciliationResponse,
    BookingResponse,
    CancellationApprovalTokenResponse,
    CancellationResponse,
)
from app.approval_service import (
    consume_approval_token,
    consume_cancellation_approval_token,
    issue_cancellation_approval_token,
    verify_approval_token,
    verify_cancellation_approval_token,
)
from app.calendar_service import push_booking_to_calendar, remove_booking_from_calendar
from app.config import KeyUnlockMode, get_settings
from app.db.models import (
    AuditLog,
    Booking,
    BookingAttempt,
    BookingAttemptStatus,
    BookingStatus,
    Cancellation,
    CancellationProvenance,
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
    runtime_connector_is_simulated,
    source_is_simulated,
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


def simulated_connector_blocks_live_deal(*, deal_source: str, connector_name: str) -> bool:
    return not source_is_simulated(deal_source) and runtime_connector_is_simulated(connector_name)
IDEMPOTENCY_CLAIM_CONSTRAINT = "uq_booking_attempts_idempotency_key"
UNRESOLVED_DEAL_CLAIM_INDEX = "ux_booking_attempts_unresolved_deal"
COMPLETED_BOOKING_STATUSES = {BookingStatus.TICKETED, BookingStatus.BOOKED}
ATTEMPT_IN_PROGRESS_MESSAGE = (
    "This booking attempt is still processing. Booking recovery is required before trying again."
)
PENDING_TICKETING_MESSAGE = (
    "The provider is still processing this booking, and automatic finalization is unavailable. "
    "Manual recovery is required."
)
PROVIDER_FAILED_MESSAGE = (
    "The provider could not confirm this booking. Manual recovery is required."
)
IDEMPOTENCY_CONFLICT_MESSAGE = (
    "This booking key belongs to different request details. Start a new booking attempt."
)
ALREADY_BOOKED_MESSAGE = (
    "This deal has already been booked. Reconcile the existing booking."
)
DEAL_EXPIRED_MESSAGE = "This deal expired. Refresh it before starting a new booking attempt."
GENERIC_CONFLICT_MESSAGE = (
    "This booking attempt needs reconciliation before another booking can start."
)
ATTEMPT_MESSAGES = {
    "attempt_in_progress": ATTEMPT_IN_PROGRESS_MESSAGE,
    "pending_ticketing": PENDING_TICKETING_MESSAGE,
    "provider_failed": PROVIDER_FAILED_MESSAGE,
    "idempotency_conflict": IDEMPOTENCY_CONFLICT_MESSAGE,
    "already_booked": ALREADY_BOOKED_MESSAGE,
    "deal_expired": DEAL_EXPIRED_MESSAGE,
    "conflict": GENERIC_CONFLICT_MESSAGE,
}


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
    existing_attempt = db.scalar(
        select(BookingAttempt).where(BookingAttempt.idempotency_key == idempotency_key)
    )
    if existing_attempt is not None:
        return _resolve_claim_conflict(
            db=db,
            user=user,
            deal_id=deal.id,
            payment_method_id=payment_method_id,
            idempotency_key=idempotency_key,
            cause=None,
            attempt=existing_attempt,
        )
    existing_replay = _get_owned_booking_replay(
        db=db,
        user=user,
        deal_id=deal.id,
        idempotency_key=idempotency_key,
    )
    if existing_replay is not None:
        raise ConflictError(
            IDEMPOTENCY_CONFLICT_MESSAGE,
            code="idempotency_conflict",
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

    unresolved_attempt = _get_unresolved_attempt_for_deal(
        db=db,
        deal_id=deal.id,
        exclude_idempotency_key=idempotency_key,
    )
    if unresolved_attempt is not None:
        raise ConflictError(
            ATTEMPT_IN_PROGRESS_MESSAGE,
            code="attempt_in_progress",
        )

    acquire_activity_writer_lock(db)
    deal = _lock_deal_for_booking(db=db, deal_id=claimed_deal_id)
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

    acquire_activity_writer_lock(db)
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
                client_message=IDEMPOTENCY_CONFLICT_MESSAGE,
                conflict_code="idempotency_conflict",
            )
        booking_attempt.booking_id = existing_by_key.id
        booking_attempt.status = BookingAttemptStatus.BOOKED
        booking_attempt.recovery_required = False
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
        booking_attempt.booking_id = existing_booking.id
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text="This deal has already been booked.",
            client_message=ALREADY_BOOKED_MESSAGE,
            conflict_code="already_booked",
        )

    if deal.status != DealStatus.PROPOSED:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text="Only proposed deals can be booked.",
            client_message=GENERIC_CONFLICT_MESSAGE,
            conflict_code="conflict",
        )

    if simulated_connector_blocks_live_deal(
        deal_source=deal.source,
        connector_name=getattr(booking_connector, "connector_name", ""),
    ):
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text="Live inventory cannot be booked by a simulated connector.",
            client_message=(
                "This deal came from a live provider search. TRAMP will not create a "
                "simulated ticket for it. Enable a live booking connector before approving it."
            ),
            conflict_code="live_booking_unavailable",
        )

    booking_attempt.status = BookingAttemptStatus.REVALIDATED
    booking_attempt.recovery_required = True
    db.add(booking_attempt)
    db.commit()
    acquire_activity_writer_lock(db)
    deal = _lock_deal_for_booking(db=db, deal_id=claimed_deal_id)

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
        logger.exception(
            "Booking provider raised an exception for attempt %s.",
            booking_attempt.idempotency_key,
        )
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=str(exc),
            client_message=PROVIDER_FAILED_MESSAGE,
            conflict_code="provider_failed",
            recovery_required=True,
        )

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
            conflict_code="provider_failed",
            recovery_required=True,
        )

    simulated_activity = bool(
        execution_simulated
        or source_is_simulated(deal.source)
        or provider_is_simulated(provider_result.provider)
        or payload_is_simulated(provider_result.provider_payload)
    )
    if not mock_data_enabled and simulated_activity:
        booking_attempt.status = BookingAttemptStatus.FAILED
        booking_attempt.recovery_required = True
        booking_attempt.error_text = (
            "Live booking is unavailable while mock data is disabled."
        )
        booking_attempt.response_payload_json = {
            "conflict_code": "provider_failed",
            "safe_to_retry": False,
        }
        db.add(booking_attempt)
        db.commit()
        raise ConflictError(
            PROVIDER_FAILED_MESSAGE,
            code="provider_failed",
        )

    try:
        provider_status = BookingStatus(provider_result.status)
    except ValueError:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=f"Unsupported provider booking status: {provider_result.status!r}.",
            client_message="Booking provider returned an unsupported status.",
            conflict_code="provider_failed",
            recovery_required=True,
        )

    if provider_status == BookingStatus.FAILED:
        error_text = provider_result.error_text or "Booking provider reported a failed status."
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=error_text,
            client_message=PROVIDER_FAILED_MESSAGE,
            conflict_code="provider_failed",
            recovery_required=True,
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
                PENDING_TICKETING_MESSAGE
            ),
            conflict_code="pending_ticketing",
            recovery_required=True,
        )

    if provider_status not in COMPLETED_BOOKING_STATUSES:
        _commit_failed_booking_attempt(
            db=db,
            booking_attempt=booking_attempt,
            error_text=f"Unsupported provider booking status: {provider_status.value}.",
            client_message="Booking provider returned an unsupported status.",
            conflict_code="provider_failed",
            recovery_required=True,
        )

    if provider_result.error_text:
        logger.warning(
            "Booking provider returned error text with completed attempt %s: %s",
            booking_attempt.idempotency_key,
            provider_result.error_text,
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
        error_text=None,
    )
    db.add(booking)
    db.flush()
    booking_attempt.booking_id = booking.id
    booking_attempt.status = BookingAttemptStatus.BOOKED
    booking_attempt.recovery_required = False

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
    calendar_detail = "Calendar sync pending after durable booking commit."
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
        simulated=simulated_activity,
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
    _commit_booking_then_sync_calendar(
        db=db,
        user=user,
        booking=booking,
        deal=deal,
        watch=watch,
        calendar_connector=calendar_connector,
        simulated=simulated_activity,
    )
    response = serialize_booking(
        db=db,
        user=user,
        booking=booking,
        tramp_stamps_awarded=stamps_awarded,
    )
    _enqueue_notification_tasks(notification_deliveries)
    return response


def _commit_booking_then_sync_calendar(
    *,
    db: Session,
    user: User,
    booking: Booking,
    deal: Deal,
    watch: TripWatch,
    calendar_connector,
    simulated: bool,
) -> None:
    """Commit the booking before attempting any external calendar side effect."""

    db.commit()
    calendar_result: dict[str, object] | None = None
    try:
        calendar_result = push_booking_to_calendar(
            db=db,
            booking=booking,
            deal=deal,
            watch=watch,
            connector=calendar_connector,
            simulated=simulated,
        )
        calendar_transport = calendar_result.get("transport", "local-safe")
        booking.calendar_detail = f"Calendar sync complete via {calendar_transport}."
    except Exception:  # noqa: BLE001
        logger.exception("Calendar sync failed for booking %s.", booking.id)
        booking.calendar_detail = "Calendar sync failed. Review server logs for details."

    db.add(booking)
    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action="booking.calendar_sync_recorded",
            target=f"booking:{booking.id}",
            at=datetime.now(UTC),
            meta_json={
                "deal_id": str(deal.id),
                "watch_id": str(watch.id),
                "calendar_detail": booking.calendar_detail,
                "transport": (
                    str(calendar_result.get("transport"))
                    if calendar_result and calendar_result.get("transport")
                    else None
                ),
                "simulated": simulated,
                "external_side_effect_suppressed": bool(
                    calendar_result
                    and calendar_result.get("external_side_effect_suppressed")
                ),
            },
        )
    )
    db.commit()


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


def reconcile_booking_attempt(
    *,
    db: Session,
    user: User,
    idempotency_key: str,
) -> BookingAttemptReconciliationResponse:
    attempt = db.scalar(
        select(BookingAttempt)
        .join(TripWatch, TripWatch.id == BookingAttempt.watch_id)
        .where(
            BookingAttempt.idempotency_key == idempotency_key,
            TripWatch.user_id == user.id,
        )
    )
    if attempt is None:
        raise LookupError("Booking attempt not found.")

    booking = db.scalar(
        select(Booking)
        .join(Deal, Deal.id == Booking.deal_id)
        .join(TripWatch, TripWatch.id == Deal.watch_id)
        .where(
            Booking.idempotency_key == idempotency_key,
            TripWatch.user_id == user.id,
        )
    )
    if booking is None and attempt.booking_id is not None:
        booking = db.scalar(
            select(Booking)
            .join(Deal, Deal.id == Booking.deal_id)
            .join(TripWatch, TripWatch.id == Deal.watch_id)
            .where(
                Booking.id == attempt.booking_id,
                TripWatch.user_id == user.id,
            )
        )
    if booking is None:
        code, message, safe_to_retry = _attempt_conflict_state(attempt)
        if code == "already_booked":
            booking = db.scalar(
                select(Booking)
                .join(Deal, Deal.id == Booking.deal_id)
                .join(TripWatch, TripWatch.id == Deal.watch_id)
                .where(
                    Booking.deal_id == attempt.deal_id,
                    TripWatch.user_id == user.id,
                )
            )
    else:
        code, message, safe_to_retry = (
            "booked",
            "Booking confirmed from the saved booking record.",
            False,
        )

    if booking is not None:
        code = "booked"
        message = "Booking confirmed from the saved booking record."
        safe_to_retry = False

    request_payload = attempt.request_payload_json or {}
    return BookingAttemptReconciliationResponse(
        idempotency_key=attempt.idempotency_key,
        deal_id=str(attempt.deal_id),
        payment_method_id=str(request_payload.get("payment_method_id") or ""),
        status=attempt.status,
        code=code,
        message=message,
        safe_to_retry=safe_to_retry,
        recovery_required=attempt.recovery_required,
        booking=(
            serialize_booking(db=db, user=user, booking=booking)
            if booking is not None
            else None
        ),
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
    )


def create_cancellation_approval(
    *,
    db: Session,
    user: User,
    booking_id: UUID,
    token_service: SignedTokenService,
) -> CancellationApprovalTokenResponse:
    acquire_activity_writer_lock(db)
    booking = _lock_owned_booking_for_cancellation(
        db=db,
        user=user,
        booking_id=booking_id,
    )
    if (
        not get_mock_data_enabled(db=db)
        and _booking_is_simulated(db=db, booking=booking)
    ):
        raise LookupError("Booking not found.")
    if _latest_cancellation_for_booking(db=db, booking=booking) is not None:
        raise ConflictError("This booking already has a cancellation record.")
    deal = get_owned_deal_record(db=db, user=user, deal_id=booking.deal_id)
    watch = _get_owned_watch_for_deal(db=db, user=user, deal=deal)
    signed = issue_cancellation_approval_token(
        booking=booking,
        deal=deal,
        watch=watch,
        user=user,
        token_service=token_service,
    )
    db.add(booking)
    db.commit()
    return CancellationApprovalTokenResponse(
        booking_id=str(booking.id),
        token=signed.token,
        expires_at=signed.expires_at,
    )


def cancel_booking(
    *,
    db: Session,
    user: User,
    booking_id: UUID,
    reason: str | None,
    approval_token: str,
    totp_code: str,
    master_key_passphrase: str | None,
    idempotency_key: str,
    token_service: SignedTokenService,
) -> CancellationResponse:
    acquire_activity_writer_lock(db)
    booking = _lock_owned_booking_for_cancellation(
        db=db,
        user=user,
        booking_id=booking_id,
    )
    mock_data_enabled = get_mock_data_enabled(db=db)
    if not mock_data_enabled and _booking_is_simulated(db=db, booking=booking):
        raise ConflictError("Live cancellation is unavailable while mock data is disabled.")
    existing_by_key = _get_cancellation_by_idempotency_key(
        db=db,
        idempotency_key=idempotency_key,
    )
    if existing_by_key is not None:
        if existing_by_key.booking_id != booking.id:
            raise ConflictError(
                "This cancellation key belongs to a different booking.",
                code="idempotency_conflict",
            )
        return serialize_cancellation(existing_by_key, idempotent_replay=True)

    deal = get_owned_deal_record(db=db, user=user, deal_id=booking.deal_id)
    watch = _get_owned_watch_for_deal(db=db, user=user, deal=deal)

    existing = _latest_cancellation_for_booking(db=db, booking=booking)
    if existing is not None:
        raise ConflictError("This booking already has a cancellation record.")

    _require_step_up_auth(
        user=user,
        totp_code=totp_code,
        master_key_passphrase=master_key_passphrase,
    )
    verify_cancellation_approval_token(
        booking=booking,
        deal=deal,
        watch=watch,
        user=user,
        token=approval_token,
        token_service=token_service,
    )

    requested_at = datetime.now(UTC)
    provider_result = get_booking_connector(db=db).cancel_booking(
        booking=booking,
        deal=deal,
        reason=reason,
        requested_at=requested_at,
        idempotency_key=idempotency_key,
    )
    execution_simulated = getattr(provider_result, "simulated", None)
    provider = str(getattr(provider_result, "provider", "") or "").strip()
    if execution_simulated is not True and execution_simulated is not False:
        raise ConflictError("Cancellation provider omitted explicit execution provenance.")
    if not provider:
        raise ConflictError("Cancellation provider omitted its provider identifier.")
    simulated_activity = bool(
        execution_simulated
        or source_is_simulated(deal.source)
        or provider_is_simulated(booking.provider)
        or provider_is_simulated(provider)
        or payload_is_simulated(provider_result.provider_payload)
    )
    if not mock_data_enabled and simulated_activity:
        raise ConflictError("Live cancellation is unavailable while mock data is disabled.")

    cancellation = Cancellation(
        booking_id=booking.id,
        reason=reason,
        idempotency_key=idempotency_key,
        refund_expected=provider_result.refund_expected,
        refund_received=provider_result.refund_received,
        currency=provider_result.currency,
        provider=provider,
        provider_correlation_id=provider_result.provider_correlation_id,
        provider_payload_json=provider_result.provider_payload,
        execution_simulated=execution_simulated,
        provenance=(
            CancellationProvenance.SIMULATED
            if simulated_activity
            else CancellationProvenance.LIVE
        ),
        prior_booking_status=booking.status,
        prior_watch_status=watch.status,
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
            calendar_result = remove_booking_from_calendar(
                db=db,
                booking=booking,
                deal=deal,
                simulated=simulated_activity,
            )
            calendar_transport = calendar_result.get("transport", "local-safe")
            booking.calendar_detail = f"Calendar unwind complete via {calendar_transport}."
        except Exception:  # noqa: BLE001
            logger.exception("Calendar unwind failed for booking %s.", booking.id)
            booking.calendar_detail = "Calendar unwind failed. Review server logs for details."
        if provider_result.refund_received > 0:
            db.add(
                SpendLedger(
                    user_id=user.id,
                    watch_id=watch.id,
                    booking_id=booking.id,
                    cancellation_id=cancellation.id,
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
        cancellation=cancellation,
        simulated=simulated_activity,
    )

    consume_cancellation_approval_token(booking=booking)
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
                "idempotency_key": idempotency_key,
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
        error_text=None,
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
        provider=cancellation.provider,
        execution_simulated=cancellation.execution_simulated,
        provenance=cancellation.provenance,
        requested_at=cancellation.requested_at,
        resolved_at=cancellation.resolved_at,
        idempotent_replay=idempotent_replay,
    )


def _integrity_constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)


def _get_unresolved_attempt_for_deal(
    *,
    db: Session,
    deal_id: UUID,
    exclude_idempotency_key: str | None = None,
) -> BookingAttempt | None:
    statement = (
        select(BookingAttempt)
        .where(
            BookingAttempt.deal_id == deal_id,
            or_(
                BookingAttempt.status.in_(
                    (
                        BookingAttemptStatus.STARTED,
                        BookingAttemptStatus.REVALIDATED,
                    )
                ),
                BookingAttempt.recovery_required.is_(True),
            ),
        )
        .order_by(BookingAttempt.started_at.asc(), BookingAttempt.id.asc())
    )
    if exclude_idempotency_key:
        statement = statement.where(
            BookingAttempt.idempotency_key != exclude_idempotency_key
        )
    return db.scalar(statement)


def _persist_booking_claim(
    *,
    db: Session,
    user: User,
    deal: Deal,
    watch: TripWatch,
    payment_method_id: UUID,
    idempotency_key: str,
) -> BookingAttempt | BookingResponse:
    acquire_activity_writer_lock(db)
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
            payment_method_id=payment_method_id,
            idempotency_key=idempotency_key,
            cause=None,
            attempt=existing_attempt,
        )

    unresolved_attempt = _get_unresolved_attempt_for_deal(
        db=db,
        deal_id=claim_deal_id,
        exclude_idempotency_key=idempotency_key,
    )
    if unresolved_attempt is not None:
        raise ConflictError(
            ATTEMPT_IN_PROGRESS_MESSAGE,
            code="attempt_in_progress",
        )

    booking_attempt = BookingAttempt(
        deal_id=claim_deal_id,
        watch_id=watch.id,
        idempotency_key=idempotency_key,
        status=BookingAttemptStatus.STARTED,
        request_payload_json={
            "user_id": str(user.id),
            "deal_id": str(claim_deal_id),
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
        if constraint_name == UNRESOLVED_DEAL_CLAIM_INDEX:
            raise ConflictError(
                ATTEMPT_IN_PROGRESS_MESSAGE,
                code="attempt_in_progress",
            ) from exc
        if constraint_name != IDEMPOTENCY_CLAIM_CONSTRAINT:
            raise
        return _resolve_claim_conflict(
            db=db,
            user=user,
            deal_id=claim_deal_id,
            payment_method_id=payment_method_id,
            idempotency_key=idempotency_key,
            cause=exc,
        )
    return booking_attempt


def _resolve_claim_conflict(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    payment_method_id: UUID,
    idempotency_key: str,
    cause: BaseException | None,
    attempt: BookingAttempt | None = None,
) -> BookingResponse:
    if attempt is None:
        attempt = db.scalar(
            select(BookingAttempt).where(
                BookingAttempt.idempotency_key == idempotency_key
            )
        )
    if attempt is not None:
        _validate_booking_attempt_request(
            db=db,
            user=user,
            attempt=attempt,
            deal_id=deal_id,
            payment_method_id=payment_method_id,
            cause=cause,
        )

    existing = db.scalar(
        select(Booking).where(Booking.idempotency_key == idempotency_key)
    )
    if existing is not None:
        if existing.deal_id != deal_id:
            raise ConflictError(
                IDEMPOTENCY_CONFLICT_MESSAGE,
                code="idempotency_conflict",
            ) from cause
        return serialize_booking(
            db=db,
            user=user,
            booking=existing,
            idempotent_replay=True,
        )

    if attempt is not None and attempt.booking_id is not None:
        attempt_booking = db.scalar(
            select(Booking).where(Booking.id == attempt.booking_id)
        )
        if attempt_booking is not None and attempt_booking.deal_id == deal_id:
            return serialize_booking(
                db=db,
                user=user,
                booking=attempt_booking,
                idempotent_replay=True,
            )

    code, message, safe_to_retry = _attempt_conflict_state(attempt)
    raise ConflictError(
        message,
        code=code,
        safe_to_retry=safe_to_retry,
    ) from cause


def _validate_booking_attempt_request(
    *,
    db: Session,
    user: User,
    attempt: BookingAttempt,
    deal_id: UUID,
    payment_method_id: UUID,
    cause: BaseException | None,
) -> None:
    payload = attempt.request_payload_json or {}
    stored_user_id = str(payload.get("user_id") or "")
    if not stored_user_id:
        owner_id = db.scalar(
            select(TripWatch.user_id).where(TripWatch.id == attempt.watch_id)
        )
        stored_user_id = str(owner_id or "")
    stored_payment_method_id = str(payload.get("payment_method_id") or "")
    if (
        stored_user_id != str(user.id)
        or attempt.deal_id != deal_id
        or stored_payment_method_id != str(payment_method_id)
    ):
        raise ConflictError(
            IDEMPOTENCY_CONFLICT_MESSAGE,
            code="idempotency_conflict",
        ) from cause


def _attempt_conflict_state(
    attempt: BookingAttempt | None,
) -> tuple[str, str, bool]:
    if attempt is None:
        return "conflict", GENERIC_CONFLICT_MESSAGE, False
    if attempt.status in {
        BookingAttemptStatus.STARTED,
        BookingAttemptStatus.REVALIDATED,
    }:
        return "attempt_in_progress", ATTEMPT_IN_PROGRESS_MESSAGE, False

    payload = attempt.response_payload_json or {}
    code = str(payload.get("conflict_code") or "conflict")
    if code not in ATTEMPT_MESSAGES:
        code = "conflict"
    safe_to_retry = (
        bool(payload.get("safe_to_retry", False))
        and code == "deal_expired"
        and not attempt.recovery_required
    )
    return code, ATTEMPT_MESSAGES[code], safe_to_retry


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
    conflict_code: str = "conflict",
    safe_to_retry: bool = False,
    recovery_required: bool = False,
) -> NoReturn:
    acquire_activity_writer_lock(db)
    booking_attempt.status = BookingAttemptStatus.FAILED
    booking_attempt.recovery_required = recovery_required
    booking_attempt.error_text = error_text
    booking_attempt.response_payload_json = {
        **(booking_attempt.response_payload_json or {}),
        "conflict_code": conflict_code,
        "safe_to_retry": safe_to_retry,
    }
    booking_attempt.finished_at = booking_attempt.finished_at or datetime.now(UTC)
    logger.error(
        "Booking attempt %s failed [%s]: %s",
        booking_attempt.idempotency_key,
        conflict_code,
        error_text,
    )
    db.add(booking_attempt)
    db.commit()
    raise ConflictError(
        client_message,
        code=conflict_code,
        safe_to_retry=safe_to_retry,
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
        raise ConflictError(
            DEAL_EXPIRED_MESSAGE,
            code="deal_expired",
            safe_to_retry=True,
        )


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


def _lock_owned_booking_for_cancellation(
    *,
    db: Session,
    user: User,
    booking_id: UUID,
) -> Booking:
    booking = db.scalar(
        select(Booking)
        .join(Deal, Deal.id == Booking.deal_id)
        .join(TripWatch, TripWatch.id == Deal.watch_id)
        .where(
            Booking.id == booking_id,
            TripWatch.user_id == user.id,
        )
        .with_for_update(of=Booking)
    )
    if booking is None:
        raise LookupError("Booking not found.")
    return booking


def _get_cancellation_by_idempotency_key(
    *,
    db: Session,
    idempotency_key: str,
) -> Cancellation | None:
    return db.scalar(
        select(Cancellation).where(
            Cancellation.idempotency_key == idempotency_key,
        )
    )


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
