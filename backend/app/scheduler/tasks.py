from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.db.models import TripWatch, User
from app.db.session import SessionLocal
from app.notification_service import send_notification_delivery
from app.scheduler.celery_app import celery_app
from app.watch_service import search_now


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
        result = search_now(db=session, user=user, watch_id=watch.id)
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


@celery_app.task(name="travel_watch.send_notification_delivery")
def deliver_notification(notification_id: str) -> dict[str, str]:
    session = SessionLocal()
    try:
        delivery = send_notification_delivery(db=session, delivery_id=UUID(notification_id))
        return {
            "notification_id": notification_id,
            "status": delivery.status.value,
            "channel": delivery.channel,
        }
    finally:
        session.close()
