from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.db.models import RefreshInterval

REFRESH_DELTAS = {
    RefreshInterval.HOURLY: timedelta(hours=1),
    RefreshInterval.SIX_HOURS: timedelta(hours=6),
    RefreshInterval.DAILY: timedelta(days=1),
}


def refresh_delta(interval: RefreshInterval | str) -> timedelta:
    resolved = interval if isinstance(interval, RefreshInterval) else RefreshInterval(interval)
    return REFRESH_DELTAS[resolved]


def watch_refresh_is_due(
    *,
    interval: RefreshInterval | str,
    last_observed_at: datetime | None,
    created_at: datetime | None,
    now: datetime,
) -> bool:
    anchor = last_observed_at or created_at
    if anchor is None:
        return True
    return _aware(now) - _aware(anchor) >= refresh_delta(interval)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RefreshLeaseRedis(Protocol):
    def set(self, name: str, value: str, *, nx: bool = False, ex: int | None = None) -> object:
        """Claim a key when it is absent."""


def claim_refresh_lease(
    redis_client: RefreshLeaseRedis,
    *,
    watch_id: str,
    ttl_seconds: int,
) -> bool:
    """Hold the refresh slot so an empty search is not repeated on every beat tick."""
    ttl = max(int(ttl_seconds), 60)
    claimed = redis_client.set(
        f"travel_watch:refresh_lease:{watch_id}",
        "1",
        nx=True,
        ex=ttl,
    )
    return bool(claimed)
