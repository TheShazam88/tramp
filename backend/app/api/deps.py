from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Environment, get_settings
from app.db.models import User, UserRole
from app.db.session import get_db_session
from app.security.tokens import SignedTokenService

SESSION_AUDIENCE = "session"


def get_token_service() -> SignedTokenService:
    return SignedTokenService()


def set_session_cookie(*, response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings()
    max_age = max(int((expires_at - datetime.now(UTC)).total_seconds()), 0)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.environment != Environment.LOCAL,
        max_age=max_age,
        expires=expires_at,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.environment != Environment.LOCAL,
        httponly=True,
        samesite="lax",
    )


def issue_session_for_user(*, response: Response, user: User, token_service: SignedTokenService) -> None:
    settings = get_settings()
    signed = token_service.create(
        subject=str(user.id),
        audience=SESSION_AUDIENCE,
        payload={"role": user.role.value, "email": user.email},
        expires_in=timedelta(hours=settings.session_ttl_hours),
    )
    set_session_cookie(response=response, token=signed.token, expires_at=signed.expires_at)


def _unauthorized(detail: str = "Authentication required.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> User:
    settings = get_settings()
    session_token = request.cookies.get(settings.session_cookie_name)
    if not session_token:
        raise _unauthorized()

    try:
        claims = token_service.decode(session_token, audience=SESSION_AUDIENCE)
        user_id = UUID(claims["sub"])
    except Exception as exc:  # noqa: BLE001
        raise _unauthorized("Invalid or expired session.") from exc

    user = db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise _unauthorized("User session could not be resolved.")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return current_user
