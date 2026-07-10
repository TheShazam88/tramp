from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

ACTIVITY_MAINTENANCE_LOCK_KEY = 6072351297463113037


def acquire_activity_maintenance_lock(db: Session) -> None:
    """Acquire the exclusive purge lock for the current transaction."""

    _acquire_postgres_lock(db, "pg_advisory_xact_lock")


def acquire_activity_writer_lock(db: Session) -> None:
    """Acquire a shared writer lock for the current transaction."""

    _acquire_postgres_lock(db, "pg_advisory_xact_lock_shared")


def _acquire_postgres_lock(db: Session, function_name: str) -> None:

    get_bind = getattr(db, "get_bind", None)
    if get_bind is None:
        return
    bind = get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(
        text(f"SELECT {function_name}(:lock_key)"),
        {"lock_key": ACTIVITY_MAINTENANCE_LOCK_KEY},
    )
