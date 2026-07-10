from __future__ import annotations

import os
from pathlib import Path

import pyotp
import pytest
from fastapi import Response
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

os.environ.setdefault("APP_SECRET", "test-master-secret-with-more-than-32-bytes")
os.environ.setdefault("BOOKING_MASTER_KEY_PASSPHRASE", "test-master-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PUBLIC_BASE_URL", "https://tramp.test")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "test-admin-password")

from app.api.routes.auth import (
    LoginRequest,
    TotpEnrollCompleteRequest,
    complete_totp_enrollment,
    login,
    start_totp_enrollment,
)
from app.config import get_settings
from app.db.models import User
from app.security.bootstrap import ensure_initial_admin
from app.security.tokens import SignedTokenService


def _configure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET", "test-master-secret-with-more-than-32-bytes")
    monkeypatch.setenv("BOOKING_MASTER_KEY_PASSPHRASE", "test-master-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://tramp.test")
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "test-admin-password")
    get_settings.cache_clear()


def _session() -> Session:
    db_path = Path("test_auth_followup.sqlite3")
    if db_path.exists():
        db_path.unlink()
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    User.__table__.create(bind=engine)
    return Session(engine)


@pytest.mark.anyio
async def test_seeded_admin_can_login_before_totp_and_enroll_afterwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_settings(monkeypatch)
    db = _session()
    try:
        seeded_user = ensure_initial_admin(db)
        assert seeded_user.email == "admin@example.com"
        assert seeded_user.totp_secret is None

        login_response = Response()
        auth = await login(
            payload=LoginRequest(
                email="admin@example.com",
                password="test-admin-password",
                totp_code=None,
            ),
            response=login_response,
            db=db,
            token_service=SignedTokenService(),
        )

        assert auth.user.email == "admin@example.com"
        assert auth.user.totp_enabled is False
        assert "set-cookie" in {key.lower() for key in login_response.headers.keys()}

        enrollment = await start_totp_enrollment(
            current_user=seeded_user,
            token_service=SignedTokenService(),
        )
        code = pyotp.TOTP(enrollment.manual_entry_key).now()

        completed = await complete_totp_enrollment(
            payload=TotpEnrollCompleteRequest(
                pending_token=enrollment.pending_token,
                totp_code=code,
            ),
            current_user=seeded_user,
            db=db,
            token_service=SignedTokenService(),
        )

        refreshed_user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert refreshed_user is not None
        assert refreshed_user.totp_secret == enrollment.manual_entry_key
        assert completed.user.totp_enabled is True
    finally:
        db.close()
