from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.db.models import ObservationKind, TripWatch
from app.integrations.types import (
    ConnectionTestResult,
    ProviderSearchError,
    ResolvedIntegrationConfig,
)

AMADEUS_HOSTS = {"test.api.amadeus.com", "api.amadeus.com"}
DEFAULT_AMADEUS_BASE = "https://test.api.amadeus.com"
MAX_RESPONSE_BYTES = 1_000_000
_TOKEN_CACHE: dict[str, tuple[str, datetime]] = {}
_TOKEN_LOCK = threading.Lock()
_IATA = re.compile(r"^[A-Z]{3}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class AmadeusSearchError(ProviderSearchError):
    """Amadeus rejected or could not complete a flight search."""


def clear_token_cache() -> None:
    with _TOKEN_LOCK:
        _TOKEN_CACHE.clear()


def count_passengers(dates_of_birth: list[date], *, on_date: date) -> tuple[int, int, int]:
    """Split travelers into Amadeus adult, child, and infant counts."""
    adults = 0
    children = 0
    infants = 0
    for dob in dates_of_birth:
        age = _age_on(dob, on_date)
        if age < 2:
            infants += 1
        elif age < 12:
            children += 1
        else:
            adults += 1
    if adults == 0:
        adults = 1
    adults = min(adults, 9)
    children = min(children, 9)
    infants = min(infants, adults)
    return adults, children, infants


def resolve_amadeus_base_url(credentials: dict[str, Any]) -> str:
    raw = str(credentials.get("api_base") or DEFAULT_AMADEUS_BASE).strip()
    if not raw:
        raw = DEFAULT_AMADEUS_BASE
    parsed = urlparse(raw)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in AMADEUS_HOSTS
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.params
        or parsed.fragment
    ):
        raise AmadeusSearchError(
            "Amadeus API base must be https://test.api.amadeus.com or https://api.amadeus.com."
        )
    return f"https://{parsed.hostname}"


def search_flight_offers(
    *,
    credentials: dict[str, Any],
    watch: TripWatch,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
) -> list[dict[str, Any]]:
    query = _search_query(
        watch,
        adults=max(adults, 1),
        children=max(children, 0),
        infants=max(infants, 0),
    )
    base_url = resolve_amadeus_base_url(credentials)
    token = _access_token(credentials=credentials, base_url=base_url)
    status, body = perform_request(
        Request(
            f"{base_url}/v2/shopping/flight-offers?{urlencode(query)}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            method="GET",
        )
    )
    payload = _decode_payload(status=status, body=body)
    offers = payload.get("data")
    if not isinstance(offers, list):
        return []
    return [
        mapped
        for offer in offers[:8]
        if isinstance(offer, dict)
        for mapped in [_map_offer(offer=offer, watch=watch)]
        if mapped is not None
    ]


def test_amadeus_credentials(*, config: ResolvedIntegrationConfig) -> ConnectionTestResult:
    warnings: list[str] = []
    try:
        base_url = resolve_amadeus_base_url(config.credentials)
        _access_token(credentials=config.credentials, base_url=base_url)
    except AmadeusSearchError as exc:
        return ConnectionTestResult(
            ok=False,
            connector=config.runtime_connector,
            message=str(exc),
            detail={
                "integration_key": config.key,
                "environment": config.environment.value,
                "check_type": "amadeus_token",
                "network_request_made": True,
            },
            warnings=warnings,
            checked_at=datetime.now(UTC),
        )
    if base_url == DEFAULT_AMADEUS_BASE:
        warnings.append(
            "The token was accepted by the Amadeus test host. Production search uses https://api.amadeus.com."
        )
    return ConnectionTestResult(
        ok=True,
        connector=config.runtime_connector,
        message="Amadeus accepted the client credentials.",
        detail={
            "integration_key": config.key,
            "environment": config.environment.value,
            "check_type": "amadeus_token",
            "network_request_made": True,
            "api_base": base_url,
        },
        warnings=warnings,
        checked_at=datetime.now(UTC),
    )


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise AmadeusSearchError("Amadeus redirected the request.")


def perform_request(request: Request, timeout: float = 20) -> tuple[int, bytes]:
    opener = build_opener(_RejectRedirects)
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status), _read_limited(response)
    except AmadeusSearchError:
        raise
    except HTTPError as exc:
        return int(exc.code), _read_limited(exc)
    except (URLError, TimeoutError, OSError) as exc:
        raise AmadeusSearchError("Amadeus could not be reached.") from exc


def _access_token(*, credentials: dict[str, Any], base_url: str) -> str:
    client_id = str(credentials.get("client_id") or "").strip()
    client_secret = str(credentials.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise AmadeusSearchError("Amadeus client id and client secret are required.")
    cache_key = _token_cache_key(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
    )
    with _TOKEN_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached and cached[1] > datetime.now(UTC):
            return cached[0]

    form = urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode("utf-8")
    status, body = perform_request(
        Request(
            f"{base_url}/v1/security/oauth2/token",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
    )
    payload = _decode_payload(status=status, body=body)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise AmadeusSearchError("Amadeus did not return an access token.")
    try:
        expires_in = int(payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0
    lifetime = max(expires_in - 60, 30)
    with _TOKEN_LOCK:
        _TOKEN_CACHE[cache_key] = (token, datetime.now(UTC) + timedelta(seconds=lifetime))
    return token


def _decode_payload(*, status: int, body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AmadeusSearchError("Amadeus returned an unreadable response.") from exc
    if not isinstance(payload, dict):
        raise AmadeusSearchError("Amadeus returned an unexpected response.")
    if status >= 400:
        raise AmadeusSearchError(_error_detail(payload))
    return payload


def _error_detail(payload: dict[str, Any]) -> str:
    errors = payload.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        detail = errors[0].get("detail") or errors[0].get("title")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()[:300]
    return "Amadeus rejected the request."


def _search_query(
    watch: TripWatch,
    *,
    adults: int,
    children: int,
    infants: int,
) -> dict[str, str]:
    adults = min(max(adults, 1), 9)
    children = min(max(children, 0), 9)
    infants = min(max(infants, 0), adults)
    origins = [
        code for code in (_airport_code(code) for code in (watch.origin_iatas or [])) if code
    ]
    destinations = [
        code for code in (_airport_code(code) for code in (watch.destination_iatas or [])) if code
    ]
    departure = watch.depart_date_from or watch.depart_date_to
    if not origins or not destinations or departure is None:
        raise AmadeusSearchError(
            "Amadeus search needs an origin airport, a destination airport, and a departure date."
        )
    return_date = watch.return_date_from or watch.return_date_to
    if return_date is not None and return_date < departure:
        raise AmadeusSearchError("The return date is before the departure date.")
    currency = (watch.budget_currency or "USD").upper()
    if _CURRENCY.fullmatch(currency) is None:
        currency = "USD"
    query = {
        "originLocationCode": origins[0],
        "destinationLocationCode": destinations[0],
        "departureDate": departure.isoformat(),
        "adults": str(adults),
        "max": "8",
        "currencyCode": currency,
    }
    if children:
        query["children"] = str(children)
    if infants:
        query["infants"] = str(infants)
    travel_class = _travel_class(watch.cabin_class)
    if travel_class:
        query["travelClass"] = travel_class
    if return_date is not None:
        query["returnDate"] = return_date.isoformat()
    if watch.max_stops == 0:
        query["nonStop"] = "true"
    return query


def _travel_class(cabin: str | None) -> str | None:
    normalized = (cabin or "").replace("_", " ").strip().lower()
    return {
        "economy": "ECONOMY",
        "premium economy": "PREMIUM_ECONOMY",
        "business": "BUSINESS",
        "first": "FIRST",
    }.get(normalized)


def _map_offer(*, offer: dict[str, Any], watch: TripWatch) -> dict[str, Any] | None:
    itineraries = offer.get("itineraries")
    if not isinstance(itineraries, list) or not itineraries or not isinstance(itineraries[0], dict):
        return None
    segments = itineraries[0].get("segments")
    if not isinstance(segments, list) or not segments or not isinstance(segments[0], dict):
        return None
    price = offer.get("price") if isinstance(offer.get("price"), dict) else {}
    currency = str(price.get("currency") or watch.budget_currency or "USD")
    total = _decimal(price.get("total"))
    base = _decimal(price.get("base"))
    if total <= 0 and base <= 0:
        return None
    if base <= 0:
        base = total
        tax = Decimal("0")
    else:
        tax = total - base if total > base else Decimal("0")
        if total <= 0:
            total = base
    first_segment = segments[0]
    last_segment = segments[-1] if isinstance(segments[-1], dict) else first_segment
    origin = str(
        (first_segment.get("departure") or {}).get("iataCode") or (watch.origin_iatas or [""])[0]
    )
    destination = str(
        (last_segment.get("arrival") or {}).get("iataCode") or (watch.destination_iatas or [""])[0]
    )
    carrier = str(first_segment.get("carrierCode") or "Amadeus")
    cabin = _offer_cabin(offer) or (watch.cabin_class or "economy")
    cabin_label = cabin.replace("_", " ")
    stops = max(len(segments) - 1, 0)
    offer_id = str(offer.get("id") or f"{origin}-{destination}-{carrier}")
    route_key = f"{origin}-{destination}:{offer_id}"
    duration = _iso_duration_minutes(str(itineraries[0].get("duration") or ""))
    refundable = bool((price.get("refundableFare")) or False)
    pricing_options = offer.get("pricingOptions")
    if isinstance(pricing_options, dict):
        refundable = bool(pricing_options.get("refundableFare"))
    return {
        "kind": ObservationKind.FLIGHT.value,
        "source": "amadeus",
        "supplier": carrier,
        "currency": currency,
        "title": f"{origin} -> {destination} {cabin_label.title()}",
        "route_key": route_key,
        "scope_key": f"{origin}-{destination}:{cabin_label.lower().replace(' ', '_')}",
        "depart_key": str(watch.depart_date_from or watch.depart_date_to or ""),
        "return_key": str(watch.return_date_from or watch.return_date_to or ""),
        "cabin": cabin_label.lower(),
        "airline_code": carrier,
        "base_amount": base,
        "tax_amount": tax,
        "fee_amount": Decimal("0"),
        "bag_amount": Decimal("0"),
        "other_amount": Decimal("0"),
        "stops": stops,
        "duration_minutes": duration,
        "refundable": refundable,
        "simulated": False,
        "attributes": [
            "nonstop" if stops == 0 else f"{stops}-stop",
            cabin_label.lower(),
            "amadeus",
        ],
    }


def _offer_cabin(offer: dict[str, Any]) -> str | None:
    pricings = offer.get("travelerPricings")
    if not isinstance(pricings, list) or not pricings or not isinstance(pricings[0], dict):
        return None
    details = pricings[0].get("fareDetailsBySegment")
    if not isinstance(details, list) or not details or not isinstance(details[0], dict):
        return None
    cabin = details[0].get("cabin")
    return str(cabin).lower() if isinstance(cabin, str) and cabin.strip() else None


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _iso_duration_minutes(value: str) -> int | None:
    match = re.fullmatch(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?", value)
    if match is None:
        return None
    total = (
        int(match.group(1) or 0) * 24 * 60
        + int(match.group(2) or 0) * 60
        + int(match.group(3) or 0)
    )
    return total or None


def _age_on(dob: date, on_date: date) -> int:
    years = on_date.year - dob.year
    if (on_date.month, on_date.day) < (dob.month, dob.day):
        years -= 1
    return years


def _airport_code(value: object) -> str:
    code = str(value or "").strip().upper()
    return code if _IATA.fullmatch(code) else ""


def _token_cache_key(*, base_url: str, client_id: str, client_secret: str) -> str:
    digest = hashlib.sha256(client_secret.encode("utf-8")).hexdigest()[:16]
    return f"{base_url}:{client_id}:{digest}"


def _read_limited(response: Any, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining > 0:
        chunk = response.read(min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    if len(body) > limit:
        raise AmadeusSearchError("Amadeus returned a response that is too large.")
    return body
