from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.db.models import (
    Deal,
    DestinationMode,
    ObservationKind,
    PriceScopeType,
    DealStatus,
    PriceObservation,
    PriceStat,
    SeatPreference,
    Traveler,
    TravelerRelationship,
    TripMode,
    TripWatch,
)
from app.watch_coverage import build_coverage_report
from app.watch_heuristics import glide_price_limit, historical_percentile_rank, percentile_rank, target_price_for_offer
from app.watch_mock_adapter import DeterministicMockAdapter
from app.watch_normalization import normalize_all_in_price
from app.watch_passports import validate_passport_expiry
from app.watch_scoring import score_offer
from app.watch_types import RejectionLearningOutcome
from app.watch_service import _offer_meets_watch_gates, _visible_deals_for_watch, _visible_observations_for_watch


class _ListSession:
    def __init__(self, items):
        self.items = items

    def scalars(self, _statement):
        return self.items


def _build_watch() -> TripWatch:
    return TripWatch(
        id=uuid4(),
        user_id=uuid4(),
        trip_mode=TripMode.FLIGHTS_THEN_HOTELS,
        destination_mode=DestinationMode.FIXED,
        origin_iatas=["HND", "NRT"],
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


def test_mock_adapter_is_deterministic_for_same_watch() -> None:
    watch = _build_watch()
    adapter = DeterministicMockAdapter()

    first = adapter.search(watch=watch)
    second = adapter.search(watch=watch)

    assert first == second
    assert len(first) >= 3


def test_normalize_all_in_price_sums_components_and_hashes_stably() -> None:
    raw_offer = {
        "kind": "flight",
        "source": "mock-duffel",
        "supplier": "ANA",
        "currency": "usd",
        "title": "HND -> SIN Business",
        "route_key": "HND-SIN",
        "depart_key": "2027-04-12",
        "return_key": "2027-04-19",
        "cabin": "business",
        "base_amount": Decimal("220.00"),
        "tax_amount": Decimal("31.20"),
        "fee_amount": Decimal("8.80"),
        "bag_amount": Decimal("0.00"),
        "other_amount": Decimal("4.00"),
        "refundable": True,
        "attributes": ["nonstop", "refundable", "business"],
    }

    normalized = normalize_all_in_price(raw_offer)

    assert normalized.total_price == Decimal("264.00")
    assert normalized.currency == "USD"
    assert normalized.fingerprint_hash == normalize_all_in_price(raw_offer).fingerprint_hash


def test_passport_expiry_validation_flags_low_validity() -> None:
    watch = _build_watch()
    traveler = Traveler(
        id=uuid4(),
        user_id=watch.user_id,
        traveler_relationship=TravelerRelationship.SELF,
        display_name="Alex",
        legal_first_name="Alex",
        legal_last_name="Traveler",
        dob=date(1990, 1, 1),
        nationality="US",
        seat_pref=SeatPreference.NO_PREFERENCE,
        infant_on_lap=False,
        passport_expiry=date(2027, 8, 1),
        created_at=datetime.now(UTC),
    )

    warnings = validate_passport_expiry(watch=watch, travelers=[traveler])

    assert len(warnings) == 1
    assert warnings[0].code == "passport_low_validity"
    assert warnings[0].traveler_name == "Alex"


def test_unconstrained_flight_search_includes_mixed_cabins() -> None:
    watch = _build_watch()
    watch.cabin_class = None
    adapter = DeterministicMockAdapter()

    flight_offers = [
        raw_offer
        for raw_offer in adapter.search(watch=watch)
        if raw_offer["kind"] == ObservationKind.FLIGHT.value
    ]
    cabins = {str(raw_offer["cabin"]).lower() for raw_offer in flight_offers}

    assert "business" in cabins
    assert "premium economy" in cabins
    assert "economy" in cabins


def test_luxury_scoring_prefers_better_cabin_when_advanced_filters_are_blank() -> None:
    watch = _build_watch()
    watch.cabin_class = None
    watch.max_stops = None
    watch.max_layover_minutes = None
    watch.min_connection_minutes = None
    watch.luxury_vs_savings = 0.72

    adapter = DeterministicMockAdapter()
    flight_offers = [
        normalize_all_in_price(raw_offer)
        for raw_offer in adapter.search(watch=watch)
        if raw_offer["kind"] == ObservationKind.FLIGHT.value
    ]
    comparable_prices = [offer.total_price for offer in flight_offers]

    for offer in flight_offers:
        percentile = percentile_rank(offer=offer, comparable_prices=comparable_prices)
        offer.value_score = score_offer(
            watch=watch,
            offer=offer,
            price_percentile=percentile,
            rejection_outcome=RejectionLearningOutcome(),
        )

    best_offer = max(flight_offers, key=lambda offer: offer.value_score or 0)

    assert best_offer.cabin in {"business", "premium economy"}
    assert best_offer.stops == 0


def test_offer_gates_respect_quality_floor_budget_and_learning_rejection() -> None:
    watch = _build_watch()
    watch.flight_budget_max = Decimal("250.00")
    watch.quality_floor = 70
    watch.value_target = 80
    watch.band_tolerance = 0.10

    raw_offer = {
        "kind": "flight",
        "source": "mock-amadeus",
        "supplier": "ANA",
        "currency": "usd",
        "title": "HND -> SIN Business",
        "route_key": "HND-SIN",
        "depart_key": "2027-04-12",
        "return_key": "2027-04-19",
        "cabin": "business",
        "airline_code": "NH",
        "base_amount": Decimal("220.00"),
        "tax_amount": Decimal("20.00"),
        "fee_amount": Decimal("10.00"),
        "bag_amount": Decimal("0.00"),
        "other_amount": Decimal("0.00"),
        "refundable": True,
        "attributes": ["nonstop", "business"],
    }
    offer = normalize_all_in_price(raw_offer)
    offer.quality_index = 82
    offer.value_score = 79

    assert _offer_meets_watch_gates(watch=watch, offer=offer) is True

    offer.raw_payload["_rejected_by_learning"] = True
    assert _offer_meets_watch_gates(watch=watch, offer=offer) is False

    offer.raw_payload["_rejected_by_learning"] = False
    offer.quality_index = 60
    assert _offer_meets_watch_gates(watch=watch, offer=offer) is False

    offer.quality_index = 82
    offer.total_price = Decimal("280.00")
    assert _offer_meets_watch_gates(watch=watch, offer=offer) is False


def test_visible_deals_and_observations_hide_simulated_records_when_mock_disabled() -> None:
    watch = _build_watch()
    simulated_deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="mock-amadeus",
        total_price=Decimal("640.00"),
        currency="USD",
        fingerprint_hash="mock-deal",
        status=DealStatus.PROPOSED,
    )
    live_deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="live-amadeus",
        total_price=Decimal("710.00"),
        currency="USD",
        fingerprint_hash="live-deal",
        status=DealStatus.PROPOSED,
    )
    simulated_observation = PriceObservation(
        id=uuid4(),
        watch_id=watch.id,
        kind=ObservationKind.FLIGHT,
        source="mock-amadeus",
        observed_at=datetime.now(UTC),
        price=Decimal("640.00"),
        currency="USD",
        payload_json={},
        fingerprint_hash="mock-observation",
    )
    live_observation = PriceObservation(
        id=uuid4(),
        watch_id=watch.id,
        kind=ObservationKind.FLIGHT,
        source="live-amadeus",
        observed_at=datetime.now(UTC),
        price=Decimal("710.00"),
        currency="USD",
        payload_json={},
        fingerprint_hash="live-observation",
    )

    visible_deals = _visible_deals_for_watch(
        db=_ListSession([simulated_deal, live_deal]),
        watch=watch,
        mock_data_enabled=False,
    )
    visible_observations = _visible_observations_for_watch(
        db=_ListSession([simulated_observation, live_observation]),
        watch=watch,
        mock_data_enabled=False,
    )

    assert visible_deals == [live_deal]
    assert visible_observations == [live_observation]


def test_coverage_report_is_honest_when_mock_data_is_disabled() -> None:
    watch = _build_watch()

    report = build_coverage_report(
        watch=watch,
        offers=[],
        mock_data_enabled=False,
    )

    assert "No live flight inventory is connected right now." in report.gaps
    assert "No live hotel inventory is connected right now." in report.gaps
    assert "No live rental car inventory is connected right now." in report.gaps
    assert report.notes[0] == "0 live sources searched."
    assert "Mock data is disabled, so no simulated offers were returned." in report.notes


def test_historical_stats_drive_target_and_glide_limit() -> None:
    watch = _build_watch()
    watch.flight_budget_max = Decimal("320.00")
    stat = PriceStat(
        scope_type=PriceScopeType.ROUTE_CABIN,
        scope_key="HND-SIN:business",
        month_bucket=date(2027, 4, 1),
        p10=Decimal("180.00"),
        p25=Decimal("220.00"),
        median=Decimal("260.00"),
        p75=Decimal("310.00"),
        sample_n=9,
    )
    offer = normalize_all_in_price(
        {
            "kind": "flight",
            "source": "mock-amadeus",
            "supplier": "ANA",
            "currency": "usd",
            "title": "HND -> SIN Business",
            "route_key": "HND-SIN",
            "depart_key": "2027-04-12",
            "return_key": "2027-04-19",
            "cabin": "business",
            "airline_code": "NH",
            "base_amount": Decimal("220.00"),
            "tax_amount": Decimal("20.00"),
            "fee_amount": Decimal("10.00"),
            "bag_amount": Decimal("0.00"),
            "other_amount": Decimal("0.00"),
            "refundable": True,
            "attributes": ["nonstop", "business"],
        }
    )

    assert target_price_for_offer(watch=watch, stat=stat) == Decimal("220.00")
    assert historical_percentile_rank(offer=offer, comparable_prices=[offer.total_price], stat=stat) == 43.8
    early_limit = glide_price_limit(
        watch=watch,
        offer=offer,
        stat=stat,
        now=datetime(2027, 1, 1, tzinfo=UTC),
    )
    late_limit = glide_price_limit(
        watch=watch,
        offer=offer,
        stat=stat,
        now=datetime(2027, 4, 11, tzinfo=UTC),
    )
    assert early_limit == Decimal("220.00")
    assert late_limit == Decimal("320.00")
