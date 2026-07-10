# ruff: noqa: B008
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_token_service
from app.api.schemas.bookings import (
    ApproveBookingRequest,
    BookingAttemptReconciliationResponse,
    BookingConflictDetail,
    BookingListResponse,
    BookingResponse,
    CancellationCreateRequest,
    CancellationResponse,
    DisruptionResponse,
)
from app.booking_service import (
    approve_and_book,
    cancel_booking,
    get_booking,
    list_bookings,
    reconcile_booking_attempt,
)
from app.db.models import Booking, Deal, TripWatch, User
from app.db.session import get_db_session
from app.disruption_service import (
    create_disruption,
    list_disruptions_for_booking,
    resolve_disruption,
)
from app.security.tokens import SignedTokenService
from app.service_errors import AuthenticationError, ConflictError

router = APIRouter()


def _map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=BookingConflictDetail(
                code=exc.code,
                message=str(exc),
                safe_to_retry=exc.safe_to_retry,
            ).model_dump(),
        )
    if isinstance(exc, AuthenticationError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _get_owned_booking_or_404(*, db: Session, user: User, booking_id: UUID) -> Booking:
    booking = db.scalar(
        select(Booking)
        .join(Deal, Deal.id == Booking.deal_id)
        .join(TripWatch, TripWatch.id == Deal.watch_id)
        .where(Booking.id == booking_id, TripWatch.user_id == user.id)
    )
    if booking is None:
        raise LookupError("Booking not found.")
    return booking


@router.post(
    "/bookings/approve",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def approve_booking(
    payload: ApproveBookingRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> BookingResponse:
    try:
        return approve_and_book(
            db=db,
            user=current_user,
            deal_id=UUID(payload.deal_id),
            approval_token=payload.approval_token,
            totp_code=payload.totp_code,
            master_key_passphrase=payload.master_key_passphrase,
            payment_method_id=UUID(payload.payment_method_id),
            idempotency_key=payload.idempotency_key,
            token_service=token_service,
        )
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc


@router.get("/bookings", response_model=BookingListResponse)
async def list_booking_records(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> BookingListResponse:
    try:
        return BookingListResponse(items=list_bookings(db=db, user=current_user))
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc


@router.get(
    "/bookings/attempts/{idempotency_key}",
    response_model=BookingAttemptReconciliationResponse,
)
async def reconcile_booking_attempt_record(
    idempotency_key: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> BookingAttemptReconciliationResponse:
    try:
        return reconcile_booking_attempt(
            db=db,
            user=current_user,
            idempotency_key=idempotency_key,
        )
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
async def get_booking_record(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> BookingResponse:
    try:
        return get_booking(db=db, user=current_user, booking_id=booking_id)
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc


@router.get("/bookings/{booking_id}/disruptions", response_model=list[DisruptionResponse])
async def list_booking_disruptions(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[DisruptionResponse]:
    try:
        _get_owned_booking_or_404(db=db, user=current_user, booking_id=booking_id)
        disruptions = list_disruptions_for_booking(db=db, booking_id=booking_id)
        return [
            DisruptionResponse(
                id=str(item.id),
                booking_id=str(item.booking_id),
                type=item.type,
                status=item.status,
                detail=item.detail_json,
                detected_at=item.detected_at,
                notified_at=item.notified_at,
                resolved_at=item.resolved_at,
            )
            for item in disruptions
        ]
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/bookings/{booking_id}/disruptions/test", response_model=DisruptionResponse)
async def create_booking_disruption(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> DisruptionResponse:
    try:
        booking = _get_owned_booking_or_404(db=db, user=current_user, booking_id=booking_id)
        disruption = create_disruption(
            db=db,
            booking=booking,
            user=current_user,
        )
        return DisruptionResponse(
            id=str(disruption.id),
            booking_id=str(disruption.booking_id),
            type=disruption.type,
            status=disruption.status,
            detail=disruption.detail_json,
            detected_at=disruption.detected_at,
            notified_at=disruption.notified_at,
            resolved_at=disruption.resolved_at,
        )
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/disruptions/{disruption_id}/resolve", response_model=DisruptionResponse)
async def resolve_booking_disruption(
    disruption_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> DisruptionResponse:
    try:
        disruption = resolve_disruption(db=db, disruption_id=disruption_id, user=current_user)
        return DisruptionResponse(
            id=str(disruption.id),
            booking_id=str(disruption.booking_id),
            type=disruption.type,
            status=disruption.status,
            detail=disruption.detail_json,
            detected_at=disruption.detected_at,
            notified_at=disruption.notified_at,
            resolved_at=disruption.resolved_at,
        )
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/bookings/{booking_id}/cancel", response_model=CancellationResponse)
async def cancel_booking_record(
    booking_id: UUID,
    payload: CancellationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> CancellationResponse:
    try:
        return cancel_booking(
            db=db,
            user=current_user,
            booking_id=booking_id,
            reason=payload.reason,
        )
    except (LookupError, ValueError, ConflictError, AuthenticationError) as exc:
        raise _map_service_error(exc) from exc
