from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from redis import Redis
from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import PriceObservation, TripWatch, TripWatchStatus, User
from app.db.session import SessionLocal
from app.notification_service import deliver_due_notifications, send_notification_delivery
from app.scheduler.cadence import claim_refresh_lease, refresh_delta, watch_refresh_is_due
from app.scheduler.celery_app import celery_app
from app.watch_service import search_now

logger = logging.getLogger(__name__)


@celery_app.task(name="travel_watch.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="travel_watch.refresh_watch")
def refresh_watch(watch_id: str) -> dict[str, str]:
    session = SessionLocal()
    try:
        watch = session.scalar(select(TripWatch).where(TripWatch.id == UUID(watch_id)))
        if watch is None:
            return {
                "watch_id": watch_id,
                "status": "missing",
                "detail": "Watch not found.",
            }
        user = session.scalar(select(User).where(User.id == watch.user_id))
        if user is None:
            return {
                "watch_id": watch_id,
                "status": "missing-user",
                "detail": "Watch owner not found.",
            }
        try:
            result = search_now(db=session, user=user, watch_id=watch.id)
        except Exception:  # noqa: BLE001
            logger.exception("Watch refresh failed for %s.", watch_id)
            session.rollback()
            return {
                "watch_id": watch_id,
                "status": "failed",
                "detail": "Watch refresh failed.",
            }
        return {
            "watch_id": watch_id,
            "status": "processed",
            "detail": (
                f"Observed {result.observations_created} offers "
                f"and upserted {result.deals_upserted} deals."
            ),
        }
    finally:
        session.close()


@celery_app.task(name="travel_watch.refresh_due_watches")
def refresh_due_watches() -> dict[str, int]:
    session = SessionLocal()
    try:
        now = datetime.now(UTC)
        watches = list(
            session.scalars(
                select(TripWatch).where(TripWatch.status == TripWatchStatus.ACTIVE)
            )
        )
        queued = 0
        redis_client = Redis.from_url(get_settings().redis_url)
        for watch in watches:
            last_observed_at = session.scalar(
                select(func.max(PriceObservation.observed_at)).where(
                    PriceObservation.watch_id == watch.id
                )
            )
            if not watch_refresh_is_due(
                interval=watch.refresh_interval,
                last_observed_at=last_observed_at,
                created_at=watch.created_at,
                now=now,
            ):
                continue
            try:
                claimed = claim_refresh_lease(
                    redis_client,
                    watch_id=str(watch.id),
                    ttl_seconds=int(refresh_delta(watch.refresh_interval).total_seconds()),
                )
                if not claimed:
                    continue
                refresh_watch.delay(str(watch.id))
            except Exception:  # noqa: BLE001
                logger.exception("Could not queue refresh for watch %s.", watch.id)
                continue
            queued += 1
        return {"queued": queued}
    finally:
        session.close()


@celery_app.task(name="travel_watch.deliver_deferred_notifications")
def deliver_deferred_notifications() -> dict[str, int]:
    session = SessionLocal()
    try:
        return {"processed": deliver_due_notifications(db=session)}
    finally:
        session.close()


@celery_app.task(name="travel_watch.send_notification_delivery")
def deliver_notification(notification_id: str) -> dict[str, str]:
    session = SessionLocal()
    try:
        delivery = send_notification_delivery(db=session, delivery_id=UUID(notification_id))
        status_value = delivery.status
        status = status_value.value if hasattr(status_value, "value") else str(status_value)
        return {
            "notification_id": notification_id,
            "status": status,
            "channel": delivery.channel,
        }
    finally:
        session.close()
