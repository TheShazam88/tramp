from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_writer_lock
from app.api.schemas.deals import (
    ApprovalTokenResponse,
    ApprovalTokenVerifyResponse,
    DealIntentResponse,
    DealTimelinePointResponse,
    DealTimelineResponse,
    StoredDealResponse,
)
from app.api.schemas.watches import (
    CoverageReportResponse,
    CtaActionResponse,
    LoyaltyPlanEntryResponse,
    ReadinessResponse,
    SemanticBadgeResponse,
    ValidationWarningResponse,
)
from app.approval_service import (
    approval_token_expiry,
    issue_approval_token,
    verify_approval_token,
)
from app.db.models import (
    AuditLog,
    Booking,
    Deal,
    DealFeedback,
    DealStatus,
    FeedbackSignalType,
    PaymentMethod,
    PriceObservation,
    RejectedFingerprint,
    SuppressedAttribute,
    SuppressedAttributeType,
    Traveler,
    TravelerGroup,
    TripWatch,
    User,
    WatchTraveler,
)
from app.integrations.service import (
    get_mock_data_enabled,
    live_inventory_available,
    source_is_simulated,
)
from app.security.tokens import SignedTokenService
from app.security.totp import verify_totp_code
from app.service_errors import ConflictError
from app.travel_readiness import (
    build_deal_actions,
    build_deal_readiness_assessment,
    build_semantic_badges,
)


def list_deals_for_watch(*, db: Session, user: User, watch_id: UUID) -> list[StoredDealResponse]:
    _get_owned_watch_or_404(db=db, user=user, watch_id=watch_id)
    mock_data_enabled = get_mock_data_enabled(db=db)
    deals = list(
        db.scalars(
            select(Deal)
            .where(Deal.watch_id == watch_id)
            .order_by(Deal.created_at.desc(), Deal.value_score.desc().nullslast())
        )
    )
    if not mock_data_enabled:
        deals = [deal for deal in deals if not source_is_simulated(deal.source)]
    return [serialize_stored_deal(db=db, deal=deal) for deal in deals]


def get_deal(*, db: Session, user: User, deal_id: UUID) -> StoredDealResponse:
    deal = get_owned_deal_record(db=db, user=user, deal_id=deal_id)
    return serialize_stored_deal(db=db, deal=deal)


def get_deal_timeline(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
) -> DealTimelineResponse:
    deal = get_owned_deal_record(db=db, user=user, deal_id=deal_id)
    watch = get_owned_watch_for_deal(db=db, user=user, deal=deal)
    mock_data_enabled = get_mock_data_enabled(db=db)
    observations = list(
        db.scalars(
            select(PriceObservation)
            .where(PriceObservation.watch_id == watch.id)
            .order_by(PriceObservation.observed_at.desc(), PriceObservation.id.desc())
        )
    )
    if not mock_data_enabled:
        observations = [item for item in observations if not source_is_simulated(item.source)]
    observations = [
        observation for observation in observations if observation.currency == deal.currency
    ]
    points = _build_timeline_points(
        deal=deal,
        watch=watch,
        observations=observations,
    )
    trend_summary = "Waiting for more history."
    if len(points) >= 2:
        latest_point = points[0]
        earlier_point = points[-1]
        delta = latest_point.price - earlier_point.price
        if delta < 0:
            trend_summary = (
                f"Down {abs(delta):.2f} {latest_point.currency} across the recent saved history."
            )
        elif delta > 0:
            trend_summary = (
                f"Up {delta:.2f} {latest_point.currency} across the recent saved history."
            )
        else:
            trend_summary = "Flat across the recent saved history."
    elif points:
        trend_summary = "One saved price point is available so far."

    return DealTimelineResponse(
        current_price=deal.total_price,
        currency=deal.currency,
        target_price=_decimal_from_payload(deal.payload_json, "target_price"),
        glide_limit=_decimal_from_payload(deal.payload_json, "glide_limit"),
        trend_summary=trend_summary,
        points=list(reversed(points)),
    )


def create_approval_token(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    token_service: SignedTokenService,
) -> ApprovalTokenResponse:
    acquire_activity_writer_lock(db)
    deal = get_owned_deal_record(db=db, user=user, deal_id=deal_id)
    _require_deal_proposed(deal)
    signed = issue_approval_token(deal=deal, user=user, token_service=token_service)
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return ApprovalTokenResponse(
        deal_id=str(deal.id),
        token=signed.token,
        expires_at=signed.expires_at,
    )


def verify_existing_approval_token(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    token: str,
    token_service: SignedTokenService,
) -> ApprovalTokenVerifyResponse:
    deal = get_owned_deal_record(db=db, user=user, deal_id=deal_id)
    _require_deal_proposed(deal)
    claims = verify_approval_token(deal=deal, user=user, token=token, token_service=token_service)
    return ApprovalTokenVerifyResponse(
        deal_id=str(deal.id),
        valid=True,
        expires_at=approval_token_expiry(claims),
    )


def confirm_deal_intent(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    token: str,
    totp_code: str,
    token_service: SignedTokenService,
) -> DealIntentResponse:
    acquire_activity_writer_lock(db)
    deal = get_owned_deal_record(db=db, user=user, deal_id=deal_id)
    _require_deal_proposed(deal)
    if not user.totp_secret or not verify_totp_code(secret=user.totp_secret, code=totp_code):
        raise ValueError("A valid TOTP code is required to confirm this deal.")
    verify_approval_token(deal=deal, user=user, token=token, token_service=token_service)
    deal.status = DealStatus.CONFIRMED
    deal.rejected_reason = None
    deal.confirm_token_hash = None
    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action="deal.confirmed",
            target=f"deal:{deal.id}",
            amount=deal.total_price,
            currency=deal.currency,
            at=datetime.now(UTC),
            meta_json={"watch_id": str(deal.watch_id)},
        )
    )
    db.add(deal)
    db.commit()
    db.refresh(deal)
    return DealIntentResponse(
        deal_id=str(deal.id),
        status=deal.status.value,
        detail="Approval intent recorded. Booking remains a separate deterministic step in V3.",
    )


def reject_deal(
    *,
    db: Session,
    user: User,
    deal_id: UUID,
    reason: str,
) -> DealIntentResponse:
    acquire_activity_writer_lock(db)
    deal = get_owned_deal_record(db=db, user=user, deal_id=deal_id)
    _require_deal_proposed(deal)
    watch = get_owned_watch_for_deal(db=db, user=user, deal=deal)
    simulated_deal = source_is_simulated(deal.source)
    if simulated_deal:
        action_taken: dict[str, object] = {
            "reason": reason.strip().lower(),
            "durable_learning_applied": False,
            "simulated_deal": True,
        }
    else:
        action_taken = _apply_rejection_feedback(
            db=db,
            watch=watch,
            deal=deal,
            reason=reason,
        )
    feedback = DealFeedback(
        watch_id=watch.id,
        deal_id=deal.id,
        rejected_value_score=deal.value_score,
        reason=reason,
        signal_type=_signal_type_for_reason(reason),
        action_taken_json=action_taken,
    )
    deal.status = DealStatus.REJECTED
    deal.rejected_reason = reason
    deal.confirm_token_hash = None
    db.add(feedback)
    db.add(deal)
    db.add(watch)
    db.add(
        AuditLog(
            actor=f"user:{user.id}",
            action="deal.rejected",
            target=f"deal:{deal.id}",
            amount=deal.total_price,
            currency=deal.currency,
            at=datetime.now(UTC),
            meta_json={"watch_id": str(watch.id), "reason": reason, "action_taken": action_taken},
        )
    )
    db.commit()
    db.refresh(deal)
    return DealIntentResponse(
        deal_id=str(deal.id),
        status=deal.status.value,
        detail=(
            "Test feedback recorded without changing durable learning."
            if simulated_deal
            else "Rejection recorded. TRAMP will use this feedback to improve future proposals."
        ),
        action_taken=action_taken,
    )


def get_owned_deal_record(*, db: Session, user: User, deal_id: UUID) -> Deal:
    deal = db.scalar(
        select(Deal)
        .join(TripWatch, TripWatch.id == Deal.watch_id)
        .where(Deal.id == deal_id, TripWatch.user_id == user.id)
    )
    if deal is None or (not get_mock_data_enabled(db=db) and source_is_simulated(deal.source)):
        raise LookupError("Deal not found.")
    return deal


def get_owned_watch_for_deal(*, db: Session, user: User, deal: Deal) -> TripWatch:
    watch = db.scalar(
        select(TripWatch).where(TripWatch.id == deal.watch_id, TripWatch.user_id == user.id)
    )
    if watch is None:
        raise LookupError("Watch not found.")
    return watch


def serialize_stored_deal(*, db: Session, deal: Deal) -> StoredDealResponse:
    booking_id = db.scalar(select(Booking.id).where(Booking.deal_id == deal.id))
    watch = db.scalar(select(TripWatch).where(TripWatch.id == deal.watch_id))
    travelers = _travelers_for_watch(db=db, watch=watch) if watch is not None else []
    payment_methods = (
        list(db.scalars(select(PaymentMethod).where(PaymentMethod.user_id == watch.user_id)))
        if watch is not None
        else []
    )
    readiness = (
        build_deal_readiness_assessment(
            user=_user_for_watch(db=db, watch=watch),
            watch=watch,
            deal=deal,
            travelers=travelers,
            payment_methods=payment_methods,
            live_inventory_available=live_inventory_available(db=db),
            mock_data_enabled=get_mock_data_enabled(db=db),
        )
        if watch is not None
        else None
    )
    badges = build_semantic_badges(deal=deal, readiness=readiness)
    return StoredDealResponse(
        id=str(deal.id),
        watch_id=str(deal.watch_id),
        booking_id=str(booking_id) if booking_id else None,
        kind=deal.kind,
        source=deal.source,
        offer_ref=deal.offer_ref,
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
        payload=deal.payload_json,
        status=deal.status.value,
        expires_at=deal.expires_at,
        created_at=deal.created_at,
        readiness=ReadinessResponse.model_validate(asdict(readiness)) if readiness else None,
        badges=[SemanticBadgeResponse.model_validate(asdict(badge)) for badge in badges],
        cta_actions=[
            CtaActionResponse.model_validate(asdict(action))
            for action in build_deal_actions(deal=deal, readiness=readiness)
        ]
        if readiness
        else [],
    )


def _coverage_to_response_json(value: dict[str, object] | None) -> CoverageReportResponse | None:
    if value is None:
        return None
    return CoverageReportResponse.model_validate(value)


def _require_deal_proposed(deal: Deal) -> None:
    if deal.status != DealStatus.PROPOSED:
        raise ConflictError("Only proposed deals can be approved or rejected.")
    if deal.expires_at is None:
        return
    expires_at = deal.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise ConflictError("This deal has expired. Refresh the watch before continuing.")


def _decimal_from_payload(payload: dict[str, object] | None, key: str) -> Decimal | None:
    if not payload:
        return None
    value = payload.get(key)
    if value in {None, ""}:
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_timeline_points(
    *,
    deal: Deal,
    watch: TripWatch,
    observations: list[PriceObservation],
) -> list[DealTimelinePointResponse]:
    observations_by_run: dict[datetime, list[PriceObservation]] = {}
    for observation in observations:
        observations_by_run.setdefault(observation.observed_at, []).append(observation)

    points: list[DealTimelinePointResponse] = []
    for observed_at in sorted(observations_by_run, reverse=True):
        run_observations = observations_by_run[observed_at]
        if deal.kind == "trip_bundle":
            point = _bundle_timeline_point(
                watch=watch,
                observed_at=observed_at,
                observations=run_observations,
                currency=deal.currency,
            )
        else:
            candidates = [
                observation
                for observation in run_observations
                if observation.kind.value == deal.kind
            ]
            point = (
                _single_timeline_point(min(candidates, key=lambda item: item.price))
                if candidates
                else None
            )
        if point is not None:
            points.append(point)
        if len(points) == 12:
            break
    return points


def _single_timeline_point(
    observation: PriceObservation,
) -> DealTimelinePointResponse:
    payload = observation.payload_json or {}
    return DealTimelinePointResponse(
        observed_at=observation.observed_at,
        price=observation.price,
        currency=observation.currency,
        label=str(payload.get("title") or observation.kind.value.title()),
        source=observation.source,
        price_percentile=_to_float(payload.get("price_percentile")),
    )


def _bundle_timeline_point(
    *,
    watch: TripWatch,
    observed_at: datetime,
    observations: list[PriceObservation],
    currency: str,
) -> DealTimelinePointResponse | None:
    by_kind = {
        kind: min(
            (item for item in observations if item.kind.value == kind),
            key=lambda item: item.price,
            default=None,
        )
        for kind in ("flight", "hotel", "car")
    }
    flight = by_kind["flight"]
    hotel = by_kind["hotel"]
    car = by_kind["car"]
    if flight is None or hotel is None or (watch.want_car and car is None):
        return None

    nights = watch.trip_min_nights or watch.trip_max_nights or 4
    price = flight.price + (hotel.price * Decimal(nights))
    sources = [flight.source, hotel.source]
    if watch.want_car and car is not None:
        price += car.price
        sources.append(car.source)
    return DealTimelinePointResponse(
        observed_at=observed_at,
        price=price,
        currency=currency,
        label="Best comparable trip bundle",
        source="+".join(sources),
        price_percentile=_to_float((flight.payload_json or {}).get("price_percentile")),
    )


def _user_for_watch(*, db: Session, watch: TripWatch | None) -> User:
    if watch is None:
        raise LookupError("Watch not found.")
    user = db.scalar(select(User).where(User.id == watch.user_id))
    if user is None:
        raise LookupError("User not found.")
    return user


def _travelers_for_watch(*, db: Session, watch: TripWatch) -> list[Traveler]:
    traveler_ids = list(
        db.scalars(select(WatchTraveler.traveler_id).where(WatchTraveler.watch_id == watch.id))
    )
    if not traveler_ids and watch.traveler_group_id is not None:
        traveler_group = db.scalar(
            select(TravelerGroup).where(
                TravelerGroup.id == watch.traveler_group_id,
                TravelerGroup.user_id == watch.user_id,
            )
        )
        traveler_ids = list(traveler_group.traveler_ids) if traveler_group else []
    if not traveler_ids:
        return []

    travelers = list(
        db.scalars(
            select(Traveler).where(
                Traveler.id.in_(traveler_ids),
                Traveler.user_id == watch.user_id,
            )
        )
    )
    traveler_map = {traveler.id: traveler for traveler in travelers}
    return [
        traveler_map[traveler_id] for traveler_id in traveler_ids if traveler_id in traveler_map
    ]


def _get_owned_watch_or_404(*, db: Session, user: User, watch_id: UUID) -> TripWatch:
    watch = db.scalar(
        select(TripWatch).where(
            TripWatch.id == watch_id,
            TripWatch.user_id == user.id,
        )
    )
    if watch is None:
        raise LookupError("Watch not found.")
    return watch


def _apply_rejection_feedback(
    *,
    db: Session,
    watch: TripWatch,
    deal: Deal,
    reason: str,
) -> dict[str, object]:
    normalized_reason = reason.strip().lower()
    action_taken: dict[str, object] = {"reason": normalized_reason}
    payload = deal.payload_json or {}
    primary_payload = _primary_payload_for_reason(payload=payload, reason=normalized_reason)

    existing_rejected = db.scalar(
        select(RejectedFingerprint).where(
            RejectedFingerprint.watch_id == watch.id,
            RejectedFingerprint.fingerprint_hash == deal.fingerprint_hash,
        )
    )
    if existing_rejected is None:
        db.add(RejectedFingerprint(watch_id=watch.id, fingerprint_hash=deal.fingerprint_hash))
        action_taken["fingerprint_recorded"] = True

    if normalized_reason == "too_pricey":
        watch.value_pressure = min(round((watch.value_pressure or 0.0) + 0.10, 2), 1.0)
        action_taken["value_pressure"] = watch.value_pressure
        return action_taken

    if normalized_reason == "not_luxurious_enough":
        watch.quality_floor = min((watch.quality_floor or 40) + 5, 100)
        action_taken["quality_floor"] = watch.quality_floor
        return action_taken

    if normalized_reason == "layover_too_long":
        layover_minutes = int(primary_payload.get("layover_minutes") or 0)
        if layover_minutes > 0:
            tighter_limit = max(30, layover_minutes - 15)
            watch.max_layover_minutes = (
                min(watch.max_layover_minutes, tighter_limit)
                if watch.max_layover_minutes is not None
                else tighter_limit
            )
            action_taken["max_layover_minutes"] = watch.max_layover_minutes
        else:
            action_taken["note"] = "No layover duration was available to tighten."
        return action_taken

    if normalized_reason == "wrong_airline":
        value = str(
            primary_payload.get("airline_code") or primary_payload.get("supplier") or ""
        ).strip()
        if value:
            _upsert_suppression(
                db=db,
                watch=watch,
                attr_type=SuppressedAttributeType.AIRLINE,
                attr_value=value,
                weight=1.0,
            )
            action_taken["suppressed"] = [f"airline:{value}"]
        return action_taken

    if normalized_reason == "wrong_hotel":
        suppressed: list[str] = []
        for attr_type, key in (
            (SuppressedAttributeType.HOTEL_PROPERTY, "hotel_name"),
            (SuppressedAttributeType.HOTEL_CHAIN, "hotel_chain"),
        ):
            value = str(primary_payload.get(key) or "").strip()
            if value:
                _upsert_suppression(
                    db=db,
                    watch=watch,
                    attr_type=attr_type,
                    attr_value=value,
                    weight=1.0,
                )
                suppressed.append(f"{attr_type.value}:{value}")
        if suppressed:
            action_taken["suppressed"] = suppressed
        return action_taken

    if normalized_reason == "wrong_area":
        value = str(primary_payload.get("area_cluster") or "").strip()
        if value:
            _upsert_suppression(
                db=db,
                watch=watch,
                attr_type=SuppressedAttributeType.AREA_CLUSTER,
                attr_value=value,
                weight=1.0,
            )
            action_taken["suppressed"] = [f"area_cluster:{value}"]
        return action_taken

    watch.value_pressure = min(round((watch.value_pressure or 0.0) + 0.02, 2), 1.0)
    action_taken["value_pressure"] = watch.value_pressure
    action_taken["note"] = "Applied a mild value-pressure nudge for ambiguous feedback."
    return action_taken


def _signal_type_for_reason(reason: str) -> FeedbackSignalType:
    normalized_reason = reason.strip().lower()
    if normalized_reason in {"too_pricey", "not_luxurious_enough"}:
        return FeedbackSignalType.VALUE
    if normalized_reason in {"wrong_airline", "wrong_hotel", "wrong_area"}:
        return FeedbackSignalType.PREFERENCE
    if normalized_reason in {"layover_too_long"}:
        return FeedbackSignalType.CONSTRAINT
    return FeedbackSignalType.AMBIGUOUS


def _primary_payload_for_reason(*, payload: dict[str, object], reason: str) -> dict[str, object]:
    if "components" not in payload:
        return payload
    components = payload.get("components")
    if not isinstance(components, dict):
        return payload
    if reason in {"wrong_hotel", "wrong_area"} and isinstance(components.get("hotel"), dict):
        return components["hotel"]
    return components.get("flight") if isinstance(components.get("flight"), dict) else payload


def _upsert_suppression(
    *,
    db: Session,
    watch: TripWatch,
    attr_type: SuppressedAttributeType,
    attr_value: str,
    weight: float,
) -> None:
    existing = db.scalar(
        select(SuppressedAttribute).where(
            SuppressedAttribute.watch_id == watch.id,
            SuppressedAttribute.attr_type == attr_type,
            SuppressedAttribute.attr_value == attr_value,
        )
    )
    if existing is not None:
        existing.weight = max(existing.weight, weight)
        db.add(existing)
        return
    db.add(
        SuppressedAttribute(
            watch_id=watch.id,
            attr_type=attr_type,
            attr_value=attr_value,
            weight=weight,
        )
    )
