from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.db.models import Booking, CancellationStatus, Deal, IntegrationEnvironment, PaymentMethod, TripWatch


@dataclass(frozen=True, slots=True)
class IntegrationCatalogEntry:
    key: str
    label: str
    description: str
    category: str = "general"
    provider_key: str | None = None
    supports_shared_profile: bool = False
    compatible_profile_provider_keys: tuple[str, ...] = ()
    default_environment: IntegrationEnvironment = IntegrationEnvironment.TEST
    default_enabled: bool = True
    credential_fields: tuple["IntegrationCredentialField", ...] = ()
    feature_flag_definitions: tuple["IntegrationFeatureFlagDefinition", ...] = ()
    validation_help: str | None = None

    @property
    def env_slug(self) -> str:
        return self.key.upper().replace("-", "_")


@dataclass(frozen=True, slots=True)
class IntegrationCredentialField:
    key: str
    label: str
    placeholder: str = ""
    help_text: str = ""
    sensitive: bool = True


@dataclass(frozen=True, slots=True)
class IntegrationFeatureFlagDefinition:
    key: str
    label: str
    default_enabled: bool = False
    description: str = ""


@dataclass(slots=True)
class ResolvedIntegrationConfig:
    key: str
    label: str
    description: str
    category: str
    provider_key: str | None
    supports_shared_profile: bool
    compatible_profile_provider_keys: list[str]
    enabled: bool
    environment: IntegrationEnvironment
    runtime_connector: str
    feature_flags: dict[str, Any]
    credentials: dict[str, Any]
    credentials_masked: dict[str, Any]
    credential_source: str
    bootstrap_credentials_present: bool
    has_stored_credentials: bool
    updated_at: datetime | None
    updated_by: str | None
    credential_profile_id: str | None = None
    credential_profile_label: str | None = None
    credential_fields: list[IntegrationCredentialField] = field(default_factory=list)
    feature_flag_definitions: list[IntegrationFeatureFlagDefinition] = field(default_factory=list)
    validation_help: str | None = None


@dataclass(slots=True)
class ResolvedCredentialProfile:
    id: str
    provider_key: str
    label: str
    credentials_masked: dict[str, Any]
    updated_at: datetime | None
    updated_by: str | None
    usage_integration_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConnectionTestResult:
    ok: bool
    connector: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class BookingExecutionResult:
    provider: str
    provider_booking_ref: str | None
    provider_correlation_id: str | None
    status: str
    amount_charged: Any
    currency: str | None
    documents: dict[str, Any] | None = None
    loyalty_attached: dict[str, Any] | None = None
    loyalty_manual_followup: bool = False
    booked_at: datetime | None = None
    error_text: str | None = None
    cancellation_policy_snapshot: dict[str, Any] | None = None
    ticketing_state: str | None = None
    provider_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class CancellationExecutionResult:
    status: CancellationStatus
    refund_expected: Any
    refund_received: Any
    currency: str | None
    resolved_at: datetime | None
    provider_correlation_id: str | None = None
    provider_payload: dict[str, Any] | None = None


class FlightConnector(Protocol):
    @property
    def connector_name(self) -> str: ...

    def search_flights(self, *, watch: TripWatch) -> list[dict[str, Any]]: ...

    def test_connection(self) -> ConnectionTestResult: ...


class HotelConnector(Protocol):
    @property
    def connector_name(self) -> str: ...

    def search_hotels(self, *, watch: TripWatch) -> list[dict[str, Any]]: ...

    def search_cars(self, *, watch: TripWatch) -> list[dict[str, Any]]: ...

    def test_connection(self) -> ConnectionTestResult: ...


class BookingConnector(Protocol):
    @property
    def connector_name(self) -> str: ...

    def book_deal(
        self,
        *,
        deal: Deal,
        watch: TripWatch,
        payment_method: PaymentMethod,
        booked_at: datetime,
    ) -> BookingExecutionResult: ...

    def cancel_booking(
        self,
        *,
        booking: Booking,
        deal: Deal,
        reason: str | None,
        requested_at: datetime,
    ) -> CancellationExecutionResult: ...

    def test_connection(self) -> ConnectionTestResult: ...


class NotificationConnector(Protocol):
    @property
    def connector_name(self) -> str: ...

    def send_test_notification(self, *, actor_email: str) -> dict[str, Any]: ...

    def send(
        self,
        *,
        destination: str,
        subject: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def test_connection(self) -> ConnectionTestResult: ...


class CalendarConnector(Protocol):
    @property
    def connector_name(self) -> str: ...

    def create_event(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime | None,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def cancel_event(self, *, event_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def test_connection(self) -> ConnectionTestResult: ...
