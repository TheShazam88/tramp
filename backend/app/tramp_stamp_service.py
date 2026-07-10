from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TrampStampLedger


def stamp_balance(*, db: Session, user_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(TrampStampLedger.amount), 0)).where(
                TrampStampLedger.user_id == user_id
            )
        )
        or 0
    )
