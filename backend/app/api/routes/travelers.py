from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.get("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def list_travelers() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Traveler endpoints are scaffolded but not implemented yet.",
    )
