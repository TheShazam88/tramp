from __future__ import annotations

import pyotp

from app.config import get_settings


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_provisioning_uri(*, email: str, secret: str) -> str:
    settings = get_settings()
    issuer = settings.app_name
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp_code(*, secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)
