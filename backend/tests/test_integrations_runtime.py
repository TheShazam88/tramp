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
    monkeypatch.setenv("APP_SECRET", "test-master-secret")
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
        assert guide.signup_url.startswith("https://"), entry.key
        assert guide.account_requirements, entry.key
        assert guide.steps, entry.key
        assert guide.environment_notes, entry.key
        assert guide.enables, entry.key
        for values in (
            guide.account_requirements,
            guide.steps,
            guide.environment_notes,
            guide.enables,
        ):
            assert isinstance(values, tuple), entry.key
            assert all(value.strip() for value in values), entry.key

    with pytest.raises(FrozenInstanceError):
        get_catalog_entry("flights_amadeus").guide.signup_url = "https://example.com"


def test_catalog_acquisition_guides_use_official_provider_links() -> None:
    expected_urls = {
        "flights_amadeus": (
            "https://developers.amadeus.com/self-service/apis-docs/guides/"
            "developer-guides/quick-start/"
        ),
        "flights_duffel": "https://duffel.com/docs/api/overview/making-requests",
        "flights_kiwi": "https://tequila.kiwi.com/",
        "hotels": "https://developer.hotelbeds.com/documentation/getting-started/",
        "notifications": "https://core.telegram.org/bots/tutorial",
        "calendar": "https://developers.google.com/workspace/calendar/api/quickstart/python",
    }

    for key, signup_url in expected_urls.items():
        assert get_catalog_entry(key).guide.signup_url == signup_url

    hotels_guide = get_catalog_entry("hotels").guide
    assert hotels_guide.application_url == "https://developers.booking.com/demand"
    assert "one credential" in " ".join(hotels_guide.steps).lower()

    booking_guide = get_catalog_entry("booking").guide
    assert booking_guide.application_url is not None
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

    kiwi_copy = " ".join(get_catalog_entry("flights_kiwi").guide.steps).lower()
    assert "approval" in kiwi_copy


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

        assert payload["guide"]["signup_url"] == entry.guide.signup_url
        assert payload["guide"]["application_url"] == entry.guide.application_url
        assert payload["guide"]["account_requirements"] == list(
            entry.guide.account_requirements
        )
        assert payload["guide"]["steps"] == list(entry.guide.steps)
        assert payload["guide"]["environment_notes"] == list(
            entry.guide.environment_notes
        )
        assert payload["guide"]["enables"] == list(entry.guide.enables)


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
    assert resolved.runtime_connector == "local-safe-flights_amadeus"
    assert resolved.enabled is False
    assert resolved.feature_flags == {"bootstrap": True, "stored": True}


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
