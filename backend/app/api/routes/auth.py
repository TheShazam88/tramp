from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.api.deps import clear_session_cookie, get_current_user, get_token_service, issue_session_for_user
from app.db.models import User, UserRole
from app.db.session import get_db_session
from app.security.passwords import hash_password, verify_password
from app.security.tokens import SignedTokenService
from app.security.totp import build_provisioning_uri, generate_totp_secret, verify_totp_code
from app.config import get_settings

router = APIRouter()


class SignupStartRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class SignupStartResponse(BaseModel):
    pending_token: str
    totp_secret: str
    provisioning_uri: str
    manual_entry_key: str


class SignupCompleteRequest(BaseModel):
    pending_token: str
    totp_code: str = Field(min_length=6, max_length=6)

    @field_validator("totp_code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("TOTP code must be numeric.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = Field(default=None, min_length=6, max_length=6)

    @field_validator("totp_code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.isdigit():
            raise ValueError("TOTP code must be numeric.")
        return value


class TotpEnrollStartResponse(BaseModel):
    pending_token: str
    totp_secret: str
    provisioning_uri: str
    manual_entry_key: str


class TotpEnrollCompleteRequest(BaseModel):
    pending_token: str
    totp_code: str = Field(min_length=6, max_length=6)

    @field_validator("totp_code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("TOTP code must be numeric.")
        return value


class CurrentUserResponse(BaseModel):
    id: str
    email: EmailStr
    role: str
    onboarding_completed: bool
    default_notify_channel: str
    telegram_chat_id: str | None
    totp_enabled: bool

    @classmethod
    def from_user(cls, user: User) -> "CurrentUserResponse":
        return cls(
            id=str(user.id),
            email=user.email,
            role=user.role.value,
            onboarding_completed=user.onboarding_completed,
            default_notify_channel=user.default_notify_channel.value,
            telegram_chat_id=user.telegram_chat_id,
            totp_enabled=bool(user.totp_secret),
        )


class AuthResponse(BaseModel):
    user: CurrentUserResponse


def _can_start_signup(*, db: Session) -> bool:
    settings = get_settings()
    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    return settings.allow_self_signup or user_count == 0


def _user_exists(*, db: Session, email: str) -> bool:
    return db.scalar(select(User.id).where(User.email == email.lower())) is not None


@router.post("/signup/start", response_model=SignupStartResponse)
async def signup_start(
    payload: SignupStartRequest,
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> SignupStartResponse:
    if not _can_start_signup(db=db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-signup is disabled. Ask an admin to invite you.",
        )

    normalized_email = payload.email.lower()
    if _user_exists(db=db, email=normalized_email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    totp_secret = generate_totp_secret()
    provisioning_uri = build_provisioning_uri(email=normalized_email, secret=totp_secret)
    pending_token = token_service.create(
        subject=normalized_email,
        audience="signup",
        payload={
            "email": normalized_email,
            "password_hash": hash_password(payload.password),
            "totp_secret": totp_secret,
        },
    )
    return SignupStartResponse(
        pending_token=pending_token.token,
        totp_secret=totp_secret,
        provisioning_uri=provisioning_uri,
        manual_entry_key=totp_secret,
    )


@router.post("/signup/complete", response_model=AuthResponse)
async def signup_complete(
    payload: SignupCompleteRequest,
    response: Response,
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> AuthResponse:
    try:
        claims = token_service.decode(payload.pending_token, audience="signup")
        email = str(claims["email"]).lower()
        password_hash = str(claims["password_hash"])
        totp_secret = str(claims["totp_secret"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signup session is invalid or expired.",
        ) from exc

    if not verify_totp_code(secret=totp_secret, code=payload.totp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code.")

    if _user_exists(db=db, email=email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered.")

    is_first_user = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
    user = User(
        email=email,
        password_hash=password_hash,
        totp_secret=totp_secret,
        role=UserRole.ADMIN if is_first_user else UserRole.USER,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    issue_session_for_user(response=response, user=user, token_service=token_service)
    return AuthResponse(user=CurrentUserResponse.from_user(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

    if user.totp_secret:
        if not payload.totp_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="TOTP code is required for this account.",
            )
        if not verify_totp_code(secret=user.totp_secret, code=payload.totp_code):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code.")

    issue_session_for_user(response=response, user=user, token_service=token_service)
    return AuthResponse(user=CurrentUserResponse.from_user(user))


@router.get("/me", response_model=AuthResponse)
async def me(current_user: User = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(user=CurrentUserResponse.from_user(current_user))


@router.post("/totp/enroll/start", response_model=TotpEnrollStartResponse)
async def start_totp_enrollment(
    current_user: User = Depends(get_current_user),
    token_service: SignedTokenService = Depends(get_token_service),
) -> TotpEnrollStartResponse:
    totp_secret = generate_totp_secret()
    provisioning_uri = build_provisioning_uri(email=current_user.email, secret=totp_secret)
    pending_token = token_service.create(
        subject=str(current_user.id),
        audience="totp-enroll",
        payload={
            "user_id": str(current_user.id),
            "totp_secret": totp_secret,
        },
    )
    return TotpEnrollStartResponse(
        pending_token=pending_token.token,
        totp_secret=totp_secret,
        provisioning_uri=provisioning_uri,
        manual_entry_key=totp_secret,
    )


@router.post("/totp/enroll/complete", response_model=AuthResponse)
async def complete_totp_enrollment(
    payload: TotpEnrollCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    token_service: SignedTokenService = Depends(get_token_service),
) -> AuthResponse:
    try:
        claims = token_service.decode(payload.pending_token, audience="totp-enroll")
        user_id = str(claims["user_id"])
        totp_secret = str(claims["totp_secret"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP enrollment session is invalid or expired.",
        ) from exc

    if user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TOTP enrollment session does not match the current user.",
        )

    if not verify_totp_code(secret=totp_secret, code=payload.totp_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code.")

    current_user.totp_secret = totp_secret
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return AuthResponse(user=CurrentUserResponse.from_user(current_user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
