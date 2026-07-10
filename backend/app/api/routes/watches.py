# ruff: noqa: B008,E501
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas.watches import (
    SearchNowResponse,
    WatchCreateRequest,
    WatchDashboardResponse,
    WatchDraftResponse,
    WatchResponse,
    WatchUpdateRequest,
)
from app.db.models import User
from app.db.session import get_db_session
from app.watch_service import (
    build_watch_draft,
    create_watch,
    get_dashboard,
    get_watch,
    list_watches,
    pause_watch,
    resume_watch,
    search_now,
    update_watch,
)

router = APIRouter()


def _map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=list[WatchResponse])
async def list_watch_records(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> list[WatchResponse]:
    return list_watches(db=db, user=current_user)


@router.post("", response_model=WatchResponse, status_code=status.HTTP_201_CREATED)
async def create_watch_record(
    payload: WatchCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> WatchResponse:
    try:
        return create_watch(db=db, user=current_user, payload=payload)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.get("/dashboard", response_model=WatchDashboardResponse)
async def get_watch_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> WatchDashboardResponse:
    return get_dashboard(db=db, user=current_user)


@router.get("/draft", response_model=WatchDraftResponse)
async def get_watch_draft(
    template_id: UUID | None = Query(default=None),
    watch_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> WatchDraftResponse:
    try:
        return build_watch_draft(
            db=db, user=current_user, template_id=template_id, watch_id=watch_id
        )
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.get("/{watch_id}", response_model=WatchResponse)
async def get_watch_record(
    watch_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> WatchResponse:
    try:
        return get_watch(db=db, user=current_user, watch_id=watch_id)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.patch("/{watch_id}", response_model=WatchResponse)
async def update_watch_record(
    watch_id: UUID,
    payload: WatchUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> WatchResponse:
    try:
        return update_watch(db=db, user=current_user, watch_id=watch_id, payload=payload)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/{watch_id}/pause", response_model=WatchResponse)
async def pause_watch_record(
    watch_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> WatchResponse:
    try:
        return pause_watch(db=db, user=current_user, watch_id=watch_id)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/{watch_id}/resume", response_model=WatchResponse)
async def resume_watch_record(
    watch_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> WatchResponse:
    try:
        return resume_watch(db=db, user=current_user, watch_id=watch_id)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc


@router.post("/{watch_id}/search-now", response_model=SearchNowResponse)
async def search_watch_now(
    watch_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> SearchNowResponse:
    try:
        return search_now(db=db, user=current_user, watch_id=watch_id)
    except (LookupError, ValueError) as exc:
        raise _map_service_error(exc) from exc
