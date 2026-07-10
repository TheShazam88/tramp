from __future__ import annotations

from app.db.models import ObservationKind, TripMode, TripWatch
from app.watch_types import CoverageReport, NormalizedOffer


def build_coverage_report(
    *,
    watch: TripWatch,
    offers: list[NormalizedOffer],
    mock_data_enabled: bool = True,
) -> CoverageReport:
    searched_sources = sorted({offer.source for offer in offers})
    gaps: list[str] = []
    notes: list[str] = []
    flight_offers = any(offer.kind == ObservationKind.FLIGHT for offer in offers)
    hotel_offers = any(offer.kind == ObservationKind.HOTEL for offer in offers)
    car_offers = any(offer.kind == ObservationKind.CAR for offer in offers)

    if mock_data_enabled:
        if watch.trip_mode != TripMode.HOTELS_ONLY:
            gaps.append("Direct airline channels are not queried in v1 mock monitoring.")
        if watch.trip_mode != TripMode.FLIGHTS_ONLY:
            gaps.append("Hotel inventory is deterministic mock data and not live availability.")
        if watch.want_car:
            gaps.append("Rental car coverage is represented as a simplified placeholder offer.")
    else:
        if watch.trip_mode != TripMode.HOTELS_ONLY and not flight_offers:
            gaps.append("No live flight inventory is connected right now.")
        if watch.trip_mode != TripMode.FLIGHTS_ONLY and not hotel_offers:
            gaps.append("No live hotel inventory is connected right now.")
        if watch.want_car and not car_offers:
            gaps.append("No live rental car inventory is connected right now.")

    if len(searched_sources) >= 4:
        confidence = "high"
    elif len(searched_sources) >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    source_kind = "mock" if mock_data_enabled else "live"
    notes.append(f"{len(searched_sources)} {source_kind} sources searched.")
    if offers:
        notes.append(f"{len(offers)} normalized offers passed through scoring.")
    elif not mock_data_enabled:
        notes.append("Mock data is disabled, so no simulated offers were returned.")
    return CoverageReport(
        confidence=confidence,
        searched_sources=searched_sources,
        gaps=gaps,
        notes=notes,
    )
