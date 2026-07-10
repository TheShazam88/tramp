from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import smtplib
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.db.models import (
    Booking,
    CancellationStatus,
    Deal,
    IntegrationEnvironment,
    ObservationKind,
    PaymentMethod,
    TripWatch,
)
from app.integrations.types import (
    BookingExecutionResult,
    CalendarConnector,
    CancellationExecutionResult,
    ConnectionTestResult,
    ResolvedIntegrationConfig,
)
from app.watch_mock_adapter import (
    DeterministicMockAdapter,
)

FLIGHT_SOURCE_BY_INTEGRATION_KEY = {
    "flights_amadeus": "mock-amadeus",
    "flights_duffel": "mock-duffel",
    "flights_kiwi": "mock-kiwi",
}


def _build_test_result(
    *,
    config: ResolvedIntegrationConfig,
    capability: str,
) -> ConnectionTestResult:
    warnings: list[str] = []
    if config.environment == IntegrationEnvironment.LIVE:
        warnings.append(
            "Live mode is selected, but runtime still uses a safe local/test connector in v1."
        )
    if not config.credentials:
        warnings.append(
            "No provider credentials are configured; the safe local connector remains usable."
        )
    return ConnectionTestResult(
        ok=True,
        connector=config.runtime_connector,
        message=f"{capability} connector is ready for safe local/test execution.",
        detail={
            "integration_key": config.key,
            "environment": config.environment.value,
            "credential_source": config.credential_source,
            "credential_keys": sorted(config.credentials.keys()),
            "feature_flags": config.feature_flags,
            "simulated": True,
        },
        warnings=warnings,
        checked_at=datetime.now(UTC),
    )


@dataclass(slots=True)
class LocalFlightConnector:
    config: ResolvedIntegrationConfig

    @property
    def connector_name(self) -> str:
        return self.config.runtime_connector

    def search_flights(self, *, watch: TripWatch) -> list[dict[str, Any]]:
        offers = [
            offer
            for offer in DeterministicMockAdapter().search(watch=watch)
            if offer.get("kind") == ObservationKind.FLIGHT.value
        ]
        expected_source = FLIGHT_SOURCE_BY_INTEGRATION_KEY.get(self.config.key)
        if not expected_source:
            return offers
        return [offer for offer in offers if offer.get("source") == expected_source]

    def test_connection(self) -> ConnectionTestResult:
        return _build_test_result(config=self.config, capability="Flight search")


@dataclass(slots=True)
class LocalHotelConnector:
    config: ResolvedIntegrationConfig

    @property
    def connector_name(self) -> str:
        return self.config.runtime_connector

    def search_hotels(self, *, watch: TripWatch) -> list[dict[str, Any]]:
        return [
            offer
            for offer in DeterministicMockAdapter().search(watch=watch)
            if offer.get("kind") == ObservationKind.HOTEL.value
        ]

    def search_cars(self, *, watch: TripWatch) -> list[dict[str, Any]]:
        return [
            offer
            for offer in DeterministicMockAdapter().search(watch=watch)
            if offer.get("kind") == ObservationKind.CAR.value
        ]

    def test_connection(self) -> ConnectionTestResult:
        return _build_test_result(config=self.config, capability="Hotel search")


@dataclass(slots=True)
class LocalBookingConnector:
    config: ResolvedIntegrationConfig

    @property
    def connector_name(self) -> str:
        return self.config.runtime_connector

    def book_deal(
        self,
        *,
        deal: Deal,
        watch: TripWatch,
        payment_method: PaymentMethod,
        booked_at: datetime,
    ) -> BookingExecutionResult:
        result = DeterministicMockAdapter().book_deal(
            deal=deal,
            watch=watch,
            payment_method=payment_method,
            booked_at=booked_at,
        )
        return BookingExecutionResult(
            provider=result.provider,
            provider_booking_ref=result.provider_booking_ref,
            provider_correlation_id=f"{result.provider}:{result.provider_booking_ref}",
            status=result.status.value,
            amount_charged=result.amount_charged,
            currency=result.currency,
            documents=result.documents,
            loyalty_attached=result.loyalty_attached,
            loyalty_manual_followup=result.loyalty_manual_followup,
            booked_at=result.booked_at,
            error_text=getattr(result, "error_text", None),
            cancellation_policy_snapshot={"mode": "mock", "refundable": True},
            ticketing_state=result.status.value,
            provider_payload={"simulated": True, "connector": self.connector_name},
        )

    def cancel_booking(
        self,
        *,
        booking: Booking,
        deal: Deal,
        reason: str | None,
        requested_at: datetime,
    ) -> CancellationExecutionResult:
        result = DeterministicMockAdapter().cancel_booking(
            booking=booking,
            deal=deal,
            reason=reason,
            requested_at=requested_at,
        )
        return CancellationExecutionResult(
            status=result.status,
            refund_expected=result.refund_expected,
            refund_received=result.refund_received,
            currency=result.currency,
            resolved_at=result.resolved_at,
            provider_correlation_id=f"{booking.provider}:{booking.provider_booking_ref}",
            provider_payload={"simulated": True, "connector": self.connector_name},
        )

    def test_connection(self) -> ConnectionTestResult:
        return _build_test_result(config=self.config, capability="Booking")


@dataclass(slots=True)
class LocalNotificationConnector:
    config: ResolvedIntegrationConfig

    @property
    def connector_name(self) -> str:
        return self.config.runtime_connector

    def send_test_notification(self, *, actor_email: str) -> dict[str, Any]:
        return {
            "channel": self._mode(),
            "actor_email": actor_email,
            "connector": self.connector_name,
            "simulated": True,
        }

    def send(
        self,
        *,
        destination: str,
        subject: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mode = self._mode()
        if mode == "smtp_dev":
            host = str(self.config.credentials.get("smtp_host") or "localhost")
            port = int(str(self.config.credentials.get("smtp_port") or "1025"))
            sender = str(
                self.config.credentials.get("smtp_from_address") or "alerts@tramp.local"
            )
            username = str(self.config.credentials.get("smtp_username") or "")
            password = str(self.config.credentials.get("smtp_password") or "")
            with smtplib.SMTP(host=host, port=port, timeout=5) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.sendmail(
                    sender,
                    [destination],
                    f"Subject: {subject}\nFrom: {sender}\nTo: {destination}\n\n{body}",
                )
            return {
                "channel": "email",
                "transport": mode,
                "destination": destination,
                "metadata": metadata or {},
            }

        if mode == "telegram_bot":
            token = str(self.config.credentials.get("telegram_bot_token") or "")
            if not token:
                raise ValueError("telegram_bot_token is required for Telegram delivery.")
            payload = {
                "chat_id": destination,
                "text": f"{subject}\n\n{body}",
                "disable_web_page_preview": True,
            }
            request = Request(
                url=f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                raw = json.loads(response.read().decode("utf-8"))
            return {
                "channel": "telegram",
                "transport": mode,
                "destination": destination,
                "metadata": metadata or {},
                "response": raw,
            }

        return {
            "channel": "log_only",
            "transport": mode,
            "destination": destination,
            "subject": subject,
            "body": body,
            "metadata": metadata or {},
            "simulated": True,
        }

    def test_connection(self) -> ConnectionTestResult:
        preview = self.send_test_notification(actor_email="admin@travel-watch.local")
        result = _build_test_result(config=self.config, capability="Notification")
        result.detail["preview"] = preview
        return result

    def _mode(self) -> str:
        return str(self.config.credentials.get("delivery_mode") or "log_only").strip().lower()


@dataclass(slots=True)
class LocalCalendarConnector(CalendarConnector):
    config: ResolvedIntegrationConfig

    @property
    def connector_name(self) -> str:
        return self.config.runtime_connector

    def create_event(
        self,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime | None,
        description: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        mode = self._mode()
        if mode != "google_calendar":
            synthetic_id = f"logonly-{int(starts_at.timestamp())}"
            return {
                "event_id": synthetic_id,
                "transport": mode,
                "simulated": True,
                "title": title,
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat() if ends_at else None,
                "description": description,
                "metadata": metadata or {},
            }

        payload = {
            "summary": title,
            "description": description,
            "start": {"dateTime": starts_at.isoformat()},
            "end": {"dateTime": (ends_at or starts_at).isoformat()},
        }
        request = Request(
            url=f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id()}/events",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return {
            "event_id": raw.get("id"),
            "transport": mode,
            "response": raw,
        }

    def cancel_event(self, *, event_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        mode = self._mode()
        if mode != "google_calendar":
            return {
                "event_id": event_id,
                "transport": mode,
                "simulated": True,
                "metadata": metadata or {},
            }

        request = Request(
            url=f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id()}/events/{event_id}",
            headers=self._headers(),
            method="DELETE",
        )
        with urlopen(request, timeout=10):
            return {
                "event_id": event_id,
                "transport": mode,
                "metadata": metadata or {},
            }

    def test_connection(self) -> ConnectionTestResult:
        mode = self._mode()
        if mode != "google_calendar":
            result = _build_test_result(config=self.config, capability="Calendar")
            result.detail["mode"] = mode
            return result
        try:
            request = Request(
                url=f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id()}",
                headers=self._headers(),
                method="GET",
            )
            with urlopen(request, timeout=10) as response:
                raw = json.loads(response.read().decode("utf-8"))
            return ConnectionTestResult(
                ok=True,
                connector=self.connector_name,
                message="Calendar connector is reachable.",
                detail={"calendar_id": self._calendar_id(), "summary": raw.get("summary")},
            )
        except (HTTPError, URLError, ValueError) as exc:
            return ConnectionTestResult(
                ok=False,
                connector=self.connector_name,
                message="Calendar connector needs attention.",
                detail={"error": str(exc)},
            )

    def _mode(self) -> str:
        return str(self.config.credentials.get("delivery_mode") or "log_only").strip().lower()

    def _calendar_id(self) -> str:
        return str(self.config.credentials.get("calendar_id") or "primary")

    def _headers(self) -> dict[str, str]:
        token = str(self.config.credentials.get("access_token") or "")
        if not token:
            raise ValueError("access_token is required for google_calendar mode.")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
