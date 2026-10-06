from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "travel_watch",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_default_queue="travel-watch",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "refresh-due-watches": {
            "task": "travel_watch.refresh_due_watches",
            "schedule": 60.0,
        },
        "deliver-deferred-notifications": {
            "task": "travel_watch.deliver_deferred_notifications",
            "schedule": 60.0,
        },
    },
)

celery_app.autodiscover_tasks(["app.scheduler"])
