from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.api.schemas.watches import ReadinessResponse
from app.db.models import (
    Deal,
    DealFraming,
    DealStatus,
    DestinationMode,
    ObservationKind,
    PaymentMethod,
    PriceObservation,
    SeatPreference,
    Traveler,
    TravelerRelationship,
    TripMode,
    TripWatch,
    TripWatchStatus,
    User,
)
from app.deal_service import _travelers_for_watch, get_deal_timeline
from app.travel_readiness import (
    build_deal_readiness_assessment,
    build_household_workspace_summary,
    build_semantic_badges,
    build_watch_actions,
)


class _QueueSession:
    def __init__(self, *, scalar_results: list[object], scalars_results: list[list[object]]):
        self.scalar_results = scalar_results
        self.scalars_results = scalars_results

    def scalar(self, _statement):
        return self.scalar_results.pop(0)

    def scalars(self, _statement):
        return self.scalars_results.pop(0)


def _build_watch() -> TripWatch:
    return TripWatch(
        id=uuid4(),
        user_id=uuid4(),
        status=TripWatchStatus.ACTIVE,
        trip_mode=TripMode.FLIGHTS_THEN_HOTELS,
        destination_mode=DestinationMode.FIXED,
        origin_iatas=["HND"],
        destination_iatas=["SIN"],
        depart_date_from=date(2027, 4, 12),
        return_date_to=date(2027, 4, 19),
        glide_start_days=42,
        glide_end_days=3,
        quality_floor=40,
        luxury_vs_savings=0.6,
        loyalty_weighting=0.0,
        band_tolerance=0.10,
        value_pressure=0.0,
    )


def test_household_workspace_summary_surfaces_setup_gaps() -> None:
    user = User(
        id=uuid4(),
        email="user@example.com",
        password_hash="hashed",
        totp_secret=None,
    )
    traveler = Traveler(
        id=uuid4(),
        user_id=user.id,
        traveler_relationship=TravelerRelationship.PARTNER,
        display_name="Partner",
        legal_first_name="Pat",
        legal_last_name="Traveler",
        dob=date(1990, 1, 1),
        nationality="US",
        seat_pref=SeatPreference.NO_PREFERENCE,
        infant_on_lap=False,
        created_at=datetime.now(UTC),
    )
    summary = build_household_workspace_summary(
        user=user,
        travelers=[traveler],
        traveler_group_count=0,
        payment_methods=[],
        template_count=1,
    )

    assert summary.traveler_count == 1
    assert summary.passport_gap_count == 1
    assert summary.totp_enabled is False
    assert any("2FA" in warning for warning in summary.setup_warnings)
    assert summary.readiness_label == "Household setup needs attention"


def test_deal_readiness_blocks_when_booking_prereqs_are_missing() -> None:
    watch = _build_watch()
    user = User(
        id=watch.user_id,
        email="user@example.com",
        password_hash="hashed",
        totp_secret=None,
    )
    traveler = Traveler(
        id=uuid4(),
        user_id=user.id,
        traveler_relationship=TravelerRelationship.SELF,
        display_name="Matt",
        legal_first_name="Matt",
        legal_last_name="Traveler",
        dob=date(1990, 1, 1),
        nationality="US",
        seat_pref=SeatPreference.NO_PREFERENCE,
        infant_on_lap=False,
        created_at=datetime.now(UTC),
    )
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="live-amadeus",
        total_price=Decimal("640.00"),
        currency="USD",
        fingerprint_hash="deal",
        status=DealStatus.PROPOSED,
    )

    readiness = build_deal_readiness_assessment(
        user=user,
        watch=watch,
        deal=deal,
        travelers=[traveler],
        payment_methods=[],
        live_inventory_available=False,
        mock_data_enabled=False,
    )

    assert readiness.label == "Blocked"
    assert readiness.score < 70
    assert any("Two-factor authentication" in blocker for blocker in readiness.blockers)
    assert any("payment method" in blocker for blocker in readiness.blockers)
    assert any("passport details" in blocker for blocker in readiness.blockers)
    resolutions = {resolution.code: resolution for resolution in readiness.resolutions}
    assert resolutions["two_factor_required"].path == "/setup/2fa"
    assert resolutions["payment_method_required"].path == "/profile"
    assert resolutions["passport_details_required"].path == "/profile"
    assert resolutions["live_inventory_required"].path == "/admin/integrations"
    assert resolutions["payment_method_required"].label == "Add payment method"
    response = ReadinessResponse.model_validate(asdict(readiness))
    assert {resolution.code for resolution in response.resolutions} == set(resolutions)


def test_hotel_only_readiness_does_not_require_passport() -> None:
    watch = _build_watch()
    watch.trip_mode = TripMode.HOTELS_ONLY
    user = User(
        id=watch.user_id,
        email="user@example.com",
        password_hash="hashed",
        totp_secret="secret",
    )
    traveler = Traveler(
        id=uuid4(),
        user_id=user.id,
        traveler_relationship=TravelerRelationship.SELF,
        display_name="Matt",
        legal_first_name="Matt",
        legal_last_name="Traveler",
        dob=date(1990, 1, 1),
        nationality="US",
        seat_pref=SeatPreference.NO_PREFERENCE,
        infant_on_lap=False,
        created_at=datetime.now(UTC),
    )
    payment_method = PaymentMethod(
        id=uuid4(),
        user_id=user.id,
        label="Primary",
    )
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="hotel",
        source="live-hotelbeds",
        total_price=Decimal("640.00"),
        currency="USD",
        fingerprint_hash="hotel-deal",
        status=DealStatus.PROPOSED,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    readiness = build_deal_readiness_assessment(
        user=user,
        watch=watch,
        deal=deal,
        travelers=[traveler],
        payment_methods=[payment_method],
        live_inventory_available=True,
        mock_data_enabled=False,
    )

    assert not any("passport" in blocker.lower() for blocker in readiness.blockers)
    assert readiness.label == "Ready"


def test_expired_deal_is_not_booking_ready() -> None:
    watch = _build_watch()
    user = User(
        id=watch.user_id,
        email="user@example.com",
        password_hash="hashed",
        totp_secret="secret",
    )
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="live-amadeus",
        total_price=Decimal("640.00"),
        currency="USD",
        fingerprint_hash="expired-deal",
        status=DealStatus.PROPOSED,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    readiness = build_deal_readiness_assessment(
        user=user,
        watch=watch,
        deal=deal,
        travelers=[],
        payment_methods=[],
        live_inventory_available=True,
        mock_data_enabled=False,
    )

    assert any("expired" in blocker.lower() for blocker in readiness.blockers)
    assert readiness.label == "Blocked"


def test_deal_readiness_loads_only_watch_travelers() -> None:
    watch = _build_watch()
    selected = Traveler(
        id=uuid4(),
        user_id=watch.user_id,
        traveler_relationship=TravelerRelationship.SELF,
        display_name="Selected",
        legal_first_name="Selected",
        legal_last_name="Traveler",
        dob=date(1990, 1, 1),
        nationality="US",
        seat_pref=SeatPreference.NO_PREFERENCE,
        infant_on_lap=False,
        created_at=datetime.now(UTC),
    )
    unrelated = Traveler(
        id=uuid4(),
        user_id=watch.user_id,
        traveler_relationship=TravelerRelationship.OTHER,
        display_name="Unrelated",
        legal_first_name="Other",
        legal_last_name="Traveler",
        dob=date(1990, 1, 1),
        nationality="US",
        seat_pref=SeatPreference.NO_PREFERENCE,
        infant_on_lap=False,
        created_at=datetime.now(UTC),
    )
    db = _QueueSession(
        scalar_results=[],
        scalars_results=[[selected.id], [selected, unrelated]],
    )

    travelers = _travelers_for_watch(db=db, watch=watch)

    assert travelers == [selected]


def test_semantic_badges_reflect_price_target_timing_and_setup() -> None:
    deal = Deal(
        id=uuid4(),
        watch_id=uuid4(),
        kind="flight",
        source="live-amadeus",
        total_price=Decimal("118.40"),
        currency="USD",
        fingerprint_hash="deal",
        price_percentile=12.0,
        timing_advice=(
            "Monitoring can continue; the stored history does not yet show strong urgency."
        ),
        status=DealStatus.PROPOSED,
        framing=DealFraming.BEST_VALUE,
        payload_json={"target_price": "120.00"},
    )
    readiness = type(
        "Readiness",
        (),
        {"score": 45, "label": "Needs setup", "blockers": ["Missing card"], "warnings": []},
    )()

    badges = build_semantic_badges(deal=deal, readiness=readiness)
    labels = {badge.label for badge in badges}

    assert {
        "better than usual",
        "target reached",
        "timing weak",
        "action needed",
    }.issubset(labels)


def test_fulfilled_watch_does_not_offer_resume_or_booking_actions() -> None:
    watch = _build_watch()
    watch.status = TripWatchStatus.FULFILLED

    actions = build_watch_actions(
        watch=watch,
        has_current_deal=True,
        readiness=None,
    )

    assert [action.key for action in actions] == ["open_deal"]


def test_deal_timeline_returns_recent_points_and_trend(monkeypatch) -> None:
    user = User(
        id=uuid4(),
        email="user@example.com",
        password_hash="hashed",
        totp_secret="secret",
    )
    watch = _build_watch()
    watch.user_id = user.id
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="live-amadeus",
        total_price=Decimal("610.00"),
        currency="USD",
        fingerprint_hash="deal",
        status=DealStatus.PROPOSED,
        payload_json={"target_price": "600.00", "glide_limit": "640.00"},
    )
    observations = [
        PriceObservation(
            id=uuid4(),
            watch_id=watch.id,
            kind=ObservationKind.FLIGHT,
            source="live-amadeus",
            observed_at=datetime(2026, 6, 30, tzinfo=UTC),
            price=Decimal("630.00"),
            currency="USD",
            payload_json={"title": "Higher offer", "price_percentile": 24},
            fingerprint_hash="obs-higher-same-run",
        ),
        PriceObservation(
            id=uuid4(),
            watch_id=watch.id,
            kind=ObservationKind.FLIGHT,
            source="live-amadeus",
            observed_at=datetime(2026, 6, 30, tzinfo=UTC),
            price=Decimal("610.00"),
            currency="USD",
            payload_json={"title": "Latest", "price_percentile": 18},
            fingerprint_hash="obs-latest",
        ),
        PriceObservation(
            id=uuid4(),
            watch_id=watch.id,
            kind=ObservationKind.FLIGHT,
            source="live-amadeus",
            observed_at=datetime(2026, 6, 20, tzinfo=UTC),
            price=Decimal("690.00"),
            currency="USD",
            payload_json={"title": "Earlier", "price_percentile": 42},
            fingerprint_hash="obs-earlier",
        ),
    ]
    db = _QueueSession(scalar_results=[deal, watch], scalars_results=[observations])
    monkeypatch.setattr("app.deal_service.get_mock_data_enabled", lambda **_: True)

    timeline = get_deal_timeline(db=db, user=user, deal_id=deal.id)

    assert timeline.current_price == Decimal("610.00")
    assert timeline.target_price == Decimal("600.00")
    assert len(timeline.points) == 2
    assert timeline.points[-1].price == Decimal("610.00")
    assert "Down" in timeline.trend_summary


def test_bundle_timeline_aggregates_comparable_components(monkeypatch) -> None:
    user = User(
        id=uuid4(),
        email="user@example.com",
        password_hash="hashed",
        totp_secret="secret",
    )
    watch = _build_watch()
    watch.user_id = user.id
    watch.trip_min_nights = 3
    bundle = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="trip_bundle",
        source="live-amadeus+live-hotelbeds",
        total_price=Decimal("900.00"),
        currency="USD",
        fingerprint_hash="bundle",
        status=DealStatus.PROPOSED,
    )
    observed_at = datetime(2026, 6, 30, tzinfo=UTC)
    observations = [
        PriceObservation(
            id=uuid4(),
            watch_id=watch.id,
            kind=ObservationKind.FLIGHT,
            source="live-amadeus",
            observed_at=observed_at,
            price=Decimal("600.00"),
            currency="USD",
            payload_json={"price_percentile": 20},
            fingerprint_hash="bundle-flight",
        ),
        PriceObservation(
            id=uuid4(),
            watch_id=watch.id,
            kind=ObservationKind.HOTEL,
            source="live-hotelbeds",
            observed_at=observed_at,
            price=Decimal("100.00"),
            currency="USD",
            payload_json={},
            fingerprint_hash="bundle-hotel",
        ),
    ]
    db = _QueueSession(scalar_results=[bundle, watch], scalars_results=[observations])
    monkeypatch.setattr("app.deal_service.get_mock_data_enabled", lambda **_: True)

    timeline = get_deal_timeline(db=db, user=user, deal_id=bundle.id)

    assert len(timeline.points) == 1
    assert timeline.points[0].price == Decimal("900.00")
    assert timeline.points[0].label == "Best comparable trip bundle"
