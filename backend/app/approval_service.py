from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.db.models import Deal, DealStatus, User
from app.security.tokens import SignedToken, SignedTokenService

APPROVAL_AUDIENCE = "deal-approval"


def issue_approval_token(
    *,
    deal: Deal,
    user: User,
    token_service: SignedTokenService,
) -> SignedToken:
    if deal.status != DealStatus.PROPOSED:
        raise ValueError("Only proposed deals can receive approval tokens.")

    settings = get_settings()
    signed = token_service.create(
        subject=str(deal.id),
        audience=APPROVAL_AUDIENCE,
        expires_in=timedelta(minutes=settings.approval_token_ttl_minutes),
        payload={
            "deal_id": str(deal.id),
            "watch_id": str(deal.watch_id),
            "user_id": str(user.id),
            "nonce": secrets.token_urlsafe(12),
        },
    )
    deal.confirm_token_hash = hash_approval_token(signed.token)
    return signed


def verify_approval_token(
    *,
    deal: Deal,
    user: User,
    token: str,
    token_service: SignedTokenService,
) -> dict[str, Any]:
    if deal.status != DealStatus.PROPOSED:
        raise ValueError("Only proposed deals may be approved.")

    claims = token_service.decode(token, audience=APPROVAL_AUDIENCE)
    if str(claims.get("deal_id") or claims.get("sub")) != str(deal.id):
        raise ValueError("Approval token does not match this deal.")
    if str(claims.get("watch_id")) != str(deal.watch_id):
        raise ValueError("Approval token does not match this watch.")
    if str(claims.get("user_id")) != str(user.id):
        raise ValueError("Approval token was issued for a different user.")
    if not deal.confirm_token_hash:
        raise ValueError("Approval token has already been used or rotated.")
    if not secrets.compare_digest(deal.confirm_token_hash, hash_approval_token(token)):
        raise ValueError("Approval token is invalid or has been superseded.")
    return claims


def consume_approval_token(*, deal: Deal) -> None:
    deal.confirm_token_hash = None


def approval_token_expiry(claims: dict[str, Any]) -> datetime:
    return datetime.fromtimestamp(int(claims["exp"]), tz=UTC)


def hash_approval_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
