from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import (
    Booking,
    BookingStatus,
    CancellationStatus,
    Deal,
    DestinationMode,
    ObservationKind,
    PaymentMethod,
    TripMode,
    TripWatch,
)


@dataclass(slots=True)
class MockBookingResult:
    provider: str
    provider_booking_ref: str
    status: BookingStatus
    amount_charged: Decimal
    currency: str
    documents: dict[str, object]
    loyalty_attached: dict[str, object]
    loyalty_manual_followup: bool
    booked_at: datetime


@dataclass(slots=True)
class MockCancellationResult:
    status: CancellationStatus
    refund_expected: Decimal
    refund_received: Decimal
    currency: str
    resolved_at: datetime


class DeterministicMockAdapter:
    def search(self, *, watch: TripWatch) -> list[dict[str, object]]:
        rng = random.Random(_seed_for_watch(watch))
        offers: list[dict[str, object]] = []

        if watch.trip_mode != TripMode.HOTELS_ONLY:
            offers.extend(_build_flight_offers(watch=watch, rng=rng))
        if watch.trip_mode != TripMode.FLIGHTS_ONLY:
            offers.extend(_build_hotel_offers(watch=watch, rng=rng))
        if watch.want_car:
            offers.append(_build_car_offer(watch=watch, rng=rng))
        return offers

    def book_deal(
        self,
        *,
        deal: Deal,
        watch: TripWatch,
        payment_method: PaymentMethod,
        booked_at: datetime,
        idempotency_key: str,
    ) -> MockBookingResult:
        digest = hashlib.sha256(
            "|".join(
                [
                    str(deal.id),
                    deal.fingerprint_hash,
                    str(payment_method.id),
                    payment_method.last4 or "",
                    idempotency_key,
                ]
            ).encode("utf-8")
        ).hexdigest()
        provider = _provider_name_for_source(deal.source)
        provider_booking_ref = f"TB-{digest[:12].upper()}"
        ticket_ref = f"ETKT-{digest[12:22].upper()}"
        booking_status = (
            BookingStatus.TICKETED
            if deal.kind in {"flight", "trip_bundle"}
            else BookingStatus.BOOKED
        )
        loyalty_plan = list(deal.loyalty_plan_json or [])
        return MockBookingResult(
            provider=provider,
            provider_booking_ref=provider_booking_ref,
            status=booking_status,
            amount_charged=deal.total_price,
            currency=deal.currency,
            documents={
                "provider": provider,
                "confirmation_code": provider_booking_ref[-6:],
                "ticket_reference": ticket_ref,
                "route_summary": _watch_route_summary(watch),
                "trip_kind": deal.kind,
            },
            loyalty_attached={
                "plan": loyalty_plan,
                "payment_method_last4": payment_method.last4,
                "applied_at": booked_at.isoformat(),
            },
            loyalty_manual_followup=any(bool(entry.get("note")) for entry in loyalty_plan),
            booked_at=booked_at,
        )

    def cancel_booking(
        self,
        *,
        booking: Booking,
        deal: Deal,
        reason: str | None,
        requested_at: datetime,
    ) -> MockCancellationResult:
        refundable_flags = _refundable_flags_for_deal(deal)
        if refundable_flags and all(refundable_flags):
            refund_ratio = Decimal("1.00")
        elif any(refundable_flags):
            refund_ratio = Decimal("0.60")
        else:
            refund_ratio = Decimal("0.00")

        booked_amount = booking.amount_charged or deal.total_price
        refund_value = (booked_amount * refund_ratio).quantize(Decimal("0.01"))
        status = (
            CancellationStatus.REFUNDED
            if refund_value > 0
            else CancellationStatus.DENIED
        )
        if reason and "duplicate" in reason.lower():
            refund_value = booked_amount.quantize(Decimal("0.01"))
            status = CancellationStatus.REFUNDED

        return MockCancellationResult(
            status=status,
            refund_expected=refund_value,
            refund_received=(
                refund_value
                if status == CancellationStatus.REFUNDED
                else Decimal("0.00")
            ),
            currency=booking.currency or deal.currency,
            resolved_at=requested_at,
        )


def _seed_for_watch(watch: TripWatch) -> int:
    stable_key = "|".join(
        [
            str(watch.id),
            ",".join(sorted(watch.origin_iatas or [])),
            ",".join(sorted(watch.destination_iatas or [])),
            str(watch.destination_mode.value),
            str(watch.depart_date_from or ""),
            str(watch.depart_date_to or ""),
            str(watch.return_date_from or ""),
            str(watch.return_date_to or ""),
            str(watch.trip_mode.value),
            str(watch.cabin_class or ""),
        ]
    )
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _build_flight_offers(*, watch: TripWatch, rng: random.Random) -> list[dict[str, object]]:
    origins = watch.origin_iatas or ["HND"]
    destinations = _destination_labels(watch)
    route_key = f"{origins[0]}-{destinations[0]}"
    requested_cabin = (watch.cabin_class or "").replace("_", " ").strip().lower()
    cabin_sequence = (
        [requested_cabin or "economy"] * 4
        if requested_cabin
        else ["business", "premium economy", "economy", "economy"]
    )

    carriers = [
        ("NH", "ANA", "star"),
        ("SQ", "Singapore Airlines", "star"),
        ("JX", "STARLUX Airlines", "none"),
        ("JL", "JAL", "oneworld"),
        ("CX", "Cathay Pacific", "oneworld"),
    ]
    sources = ["mock-duffel", "mock-amadeus", "mock-kiwi", "mock-google-flights"]
    offers: list[dict[str, object]] = []
    for index in range(4):
        cabin = cabin_sequence[index % len(cabin_sequence)]
        airline_code, supplier, alliance = carriers[index % len(carriers)]
        base_amount = Decimal(185 + rng.randint(0, 120) + (index * 22))
        if "business" in cabin.lower():
            base_amount += Decimal("210")
        elif "first" in cabin.lower():
            base_amount += Decimal("320")
        elif "premium" in cabin.lower():
            base_amount += Decimal("70")
        taxes = Decimal(24 + rng.randint(0, 12))
        fees = Decimal(8 + index * 2)
        bags = Decimal(0 if index == 0 else 12)
        stops = 0 if index < 2 else 1
        duration_minutes = 410 + (index * 45) + rng.randint(0, 20)
        layover_minutes = 0 if stops == 0 else 75 + (index * 20)
        refundable = index % 2 == 0 or watch.prefer_refundable
        title = f"{origins[0]} -> {destinations[0]} {cabin.title()}"
        offers.append(
            {
                "kind": ObservationKind.FLIGHT.value,
                "source": sources[index % len(sources)],
                "supplier": supplier,
                "currency": watch.budget_currency or "USD",
                "title": title,
                "route_key": route_key,
                "scope_key": f"{route_key}:{cabin.lower().replace(' ', '_')}",
                "depart_key": str(watch.depart_date_from or watch.depart_date_to or ""),
                "return_key": str(watch.return_date_from or watch.return_date_to or ""),
                "cabin": cabin,
                "airline_code": airline_code,
                "alliance": alliance,
                "base_amount": base_amount,
                "tax_amount": taxes,
                "fee_amount": fees,
                "bag_amount": bags,
                "other_amount": Decimal("0"),
                "stops": stops,
                "layover_minutes": layover_minutes,
                "duration_minutes": duration_minutes,
                "refundable": refundable,
                "attributes": [
                    "nonstop" if stops == 0 else "one-stop",
                    "refundable" if refundable else "nonrefundable",
                    cabin.lower(),
                ],
            }
        )
    return offers


def _build_hotel_offers(*, watch: TripWatch, rng: random.Random) -> list[dict[str, object]]:
    destinations = _destination_labels(watch)
    sources = ["mock-booking", "mock-expedia", "mock-hotelbeds"]
    hotel_names = ["Harbor Grand", "City Lights Suites", "Garden Terrace", "Skyline House"]
    offers: list[dict[str, object]] = []
    for index in range(3):
        rating = round(3.9 + (index * 0.35) + rng.random() * 0.15, 1)
        base_amount = Decimal(120 + rng.randint(0, 35) + (index * 18))
        taxes = Decimal(18 + index * 3)
        refundable = index != 2 or watch.prefer_refundable
        hotel_chain = ["Marriott", "Hilton", "Hyatt"][index % 3]
        hotel_name = f"{destinations[0]} {hotel_names[index]}"
        offers.append(
            {
                "kind": ObservationKind.HOTEL.value,
                "source": sources[index % len(sources)],
                "supplier": sources[index % len(sources)].replace("mock-", "").title(),
                "currency": watch.budget_currency or "USD",
                "title": f"{hotel_name} nightly rate",
                "route_key": destinations[0],
                "scope_key": f"{destinations[0]}:hotel_area",
                "hotel_key": hotel_name.lower().replace(" ", "-"),
                "hotel_name": hotel_name,
                "hotel_chain": hotel_chain,
                "area_cluster": watch.flexible_region or destinations[0],
                "base_amount": base_amount,
                "tax_amount": taxes,
                "fee_amount": Decimal("0"),
                "bag_amount": Decimal("0"),
                "other_amount": Decimal("0"),
                "hotel_rating": rating,
                "preferred_brand_match": False,
                "refundable": refundable,
                "attributes": [
                    f"{rating:.1f}-stars",
                    "refundable" if refundable else "advance-purchase",
                    hotel_chain.lower(),
                ],
            }
        )
    return offers


def _build_car_offer(*, watch: TripWatch, rng: random.Random) -> dict[str, object]:
    destinations = _destination_labels(watch)
    daily_rate = Decimal(38 + rng.randint(0, 20))
    pickup_key = str(watch.depart_date_from or watch.depart_date_to or datetime.now(UTC).date())
    return {
        "kind": ObservationKind.CAR.value,
        "source": "mock-rentalcars",
        "supplier": "Rentalcars",
        "currency": watch.budget_currency or "USD",
        "title": f"{destinations[0]} standard rental",
        "route_key": destinations[0],
        "scope_key": f"{destinations[0]}:car",
        "depart_key": pickup_key,
        "base_amount": daily_rate * Decimal(max(watch.trip_min_nights or 3, 1)),
        "tax_amount": Decimal("22"),
        "fee_amount": Decimal("12"),
        "bag_amount": Decimal("0"),
        "other_amount": Decimal("0"),
        "refundable": True,
        "attributes": ["standard", "automatic", "refundable"],
    }


def _destination_labels(watch: TripWatch) -> list[str]:
    if watch.destination_mode == DestinationMode.FIXED and watch.destination_iatas:
        return watch.destination_iatas
    if watch.flexible_region:
        return [watch.flexible_region.title()]
    if watch.flexible_theme:
        return [watch.flexible_theme.title()]
    return ["Flexible"]


def _provider_name_for_source(source: str) -> str:
    if source.startswith("mock-"):
        return source
    parts = [part for part in source.replace("_", "-").split("-") if part]
    return "mock-" + "-".join(parts) if parts else "mock-provider"


def _watch_route_summary(watch: TripWatch) -> str:
    origins = ", ".join(watch.origin_iatas or ["Anywhere"])
    destinations = ", ".join(_destination_labels(watch))
    return f"{origins} -> {destinations}"


def _refundable_flags_for_deal(deal: Deal) -> list[bool]:
    payload = deal.payload_json or {}
    components = payload.get("components")
    if isinstance(components, dict):
        flags: list[bool] = []
        for component in components.values():
            if isinstance(component, dict) and "refundable" in component:
                flags.append(bool(component["refundable"]))
        return flags
    if "refundable" in payload:
        return [bool(payload["refundable"])]
    return []
