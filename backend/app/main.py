from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.config import validate_settings
from app.db.session import SessionLocal
from app.security.bootstrap import ensure_initial_admin


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_settings()
    session = SessionLocal()
    try:
        ensure_initial_admin(session)
    finally:
        session.close()
    yield


def create_app() -> FastAPI:
    settings = validate_settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=settings.api_v1_prefix)

    @application.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "status": "ok",
            "docs_url": "/docs",
        }

    return application


app = create_app()
