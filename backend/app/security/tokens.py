from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import get_settings


@dataclass(slots=True)
class SignedToken:
    token: str
    expires_at: datetime


class SignedTokenService:
    def __init__(self) -> None:
        settings = get_settings()
        self._secret = settings.app_secret.get_secret_value()
        self._issuer = settings.public_base_url.unicode_string()

    def create(
        self,
        *,
        subject: str,
        audience: str,
        payload: dict[str, Any] | None = None,
        expires_in: timedelta = timedelta(minutes=30),
    ) -> SignedToken:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + expires_in
        claims: dict[str, Any] = {
            "sub": subject,
            "aud": audience,
            "iss": self._issuer,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        if payload:
            claims.update(payload)
        token = jwt.encode(claims, self._secret, algorithm="HS256")
        return SignedToken(token=token, expires_at=expires_at)

    def decode(self, token: str, *, audience: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._secret,
            algorithms=["HS256"],
            audience=audience,
            issuer=self._issuer,
        )
