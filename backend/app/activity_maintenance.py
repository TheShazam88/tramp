from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

ACTIVITY_MAINTENANCE_LOCK_KEY = 6072351297463113037


def acquire_activity_maintenance_lock(db: Session) -> None:
    """Serialize purge snapshots and activity writes in the current transaction."""

    get_bind = getattr(db, "get_bind", None)
    if get_bind is None:
        return
    bind = get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": ACTIVITY_MAINTENANCE_LOCK_KEY},
    )
