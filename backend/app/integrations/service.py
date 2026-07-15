from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    IntegrationCredentialProfile,
    IntegrationEnvironment,
    PlatformIntegration,
    User,
)
from app.integrations.catalog import get_catalog_entry, list_catalog_entries
from app.integrations.connectors import (
    LocalBookingConnector,
    LocalCalendarConnector,
    LocalFlightConnector,
    LocalHotelConnector,
    LocalNotificationConnector,
)
from app.integrations.types import (
    ConnectionTestResult,
    ResolvedCredentialProfile,
    ResolvedIntegrationConfig,
)
from app.security.crypto import decrypt_with_app_secret, encrypt_with_app_secret

BOOTSTRAP_ENV_PREFIX = "TRAVEL_WATCH_INTEGRATION_"
MASKED_SENTINELS = {"<masked>", "[masked]", "__masked__"}
RUNTIME_CONFIG_KEY = "platform_runtime"
MOCK_DATA_ENABLED_FLAG = "mock_data_enabled"
FLIGHT_INTEGRATION_KEYS = ("flights_amadeus", "flights_duffel", "flights_kiwi")
SIMULATED_CONNECTOR_PREFIXES = ("mock-", "local-safe-", "off-")
CATEGORY_DEFINITIONS = {
    "flights": {
        "title": "Flights",
        "description": "Flight shopping providers that are queried together and ranked by TRAMP.",
    },
    "hotels": {
        "title": "Hotels",
        "description": "Hotel and car-search inventory connectors.",
    },
    "booking": {
        "title": "Booking",
        "description": (
            "Checkout and booking execution connectors that can reuse shared provider credentials."
        ),
    },
    "messaging": {
        "title": "Messaging",
        "description": "Outbound delivery channels such as email and Telegram.",
    },
    "calendar": {
        "title": "Calendar",
        "description": "Calendar sync providers for booking events and cancellations.",
    },
    "runtime": {
        "title": "Runtime",
        "description": "Mock/live runtime behavior and diagnostic controls.",
    },
}


def list_integrations(
    *,
    db: Session,
    category: str | None = None,
) -> list[ResolvedIntegrationConfig]:
    _backfill_shared_profiles(db=db)
    records = {
        record.key: record
        for record in db.scalars(
            select(PlatformIntegration).where(
                PlatformIntegration.key.in_([entry.key for entry in list_catalog_entries()])
            )
        )
    }
    items = [
        resolve_integration_state(db=db, key=entry.key, record=records.get(entry.key))
        for entry in list_catalog_entries()
    ]
    if category:
        return [item for item in items if item.category == category]
    return items


def get_integration(*, db: Session, key: str) -> ResolvedIntegrationConfig:
    _backfill_shared_profiles(db=db)
    record = _get_record(db=db, key=key)
    return resolve_integration_state(db=db, key=key, record=record)


def list_integration_categories() -> list[dict[str, str]]:
    return [
        {
            "id": category_key,
            "title": payload["title"],
            "description": payload["description"],
        }
        for category_key, payload in CATEGORY_DEFINITIONS.items()
    ]


def list_credential_profiles(
    *,
    db: Session,
    provider_keys: list[str] | tuple[str, ...] | None = None,
) -> list[ResolvedCredentialProfile]:
    _backfill_shared_profiles(db=db)
    query = select(IntegrationCredentialProfile)
    if provider_keys:
        query = query.where(IntegrationCredentialProfile.provider_key.in_(list(provider_keys)))
    profiles = list(
        db.scalars(
            query.order_by(
                IntegrationCredentialProfile.provider_key,
                IntegrationCredentialProfile.label,
            )
        )
    )
    return [_serialize_credential_profile(db=db, profile=profile) for profile in profiles]


def update_integration(
    *,
    db: Session,
    actor: User,
    key: str,
    enabled: bool | None = None,
    environment: IntegrationEnvironment | None = None,
    feature_flags: dict[str, Any] | None = None,
    credentials: dict[str, Any] | None = None,
    credential_profile_id: str | None = None,
    fields_set: set[str] | None = None,
) -> ResolvedIntegrationConfig:
    entry = get_catalog_entry(key)
    _backfill_shared_profiles(db=db)
    record = _get_record(db=db, key=entry.key)
    bootstrap = _load_bootstrap(entry.key)
    stored_overrides = _load_stored_credentials(record=record, key=entry.key)
    linked_profile = _get_linked_profile(db=db, record=record)
    linked_profile_credentials = _load_profile_credentials(profile=linked_profile)
    effective_masked = mask_catalog_credentials(
        credentials={
            **bootstrap["credentials"],
            **linked_profile_credentials,
            **stored_overrides,
        },
        public_keys=_public_credential_keys(entry.credential_fields),
    )

    if record is None:
        record = PlatformIntegration(
            key=entry.key,
            encrypted_credentials=_encrypt_credentials(entry.key, stored_overrides),
            environment=environment or bootstrap["environment"],
            enabled=enabled if enabled is not None else bootstrap["enabled"],
            feature_flags_json=None,
            updated_by=actor.id,
        )

    effective_fields = fields_set or set()
    if "enabled" in effective_fields and enabled is not None:
        record.enabled = enabled
    if "environment" in effective_fields and environment is not None:
        record.environment = environment
    if "feature_flags" in effective_fields:
        record.feature_flags_json = dict(feature_flags or {}) or None
    if "credential_profile_id" in effective_fields:
        record.credential_profile_id = _parse_profile_id(
            credential_profile_id,
            allowed_provider_keys=entry.compatible_profile_provider_keys,
            db=db,
        )
        linked_profile = _get_linked_profile(db=db, record=record)
        linked_profile_credentials = _load_profile_credentials(profile=linked_profile)
        effective_masked = mask_catalog_credentials(
            credentials={
                **bootstrap["credentials"],
                **linked_profile_credentials,
                **stored_overrides,
            },
            public_keys=_public_credential_keys(entry.credential_fields),
        )
    if "credentials" in effective_fields:
        stored_overrides = merge_credential_updates(
            current=stored_overrides,
            updates=credentials,
            effective_masked=effective_masked,
        )
        _validate_credentials(
            entry.key,
            stored_overrides,
            profile_provider_key=linked_profile.provider_key if linked_profile else None,
        )
        record.encrypted_credentials = _encrypt_credentials(entry.key, stored_overrides)

    resolved_environment = record.environment if record is not None else bootstrap["environment"]
    resolved_enabled = record.enabled if record is not None else bootstrap["enabled"]
    _validate_operating_mode(
        key=entry.key,
        environment=resolved_environment,
        enabled=resolved_enabled,
        credentials={**linked_profile_credentials, **stored_overrides},
        profile_provider_key=linked_profile.provider_key if linked_profile else None,
    )

    record.updated_by = actor.id
    db.add(record)
    db.commit()
    db.refresh(record)
    return resolve_integration_state(db=db, key=entry.key, record=record)


def create_credential_profile(
    *,
    db: Session,
    actor: User,
    provider_key: str,
    label: str,
    credentials: dict[str, Any] | None,
) -> ResolvedCredentialProfile:
    normalized_provider = provider_key.strip().lower()
    if not normalized_provider:
        raise ValueError("provider_key is required.")
    if not label.strip():
        raise ValueError("label is required.")
    profile = IntegrationCredentialProfile(
        id=uuid4(),
        provider_key=normalized_provider,
        label=label.strip(),
        encrypted_credentials="",
        updated_by=actor.id,
    )
    merged_credentials = merge_credential_updates(
        current={},
        updates=credentials or {},
        effective_masked={},
    )
    profile.encrypted_credentials = _encrypt_profile_credentials(
        profile_id=profile.id,
        credentials=merged_credentials,
    )
    profile.updated_by = actor.id
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _serialize_credential_profile(db=db, profile=profile)


def update_credential_profile(
    *,
    db: Session,
    actor: User,
    profile_id: str,
    label: str | None = None,
    credentials: dict[str, Any] | None = None,
) -> ResolvedCredentialProfile:
    profile = _require_credential_profile(db=db, profile_id=profile_id)
    current_credentials = _load_profile_credentials(profile=profile)
    effective_masked = mask_catalog_credentials(
        credentials=current_credentials,
        public_keys=_profile_public_credential_keys(profile.provider_key),
    )
    if label is not None and label.strip():
        profile.label = label.strip()
    if credentials is not None:
        merged_credentials = merge_credential_updates(
            current=current_credentials,
            updates=credentials,
            effective_masked=effective_masked,
        )
        profile.encrypted_credentials = _encrypt_profile_credentials(
            profile_id=profile.id,
            credentials=merged_credentials,
        )
    profile.updated_by = actor.id
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _serialize_credential_profile(db=db, profile=profile)


def delete_credential_profile(*, db: Session, profile_id: str) -> None:
    profile = _require_credential_profile(db=db, profile_id=profile_id)
    in_use = list(
        db.scalars(
            select(PlatformIntegration).where(
                PlatformIntegration.credential_profile_id == profile.id
            )
        )
    )
    if in_use:
        labels = ", ".join(item.key for item in in_use)
        raise ValueError(f"Credential profile is still linked to: {labels}.")
    db.delete(profile)
    db.commit()


def test_connection(*, db: Session, key: str, actor: User) -> ConnectionTestResult:
    if key in FLIGHT_INTEGRATION_KEYS:
        return get_flight_connector(db=db, key=key, allow_disabled=True).test_connection()
    if key == "hotels":
        return get_hotel_connector(db=db, allow_disabled=True).test_connection()
    if key == "booking":
        return get_booking_connector(db=db, allow_disabled=True).test_connection()
    if key == "notifications":
        connector = get_notification_connector(db=db, allow_disabled=True)
        connector.send_test_notification(actor_email=actor.email)
        return connector.test_connection()
    if key == "calendar":
        return get_calendar_connector(db=db, allow_disabled=True).test_connection()
    raise LookupError(f"Unknown integration '{key}'.")


def get_mock_data_enabled(*, db: Session) -> bool:
    record = db.scalar(
        select(PlatformIntegration).where(
            PlatformIntegration.key == RUNTIME_CONFIG_KEY
        )
    )
    if record is None or not record.feature_flags_json:
        return True
    return bool(record.feature_flags_json.get(MOCK_DATA_ENABLED_FLAG, True))


def set_mock_data_enabled(*, db: Session, actor: User, enabled: bool) -> bool:
    record = db.scalar(
        select(PlatformIntegration).where(
            PlatformIntegration.key == RUNTIME_CONFIG_KEY
        )
    )
    if record is None:
        record = PlatformIntegration(
            key=RUNTIME_CONFIG_KEY,
            encrypted_credentials=_encrypt_credentials(RUNTIME_CONFIG_KEY, {}),
            environment=IntegrationEnvironment.TEST,
            enabled=False,
            feature_flags_json={},
            updated_by=actor.id,
        )

    feature_flags = dict(record.feature_flags_json or {})
    feature_flags[MOCK_DATA_ENABLED_FLAG] = enabled
    record.feature_flags_json = feature_flags
    record.updated_by = actor.id
    db.add(record)
    db.commit()
    db.refresh(record)
    return bool(record.feature_flags_json.get(MOCK_DATA_ENABLED_FLAG, True))


def live_inventory_available(*, db: Session) -> bool:
    inventory_integrations = [
        *[
            resolve_integration_state(db=db, key=key, record=_get_record(db=db, key=key))
            for key in FLIGHT_INTEGRATION_KEYS
        ],
        resolve_integration_state(db=db, key="hotels", record=_get_record(db=db, key="hotels")),
    ]
    return any(
        integration.enabled
        and integration.environment == IntegrationEnvironment.LIVE
        and not runtime_connector_is_simulated(integration.runtime_connector)
        for integration in inventory_integrations
    )


def runtime_connector_is_simulated(runtime_connector: str | None) -> bool:
    return _has_simulated_component(runtime_connector)


def source_is_simulated(source: str | None) -> bool:
    return _has_simulated_component(source)


def provider_is_simulated(provider: str | None) -> bool:
    return _has_simulated_component(provider)


def payload_is_simulated(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("simulated"))


def _has_simulated_component(value: str | None) -> bool:
    components = (value or "").split("+")
    return any(
        component.strip().lower().startswith(SIMULATED_CONNECTOR_PREFIXES)
        for component in components
    )


def get_flight_connector(
    *,
    db: Session,
    key: str,
    allow_disabled: bool = False,
) -> LocalFlightConnector:
    resolved = get_integration(db=db, key=key)
    _require_enabled(resolved=resolved, allow_disabled=allow_disabled)
    return LocalFlightConnector(config=resolved)


def get_flight_connectors(
    *,
    db: Session,
    allow_disabled: bool = False,
) -> list[LocalFlightConnector]:
    connectors: list[LocalFlightConnector] = []
    for key in FLIGHT_INTEGRATION_KEYS:
        resolved = get_integration(db=db, key=key)
        if allow_disabled or resolved.enabled:
            if allow_disabled or resolved.environment != IntegrationEnvironment.OFF:
                connectors.append(LocalFlightConnector(config=resolved))
    return connectors


def get_hotel_connector(*, db: Session, allow_disabled: bool = False) -> LocalHotelConnector:
    resolved = get_integration(db=db, key="hotels")
    _require_enabled(resolved=resolved, allow_disabled=allow_disabled)
    return LocalHotelConnector(config=resolved)


def get_booking_connector(*, db: Session, allow_disabled: bool = False) -> LocalBookingConnector:
    resolved = get_integration(db=db, key="booking")
    _require_enabled(resolved=resolved, allow_disabled=allow_disabled)
    return LocalBookingConnector(config=resolved)


def get_notification_connector(
    *,
    db: Session,
    allow_disabled: bool = False,
) -> LocalNotificationConnector:
    resolved = get_integration(db=db, key="notifications")
    _require_enabled(resolved=resolved, allow_disabled=allow_disabled)
    return LocalNotificationConnector(config=resolved)


def get_calendar_connector(
    *,
    db: Session,
    allow_disabled: bool = False,
) -> LocalCalendarConnector:
    resolved = get_integration(db=db, key="calendar")
    _require_enabled(resolved=resolved, allow_disabled=allow_disabled)
    return LocalCalendarConnector(config=resolved)


def resolve_integration_state(
    *,
    db: Session,
    key: str,
    record: PlatformIntegration | None,
) -> ResolvedIntegrationConfig:
    entry = get_catalog_entry(key)
    bootstrap = _load_bootstrap(entry.key)
    stored_overrides = _load_stored_credentials(record=record, key=entry.key)
    linked_profile = _get_linked_profile(db=db, record=record)
    linked_profile_credentials = _load_profile_credentials(profile=linked_profile)
    effective_credentials = {
        **bootstrap["credentials"],
        **linked_profile_credentials,
        **stored_overrides,
    }
    feature_flags = dict(bootstrap["feature_flags"])
    if record is not None and record.feature_flags_json:
        feature_flags.update(record.feature_flags_json)
    environment = record.environment if record is not None else bootstrap["environment"]
    enabled = record.enabled if record is not None else bootstrap["enabled"]
    runtime_connector = _runtime_connector_name(key=entry.key, environment=environment)
    credential_source = (
        "stored_override"
        if stored_overrides
        else "bootstrap"
        if bootstrap["credentials"]
        else "none"
    )

    return ResolvedIntegrationConfig(
        key=entry.key,
        label=entry.label,
        description=entry.description,
        category=entry.category,
        provider_key=entry.provider_key,
        supports_shared_profile=entry.supports_shared_profile,
        compatible_profile_provider_keys=list(entry.compatible_profile_provider_keys),
        enabled=enabled,
        environment=environment,
        runtime_connector=runtime_connector,
        feature_flags=feature_flags,
        credentials=effective_credentials,
        credentials_masked=mask_catalog_credentials(
            credentials=effective_credentials,
            public_keys=_public_credential_keys(entry.credential_fields),
        ),
        credential_source=credential_source,
        bootstrap_credentials_present=bool(bootstrap["credentials"]),
        has_stored_credentials=bool(stored_overrides),
        updated_at=record.updated_at if record is not None else None,
        updated_by=str(record.updated_by) if record is not None and record.updated_by else None,
        credential_profile_id=(
            str(record.credential_profile_id)
            if record and record.credential_profile_id
            else None
        ),
        credential_profile_label=linked_profile.label if linked_profile else None,
        credential_fields=list(entry.credential_fields),
        feature_flag_definitions=list(entry.feature_flag_definitions),
        validation_help=entry.validation_help,
        guide=entry.guide,
    )


def mask_secret_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: mask_secret_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_secret_payload(item) for item in value]
    if isinstance(value, str):
        if not value:
            return value
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}{'*' * max(len(value) - 4, 4)}{value[-2:]}"
    return value


def mask_catalog_credentials(
    *,
    credentials: dict[str, Any],
    public_keys: set[str],
) -> dict[str, Any]:
    return {
        key: value if key in public_keys else mask_secret_payload(value)
        for key, value in credentials.items()
    }


def _public_credential_keys(fields) -> set[str]:
    return {field.key for field in fields if not field.sensitive}


def _profile_public_credential_keys(provider_key: str) -> set[str]:
    return {
        field.key
        for entry in list_catalog_entries()
        if (
            entry.provider_key == provider_key
            or provider_key in entry.compatible_profile_provider_keys
        )
        for field in entry.credential_fields
        if not field.sensitive
    }


def merge_credential_updates(
    *,
    current: dict[str, Any],
    updates: dict[str, Any] | None,
    effective_masked: dict[str, Any],
) -> dict[str, Any]:
    if updates is None:
        return {}
    merged = json.loads(json.dumps(current))
    _merge_values(target=merged, updates=updates, effective_masked=effective_masked)
    return merged


def _merge_values(
    *,
    target: dict[str, Any],
    updates: dict[str, Any],
    effective_masked: dict[str, Any],
) -> None:
    for key, value in updates.items():
        masked_reference = effective_masked.get(key)
        if value is None:
            target.pop(key, None)
            continue
        if isinstance(value, dict):
            existing = target.get(key)
            target[key] = dict(existing) if isinstance(existing, dict) else {}
            nested_mask = masked_reference if isinstance(masked_reference, dict) else {}
            _merge_values(
                target=target[key],
                updates=value,
                effective_masked=nested_mask,
            )
            if not target[key]:
                target.pop(key, None)
            continue
        if _is_masked_placeholder(value=value, masked_reference=masked_reference):
            continue
        target[key] = value


def _is_masked_placeholder(*, value: Any, masked_reference: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    if lowered in MASKED_SENTINELS:
        return True
    return isinstance(masked_reference, str) and value == masked_reference


def _get_record(*, db: Session, key: str) -> PlatformIntegration | None:
    entry = get_catalog_entry(key)
    return db.scalar(select(PlatformIntegration).where(PlatformIntegration.key == entry.key))


def _require_enabled(*, resolved: ResolvedIntegrationConfig, allow_disabled: bool) -> None:
    if allow_disabled or resolved.enabled:
        return
    raise ValueError(f"{resolved.label} integration is disabled.")


def _runtime_connector_name(*, key: str, environment: IntegrationEnvironment) -> str:
    if environment == IntegrationEnvironment.OFF:
        return f"off-{key}"
    mode = "mock" if environment == IntegrationEnvironment.TEST else "local-safe"
    return f"{mode}-{key}"


def _validate_operating_mode(
    *,
    key: str,
    environment: IntegrationEnvironment,
    enabled: bool,
    credentials: dict[str, Any],
    profile_provider_key: str | None = None,
) -> None:
    if environment == IntegrationEnvironment.OFF and enabled:
        raise ValueError(f"{key} cannot be enabled while environment is off.")
    if not enabled:
        return
    _validate_credentials(key, credentials, profile_provider_key=profile_provider_key)


def _validate_credentials(
    key: str,
    credentials: dict[str, Any],
    *,
    profile_provider_key: str | None = None,
) -> None:
    if key == "flights_amadeus":
        missing = [
            field
            for field in ("client_id", "client_secret")
            if not str(credentials.get(field) or "").strip()
        ]
        if missing:
            raise ValueError(f"flights_amadeus requires: {', '.join(missing)}.")
        return

    if key == "flights_duffel":
        if not str(credentials.get("access_token") or "").strip():
            raise ValueError("flights_duffel requires access_token.")
        return

    if key == "flights_kiwi":
        if not str(credentials.get("api_key") or "").strip():
            raise ValueError("flights_kiwi requires api_key.")
        return

    if key == "hotels":
        provider = str(credentials.get("provider") or "").strip().lower()
        if provider == "hotelbeds":
            missing = [
                field
                for field in ("api_key", "api_secret")
                if not str(credentials.get(field) or "").strip()
            ]
            if missing:
                raise ValueError(f"hotels using hotelbeds requires: {', '.join(missing)}.")
        return

    if key == "booking":
        provider = (profile_provider_key or str(credentials.get("provider") or "")).strip().lower()
        if not provider:
            raise ValueError(
                "booking requires a provider or a matching shared credential profile."
            )
        if provider == "amadeus":
            missing = [
                field
                for field in ("client_id", "client_secret")
                if not str(credentials.get(field) or "").strip()
            ]
            if missing:
                raise ValueError(f"booking using amadeus requires: {', '.join(missing)}.")
            return
        if provider in {"duffel", "kiwi"}:
            accepted_key = "access_token" if provider == "duffel" else "api_key"
            if not str(credentials.get(accepted_key) or "").strip():
                raise ValueError(f"booking using {provider} requires {accepted_key}.")
            return
        raise ValueError(
            "booking provider must be duffel, amadeus, or kiwi, "
            "or use a matching shared credential profile."
        )

    if key == "notifications":
        delivery_mode = str(credentials.get("delivery_mode") or "log_only").strip().lower()
        if delivery_mode == "log_only":
            return
        if delivery_mode == "smtp_dev":
            missing = [
                field
                for field in ("smtp_host", "smtp_from_address")
                if not str(credentials.get(field) or "").strip()
            ]
            if missing:
                raise ValueError(
                    f"notifications smtp_dev mode requires: {', '.join(missing)}."
                )
            return
        if delivery_mode == "telegram_bot":
            if not str(credentials.get("telegram_bot_token") or "").strip():
                raise ValueError(
                    "notifications telegram_bot mode requires telegram_bot_token."
                )
            return
        raise ValueError(
            "notifications delivery_mode must be one of: log_only, smtp_dev, telegram_bot."
        )

    if key == "calendar":
        delivery_mode = str(credentials.get("delivery_mode") or "log_only").strip().lower()
        if delivery_mode == "log_only":
            return
        if delivery_mode == "google_calendar":
            missing = [
                field
                for field in ("calendar_id", "access_token")
                if not str(credentials.get(field) or "").strip()
            ]
            if missing:
                raise ValueError(
                    f"calendar google_calendar mode requires: {', '.join(missing)}."
                )
            return
        raise ValueError(
            "calendar delivery_mode must be one of: log_only, google_calendar."
        )


def _encrypt_credentials(key: str, credentials: dict[str, Any]) -> str:
    payload = json.dumps(credentials, sort_keys=True)
    return encrypt_with_app_secret(plaintext=payload, aad=_credentials_aad(key))


def _load_stored_credentials(
    *,
    record: PlatformIntegration | None,
    key: str,
) -> dict[str, Any]:
    if record is None or not record.encrypted_credentials:
        return {}
    payload = decrypt_with_app_secret(
        ciphertext=record.encrypted_credentials,
        aad=_credentials_aad(key),
    )
    parsed = json.loads(payload)
    return parsed if isinstance(parsed, dict) else {}


def _get_linked_profile(
    *,
    db: Session,
    record: PlatformIntegration | None,
) -> IntegrationCredentialProfile | None:
    if record is None or not record.credential_profile_id:
        return None
    return db.scalar(
        select(IntegrationCredentialProfile).where(
            IntegrationCredentialProfile.id == record.credential_profile_id
        )
    )


def _require_credential_profile(*, db: Session, profile_id: str) -> IntegrationCredentialProfile:
    try:
        profile_uuid = UUID(profile_id)
    except ValueError as exc:
        raise LookupError("Credential profile was not found.") from exc
    profile = db.scalar(
        select(IntegrationCredentialProfile).where(IntegrationCredentialProfile.id == profile_uuid)
    )
    if profile is None:
        raise LookupError("Credential profile was not found.")
    return profile


def _parse_profile_id(
    credential_profile_id: str | None,
    *,
    allowed_provider_keys: tuple[str, ...],
    db: Session,
) -> UUID | None:
    if credential_profile_id is None or not credential_profile_id.strip():
        return None
    profile = _require_credential_profile(db=db, profile_id=credential_profile_id)
    if allowed_provider_keys and profile.provider_key not in allowed_provider_keys:
        raise ValueError(
            f"Credential profile provider '{profile.provider_key}' "
            "is not compatible with this connector."
        )
    return profile.id


def _load_profile_credentials(
    *,
    profile: IntegrationCredentialProfile | None,
) -> dict[str, Any]:
    if profile is None or not profile.encrypted_credentials:
        return {}
    payload = decrypt_with_app_secret(
        ciphertext=profile.encrypted_credentials,
        aad=_profile_credentials_aad(profile.id),
    )
    parsed = json.loads(payload)
    return parsed if isinstance(parsed, dict) else {}


def _encrypt_profile_credentials(
    *,
    profile_id: UUID,
    credentials: dict[str, Any],
) -> str:
    payload = json.dumps(credentials, sort_keys=True)
    return encrypt_with_app_secret(
        plaintext=payload,
        aad=_profile_credentials_aad(profile_id),
    )


def _profile_credentials_aad(profile_id: UUID) -> str:
    return f"integration-credential-profile:{profile_id}"


def _serialize_credential_profile(
    *,
    db: Session,
    profile: IntegrationCredentialProfile,
) -> ResolvedCredentialProfile:
    usage = list(
        db.scalars(
            select(PlatformIntegration.key).where(
                PlatformIntegration.credential_profile_id == profile.id
            )
        )
    )
    return ResolvedCredentialProfile(
        id=str(profile.id),
        provider_key=profile.provider_key,
        label=profile.label,
        credentials_masked=mask_catalog_credentials(
            credentials=_load_profile_credentials(profile=profile),
            public_keys=_profile_public_credential_keys(profile.provider_key),
        ),
        updated_at=profile.updated_at,
        updated_by=str(profile.updated_by) if profile.updated_by else None,
        usage_integration_keys=list(usage),
    )


def _load_bootstrap(key: str) -> dict[str, Any]:
    entry = get_catalog_entry(key)
    prefix = f"{BOOTSTRAP_ENV_PREFIX}{entry.env_slug}_"
    credentials = _json_env(f"{prefix}CREDENTIALS_JSON")
    feature_flags = _json_env(f"{prefix}FEATURE_FLAGS_JSON")
    enabled = _bool_env(f"{prefix}ENABLED", default=entry.default_enabled)
    environment_value = os.getenv(
        f"{prefix}ENVIRONMENT",
        entry.default_environment.value,
    ).strip().lower()
    environment = (
        IntegrationEnvironment(environment_value)
        if environment_value in {item.value for item in IntegrationEnvironment}
        else entry.default_environment
    )
    return {
        "credentials": credentials if isinstance(credentials, dict) else {},
        "feature_flags": feature_flags if isinstance(feature_flags, dict) else {},
        "enabled": enabled,
        "environment": environment,
    }


def _backfill_shared_profiles(*, db: Session) -> None:
    mutated = False
    records = list(
        db.scalars(
            select(PlatformIntegration).where(
                PlatformIntegration.key.in_([entry.key for entry in list_catalog_entries()])
            )
        )
    )
    for record in records:
        entry = get_catalog_entry(record.key)
        if not entry.supports_shared_profile or record.credential_profile_id:
            continue
        stored_credentials = _load_stored_credentials(record=record, key=record.key)
        if not stored_credentials:
            continue
        inferred_provider_key = (
            entry.provider_key
            or str(stored_credentials.get("provider") or "").strip().lower()
        )
        if (
            entry.compatible_profile_provider_keys
            and inferred_provider_key not in entry.compatible_profile_provider_keys
        ):
            continue
        if not inferred_provider_key:
            continue
        profile = IntegrationCredentialProfile(
            id=uuid4(),
            provider_key=inferred_provider_key,
            label=f"{entry.label} shared profile",
            encrypted_credentials="",
            updated_by=record.updated_by,
        )
        profile.encrypted_credentials = _encrypt_profile_credentials(
            profile_id=profile.id,
            credentials=stored_credentials,
        )
        db.add(profile)
        db.flush()
        record.credential_profile_id = profile.id
        record.encrypted_credentials = _encrypt_credentials(record.key, {})
        db.add(record)
        mutated = True
    if mutated:
        db.commit()


def _json_env(name: str) -> dict[str, Any] | list[Any] | None:
    raw = os.getenv(name)
    if not raw:
        return None
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, (dict, list)) else None


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _credentials_aad(key: str) -> str:
    return f"platform-integration:{key}"
