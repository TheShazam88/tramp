from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Environment(StrEnum):
    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class KeyUnlockMode(StrEnum):
    MASTER_KEY = "master_key"
    AUTO = "auto"


class MasterKeySource(StrEnum):
    VAULT = "vault"
    KEYCHAIN = "keychain"
    LOCAL_FILE = "local_file"


class EmailProvider(StrEnum):
    DISABLED = "disabled"
    SES = "ses"
    POSTMARK = "postmark"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TRAMP API"
    environment: Environment = Environment.LOCAL
    api_v1_prefix: str = "/api/v1"
    session_cookie_name: str = "travel_watch_session"
    session_ttl_hours: int = 168
    approval_token_ttl_minutes: int = Field(30, alias="APPROVAL_TOKEN_TTL_MINUTES")
    initial_admin_email: str = Field(..., alias="INITIAL_ADMIN_EMAIL")
    initial_admin_password: SecretStr = Field(..., alias="INITIAL_ADMIN_PASSWORD")

    app_secret: SecretStr = Field(..., alias="APP_SECRET")
    booking_master_key_passphrase: SecretStr | None = Field(
        None,
        alias="BOOKING_MASTER_KEY_PASSPHRASE",
    )
    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")
    public_base_url: AnyHttpUrl = Field(..., alias="PUBLIC_BASE_URL")

    allow_self_signup: bool = Field(False, alias="ALLOW_SELF_SIGNUP")
    key_unlock_mode: KeyUnlockMode = Field(
        KeyUnlockMode.MASTER_KEY,
        alias="KEY_UNLOCK_MODE",
    )
    master_key_source: MasterKeySource = Field(
        MasterKeySource.VAULT,
        alias="MASTER_KEY_SOURCE",
    )
    vault_addr: str | None = Field(None, alias="VAULT_ADDR")
    vault_token: SecretStr | None = Field(None, alias="VAULT_TOKEN")
    auto_unlock_local_file_path: str | None = Field(
        ".tramp-auto-unlock.key",
        alias="AUTO_UNLOCK_LOCAL_FILE_PATH",
    )
    auto_unlock_seed_material: SecretStr | None = Field(
        None,
        alias="AUTO_UNLOCK_SEED_MATERIAL",
    )

    email_provider: EmailProvider = Field(EmailProvider.DISABLED, alias="EMAIL_PROVIDER")
    ses_region: str | None = Field(None, alias="SES_REGION")
    alert_from_address: str | None = Field(None, alias="ALERT_FROM_ADDRESS")
    telegram_bot_token: SecretStr | None = Field(None, alias="TELEGRAM_BOT_TOKEN")

    default_luxury_vs_savings: float = Field(0.6, alias="DEFAULT_LUXURY_VS_SAVINGS")
    default_quality_floor: int = Field(40, alias="DEFAULT_QUALITY_FLOOR")
    default_band_tolerance: float = Field(0.10, alias="DEFAULT_BAND_TOLERANCE")
    target_percentile: int = Field(25, alias="TARGET_PERCENTILE")
    glide_start_days: int = Field(42, alias="GLIDE_START_DAYS")
    glide_end_days: int = Field(3, alias="GLIDE_END_DAYS")

    global_max_auto_book_amount: float | None = Field(
        None,
        alias="GLOBAL_MAX_AUTO_BOOK_AMOUNT",
    )
    weekly_max_spend: float | None = Field(None, alias="WEEKLY_MAX_SPEND")
    weekly_max_bookings: int | None = Field(None, alias="WEEKLY_MAX_BOOKINGS")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        parsed = make_url(value)
        if not parsed.drivername.startswith("postgresql"):
            raise ValueError("DATABASE_URL must use a PostgreSQL SQLAlchemy driver.")
        return value

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must start with redis:// or rediss://.")
        return value

    @field_validator("default_luxury_vs_savings", "default_band_tolerance")
    @classmethod
    def validate_ratio(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("Expected a value between 0 and 1.")
        return value

    @field_validator("default_quality_floor")
    @classmethod
    def validate_quality_floor(cls, value: int) -> int:
        if not 0 <= value <= 100:
            raise ValueError("DEFAULT_QUALITY_FLOOR must be between 0 and 100.")
        return value

    @model_validator(mode="after")
    def validate_operational_requirements(self) -> Settings:
        if self.session_ttl_hours <= 0:
            raise ValueError("session_ttl_hours must be greater than 0.")

        if self.approval_token_ttl_minutes <= 0:
            raise ValueError("approval_token_ttl_minutes must be greater than 0.")

        if self.glide_end_days > self.glide_start_days:
            raise ValueError("GLIDE_END_DAYS cannot be greater than GLIDE_START_DAYS.")

        if self.key_unlock_mode == KeyUnlockMode.AUTO:
            if self.master_key_source == MasterKeySource.VAULT:
                if not self.vault_addr or not self.vault_token:
                    raise ValueError(
                        "VAULT_ADDR and VAULT_TOKEN are required when KEY_UNLOCK_MODE=auto "
                        "and MASTER_KEY_SOURCE=vault."
                    )
            if self.master_key_source == MasterKeySource.LOCAL_FILE:
                if not self.auto_unlock_local_file_path:
                    raise ValueError(
                        "AUTO_UNLOCK_LOCAL_FILE_PATH is required when KEY_UNLOCK_MODE=auto "
                        "and MASTER_KEY_SOURCE=local_file."
                    )

        if self.email_provider != EmailProvider.DISABLED and not self.alert_from_address:
            raise ValueError("ALERT_FROM_ADDRESS is required when EMAIL_PROVIDER is enabled.")

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def validate_settings() -> Settings:
    return get_settings()
