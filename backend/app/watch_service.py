# ruff: noqa: E501
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import quote
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_writer_lock
from app.api.schemas.watches import (
    CoverageReportResponse,
    CtaActionResponse,
    DashboardHighlightResponse,
    LoyaltyPlanEntryResponse,
    NormalizedOfferResponse,
    ReadinessResponse,
    SearchNowDealResponse,
    SearchNowResponse,
    SemanticBadgeResponse,
    ValidationWarningResponse,
    WatchCreateRequest,
    WatchCurrentDealResponse,
    WatchDashboardCardResponse,
    WatchDashboardResponse,
    WatchDraftGroupResponse,
    WatchDraftResponse,
    WatchResponse,
    WatchUpdateRequest,
)
from app.approval_service import issue_approval_token
from app.config import get_settings
from app.db.models import (
    Deal,
    DealFraming,
    DealStatus,
    DestinationMode,
    NotificationChannel,
    NotificationDelivery,
    ObservationKind,
    PaymentMethod,
    PriceObservation,
    PriceScopeType,
    PriceStat,
    Traveler,
    TravelerGroup,
    TripMode,
    TripTemplate,
    TripWatch,
    TripWatchStatus,
    User,
    UserPreference,
    WatchTraveler,
)
from app.integrations.service import (
    get_flight_connectors,
    get_hotel_connector,
    get_mock_data_enabled,
    live_inventory_available,
    source_is_simulated,
)
from app.notification_service import queue_notification
from app.scheduler.celery_app import celery_app
from app.security.tokens import SignedTokenService
from app.travel_readiness import (
    build_deal_readiness_assessment,
    build_semantic_badges,
    build_watch_actions,
)
from app.watch_coverage import build_coverage_report
from app.watch_heuristics import (
    glide_price_limit,
    historical_percentile_rank,
    month_bucket_for_watch,
    price_context,
    pricing_signal,
    target_price_for_offer,
    timing_advice,
)
from app.watch_loyalty import build_loyalty_plan
from app.watch_normalization import normalize_all_in_price
from app.watch_passports import validate_passport_expiry
from app.watch_rejections import apply_rejection_learning
from app.watch_scoring import score_offer
from app.watch_types import CoverageReport, LoyaltyPlanEntry, NormalizedOffer, ValidationWarning

DEAL_TTL = timedelta(hours=6)


def list_watches(*, db: Session, user: User) -> list[WatchResponse]:
    watches = list(
        db.scalars(
            select(TripWatch)
            .where(TripWatch.user_id == user.id)
            .order_by(TripWatch.created_at.desc())
        )
    )
    return [serialize_watch(db=db, user=user, watch=watch) for watch in watches]


def create_watch(*, db: Session, user: User, payload: WatchCreateRequest) -> WatchResponse:
    acquire_activity_writer_lock(db)
    traveler_group = _resolve_traveler_group(
        db=db, user=user, traveler_group_id=payload.traveler_group_id
    )
    traveler_ids = _resolve_traveler_ids(
        db=db,
        user=user,
        traveler_group=traveler_group,
        traveler_ids=payload.traveler_ids,
    )
    watch = TripWatch(
        id=uuid4(),
        user_id=user.id,
        status=TripWatchStatus.ACTIVE,
        trip_mode=payload.trip_mode,
        traveler_group_id=traveler_group.id if traveler_group else None,
        origin_iatas=payload.origin_iatas or None,
        destination_iatas=payload.destination_iatas or None,
        destination_mode=payload.destination_mode,
        flexible_region=payload.flexible_region,
        flexible_theme=payload.flexible_theme,
        depart_date_from=payload.depart_date_from,
        depart_date_to=payload.depart_date_to,
        return_date_from=payload.return_date_from,
        return_date_to=payload.return_date_to,
        trip_min_nights=payload.trip_min_nights,
        trip_max_nights=payload.trip_max_nights,
        cabin_class=payload.cabin_class,
        max_stops=payload.max_stops,
        max_layover_minutes=payload.max_layover_minutes,
        min_connection_minutes=payload.min_connection_minutes,
        preferred_airlines=payload.preferred_airlines or None,
        preferred_alliances=payload.preferred_alliances or None,
        avoid_redeye=payload.avoid_redeye,
        outbound_earliest_depart=payload.outbound_earliest_depart,
        outbound_latest_depart=payload.outbound_latest_depart,
        outbound_arrive_by=payload.outbound_arrive_by,
        return_earliest_depart=payload.return_earliest_depart,
        return_latest_depart=payload.return_latest_depart,
        return_arrive_by=payload.return_arrive_by,
        flight_budget_max=payload.flight_budget_max,
        hotel_budget_per_night_max=payload.hotel_budget_per_night_max,
        max_total_trip_spend=payload.max_total_trip_spend,
        budget_currency=payload.budget_currency,
        ideal_price=payload.ideal_price,
        glide_start_days=payload.glide_start_days,
        glide_end_days=payload.glide_end_days,
        quality_floor=payload.quality_floor,
        luxury_vs_savings=payload.luxury_vs_savings,
        hotel_min_rating=payload.hotel_min_rating,
        hotel_area_lat=payload.hotel_area_lat,
        hotel_area_lng=payload.hotel_area_lng,
        hotel_radius_km=payload.hotel_radius_km,
        prefer_refundable=payload.prefer_refundable,
        loyalty_weighting=payload.loyalty_weighting,
        value_target=payload.value_target,
        band_tolerance=payload.band_tolerance,
        value_pressure=payload.value_pressure,
        include_airbnb=payload.include_airbnb,
        airbnb_disclosure_ack_at=datetime.now(UTC) if payload.include_airbnb else None,
        refresh_interval=payload.refresh_interval,
        notify_channel=payload.notify_channel,
        want_car=payload.want_car,
        auto_book_mode=payload.auto_book_mode,
    )
    db.add(watch)
    db.flush()
    _sync_watch_travelers(db=db, watch=watch, traveler_ids=traveler_ids)
    db.commit()
    db.refresh(watch)
    return serialize_watch(db=db, user=user, watch=watch)


def get_watch(*, db: Session, user: User, watch_id: UUID) -> WatchResponse:
    watch = _get_watch_or_404(db=db, user=user, watch_id=watch_id)
    return serialize_watch(db=db, user=user, watch=watch)


def update_watch(
    *, db: Session, user: User, watch_id: UUID, payload: WatchUpdateRequest
) -> WatchResponse:
    acquire_activity_writer_lock(db)
    watch = _get_watch_or_404(db=db, user=user, watch_id=watch_id)
    traveler_group = (
        _resolve_traveler_group(db=db, user=user, traveler_group_id=payload.traveler_group_id)
        if "traveler_group_id" in payload.model_fields_set
        else _get_watch_traveler_group(db=db, watch=watch)
    )

    field_names = (
        "status",
        "trip_mode",
        "destination_mode",
        "flexible_region",
        "flexible_theme",
        "depart_date_from",
        "depart_date_to",
        "return_date_from",
        "return_date_to",
        "trip_min_nights",
        "trip_max_nights",
        "cabin_class",
        "max_stops",
        "max_layover_minutes",
        "min_connection_minutes",
        "avoid_redeye",
        "outbound_earliest_depart",
        "outbound_latest_depart",
        "outbound_arrive_by",
        "return_earliest_depart",
        "return_latest_depart",
        "return_arrive_by",
        "flight_budget_max",
        "hotel_budget_per_night_max",
        "max_total_trip_spend",
        "budget_currency",
        "ideal_price",
        "glide_start_days",
        "glide_end_days",
        "quality_floor",
        "luxury_vs_savings",
        "hotel_min_rating",
        "hotel_area_lat",
        "hotel_area_lng",
        "hotel_radius_km",
        "prefer_refundable",
        "loyalty_weighting",
        "value_target",
        "band_tolerance",
        "value_pressure",
        "include_airbnb",
        "refresh_interval",
        "notify_channel",
        "want_car",
        "auto_book_mode",
    )
    for field_name in field_names:
        if field_name in payload.model_fields_set:
            setattr(watch, field_name, getattr(payload, field_name))

    if "origin_iatas" in payload.model_fields_set:
        watch.origin_iatas = payload.origin_iatas or None
    if "destination_iatas" in payload.model_fields_set:
        watch.destination_iatas = payload.destination_iatas or None
    if "preferred_airlines" in payload.model_fields_set:
        watch.preferred_airlines = payload.preferred_airlines or None
    if "preferred_alliances" in payload.model_fields_set:
        watch.preferred_alliances = payload.preferred_alliances or None
    if "traveler_group_id" in payload.model_fields_set:
        watch.traveler_group_id = traveler_group.id if traveler_group else None
    if "include_airbnb" in payload.model_fields_set:
        watch.airbnb_disclosure_ack_at = datetime.now(UTC) if payload.include_airbnb else None

    if (
        "traveler_ids" in payload.model_fields_set
        or "traveler_group_id" in payload.model_fields_set
    ):
        traveler_ids = _resolve_traveler_ids(
            db=db,
            user=user,
            traveler_group=traveler_group,
            traveler_ids=payload.traveler_ids
            if payload.traveler_ids is not None
            else _current_watch_traveler_ids(db=db, watch=watch),
        )
        _sync_watch_travelers(db=db, watch=watch, traveler_ids=traveler_ids)

    db.add(watch)
    db.commit()
    db.refresh(watch)
    return serialize_watch(db=db, user=user, watch=watch)


def pause_watch(*, db: Session, user: User, watch_id: UUID) -> WatchResponse:
    acquire_activity_writer_lock(db)
    watch = _get_watch_or_404(db=db, user=user, watch_id=watch_id)
    watch.status = TripWatchStatus.PAUSED
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return serialize_watch(db=db, user=user, watch=watch)


def resume_watch(*, db: Session, user: User, watch_id: UUID) -> WatchResponse:
    acquire_activity_writer_lock(db)
    watch = _get_watch_or_404(db=db, user=user, watch_id=watch_id)
    watch.status = TripWatchStatus.ACTIVE
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return serialize_watch(db=db, user=user, watch=watch)


def get_dashboard(*, db: Session, user: User) -> WatchDashboardResponse:
    mock_data_enabled = get_mock_data_enabled(db=db)
    watches = list(
        db.scalars(
            select(TripWatch)
            .where(TripWatch.user_id == user.id)
            .order_by(TripWatch.created_at.desc())
        )
    )
    watch_cards = [
        serialize_dashboard_card(db=db, watch=watch, mock_data_enabled=mock_data_enabled)
        for watch in watches
    ]

    best_deal = _best_deal_for_watches(
        db=db,
        watches=watches,
        mock_data_enabled=mock_data_enabled,
    )
    highlights = [
        DashboardHighlightResponse(
            label="Best value today",
            value=_format_price(best_deal.total_price, best_deal.currency)
            if best_deal
            else "No deal yet",
            note=best_deal.summary_text
            if best_deal and best_deal.summary_text
            else "Run search-now on a watch to create deals.",
        ),
        DashboardHighlightResponse(
            label="Active watches",
            value=str(sum(1 for watch in watches if watch.status == TripWatchStatus.ACTIVE)),
            note=f"{len(watches)} total watches on this account.",
        ),
        DashboardHighlightResponse(
            label="Coverage confidence",
            value=_dashboard_confidence_label(watches=watch_cards),
            note="Based on the latest stored coverage report for each watch.",
        ),
    ]
    return WatchDashboardResponse(highlights=highlights, watches=watch_cards)


def build_watch_draft(
    *,
    db: Session,
    user: User,
    template_id: UUID | None = None,
    watch_id: UUID | None = None,
) -> WatchDraftResponse:
    watch = _get_watch_or_404(db=db, user=user, watch_id=watch_id) if watch_id else None
    preference = db.scalar(select(UserPreference).where(UserPreference.user_id == user.id))
    templates = list(
        db.scalars(
            select(TripTemplate).where(TripTemplate.user_id == user.id).order_by(TripTemplate.name)
        )
    )
    template = None
    if template_id is not None:
        template = db.scalar(
            select(TripTemplate).where(
                TripTemplate.id == template_id, TripTemplate.user_id == user.id
            )
        )
    elif templates:
        template = templates[0]

    traveler_groups = list(
        db.scalars(
            select(TravelerGroup)
            .where(TravelerGroup.user_id == user.id)
            .order_by(TravelerGroup.name)
        )
    )
    selected_group = _select_draft_group(
        traveler_groups=traveler_groups, watch=watch, template=template
    )
    template_payload = template.watch_payload_json if template else {}

    if watch is not None:
        defaults = _watch_to_defaults(db=db, watch=watch)
        title = "Refine watch"
    else:
        defaults = _draft_defaults_from_sources(
            preference=preference,
            template_payload=template_payload,
            selected_group=selected_group,
        )
        title = "Create a new watch"

    options = _draft_options_from_defaults(defaults=defaults)
    return WatchDraftResponse(
        title=title,
        traveler_groups=[
            WatchDraftGroupResponse(
                id=str(group.id),
                name=group.name,
                traveler_ids=[str(traveler_id) for traveler_id in group.traveler_ids],
            )
            for group in traveler_groups
        ],
        selected_group_id=str(selected_group.id) if selected_group else None,
        selected_group_name=selected_group.name if selected_group else "All travelers",
        origins=", ".join(defaults["origin_iatas"]) or "HND, NRT",
        destination=defaults["destination_label"],
        date_window=defaults["date_window"],
        stay_length=defaults["stay_length"],
        flight_budget=defaults["flight_budget"],
        hotel_budget=defaults["hotel_budget"],
        luxury_vs_savings=defaults["luxury_vs_savings"],
        options=options,
        watch_defaults=defaults["watch_defaults"],
    )


def search_now(*, db: Session, user: User, watch_id: UUID) -> SearchNowResponse:
    acquire_activity_writer_lock(db)
    watch = _get_watch_or_404(db=db, user=user, watch_id=watch_id)
    travelers = _travelers_for_watch(db=db, watch=watch, user=user)
    observed_at = datetime.now(UTC)
    mock_data_enabled = get_mock_data_enabled(db=db)

    raw_offers: list[dict[str, object]] = []
    if watch.trip_mode != TripMode.HOTELS_ONLY:
        for flight_connector in get_flight_connectors(db=db):
            raw_offers.extend(flight_connector.search_flights(watch=watch))
    if watch.trip_mode != TripMode.FLIGHTS_ONLY:
        hotel_connector = get_hotel_connector(db=db)
        raw_offers.extend(hotel_connector.search_hotels(watch=watch))
        if watch.want_car:
            raw_offers.extend(hotel_connector.search_cars(watch=watch))
    offers = [normalize_all_in_price(raw_offer) for raw_offer in raw_offers]
    if not mock_data_enabled:
        offers = [offer for offer in offers if not source_is_simulated(offer.source)]

    flight_prices = [offer.total_price for offer in offers if offer.kind == ObservationKind.FLIGHT]
    hotel_prices = [offer.total_price for offer in offers if offer.kind == ObservationKind.HOTEL]
    car_prices = [offer.total_price for offer in offers if offer.kind == ObservationKind.CAR]

    validation_warnings = validate_passport_expiry(watch=watch, travelers=travelers)
    coverage_report = build_coverage_report(
        watch=watch,
        offers=offers,
        mock_data_enabled=mock_data_enabled,
    )

    observations_created = 0
    for offer in offers:
        historical_stat = _get_price_stat(db=db, watch=watch, offer=offer)
        comparable_prices = {
            ObservationKind.FLIGHT: flight_prices,
            ObservationKind.HOTEL: hotel_prices,
            ObservationKind.CAR: car_prices,
        }[offer.kind]
        percentile = historical_percentile_rank(
            offer=offer,
            comparable_prices=comparable_prices,
            stat=historical_stat,
        )
        rejection_outcome = apply_rejection_learning(db=db, watch=watch, offer=offer)
        offer.price_percentile = percentile
        offer.timing_advice = timing_advice(
            watch=watch,
            offer=offer,
            percentile=percentile,
            stat=historical_stat,
        )
        offer.value_score = score_offer(
            watch=watch,
            offer=offer,
            price_percentile=percentile,
            rejection_outcome=rejection_outcome,
        )
        offer.raw_payload["_rejected_by_learning"] = rejection_outcome.rejected
        if not rejection_outcome.rejected:
            observations_created += _store_observation(
                db=db, watch=watch, offer=offer, observed_at=observed_at
            )
        _upsert_price_stat(db=db, watch=watch, offer=offer)

    deals = _upsert_deals(
        db=db,
        watch=watch,
        travelers=travelers,
        offers=offers,
        coverage_report=coverage_report,
        validation_warnings=validation_warnings,
    )
    notification_deliveries = _queue_deal_notifications(
        db=db,
        user=user,
        watch=watch,
        deals=deals,
    )
    db.commit()
    _enqueue_notification_tasks(notification_deliveries)

    return SearchNowResponse(
        observed_at=observed_at,
        observations_created=observations_created,
        deals_upserted=len(deals),
        coverage_report=_coverage_to_response(coverage_report),
        offers=[
            NormalizedOfferResponse(
                fingerprint_hash=offer.fingerprint_hash,
                kind=offer.kind,
                source=offer.source,
                title=offer.title,
                total_price=offer.total_price,
                currency=offer.currency,
                quality_index=offer.quality_index,
                value_score=offer.value_score,
                price_percentile=offer.price_percentile,
                timing_advice=offer.timing_advice,
                attributes=offer.attributes,
            )
            for offer in offers
        ],
        proposed_deals=[
            _serialize_search_now_deal(
                db=db,
                user=user,
                watch=watch,
                travelers=travelers,
                deal=deal,
            )
            for deal in deals
        ],
    )


def serialize_watch(*, db: Session, user: User, watch: TripWatch) -> WatchResponse:
    mock_data_enabled = get_mock_data_enabled(db=db)
    traveler_group = _get_watch_traveler_group(db=db, watch=watch)
    travelers = _travelers_for_watch(db=db, watch=watch, user=user)
    traveler_ids = [str(traveler.id) for traveler in travelers]
    traveler_names = [traveler.display_name for traveler in travelers]
    observations = _visible_observations_for_watch(
        db=db,
        watch=watch,
        mock_data_enabled=mock_data_enabled,
    )
    visible_deals = _visible_deals_for_watch(
        db=db,
        watch=watch,
        mock_data_enabled=mock_data_enabled,
    )
    observation_count = len(observations)
    deal_count = len(visible_deals)
    latest_observed_at = observations[0].observed_at if observations else None
    current_deal = visible_deals[0] if visible_deals else None
    readiness = _readiness_for_watch(
        db=db,
        user=user,
        watch=watch,
        travelers=travelers,
        current_deal=current_deal,
    )
    badges = build_semantic_badges(deal=current_deal, readiness=readiness)

    return WatchResponse(
        id=str(watch.id),
        status=watch.status,
        trip_mode=watch.trip_mode,
        destination_mode=watch.destination_mode,
        traveler_group_id=str(traveler_group.id) if traveler_group else None,
        traveler_group_name=traveler_group.name if traveler_group else None,
        traveler_ids=traveler_ids,
        traveler_names=traveler_names,
        origin_iatas=list(watch.origin_iatas or []),
        destination_iatas=list(watch.destination_iatas or []),
        flexible_region=watch.flexible_region,
        flexible_theme=watch.flexible_theme,
        depart_date_from=watch.depart_date_from,
        depart_date_to=watch.depart_date_to,
        return_date_from=watch.return_date_from,
        return_date_to=watch.return_date_to,
        trip_min_nights=watch.trip_min_nights,
        trip_max_nights=watch.trip_max_nights,
        cabin_class=watch.cabin_class,
        max_stops=watch.max_stops,
        max_layover_minutes=watch.max_layover_minutes,
        min_connection_minutes=watch.min_connection_minutes,
        preferred_airlines=list(watch.preferred_airlines or []),
        preferred_alliances=list(watch.preferred_alliances or []),
        avoid_redeye=watch.avoid_redeye,
        flight_budget_max=watch.flight_budget_max,
        hotel_budget_per_night_max=watch.hotel_budget_per_night_max,
        max_total_trip_spend=watch.max_total_trip_spend,
        budget_currency=watch.budget_currency,
        ideal_price=watch.ideal_price,
        glide_start_days=watch.glide_start_days,
        glide_end_days=watch.glide_end_days,
        quality_floor=watch.quality_floor,
        luxury_vs_savings=watch.luxury_vs_savings,
        hotel_min_rating=watch.hotel_min_rating,
        prefer_refundable=watch.prefer_refundable,
        loyalty_weighting=watch.loyalty_weighting,
        value_target=watch.value_target,
        band_tolerance=watch.band_tolerance,
        value_pressure=watch.value_pressure,
        include_airbnb=watch.include_airbnb,
        refresh_interval=watch.refresh_interval,
        notify_channel=watch.notify_channel,
        want_car=watch.want_car,
        auto_book_mode=watch.auto_book_mode,
        route=_route_label(watch),
        dates_label=_date_label(watch),
        travelers_label=_travelers_label(travelers),
        cabin_label=(watch.cabin_class or "Flexible cabin").replace("_", " ").title(),
        cadence_label=_cadence_label(watch),
        observation_count=int(observation_count),
        deal_count=int(deal_count),
        latest_observed_at=latest_observed_at,
        current_deal=_serialize_current_deal(current_deal, readiness=readiness),
        readiness=ReadinessResponse.model_validate(asdict(readiness)),
        badges=[SemanticBadgeResponse.model_validate(asdict(badge)) for badge in badges],
        cta_actions=[
            CtaActionResponse.model_validate(asdict(action))
            for action in build_watch_actions(
                watch=watch,
                has_current_deal=current_deal is not None,
                readiness=readiness,
            )
        ],
        created_at=watch.created_at,
        updated_at=watch.updated_at,
    )


def serialize_dashboard_card(
    *,
    db: Session,
    watch: TripWatch,
    mock_data_enabled: bool | None = None,
) -> WatchDashboardCardResponse:
    if mock_data_enabled is None:
        mock_data_enabled = get_mock_data_enabled(db=db)
    traveler_names = [
        traveler.display_name for traveler in _travelers_for_watch(db=db, watch=watch, user=None)
    ]
    current_deal = _latest_deal_for_watch(
        db=db,
        watch=watch,
        mock_data_enabled=mock_data_enabled,
    )
    travelers = _travelers_for_watch(db=db, watch=watch, user=None)
    watch_user = db.scalar(select(User).where(User.id == watch.user_id))
    readiness = (
        _readiness_for_watch(
            db=db,
            user=watch_user,
            watch=watch,
            travelers=travelers,
            current_deal=current_deal,
        )
        if watch_user is not None
        else None
    )
    badges = build_semantic_badges(deal=current_deal, readiness=readiness)
    framing = (
        current_deal.framing.value.replace("_", " ").title()
        if current_deal
        else _default_framing_label(watch)
    )
    insight = (
        current_deal.summary_text
        if current_deal and current_deal.summary_text
        else "No stored deals yet. Use search-now to generate deterministic coverage."
    )
    if watch.status == TripWatchStatus.PAUSED:
        best_now = "Paused"
        insight = "Monitoring is paused for this watch."
    else:
        best_now = (
            _format_price(current_deal.total_price, current_deal.currency)
            if current_deal
            else "No deal yet"
        )
    return WatchDashboardCardResponse(
        id=str(watch.id),
        route=_route_label(watch),
        dates=_date_label(watch),
        travelers=", ".join(traveler_names) if traveler_names else "No travelers selected",
        cabin=(watch.cabin_class or "Flexible").replace("_", " ").title(),
        status=watch.status,
        framing=framing,
        best_now=best_now,
        insight=insight,
        cadence=_cadence_label(watch),
        deal_id=str(current_deal.id) if current_deal else None,
        current_deal_status=current_deal.status.value if current_deal else None,
        search_label="Open deal" if current_deal else "Search now",
        readiness=ReadinessResponse.model_validate(asdict(readiness)) if readiness else None,
        badges=[SemanticBadgeResponse.model_validate(asdict(badge)) for badge in badges],
        cta_actions=[
            CtaActionResponse.model_validate(asdict(action))
            for action in build_watch_actions(
                watch=watch,
                has_current_deal=current_deal is not None,
                readiness=readiness,
            )
        ],
    )


def _get_watch_or_404(*, db: Session, user: User, watch_id: UUID) -> TripWatch:
    watch = db.scalar(
        select(TripWatch).where(TripWatch.id == watch_id, TripWatch.user_id == user.id)
    )
    if watch is None:
        raise LookupError("Watch not found.")
    return watch


def _resolve_traveler_group(
    *,
    db: Session,
    user: User,
    traveler_group_id: str | None,
) -> TravelerGroup | None:
    if traveler_group_id is None:
        return None
    try:
        group_uuid = UUID(traveler_group_id)
    except ValueError as exc:
        raise ValueError("traveler_group_id must be a valid UUID.") from exc
    traveler_group = db.scalar(
        select(TravelerGroup).where(
            TravelerGroup.id == group_uuid, TravelerGroup.user_id == user.id
        )
    )
    if traveler_group is None:
        raise ValueError("Traveler group not found.")
    return traveler_group


def _resolve_traveler_ids(
    *,
    db: Session,
    user: User,
    traveler_group: TravelerGroup | None,
    traveler_ids: list[str] | None,
) -> list[UUID]:
    raw_ids = traveler_ids or []
    if not raw_ids and traveler_group is not None:
        return list(traveler_group.traveler_ids)
    if not raw_ids:
        return []

    parsed_ids: list[UUID] = []
    for traveler_id in raw_ids:
        try:
            parsed_ids.append(UUID(traveler_id))
        except ValueError as exc:
            raise ValueError("traveler_ids must contain valid UUID values.") from exc
    owned_ids = set(
        db.scalars(
            select(Traveler.id).where(Traveler.user_id == user.id, Traveler.id.in_(parsed_ids))
        )
    )
    if len(owned_ids) != len(set(parsed_ids)):
        raise ValueError("traveler_ids may only include the current user's travelers.")
    return list(dict.fromkeys(parsed_ids))


def _sync_watch_travelers(*, db: Session, watch: TripWatch, traveler_ids: list[UUID]) -> None:
    db.execute(delete(WatchTraveler).where(WatchTraveler.watch_id == watch.id))
    for traveler_id in traveler_ids:
        db.add(WatchTraveler(watch_id=watch.id, traveler_id=traveler_id))
    db.flush()


def _current_watch_traveler_ids(*, db: Session, watch: TripWatch) -> list[str]:
    return [
        str(value)
        for value in db.scalars(
            select(WatchTraveler.traveler_id).where(WatchTraveler.watch_id == watch.id)
        )
    ]


def _travelers_for_watch(*, db: Session, watch: TripWatch, user: User | None) -> list[Traveler]:
    traveler_ids = list(
        db.scalars(select(WatchTraveler.traveler_id).where(WatchTraveler.watch_id == watch.id))
    )
    if not traveler_ids and watch.traveler_group_id is not None:
        traveler_group = _get_watch_traveler_group(db=db, watch=watch)
        traveler_ids = list(traveler_group.traveler_ids) if traveler_group else []
    if not traveler_ids:
        return []

    query = select(Traveler).where(Traveler.id.in_(traveler_ids))
    if user is not None:
        query = query.where(Traveler.user_id == user.id)
    travelers = list(db.scalars(query.order_by(Traveler.created_at.asc())))
    traveler_map = {traveler.id: traveler for traveler in travelers}
    return [
        traveler_map[traveler_id] for traveler_id in traveler_ids if traveler_id in traveler_map
    ]


def _get_watch_traveler_group(*, db: Session, watch: TripWatch) -> TravelerGroup | None:
    if watch.traveler_group_id is None:
        return None
    return db.scalar(select(TravelerGroup).where(TravelerGroup.id == watch.traveler_group_id))


def _store_observation(
    *, db: Session, watch: TripWatch, offer: NormalizedOffer, observed_at: datetime
) -> int:
    observation = PriceObservation(
        watch_id=watch.id,
        kind=offer.kind,
        source=offer.source,
        observed_at=observed_at,
        price=offer.total_price,
        currency=offer.currency,
        payload_json={
            **offer.raw_payload,
            "price_percentile": offer.price_percentile,
            "value_score": offer.value_score,
            "timing_advice": offer.timing_advice,
        },
        fingerprint_hash=offer.fingerprint_hash,
    )
    db.add(observation)
    db.flush()
    return 1


def _upsert_price_stat(*, db: Session, watch: TripWatch, offer: NormalizedOffer) -> None:
    scope_type, scope_key = _price_scope_for_offer(offer)
    month_bucket = month_bucket_for_watch(watch)
    stat = db.scalar(
        select(PriceStat).where(
            PriceStat.scope_type == scope_type,
            PriceStat.scope_key == scope_key,
            PriceStat.month_bucket == month_bucket,
        )
    )
    if stat is None:
        stat = PriceStat(
            scope_type=scope_type,
            scope_key=scope_key,
            month_bucket=month_bucket,
            sample_n=0,
        )

    observation_prices = sorted(
        offer.total_price
        for observation in db.scalars(
            select(PriceObservation).where(
                PriceObservation.watch_id == watch.id,
                PriceObservation.kind == offer.kind,
            )
        )
        for offer in [
            NormalizedOffer(
                fingerprint_hash=observation.fingerprint_hash,
                kind=observation.kind,
                source=observation.source,
                title=str((observation.payload_json or {}).get("title") or ""),
                total_price=observation.price,
                currency=observation.currency,
                quality_index=float((observation.payload_json or {}).get("quality_index") or 0),
                attributes=list((observation.payload_json or {}).get("attributes") or []),
                raw_payload=observation.payload_json or {},
            )
        ]
        if str((offer.raw_payload or {}).get("scope_key") or offer.title) == scope_key
    )
    if offer.total_price not in observation_prices:
        observation_prices.append(offer.total_price)
        observation_prices.sort()

    stat.sample_n = len(observation_prices)
    stat.p10 = _percentile_value(observation_prices, 0.10)
    stat.p25 = _percentile_value(observation_prices, 0.25)
    stat.median = _percentile_value(observation_prices, 0.50)
    stat.p75 = _percentile_value(observation_prices, 0.75)
    stat.volatility = round(
        float((stat.p75 or offer.total_price) - (stat.p25 or offer.total_price)), 2
    )
    db.add(stat)
    db.flush()


def _upsert_deals(
    *,
    db: Session,
    watch: TripWatch,
    travelers: list[Traveler],
    offers: list[NormalizedOffer],
    coverage_report: CoverageReport,
    validation_warnings: list[ValidationWarning],
) -> list[Deal]:
    deals: list[Deal] = []
    if watch.trip_mode == TripMode.FLIGHTS_ONLY:
        candidate_offers = sorted(
            [
                offer
                for offer in offers
                if offer.kind == ObservationKind.FLIGHT
                and _offer_meets_watch_gates(
                    watch=watch,
                    offer=offer,
                    historical_stat=_get_price_stat(db=db, watch=watch, offer=offer),
                )
            ],
            key=lambda offer: (-(offer.value_score or 0), offer.total_price),
        )[:3]
        for offer in candidate_offers:
            deals.append(
                _upsert_single_component_deal(
                    db=db,
                    watch=watch,
                    offer=offer,
                    coverage_report=coverage_report,
                    validation_warnings=validation_warnings,
                    loyalty_plan=build_loyalty_plan(db=db, travelers=travelers, offer=offer),
                )
            )
        return deals

    if watch.trip_mode == TripMode.HOTELS_ONLY:
        candidate_offers = sorted(
            [
                offer
                for offer in offers
                if offer.kind == ObservationKind.HOTEL
                and _offer_meets_watch_gates(
                    watch=watch,
                    offer=offer,
                    historical_stat=_get_price_stat(db=db, watch=watch, offer=offer),
                )
            ],
            key=lambda offer: (-(offer.value_score or 0), offer.total_price),
        )[:3]
        for offer in candidate_offers:
            deals.append(
                _upsert_single_component_deal(
                    db=db,
                    watch=watch,
                    offer=offer,
                    coverage_report=coverage_report,
                    validation_warnings=validation_warnings,
                    loyalty_plan=[],
                )
            )
        return deals

    flights = sorted(
        [
            offer
            for offer in offers
            if offer.kind == ObservationKind.FLIGHT
            and _offer_meets_watch_gates(
                watch=watch,
                offer=offer,
                historical_stat=_get_price_stat(db=db, watch=watch, offer=offer),
            )
        ],
        key=lambda offer: (-(offer.value_score or 0), offer.total_price),
    )
    hotels = sorted(
        [
            offer
            for offer in offers
            if offer.kind == ObservationKind.HOTEL
            and _offer_meets_watch_gates(
                watch=watch,
                offer=offer,
                historical_stat=_get_price_stat(db=db, watch=watch, offer=offer),
            )
        ],
        key=lambda offer: (-(offer.value_score or 0), offer.total_price),
    )
    cars = sorted(
        [
            offer
            for offer in offers
            if offer.kind == ObservationKind.CAR
            and _offer_meets_watch_gates(
                watch=watch,
                offer=offer,
                historical_stat=_get_price_stat(db=db, watch=watch, offer=offer),
            )
        ],
        key=lambda offer: (-(offer.value_score or 0), offer.total_price),
    )
    nights = watch.trip_min_nights or watch.trip_max_nights or 4
    best_car = cars[0] if cars else None
    for flight in flights[:2]:
        for hotel in hotels[:2]:
            component_total = flight.total_price + (hotel.total_price * Decimal(nights))
            if best_car is not None:
                component_total += best_car.total_price
            value_score = round(
                (
                    (flight.value_score or 0)
                    + (hotel.value_score or 0)
                    + ((best_car.value_score or 0) if best_car else 0)
                )
                / (3 if best_car else 2),
                1,
            )
            quality_index = round(
                (
                    flight.quality_index
                    + hotel.quality_index
                    + (best_car.quality_index if best_car else 0)
                )
                / (3 if best_car else 2),
                1,
            )
            summary = (
                f"{pricing_signal(watch=watch, offer=flight, percentile=flight.price_percentile or 50)} "
                f"Includes {nights} hotel nights for an all-in trip estimate."
            )
            if (
                watch.max_total_trip_spend is not None
                and component_total > watch.max_total_trip_spend
            ):
                continue
            loyalty_plan = build_loyalty_plan(db=db, travelers=travelers, offer=flight)
            deals.append(
                _upsert_bundle_deal(
                    db=db,
                    watch=watch,
                    flight=flight,
                    hotel=hotel,
                    car=best_car,
                    total_price=component_total,
                    quality_index=quality_index,
                    value_score=value_score,
                    summary=summary,
                    coverage_report=coverage_report,
                    validation_warnings=validation_warnings,
                    loyalty_plan=loyalty_plan,
                )
            )
    return sorted(deals, key=lambda deal: (-(deal.value_score or 0), deal.total_price))[:3]


def _upsert_single_component_deal(
    *,
    db: Session,
    watch: TripWatch,
    offer: NormalizedOffer,
    coverage_report: CoverageReport,
    validation_warnings: list[ValidationWarning],
    loyalty_plan: list[LoyaltyPlanEntry],
) -> Deal:
    historical_stat = _get_price_stat(db=db, watch=watch, offer=offer)
    target_price = target_price_for_offer(watch=watch, stat=historical_stat)
    glide_limit = glide_price_limit(watch=watch, offer=offer, stat=historical_stat)
    summary_context = price_context(
        offer=offer,
        stat=historical_stat,
        percentile=offer.price_percentile or 50,
        watch=watch,
    )
    deal = db.scalar(
        select(Deal).where(
            Deal.watch_id == watch.id, Deal.fingerprint_hash == offer.fingerprint_hash
        )
    )
    if deal is None:
        deal = Deal(
            watch_id=watch.id,
            kind=offer.kind.value,
            source=offer.source,
            total_price=offer.total_price,
            currency=offer.currency,
            fingerprint_hash=offer.fingerprint_hash,
            offer_ref=offer.fingerprint_hash[:16],
        )
    deal.quality_index = offer.quality_index
    deal.value_score = offer.value_score
    deal.price_percentile = offer.price_percentile
    deal.timing_advice = offer.timing_advice
    deal.framing = _framing_for_watch(watch)
    deal.summary_text = (
        f"{pricing_signal(watch=watch, offer=offer, percentile=offer.price_percentile or 50, stat=historical_stat)} "
        f"{summary_context} {offer.timing_advice or ''}".strip()
    )
    deal.coverage_report_json = _coverage_json(coverage_report)
    deal.validation_warnings_json = [_validation_json(item) for item in validation_warnings]
    deal.loyalty_plan_json = [_loyalty_json(item) for item in loyalty_plan]
    deal.status = DealStatus.PROPOSED
    deal.expires_at = datetime.now(UTC) + DEAL_TTL
    deal.payload_json = {
        **offer.raw_payload,
        "historical_context": summary_context,
        "target_price": str(target_price) if target_price is not None else None,
        "glide_limit": str(glide_limit) if glide_limit is not None else None,
    }
    db.add(deal)
    db.flush()
    return deal


def _upsert_bundle_deal(
    *,
    db: Session,
    watch: TripWatch,
    flight: NormalizedOffer,
    hotel: NormalizedOffer,
    car: NormalizedOffer | None,
    total_price: Decimal,
    quality_index: float,
    value_score: float,
    summary: str,
    coverage_report: CoverageReport,
    validation_warnings: list[ValidationWarning],
    loyalty_plan: list[LoyaltyPlanEntry],
) -> Deal:
    flight_stat = _get_price_stat(db=db, watch=watch, offer=flight)
    summary_context = price_context(
        offer=flight,
        stat=flight_stat,
        percentile=flight.price_percentile or 50,
        watch=watch,
    )
    component_fingerprints = [flight.fingerprint_hash, hotel.fingerprint_hash]
    if car is not None:
        component_fingerprints.append(car.fingerprint_hash)
    bundle_fingerprint = hashlib.sha256(
        json.dumps(component_fingerprints, sort_keys=True).encode("utf-8")
    ).hexdigest()
    deal = db.scalar(
        select(Deal).where(Deal.watch_id == watch.id, Deal.fingerprint_hash == bundle_fingerprint)
    )
    if deal is None:
        deal = Deal(
            watch_id=watch.id,
            kind="trip_bundle",
            source="+".join(
                filter(None, [flight.source, hotel.source, car.source if car else None])
            ),
            total_price=total_price,
            currency=flight.currency,
            fingerprint_hash=bundle_fingerprint,
            offer_ref=bundle_fingerprint[:16],
        )
    deal.total_price = total_price
    deal.currency = flight.currency
    deal.quality_index = quality_index
    deal.value_score = value_score
    deal.price_percentile = min(
        value for value in [flight.price_percentile, hotel.price_percentile] if value is not None
    )
    deal.timing_advice = flight.timing_advice
    deal.framing = _framing_for_watch(watch)
    deal.summary_text = f"{summary} {summary_context}".strip()
    deal.coverage_report_json = _coverage_json(coverage_report)
    deal.validation_warnings_json = [_validation_json(item) for item in validation_warnings]
    deal.loyalty_plan_json = [_loyalty_json(item) for item in loyalty_plan]
    deal.status = DealStatus.PROPOSED
    deal.expires_at = datetime.now(UTC) + DEAL_TTL
    deal.payload_json = {
        "components": {
            "flight": flight.raw_payload,
            "hotel": hotel.raw_payload,
            "car": car.raw_payload if car else None,
        },
        "historical_context": summary_context,
        "target_price": str(target_price_for_offer(watch=watch, stat=flight_stat))
        if target_price_for_offer(watch=watch, stat=flight_stat) is not None
        else None,
        "glide_limit": str(glide_price_limit(watch=watch, offer=flight, stat=flight_stat))
        if glide_price_limit(watch=watch, offer=flight, stat=flight_stat) is not None
        else None,
    }
    db.add(deal)
    db.flush()
    return deal


def _visible_observations_for_watch(
    *,
    db: Session,
    watch: TripWatch,
    mock_data_enabled: bool,
) -> list[PriceObservation]:
    observations = list(
        db.scalars(
            select(PriceObservation)
            .where(PriceObservation.watch_id == watch.id)
            .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        )
    )
    if mock_data_enabled:
        return observations
    return [item for item in observations if not source_is_simulated(item.source)]


def _visible_deals_for_watch(
    *,
    db: Session,
    watch: TripWatch,
    mock_data_enabled: bool,
) -> list[Deal]:
    deals = list(
        db.scalars(
            select(Deal)
            .where(Deal.watch_id == watch.id)
            .order_by(Deal.value_score.desc().nullslast(), Deal.created_at.desc())
        )
    )
    if mock_data_enabled:
        return deals
    return [deal for deal in deals if not source_is_simulated(deal.source)]


def _latest_deal_for_watch(
    *,
    db: Session,
    watch: TripWatch,
    mock_data_enabled: bool,
) -> Deal | None:
    deals = _visible_deals_for_watch(
        db=db,
        watch=watch,
        mock_data_enabled=mock_data_enabled,
    )
    return deals[0] if deals else None


def _best_deal_for_watches(
    *,
    db: Session,
    watches: list[TripWatch],
    mock_data_enabled: bool,
) -> Deal | None:
    if not watches:
        return None
    watch_ids = [watch.id for watch in watches]
    deals = list(
        db.scalars(
            select(Deal)
            .where(Deal.watch_id.in_(watch_ids))
            .order_by(Deal.value_score.desc().nullslast(), Deal.created_at.desc())
        )
    )
    if not mock_data_enabled:
        deals = [deal for deal in deals if not source_is_simulated(deal.source)]
    return deals[0] if deals else None


def _readiness_for_watch(
    *,
    db: Session,
    user: User,
    watch: TripWatch,
    travelers: list[Traveler],
    current_deal: Deal | None,
):
    payment_methods = list(
        db.scalars(
            select(PaymentMethod)
            .where(PaymentMethod.user_id == user.id)
            .order_by(PaymentMethod.label)
        )
    )
    return build_deal_readiness_assessment(
        user=user,
        watch=watch,
        deal=current_deal,
        travelers=travelers,
        payment_methods=payment_methods,
        live_inventory_available=live_inventory_available(db=db),
        mock_data_enabled=get_mock_data_enabled(db=db),
    )


def _serialize_current_deal(
    deal: Deal | None,
    *,
    readiness: object | None = None,
) -> WatchCurrentDealResponse | None:
    if deal is None:
        return None
    badges = build_semantic_badges(deal=deal, readiness=readiness)
    return WatchCurrentDealResponse(
        id=str(deal.id),
        kind=deal.kind,
        framing=deal.framing,
        total_price=deal.total_price,
        currency=deal.currency,
        quality_index=deal.quality_index,
        value_score=deal.value_score,
        price_percentile=deal.price_percentile,
        timing_advice=deal.timing_advice,
        summary_text=deal.summary_text,
        status=deal.status.value,
        created_at=deal.created_at,
        readiness=ReadinessResponse.model_validate(asdict(readiness)) if readiness else None,
        badges=[SemanticBadgeResponse.model_validate(asdict(badge)) for badge in badges],
    )


def _serialize_search_now_deal(
    *,
    db: Session,
    user: User,
    watch: TripWatch,
    travelers: list[Traveler],
    deal: Deal,
) -> SearchNowDealResponse:
    readiness = _readiness_for_watch(
        db=db,
        user=user,
        watch=watch,
        travelers=travelers,
        current_deal=deal,
    )
    badges = build_semantic_badges(deal=deal, readiness=readiness)
    return SearchNowDealResponse(
        id=str(deal.id),
        kind=deal.kind,
        source=deal.source,
        total_price=deal.total_price,
        currency=deal.currency,
        quality_index=deal.quality_index,
        value_score=deal.value_score,
        price_percentile=deal.price_percentile,
        timing_advice=deal.timing_advice,
        framing=deal.framing,
        summary_text=deal.summary_text,
        coverage_report=_coverage_to_response_json(deal.coverage_report_json),
        validation_warnings=[
            ValidationWarningResponse.model_validate(item)
            for item in (deal.validation_warnings_json or [])
        ],
        loyalty_plan=[
            LoyaltyPlanEntryResponse.model_validate(item) for item in (deal.loyalty_plan_json or [])
        ],
        status=deal.status.value,
        readiness=ReadinessResponse.model_validate(asdict(readiness)),
        badges=[SemanticBadgeResponse.model_validate(asdict(badge)) for badge in badges],
    )


def _queue_deal_notifications(
    *,
    db: Session,
    user: User,
    watch: TripWatch,
    deals: list[Deal],
) -> list[NotificationDelivery]:
    if not deals:
        return []
    best_deal = sorted(
        [deal for deal in deals if deal.status == DealStatus.PROPOSED],
        key=lambda deal: (-(deal.value_score or 0), deal.total_price),
    )
    if not best_deal:
        return []
    candidate = best_deal[0]
    already_notified = db.scalar(
        select(NotificationDelivery.id).where(
            NotificationDelivery.deal_id == candidate.id,
            NotificationDelivery.message_type == "deal.proposed",
        )
    )
    if already_notified is not None:
        return []

    token_service = SignedTokenService()
    signed = issue_approval_token(deal=candidate, user=user, token_service=token_service)
    approval_url = _approval_url(
        deal_id=str(candidate.id), watch_id=str(watch.id), token=signed.token
    )
    subject = f"TRAMP deal ready: {_route_label(watch)}"
    body = "\n".join(
        [
            f"Best value found for {_route_label(watch)}.",
            f"Price: {_format_price(candidate.total_price, candidate.currency)}",
            candidate.summary_text or "A new deal is ready for review.",
            "Open your secure review link to confirm or reject:",
            approval_url,
            "If you reject it, choose the closest reason so TRAMP can learn from it.",
        ]
    )
    deliveries = queue_notification(
        db=db,
        user=user,
        message_type="deal.proposed",
        subject=subject,
        body=body,
        deal=candidate,
        channel=watch.notify_channel or NotificationChannel.INHERIT,
    )
    db.add(candidate)
    return deliveries


def _approval_url(*, deal_id: str, watch_id: str, token: str) -> str:
    settings = get_settings()
    base = str(settings.public_base_url).rstrip("/")
    return f"{base}/deals/{quote(deal_id)}?watchId={quote(watch_id)}&approvalToken={quote(token)}"


def _enqueue_notification_tasks(deliveries: list[NotificationDelivery]) -> None:
    for delivery in deliveries:
        celery_app.send_task("travel_watch.send_notification_delivery", args=[str(delivery.id)])


def _offer_meets_watch_gates(
    *,
    watch: TripWatch,
    offer: NormalizedOffer,
    historical_stat: PriceStat | None = None,
) -> bool:
    if bool(offer.raw_payload.get("_rejected_by_learning")):
        return False
    if watch.quality_floor is not None and offer.quality_index < watch.quality_floor:
        return False
    if watch.value_target is not None and offer.value_score is not None:
        band_low = watch.value_target * (1 - (watch.band_tolerance or 0))
        band_low *= 1 - min(max(watch.value_pressure or 0.0, 0.0), 1.0) * 0.35
        if offer.value_score < band_low:
            return False
    glide_limit = glide_price_limit(watch=watch, offer=offer, stat=historical_stat)
    if glide_limit is not None and offer.total_price > glide_limit:
        return False
    if offer.kind == ObservationKind.FLIGHT and watch.flight_budget_max is not None:
        return offer.total_price <= watch.flight_budget_max
    if offer.kind == ObservationKind.HOTEL and watch.hotel_budget_per_night_max is not None:
        return offer.total_price <= watch.hotel_budget_per_night_max
    return True


def _get_price_stat(*, db: Session, watch: TripWatch, offer: NormalizedOffer) -> PriceStat | None:
    scope_type, scope_key = _price_scope_for_offer(offer)
    month_bucket = month_bucket_for_watch(watch)
    return db.scalar(
        select(PriceStat).where(
            PriceStat.scope_type == scope_type,
            PriceStat.scope_key == scope_key,
            PriceStat.month_bucket == month_bucket,
        )
    )


def _price_scope_for_offer(offer: NormalizedOffer) -> tuple[PriceScopeType, str]:
    scope_type = (
        PriceScopeType.ROUTE_CABIN
        if offer.kind == ObservationKind.FLIGHT
        else PriceScopeType.HOTEL_AREA
    )
    scope_key = str(offer.raw_payload.get("scope_key") or offer.title)
    return scope_type, scope_key


def _percentile_value(prices: list[Decimal], percentile: float) -> Decimal:
    if not prices:
        return Decimal("0.00")
    if len(prices) == 1:
        return prices[0].quantize(Decimal("0.01"))
    position = (len(prices) - 1) * percentile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(prices) - 1)
    lower = prices[lower_index]
    upper = prices[upper_index]
    if lower_index == upper_index:
        return lower.quantize(Decimal("0.01"))
    weight = Decimal(str(position - lower_index))
    return (lower + ((upper - lower) * weight)).quantize(Decimal("0.01"))


def _select_draft_group(
    *,
    traveler_groups: list[TravelerGroup],
    watch: TripWatch | None,
    template: TripTemplate | None,
) -> TravelerGroup | None:
    if watch and watch.traveler_group_id:
        for group in traveler_groups:
            if group.id == watch.traveler_group_id:
                return group
    if template is not None:
        template_group_name = (
            str(template.watch_payload_json.get("travelerGroup") or "").strip().lower()
        )
        for group in traveler_groups:
            if group.name.lower() == template_group_name:
                return group
    return traveler_groups[0] if traveler_groups else None


def _draft_defaults_from_sources(
    *,
    preference: UserPreference | None,
    template_payload: dict[str, object],
    selected_group: TravelerGroup | None,
) -> dict[str, object]:
    origin_iatas = list(preference.home_airports) if preference and preference.home_airports else []
    template_origin = template_payload.get("origin") or template_payload.get("origins")
    template_destination = template_payload.get("destination")
    flight_budget = template_payload.get("flightBudgetMax")
    hotel_budget = template_payload.get("hotelBudgetPerNightMax")
    destination_mode = (
        DestinationMode.FLEXIBLE
        if not template_destination and template_payload.get("flexibleRegion")
        else DestinationMode.FIXED
    )
    return {
        "origin_iatas": origin_iatas
        or (_split_csv(str(template_origin)) if template_origin else []),
        "destination_label": str(
            template_destination or template_payload.get("flexibleRegion") or "Singapore"
        ),
        "date_window": str(template_payload.get("dateWindow") or "12 Apr - 19 Apr"),
        "stay_length": str(template_payload.get("stayLength") or "5-9 nights"),
        "flight_budget": str(flight_budget or "USD 1,200"),
        "hotel_budget": str(hotel_budget or "USD 280 / night"),
        "luxury_vs_savings": (preference.default_luxury_vs_savings if preference else 0.6),
        "watch_defaults": {
            "trip_mode": "flights_then_hotels",
            "traveler_group_id": str(selected_group.id) if selected_group else None,
            "traveler_ids": [
                str(traveler_id)
                for traveler_id in (selected_group.traveler_ids if selected_group else [])
            ],
            "origin_iatas": origin_iatas
            or (_split_csv(str(template_origin)) if template_origin else []),
            "destination_iatas": [str(template_destination).upper()]
            if template_destination
            else [],
            "destination_mode": destination_mode.value,
            "flexible_region": template_payload.get("flexibleRegion"),
            "depart_date_from": None,
            "depart_date_to": None,
            "return_date_from": None,
            "return_date_to": None,
            "trip_min_nights": 5,
            "trip_max_nights": 9,
            "cabin_class": (
                preference.default_cabin if preference and preference.default_cabin else "economy"
            ),
            "flight_budget_max": _numeric_budget(flight_budget),
            "hotel_budget_per_night_max": _numeric_budget(hotel_budget),
            "budget_currency": "USD",
            "avoid_redeye": preference.avoid_redeye if preference else False,
            "prefer_refundable": preference.prefer_refundable if preference else False,
            "refresh_interval": "daily",
            "notify_channel": (
                preference.default_notify_channel.value
                if preference and preference.default_notify_channel != NotificationChannel.INHERIT
                else NotificationChannel.INHERIT.value
            ),
        },
    }


def _watch_to_defaults(*, db: Session, watch: TripWatch) -> dict[str, object]:
    group = _get_watch_traveler_group(db=db, watch=watch)
    return {
        "origin_iatas": list(watch.origin_iatas or []),
        "destination_label": _route_destination_label(watch),
        "date_window": _date_label(watch),
        "stay_length": _stay_length_label(watch),
        "flight_budget": _format_price(watch.flight_budget_max, watch.budget_currency)
        if watch.flight_budget_max
        else "",
        "hotel_budget": (
            f"{_format_price(watch.hotel_budget_per_night_max, watch.budget_currency)} / night"
            if watch.hotel_budget_per_night_max
            else ""
        ),
        "luxury_vs_savings": watch.luxury_vs_savings,
        "watch_defaults": {
            "trip_mode": watch.trip_mode.value,
            "traveler_group_id": str(group.id) if group else None,
            "traveler_ids": _current_watch_traveler_ids(db=db, watch=watch),
            "origin_iatas": list(watch.origin_iatas or []),
            "destination_iatas": list(watch.destination_iatas or []),
            "destination_mode": watch.destination_mode.value,
            "flexible_region": watch.flexible_region,
            "flexible_theme": watch.flexible_theme,
            "depart_date_from": watch.depart_date_from.isoformat()
            if watch.depart_date_from
            else None,
            "depart_date_to": watch.depart_date_to.isoformat() if watch.depart_date_to else None,
            "return_date_from": watch.return_date_from.isoformat()
            if watch.return_date_from
            else None,
            "return_date_to": watch.return_date_to.isoformat() if watch.return_date_to else None,
            "trip_min_nights": watch.trip_min_nights,
            "trip_max_nights": watch.trip_max_nights,
            "cabin_class": watch.cabin_class,
            "flight_budget_max": str(watch.flight_budget_max)
            if watch.flight_budget_max is not None
            else None,
            "hotel_budget_per_night_max": (
                str(watch.hotel_budget_per_night_max)
                if watch.hotel_budget_per_night_max is not None
                else None
            ),
            "budget_currency": watch.budget_currency,
            "avoid_redeye": watch.avoid_redeye,
            "prefer_refundable": watch.prefer_refundable,
            "refresh_interval": watch.refresh_interval.value,
            "notify_channel": watch.notify_channel.value,
        },
    }


def _draft_options_from_defaults(*, defaults: dict[str, object]) -> list[str]:
    watch_defaults = defaults["watch_defaults"]
    options = [
        f"{watch_defaults['cabin_class']} cabin" if watch_defaults.get("cabin_class") else "",
        "Avoid red-eye" if watch_defaults.get("avoid_redeye") else "",
        "Refundable preferred" if watch_defaults.get("prefer_refundable") else "",
        (
            f"Notify via {watch_defaults['notify_channel']}"
            if watch_defaults.get("notify_channel")
            and watch_defaults["notify_channel"] != "inherit"
            else ""
        ),
        (
            f"{watch_defaults['refresh_interval'].replace('_', ' ')} refresh"
            if watch_defaults.get("refresh_interval")
            else ""
        ),
    ]
    return [option for option in options if option]


def _route_label(watch: TripWatch) -> str:
    origin = ", ".join(watch.origin_iatas or []) or "Anywhere"
    destination = _route_destination_label(watch)
    return f"{origin} -> {destination}"


def _route_destination_label(watch: TripWatch) -> str:
    if watch.destination_mode == DestinationMode.FIXED:
        return ", ".join(watch.destination_iatas or []) or "Anywhere"
    if watch.flexible_region:
        return watch.flexible_region
    if watch.flexible_theme:
        return f"Anywhere {watch.flexible_theme}"
    return "Flexible"


def _date_label(watch: TripWatch) -> str:
    if watch.depart_date_from and watch.return_date_to:
        return (
            f"{watch.depart_date_from.strftime('%d %b')} - {watch.return_date_to.strftime('%d %b')}"
        )
    if watch.depart_date_from and watch.depart_date_to:
        return (
            f"{watch.depart_date_from.strftime('%d %b')} - {watch.depart_date_to.strftime('%d %b')}"
        )
    if watch.depart_date_from:
        return watch.depart_date_from.strftime("%d %b")
    return "Dates flexible"


def _stay_length_label(watch: TripWatch) -> str:
    if watch.trip_min_nights and watch.trip_max_nights:
        return f"{watch.trip_min_nights}-{watch.trip_max_nights} nights"
    if watch.trip_min_nights:
        return f"{watch.trip_min_nights}+ nights"
    return "Flexible stay"


def _travelers_label(travelers: list[Traveler]) -> str:
    if not travelers:
        return "No travelers selected"
    if len(travelers) == 1:
        return travelers[0].display_name
    return f"{len(travelers)} travelers"


def _cadence_label(watch: TripWatch) -> str:
    mapping = {
        "daily": "Daily refresh",
        "6h": "6h refresh",
        "hourly": "Hourly refresh",
    }
    return mapping.get(watch.refresh_interval.value, watch.refresh_interval.value)


def _format_price(amount: Decimal | None, currency: str | None) -> str:
    if amount is None:
        return "No price"
    return f"{(currency or 'USD').upper()} {amount:,.2f}"


def _default_framing_label(watch: TripWatch) -> str:
    return _framing_for_watch(watch).value.replace("_", " ").title()


def _framing_for_watch(watch: TripWatch) -> DealFraming:
    if watch.luxury_vs_savings >= 0.75:
        return DealFraming.MAX_LUXURY
    if watch.luxury_vs_savings <= 0.30:
        return DealFraming.CHEAPEST_OK
    return DealFraming.BEST_VALUE


def _dashboard_confidence_label(*, watches: list[WatchDashboardCardResponse]) -> str:
    if not watches:
        return "Low"
    if any("No stored deals yet" in watch.insight for watch in watches):
        return "Medium"
    return "High"


def _coverage_json(coverage_report: CoverageReport) -> dict[str, object]:
    return {
        "confidence": coverage_report.confidence,
        "searched_sources": coverage_report.searched_sources,
        "gaps": coverage_report.gaps,
        "notes": coverage_report.notes,
    }


def _validation_json(item: ValidationWarning) -> dict[str, object]:
    return {
        "code": item.code,
        "severity": item.severity,
        "message": item.message,
        "traveler_name": item.traveler_name,
    }


def _loyalty_json(item: LoyaltyPlanEntry) -> dict[str, object]:
    return {
        "traveler_name": item.traveler_name,
        "program_code": item.program_code,
        "alliance": item.alliance,
        "note": item.note,
    }


def _coverage_to_response(coverage_report: CoverageReport) -> CoverageReportResponse:
    return CoverageReportResponse(
        confidence=coverage_report.confidence,
        searched_sources=coverage_report.searched_sources,
        gaps=coverage_report.gaps,
        notes=coverage_report.notes,
    )


def _coverage_to_response_json(value: dict[str, object] | None) -> CoverageReportResponse | None:
    if value is None:
        return None
    return CoverageReportResponse.model_validate(value)


def _numeric_budget(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    digits = "".join(
        character for character in str(raw_value) if character.isdigit() or character == "."
    )
    return digits or None


def _split_csv(raw_value: str) -> list[str]:
    return [part.strip().upper() for part in raw_value.split(",") if part.strip()]
