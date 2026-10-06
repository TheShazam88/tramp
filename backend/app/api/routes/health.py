from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.config import get_settings
from app.db.session import SessionLocal
from app.integrations.service import (
    get_mock_data_enabled,
    live_inventory_available,
)

router = APIRouter()


@router.get("")
async def healthcheck() -> dict[str, object]:
    settings = get_settings()
    database_ok = False
    redis_ok = False
    mock_data_enabled = True
    live_data_available = False

    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        database_ok = True
        mock_data_enabled = get_mock_data_enabled(db=session)
        live_data_available = live_inventory_available(db=session)
    except Exception:  # noqa: BLE001
        database_ok = False
    finally:
        session.close()

    try:
        from redis import Redis

        Redis.from_url(settings.redis_url).ping()
        redis_ok = True
    except Exception:  # noqa: BLE001
        redis_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "environment": settings.environment.value,
        "app": settings.app_name,
        "checks": {
            "database": database_ok,
            "redis": redis_ok,
            "mock_data_enabled": mock_data_enabled,
            "live_inventory_available": live_data_available,
            "inventory_mode": (
                "live" if live_data_available else "mock" if mock_data_enabled else "empty"
            ),
        },
    }
