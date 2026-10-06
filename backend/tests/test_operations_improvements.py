# ruff: noqa: E402
from __future__ import annotations

import os

os.environ.setdefault(
    "APP_SECRET",
    "test-master-secret-with-more-than-thirty-two-bytes",
)
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PUBLIC_BASE_URL", "https://travel-watch.test")

import asyncio
import json
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest
from starlette.responses import Response

import app.integrations.amadeus as amadeus
from app.api.deps import clear_session_cookie, set_session_cookie
from app.api.routes.health import healthcheck
from app.booking_service import simulated_connector_blocks_live_deal
from app.config import get_settings
from app.db.models import IntegrationEnvironment, RefreshInterval, TripMode, TripWatch
from app.integrations.amadeus import (
    AmadeusSearchError,
    clear_token_cache,
    count_passengers,
    resolve_amadeus_base_url,
    search_flight_offers,
)
from app.integrations.connectors import LocalFlightConnector
from app.integrations.service import runtime_connector_is_simulated, source_is_simulated
from app.integrations.types import ResolvedIntegrationConfig
from app.notification_service import _in_quiet_hours, next_quiet_hours_end
from app.scheduler.cadence import claim_refresh_lease, watch_refresh_is_due
from app.scheduler.celery_app import celery_app


def _configure_settings(monkeypatch: pytest.MonkeyPatch, *, environment: str = "local") -> None:
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv(
        "APP_SECRET",
        "test-master-secret-with-more-than-thirty-two-bytes",
    )
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://travel-watch.test")
    get_settings.cache_clear()


def _watch() -> TripWatch:
    return TripWatch(
        id=uuid4(),
        user_id=uuid4(),
        trip_mode=TripMode.FLIGHTS_ONLY,
        origin_iatas=["HND"],
        destination_iatas=["SIN"],
        depart_date_from=datetime(2027, 4, 12, tzinfo=UTC).date(),
        return_date_from=datetime(2027, 4, 19, tzinfo=UTC).date(),
        cabin_class="business",
        budget_currency="JPY",
    )


def test_session_cookie_is_secure_outside_local(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch, environment="production")
    response = Response()
    set_session_cookie(
        response=response,
        token="session-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert "secure" in response.headers["set-cookie"].lower()

    _configure_settings(monkeypatch, environment="local")
    local_response = Response()
    set_session_cookie(
        response=local_response,
        token="session-token",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    assert "secure" not in local_response.headers["set-cookie"].lower()

    _configure_settings(monkeypatch, environment="production")
    cleared = Response()
    clear_session_cookie(cleared)
    cleared_cookie = cleared.headers["set-cookie"].lower()
    assert "secure" in cleared_cookie
    assert "max-age=0" in cleared_cookie


def test_public_health_hides_integration_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure_settings(monkeypatch)

    class Session:
        def execute(self, *_args, **_kwargs):
            return None

        def close(self) -> None:
            return None

    class RedisClient:
        def ping(self) -> bool:
            return True

    monkeypatch.setattr("app.api.routes.health.SessionLocal", lambda: Session())
    monkeypatch.setattr("app.api.routes.health.get_mock_data_enabled", lambda **_kwargs: False)
    monkeypatch.setattr("app.api.routes.health.live_inventory_available", lambda **_kwargs: True)
    monkeypatch.setattr("redis.Redis.from_url", lambda *_args, **_kwargs: RedisClient())

    payload = asyncio.run(healthcheck())

    assert payload["checks"]["database"] is True
    assert payload["checks"]["inventory_mode"] == "live"
    assert "integrations" not in payload["checks"]
    assert "key_unlock_mode" not in payload["checks"]
    assert "master_key_source" not in payload["checks"]


def test_quiet_hours_timezone_must_be_a_real_zone() -> None:
    from app.api.schemas.profile import UserPreferenceUpsertRequest

    saved = UserPreferenceUpsertRequest(quiet_hours_timezone="  Asia/Tokyo  ")
    assert saved.quiet_hours_timezone == "Asia/Tokyo"
    with pytest.raises(ValueError, match="IANA timezone"):
        UserPreferenceUpsertRequest(quiet_hours_timezone="Not/AZone")


def test_quiet_hours_follow_the_saved_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    class Preference:
        quiet_hours_start = time(22, 0)
        quiet_hours_end = time(7, 0)
        quiet_hours_timezone = "Asia/Tokyo"

    class Session:
        def scalar(self, _statement):
            return Preference()

    class User:
        id = uuid4()

    class Clock:
        @staticmethod
        def now(_tz=None):
            return datetime(2026, 10, 6, 13, 0, tzinfo=UTC)

    assert next_quiet_hours_end(
        start=time(22, 0),
        end=time(7, 0),
        now=datetime(2026, 10, 6, 13, 0, tzinfo=UTC),
        timezone_name="Asia/Tokyo",
    ) == datetime(2026, 10, 6, 22, 0, tzinfo=UTC)
    monkeypatch.setattr("app.notification_service.datetime", Clock)
    assert _in_quiet_hours(db=Session(), user=User()) is True


def test_quiet_hours_end_is_the_next_open_moment() -> None:
    midday = datetime(2026, 10, 6, 13, 0, tzinfo=UTC)
    assert next_quiet_hours_end(start=time(12, 0), end=time(14, 0), now=midday) == datetime(
        2026, 10, 6, 14, 0, tzinfo=UTC
    )
    evening = datetime(2026, 10, 6, 23, 0, tzinfo=UTC)
    assert next_quiet_hours_end(start=time(22, 0), end=time(7, 0), now=evening) == datetime(
        2026, 10, 7, 7, 0, tzinfo=UTC
    )


def test_quiet_hours_release_the_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    class Preference:
        quiet_hours_start = time(9, 0)
        quiet_hours_end = time(10, 0)

    class Session:
        def scalar(self, _statement):
            return Preference()

    class User:
        id = uuid4()

    class Clock:
        @staticmethod
        def now(_tz=None):
            return datetime(2026, 10, 6, 10, 0, tzinfo=UTC)

    monkeypatch.setattr("app.notification_service.datetime", Clock)
    assert _in_quiet_hours(db=Session(), user=User()) is False


def test_watch_refresh_follows_the_stored_interval() -> None:
    created = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
    assert watch_refresh_is_due(
        interval=RefreshInterval.HOURLY,
        last_observed_at=created,
        created_at=created,
        now=created + timedelta(minutes=59),
    ) is False
    assert watch_refresh_is_due(
        interval=RefreshInterval.HOURLY,
        last_observed_at=created,
        created_at=created,
        now=created + timedelta(hours=1),
    ) is True
    assert watch_refresh_is_due(
        interval=RefreshInterval.DAILY,
        last_observed_at=None,
        created_at=None,
        now=created,
    ) is True


def test_simulated_booking_connector_blocks_a_live_deal() -> None:
    assert simulated_connector_blocks_live_deal(
        deal_source="amadeus",
        connector_name="local-safe-booking",
    )
    assert (
        simulated_connector_blocks_live_deal(
            deal_source="mock-amadeus",
            connector_name="local-safe-booking",
        )
        is False
    )


def test_beat_schedule_runs_refresh_and_deferred_delivery() -> None:
    schedule = celery_app.conf.beat_schedule
    assert schedule["refresh-due-watches"]["task"] == "travel_watch.refresh_due_watches"
    assert schedule["deliver-deferred-notifications"]["task"] == (
        "travel_watch.deliver_deferred_notifications"
    )


def test_live_amadeus_search_uses_the_injected_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_token_cache()
    calls: list[str] = []

    def fake_request(request, timeout=20):
        calls.append(request.full_url)
        if request.full_url.endswith("/oauth2/token"):
            return 200, json.dumps({"access_token": "token-1", "expires_in": 1800}).encode()
        return 200, json.dumps(
            {
                "data": [
                    {
                        "id": "offer-1",
                        "price": {"currency": "JPY", "total": "120000.00", "base": "100000.00"},
                        "pricingOptions": {"refundableFare": False},
                        "itineraries": [
                            {
                                "duration": "PT7H10M",
                                "segments": [
                                    {
                                        "carrierCode": "NH",
                                        "departure": {"iataCode": "HND"},
                                        "arrival": {"iataCode": "SIN"},
                                    }
                                ],
                            }
                        ],
                        "travelerPricings": [
                            {"fareDetailsBySegment": [{"cabin": "BUSINESS"}]}
                        ],
                    }
                ]
            }
        ).encode()

    monkeypatch.setattr(amadeus, "perform_request", fake_request)
    offers = search_flight_offers(
        credentials={"client_id": "id", "client_secret": "secret"},
        watch=_watch(),
    )

    assert len(calls) == 2
    assert calls[0].startswith("https://test.api.amadeus.com/v1/security/oauth2/token")
    assert "flight-offers" in calls[1]
    assert offers[0]["source"] == "amadeus"
    assert offers[0]["simulated"] is False
    assert source_is_simulated(str(offers[0]["source"])) is False
    assert runtime_connector_is_simulated("amadeus") is False
    assert offers[0]["supplier"] == "NH"
    assert offers[0]["duration_minutes"] == 430


def test_amadeus_base_url_rejects_unofficial_hosts() -> None:
    with pytest.raises(AmadeusSearchError):
        resolve_amadeus_base_url({"api_base": "https://example.com"})


def test_live_flight_connector_does_not_emit_mock_offers(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_token_cache()
    def fake_request(request, timeout=20):
        if request.full_url.endswith("/token"):
            return 200, json.dumps({"access_token": "token-1", "expires_in": 60}).encode()
        return 200, json.dumps({"data": []}).encode()

    monkeypatch.setattr(amadeus, "perform_request", fake_request)
    connector = LocalFlightConnector(
        config=ResolvedIntegrationConfig(
            key="flights_amadeus",
            label="Amadeus",
            description="Live Amadeus",
            category="flights",
            provider_key="amadeus",
            supports_shared_profile=True,
            compatible_profile_provider_keys=["amadeus"],
            enabled=True,
            environment=IntegrationEnvironment.LIVE,
            runtime_connector="amadeus",
            feature_flags={},
            credentials={"client_id": "id", "client_secret": "secret"},
            credentials_masked={},
            credential_source="stored_override",
            bootstrap_credentials_present=False,
            has_stored_credentials=True,
            updated_at=None,
            updated_by=None,
            credential_fields=[],
            feature_flag_definitions=[],
            validation_help=None,
        )
    )

    assert connector.search_flights(watch=_watch()) == []
    result = connector.test_connection()
    assert result.ok is True
    assert result.detail["network_request_made"] is True


def test_passenger_counts_follow_age_on_departure() -> None:
    adults, children, infants = count_passengers(
        [date(1980, 1, 1), date(2018, 6, 1), date(2026, 5, 1)],
        on_date=date(2027, 4, 12),
    )
    assert (adults, children, infants) == (1, 1, 1)


def test_amadeus_search_rejects_a_bad_airport_before_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_request(request, timeout=20):
        raise AssertionError(request.full_url)

    monkeypatch.setattr(amadeus, "perform_request", fail_request)
    watch = _watch()
    watch.origin_iatas = ["TOKYO"]
    with pytest.raises(AmadeusSearchError, match="origin airport"):
        search_flight_offers(
            credentials={"client_id": "id", "client_secret": "secret"},
            watch=watch,
        )


def test_refresh_lease_blocks_a_second_claim() -> None:
    class Store:
        def __init__(self) -> None:
            self.keys: set[str] = set()

        def set(self, name: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
            if nx and name in self.keys:
                return False
            self.keys.add(name)
            return True

    store = Store()
    assert claim_refresh_lease(store, watch_id="watch-1", ttl_seconds=30) is True
    assert claim_refresh_lease(store, watch_id="watch-1", ttl_seconds=30) is False
