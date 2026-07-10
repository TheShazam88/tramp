from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import User, UserRole
from app.security.passwords import hash_password, verify_password


def ensure_initial_admin(session: Session) -> User:
    settings = get_settings()
    email = settings.initial_admin_email.lower().strip()
    password = settings.initial_admin_password.get_secret_value()

    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            onboarding_completed=False,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    changed = False
    if user.role != UserRole.ADMIN:
        user.role = UserRole.ADMIN
        changed = True
    if not verify_password(password, user.password_hash):
        user.password_hash = hash_password(password)
        changed = True

    if changed:
        session.add(user)
        session.commit()
        session.refresh(user)

    return user
