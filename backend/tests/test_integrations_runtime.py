from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

import app.integrations.service as integrations_service
from app.api.schemas.integrations import AdminIntegrationResponse
from app.config import KeyUnlockMode, MasterKeySource, get_settings
from app.db.models import (
    Booking,
    BookingStatus,
    Deal,
    DealStatus,
    DestinationMode,
    IntegrationEnvironment,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTransport,
    PaymentMethod,
    PlatformIntegration,
    TripMode,
    TripWatch,
    User,
)
from app.integrations.catalog import get_catalog_entry, list_catalog_entries
from app.integrations.connectors import (
    FLIGHT_SOURCE_BY_INTEGRATION_KEY,
    LocalBookingConnector,
    LocalCalendarConnector,
    LocalFlightConnector,
    LocalHotelConnector,
    LocalNotificationConnector,
)
from app.integrations.service import (
    get_mock_data_enabled,
    live_inventory_available,
    mask_secret_payload,
    merge_credential_updates,
    payload_is_simulated,
    provider_is_simulated,
    resolve_integration_state,
    runtime_connector_is_simulated,
    set_mock_data_enabled,
    source_is_simulated,
)
from app.integrations.types import ResolvedIntegrationConfig
from app.security.crypto import encrypt_with_app_secret
from app.security.key_provider import get_key_provider
from app.watch_mock_adapter import DeterministicMockAdapter


def _configure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "APP_SECRET",
        "test-master-secret-with-more-than-thirty-two-bytes",
    )
    monkeypatch.setenv("BOOKING_MASTER_KEY_PASSPHRASE", "test-master-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://travel-watch.test")
    get_settings.cache_clear()


def _build_watch() -> TripWatch:
    return TripWatch(
        id=uuid4(),
        user_id=uuid4(),
        trip_mode=TripMode.FLIGHTS_THEN_HOTELS,
        destination_mode=DestinationMode.FIXED,
        origin_iatas=["HND"],
        destination_iatas=["SIN"],
        depart_date_from=date(2027, 4, 12),
        return_date_to=date(2027, 4, 19),
        cabin_class="business",
        budget_currency="USD",
        prefer_refundable=True,
        want_car=True,
        glide_start_days=42,
        glide_end_days=3,
        quality_floor=40,
        luxury_vs_savings=0.6,
        loyalty_weighting=0.0,
        band_tolerance=0.10,
        value_pressure=0.0,
    )


def _resolved_config(
    key: str,
    *,
    environment: IntegrationEnvironment = IntegrationEnvironment.TEST,
) -> ResolvedIntegrationConfig:
    return ResolvedIntegrationConfig(
        key=key,
        label=key.title(),
        description=f"{key} connector",
        category="tests",
        provider_key=None,
        supports_shared_profile=False,
        compatible_profile_provider_keys=[],
        enabled=True,
        environment=environment,
        runtime_connector=("mock-" if environment == IntegrationEnvironment.TEST else "local-safe-")
        + key,
        feature_flags={},
        credentials={"api_key": "stored-secret"},
        credentials_masked={"api_key": "st*********et"},
        credential_source="stored_override",
        bootstrap_credentials_present=False,
        has_stored_credentials=True,
        updated_at=None,
        updated_by=None,
        credential_fields=[],
        feature_flag_definitions=[],
        validation_help=None,
    )


class _FakeRuntimeSession:
    def __init__(self) -> None:
        self.record: PlatformIntegration | None = None

    def scalar(self, _statement):
        return self.record

    def add(self, record: PlatformIntegration) -> None:
        self.record = record

    def commit(self) -> None:
        return None

    def refresh(self, _record: PlatformIntegration) -> None:
        return None


class _NoopSession:
    def scalar(self, _statement):
        return None


def test_every_catalog_entry_has_a_complete_frozen_acquisition_guide() -> None:
    entries = list_catalog_entries()

    assert {entry.key for entry in entries} == {
        "flights_amadeus",
        "flights_duffel",
        "flights_kiwi",
        "hotels",
        "booking",
        "notifications",
        "calendar",
    }

    for entry in entries:
        guide = entry.guide
        assert guide is not None, entry.key
        assert guide.links, entry.key
        assert guide.account_requirements, entry.key
        assert guide.steps, entry.key
        assert guide.environment_notes, entry.key
        assert guide.enables, entry.key
        for link in guide.links:
            assert link.label.strip(), entry.key
            assert link.url.startswith("https://"), entry.key
        for values in (
            guide.account_requirements,
            guide.steps,
            guide.environment_notes,
            guide.enables,
        ):
            assert isinstance(values, tuple), entry.key
            assert all(value.strip() for value in values), entry.key

    with pytest.raises(FrozenInstanceError):
        get_catalog_entry("flights_amadeus").guide.links[0].label = "Changed"


def test_catalog_acquisition_guides_use_official_provider_links() -> None:
    expected_links = {
        "flights_amadeus": (
            (
                "Amadeus developer portal registration",
                "https://developers.amadeus.com/",
            ),
            (
                "Amadeus quick start and application creation",
                "https://developers.amadeus.com/self-service/apis-docs/guides/"
                "developer-guides/quick-start/",
            ),
            (
                "Amadeus production access guide",
                "https://developers.amadeus.com/self-service/apis-docs/guides/"
                "developer-guides/API-Keys/moving-to-production/",
            ),
        ),
        "flights_duffel": (
            (
                "Duffel account signup",
                "https://duffel.com/",
            ),
            (
                "Duffel dashboard and access-token setup",
                "https://duffel.com/guides/getting-started",
            ),
            (
                "Duffel API authentication guide",
                "https://duffel.com/docs/api/overview/making-requests",
            ),
        ),
        "flights_kiwi": (
            (
                "Kiwi invitation-only partnership announcement",
                "https://media.kiwi.com/articles-and-interviews/"
                "better-for-business-kiwi-com-takes-a-new-approach-to-partnerships/",
            ),
            ("Kiwi Tequila portal", "https://tequila.kiwi.com/"),
        ),
        "hotels": (
            (
                "Hotelbeds API key registration",
                "https://developer.hotelbeds.com/register/",
            ),
            (
                "Hotelbeds getting started",
                "https://developer.hotelbeds.com/documentation/getting-started/",
            ),
            (
                "Booking.com affiliate application",
                "https://partnerships.booking.com/",
            ),
            (
                "Booking.com Demand API prerequisites",
                "https://developers.booking.com/demand/docs/getting-started/prerequisites",
            ),
            ("Booking.com Demand API", "https://developers.booking.com/demand"),
        ),
        "booking": (
            (
                "Duffel flights getting started",
                "https://duffel.com/docs/guides/getting-started-with-flights",
            ),
            (
                "Amadeus quick start",
                "https://developers.amadeus.com/self-service/apis-docs/guides/"
                "developer-guides/quick-start/",
            ),
            (
                "Kiwi invitation-only partnership announcement",
                "https://media.kiwi.com/articles-and-interviews/"
                "better-for-business-kiwi-com-takes-a-new-approach-to-partnerships/",
            ),
        ),
        "notifications": (
            ("Telegram BotFather bot creation", "https://t.me/BotFather"),
            ("Telegram BotFather tutorial", "https://core.telegram.org/bots/tutorial"),
        ),
        "calendar": (
            (
                "Google Cloud Calendar API enablement",
                "https://console.cloud.google.com/flows/enableapi"
                "?apiid=calendar-json.googleapis.com",
            ),
            (
                "Google Cloud OAuth credentials",
                "https://console.cloud.google.com/apis/credentials",
            ),
            (
                "Google Calendar create events guide",
                "https://developers.google.com/workspace/calendar/api/guides/create-events",
            ),
        ),
    }

    for key, links in expected_links.items():
        guide = get_catalog_entry(key).guide
        assert tuple((link.label, link.url) for link in guide.links) == links

    booking_guide = get_catalog_entry("booking").guide
    assert "provider" in " ".join(booking_guide.steps).lower()

    notifications_guide = get_catalog_entry("notifications").guide
    notification_copy = " ".join(
        (
            *notifications_guide.account_requirements,
            *notifications_guide.steps,
            *notifications_guide.environment_notes,
        )
    ).lower()
    assert "mailpit" in notification_copy
    assert "smtp provider" in notification_copy
    assert "smtp and telegram can send externally" in notification_copy

    kiwi_guide = get_catalog_entry("flights_kiwi").guide
    kiwi_copy = " ".join((*kiwi_guide.steps, *kiwi_guide.environment_notes)).lower()
    assert "invitation only" in kiwi_copy
    assert "self-service" not in kiwi_copy

    hotels_guide = get_catalog_entry("hotels").guide
    hotel_copy = " ".join(
        (
            *hotels_guide.account_requirements,
            *hotels_guide.steps,
            *hotels_guide.environment_notes,
        )
    ).lower()
    assert "api key" in hotel_copy
    assert "secret" in hotel_copy
    assert "x-signature" in hotel_copy
    assert "managed affiliate partner" in hotel_copy
    assert "affiliate signup does not guarantee demand api access" in hotel_copy

    calendar_guide = get_catalog_entry("calendar").guide
    calendar_copy = " ".join(
        (
            *calendar_guide.account_requirements,
            *calendar_guide.steps,
            *calendar_guide.environment_notes,
            *calendar_guide.enables,
        )
    )
    assert "https://www.googleapis.com/auth/calendar" in calendar_copy
    assert "create and delete live events" in calendar_copy.lower()

    all_guide_copy = " ".join(
        text
        for entry in list_catalog_entries()
        for text in (
            *entry.guide.steps,
            *entry.guide.environment_notes,
            *entry.guide.enables,
        )
    ).lower()
    assert "credential validation" not in all_guide_copy


def test_every_resolved_acquisition_guide_serializes_for_the_admin_api() -> None:
    for entry in list_catalog_entries():
        resolved = resolve_integration_state(
            db=_NoopSession(),
            key=entry.key,
            record=None,
        )

        payload = AdminIntegrationResponse.model_validate(asdict(resolved)).model_dump(
            mode="json"
        )

        assert payload["guide"]["links"] == [
            {"label": link.label, "url": link.url} for link in entry.guide.links
        ]
        assert payload["guide"]["account_requirements"] == list(
            entry.guide.account_requirements
        )
        assert payload["guide"]["steps"] == list(entry.guide.steps)
        assert payload["guide"]["environment_notes"] == list(
            entry.guide.environment_notes
        )
        assert payload["guide"]["enables"] == list(entry.guide.enables)


@pytest.mark.parametrize(
    ("provider", "credentials"),
    (
        ("duffel", {"provider": "duffel", "access_token": "duffel_test_token"}),
        (
            "amadeus",
            {
                "provider": "amadeus",
                "client_id": "amadeus-key",
                "client_secret": "amadeus-secret",
            },
        ),
        ("kiwi", {"provider": "kiwi", "api_key": "kiwi-key"}),
    ),
)
def test_booking_direct_credentials_accept_provider_specific_shapes(
    provider: str,
    credentials: dict[str, str],
) -> None:
    integrations_service._validate_credentials("booking", credentials)


@pytest.mark.parametrize(
    ("provider", "credentials", "missing_field"),
    (
        ("duffel", {"provider": "duffel"}, "access_token"),
        (
            "amadeus",
            {"provider": "amadeus", "client_id": "amadeus-key"},
            "client_secret",
        ),
        ("kiwi", {"provider": "kiwi"}, "api_key"),
    ),
)
def test_booking_direct_credentials_reject_incomplete_provider_shapes(
    provider: str,
    credentials: dict[str, str],
    missing_field: str,
) -> None:
    with pytest.raises(ValueError, match=missing_field):
        integrations_service._validate_credentials("booking", credentials)


def test_booking_requires_a_supported_direct_provider_or_matching_profile() -> None:
    with pytest.raises(ValueError, match="provider or a matching shared credential profile"):
        integrations_service._validate_credentials("booking", {})

    with pytest.raises(ValueError, match="duffel, amadeus, or kiwi"):
        integrations_service._validate_credentials(
            "booking",
            {"provider": "custom", "access_token": "token"},
        )

    integrations_service._validate_credentials(
        "booking",
        {"access_token": "profile-token"},
        profile_provider_key="duffel",
    )


def test_hotelbeds_credentials_require_api_key_and_secret() -> None:
    integrations_service._validate_credentials(
        "hotels",
        {
            "provider": "hotelbeds",
            "api_key": "hotelbeds-key",
            "api_secret": "hotelbeds-secret",
        },
    )

    with pytest.raises(ValueError, match="api_secret"):
        integrations_service._validate_credentials(
            "hotels",
            {"provider": "hotelbeds", "api_key": "hotelbeds-key"},
        )

    fields = {field.key: field for field in get_catalog_entry("hotels").credential_fields}
    assert {"provider", "api_key", "api_secret"} <= fields.keys()
    assert "X-Signature" in fields["api_secret"].help_text


def test_local_connection_test_reports_configuration_shape_not_network_validation() -> None:
    valid_config = _resolved_config("flights_amadeus")
    valid_config.credentials = {
        "client_id": "amadeus-key",
        "client_secret": "amadeus-secret",
    }
    valid_result = LocalFlightConnector(config=valid_config).test_connection()

    assert valid_result.ok is True
    assert "local configuration check passed" in valid_result.message.lower()
    assert "no provider network request" in valid_result.message.lower()
    assert valid_result.detail["check_type"] == "local_presence_and_shape"
    assert valid_result.detail["network_request_made"] is False
    assert "simulated" not in valid_result.detail

    invalid_config = _resolved_config("flights_amadeus")
    invalid_config.credentials = {"client_id": "amadeus-key"}
    invalid_result = LocalFlightConnector(config=invalid_config).test_connection()

    assert invalid_result.ok is False
    assert invalid_result.detail["missing_fields"] == ["client_secret"]


def test_resolve_integration_state_prefers_stored_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_settings(monkeypatch)
    monkeypatch.setenv(
        "TRAVEL_WATCH_INTEGRATION_FLIGHTS_AMADEUS_CREDENTIALS_JSON",
        json.dumps({"client_id": "env-secret", "account_id": "acct-env"}),
    )
    monkeypatch.setenv(
        "TRAVEL_WATCH_INTEGRATION_FLIGHTS_AMADEUS_FEATURE_FLAGS_JSON",
        json.dumps({"bootstrap": True}),
    )

    encrypted = encrypt_with_app_secret(
        plaintext=json.dumps({"client_id": "db-secret", "workspace": "ops"}),
        aad="platform-integration:flights_amadeus",
    )
    record = PlatformIntegration(
        key="flights_amadeus",
        encrypted_credentials=encrypted,
        environment=IntegrationEnvironment.LIVE,
        enabled=False,
        feature_flags_json={"stored": True},
    )

    resolved = resolve_integration_state(
        db=_NoopSession(),
        key="flights_amadeus",
        record=record,
    )

    assert resolved.credentials["client_id"] == "db-secret"
    assert resolved.credentials["account_id"] == "acct-env"
    assert resolved.credentials["workspace"] == "ops"
    assert resolved.credentials_masked["client_id"] != "db-secret"
    assert resolved.credential_source == "stored_override"
    assert resolved.runtime_connector == "amadeus"
    assert resolved.enabled is False
    assert resolved.feature_flags == {"bootstrap": True, "stored": True}


def test_non_secret_catalog_fields_round_trip_clear_while_secrets_stay_masked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_settings(monkeypatch)
    credentials = {
        "delivery_mode": "telegram_bot",
        "smtp_host": "smtp.example.com",
        "smtp_port": "2525",
        "smtp_from_address": "alerts@example.com",
        "telegram_bot_token": "123456:super-secret-token",
        "unlisted_internal_value": "must-stay-secret",
    }
    record = PlatformIntegration(
        key="notifications",
        encrypted_credentials=encrypt_with_app_secret(
            plaintext=json.dumps(credentials),
            aad="platform-integration:notifications",
        ),
        environment=IntegrationEnvironment.LIVE,
        enabled=True,
        feature_flags_json={},
    )

    resolved = resolve_integration_state(
        db=_NoopSession(),
        key="notifications",
        record=record,
    )
    response = AdminIntegrationResponse.model_validate(asdict(resolved))

    assert response.credentials_masked["delivery_mode"] == "telegram_bot"
    assert response.credentials_masked["smtp_host"] == "smtp.example.com"
    assert response.credentials_masked["smtp_port"] == "2525"
    assert response.credentials_masked["smtp_from_address"] == "alerts@example.com"
    assert response.credentials_masked["telegram_bot_token"] != credentials[
        "telegram_bot_token"
    ]
    assert response.credentials_masked["unlisted_internal_value"] != credentials[
        "unlisted_internal_value"
    ]


def test_merge_credential_updates_keeps_masked_values() -> None:
    current = {
        "api_key": "db-secret",
        "nested": {"secret": "nested-secret", "region": "us"},
    }
    effective_masked = mask_secret_payload(
        {
            "api_key": "db-secret",
            "nested": {"secret": "nested-secret", "region": "us"},
            "account_id": "acct-env",
        }
    )

    merged = merge_credential_updates(
        current=current,
        updates={
            "api_key": effective_masked["api_key"],
            "nested": {
                "secret": "<masked>",
                "region": "eu",
            },
            "account_id": None,
            "api_base": "http://localhost:8080",
        },
        effective_masked=effective_masked,
    )

    assert merged["api_key"] == "db-secret"
    assert merged["nested"]["secret"] == "nested-secret"
    assert merged["nested"]["region"] == "eu"
    assert "account_id" not in merged
    assert merged["api_base"] == "http://localhost:8080"


def test_mock_data_toggle_defaults_on_without_runtime_record() -> None:
    assert get_mock_data_enabled(db=_FakeRuntimeSession()) is True


def test_simulated_runtime_helpers_detect_mock_and_local_safe_values() -> None:
    assert runtime_connector_is_simulated("mock-flights_amadeus") is True
    assert runtime_connector_is_simulated("local-safe-hotels") is True
    assert runtime_connector_is_simulated("off-booking") is True
    assert runtime_connector_is_simulated("live-amadeus") is False
    assert source_is_simulated("mock-duffel") is True
    assert source_is_simulated("live-duffel") is False
    assert source_is_simulated("live-amadeus+mock-booking") is True
    assert provider_is_simulated("mock-booking") is True
    assert provider_is_simulated("Duffel") is False
    assert provider_is_simulated("duffel+local-safe-booking") is True
    assert payload_is_simulated({"simulated": True}) is True
    assert payload_is_simulated({"simulated": False}) is False


def test_notification_delivery_enums_bind_lowercase_values() -> None:
    transport_processor = NotificationDelivery.__table__.c.transport.type.bind_processor(
        postgresql.dialect()
    )
    status_processor = NotificationDelivery.__table__.c.status.type.bind_processor(
        postgresql.dialect()
    )

    assert transport_processor is not None
    assert status_processor is not None
    assert transport_processor(NotificationTransport.LOG_ONLY) == "log_only"
    assert status_processor(NotificationDeliveryStatus.PENDING) == "pending"


def test_mock_data_toggle_persists_in_platform_runtime_record() -> None:
    session = _FakeRuntimeSession()
    actor = User(
        id=uuid4(),
        email="admin@example.com",
        password_hash="hashed-password",
    )

    assert set_mock_data_enabled(db=session, actor=actor, enabled=False) is False
    assert get_mock_data_enabled(db=session) is False
    assert set_mock_data_enabled(db=session, actor=actor, enabled=True) is True
    assert get_mock_data_enabled(db=session) is True


def test_live_inventory_available_reflects_current_connector_stack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_settings(monkeypatch)
    records = {
        "flights_amadeus": PlatformIntegration(
            key="flights_amadeus",
            encrypted_credentials=encrypt_with_app_secret(
                plaintext=json.dumps({"client_id": "live-flight-secret"}),
                aad="platform-integration:flights_amadeus",
            ),
            environment=IntegrationEnvironment.LIVE,
            enabled=True,
            feature_flags_json={},
        ),
        "hotels": PlatformIntegration(
            key="hotels",
            encrypted_credentials=encrypt_with_app_secret(
                plaintext=json.dumps({"api_key": "live-hotel-secret"}),
                aad="platform-integration:hotels",
            ),
            environment=IntegrationEnvironment.LIVE,
            enabled=True,
            feature_flags_json={},
        ),
    }
    monkeypatch.setattr(
        integrations_service,
        "_get_record",
        lambda *, db, key: records.get(key),
    )

    assert live_inventory_available(db=object()) is True
    records["flights_amadeus"].enabled = False
    assert live_inventory_available(db=object()) is False


def test_local_connectors_wrap_existing_mock_adapter() -> None:
    watch = _build_watch()
    flight_connector = LocalFlightConnector(config=_resolved_config("flights_amadeus"))
    hotel_connector = LocalHotelConnector(config=_resolved_config("hotels"))

    flights = flight_connector.search_flights(watch=watch)
    hotels = hotel_connector.search_hotels(watch=watch)
    cars = hotel_connector.search_cars(watch=watch)

    assert flights
    assert hotels
    assert cars
    assert {offer["kind"] for offer in flights} == {"flight"}
    assert {offer["source"] for offer in flights} == {
        FLIGHT_SOURCE_BY_INTEGRATION_KEY["flights_amadeus"]
    }
    assert {offer["kind"] for offer in hotels} == {"hotel"}
    assert {offer["kind"] for offer in cars} == {"car"}


def test_local_booking_and_notification_connectors_are_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_settings(monkeypatch)
    watch = _build_watch()
    user = User(
        id=uuid4(),
        email="traveler@example.com",
        password_hash="hashed-password",
        default_notify_channel=NotificationChannel.EMAIL,
    )
    deal = DeterministicMockAdapter().search(watch=watch)[0]
    payment_method = PaymentMethod(
        id=uuid4(),
        user_id=user.id,
        label="Visa",
        encrypted_blob="encrypted",
        last4="4242",
    )

    booking_connector = LocalBookingConnector(
        config=_resolved_config("booking", environment=IntegrationEnvironment.LIVE)
    )
    notification_connector = LocalNotificationConnector(
        config=_resolved_config("notifications", environment=IntegrationEnvironment.LIVE)
    )

    booking_deal = Booking(
        deal_id=uuid4(),
        provider="mock-duffel",
        status=BookingStatus.TICKETED,
        idempotency_key="booking-12345",
        amount_charged=Decimal("640.00"),
        currency="USD",
    )

    normalized_deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source=str(deal["source"]),
        total_price=Decimal("640.00"),
        currency="USD",
        fingerprint_hash="fingerprint",
        status=DealStatus.PROPOSED,
        loyalty_plan_json=[],
        payload_json={"refundable": True},
    )

    booked = booking_connector.book_deal(
        deal=normalized_deal,
        watch=watch,
        payment_method=payment_method,
        booked_at=datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
        idempotency_key="local-booking-idempotency-key",
    )
    cancelled = booking_connector.cancel_booking(
        booking=booking_deal,
        deal=normalized_deal,
        reason="duplicate booking",
        requested_at=datetime(2026, 6, 29, 12, 5, tzinfo=UTC),
    )
    notification_result = notification_connector.test_connection()

    assert booked.provider.startswith("mock-")
    assert booked.simulated is True
    assert booked.provider_payload["idempotency_key"] == "local-booking-idempotency-key"
    assert cancelled.refund_received == Decimal("640.00")
    assert notification_result.ok is True
    assert notification_result.warnings


def test_local_calendar_connector_is_safe() -> None:
    connector = LocalCalendarConnector(config=_resolved_config("calendar"))
    result = connector.create_event(
        title="TRAMP test trip",
        starts_at=datetime(2026, 6, 29, 12, 0, tzinfo=UTC),
        ends_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        description="Localhost calendar test",
    )

    assert result["simulated"] is True
    assert str(result["event_id"]).startswith("logonly-")


def test_auto_unlock_local_file_provider_bootstraps_seed_material(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_settings(monkeypatch)
    auto_unlock_path = tmp_path / "auto-unlock.key"
    monkeypatch.setenv("KEY_UNLOCK_MODE", KeyUnlockMode.AUTO.value)
    monkeypatch.setenv("MASTER_KEY_SOURCE", MasterKeySource.LOCAL_FILE.value)
    monkeypatch.setenv("AUTO_UNLOCK_LOCAL_FILE_PATH", str(auto_unlock_path))
    monkeypatch.setenv("AUTO_UNLOCK_SEED_MATERIAL", "bootstrap-localhost-secret")
    get_settings.cache_clear()

    key_material = get_key_provider().get_key()

    try:
        assert key_material.ciphertext_key_id == "auto-unlock-local-file"
        assert auto_unlock_path.exists()
        assert len(key_material.plaintext) == 32
    finally:
        key_material.zeroize()
