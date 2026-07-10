# ruff: noqa: B008
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_token_service
from app.api.schemas.deals import (
    ApprovalTokenResponse,
    ApprovalTokenVerifyRequest,
    ApprovalTokenVerifyResponse,
    DealIntentConfirmRequest,
    DealIntentResponse,
    DealRejectRequest,
    DealTimelineResponse,
    StoredDealResponse,
)
from app.db.models import User
from app.db.session import get_db_session
from app.deal_service import (
    confirm_deal_intent,
    create_approval_token,
    get_deal,
    get_deal_timeline,
    list_deals_for_watch,
    reject_deal,
    verify_existing_approval_token,
)
from app.security.tokens import SignedTokenService
from app.service_errors import ConflictError

router = APIRouter()


def _map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/watches/{watch_id}/deals", response_model=list[StoredDealResponse])
async def list_watch_deals(
    watch_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[StoredDealResponse]:
    try:
        return list_deals_for_watch(db=db, user=current_user, watch_id=watch_id)
    except (LookupError, ValueError, ConflictError) as exc:
        raise _map_service_error(exc) from exc


@router.get("/deals/{deal_id}", response_model=StoredDealResponse)
async def get_deal_record(
    deal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> StoredDealResponse:
    try:
        return get_deal(db=db, user=current_user, deal_id=deal_id)
    except (LookupError, ValueError, ConflictError) as exc:
        raise _map_service_error(exc) from exc


@router.get("/deals/{deal_id}/timeline", response_model=DealTimelineResponse)
async def get_deal_price_timeline(
    deal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> DealTimelineResponse:
    try:
        return get_deal_timeline(db=db, user=current_user, deal_id=deal_id)
    except (LookupError, ValueError, ConflictError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/deals/{deal_id}/approval-token", response_model=ApprovalTokenResponse)
async def create_deal_approval_token(
    deal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> ApprovalTokenResponse:
    try:
        return create_approval_token(
            db=db,
            user=current_user,
            deal_id=deal_id,
            token_service=token_service,
        )
    except (LookupError, ValueError, ConflictError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/deals/{deal_id}/approval-token/verify", response_model=ApprovalTokenVerifyResponse)
async def verify_deal_approval_token(
    deal_id: UUID,
    payload: ApprovalTokenVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> ApprovalTokenVerifyResponse:
    try:
        return verify_existing_approval_token(
            db=db,
            user=current_user,
            deal_id=deal_id,
            token=payload.token,
            token_service=token_service,
        )
    except (LookupError, ValueError, ConflictError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/deals/{deal_id}/confirm-intent", response_model=DealIntentResponse)
async def confirm_deal_review_intent(
    deal_id: UUID,
    payload: DealIntentConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> DealIntentResponse:
    try:
        return confirm_deal_intent(
            db=db,
            user=current_user,
            deal_id=deal_id,
            token=payload.token,
            totp_code=payload.totp_code,
            token_service=token_service,
        )
    except (LookupError, ValueError, ConflictError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/deals/{deal_id}/reject", response_model=DealIntentResponse)
async def reject_deal_review(
    deal_id: UUID,
    payload: DealRejectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> DealIntentResponse:
    try:
        return reject_deal(
            db=db,
            user=current_user,
            deal_id=deal_id,
            reason=payload.reason,
        )
    except (LookupError, ValueError, ConflictError) as exc:
        raise _map_service_error(exc) from exc
