from __future__ import annotations

from app.db.models import TripWatch
from app.watch_types import NormalizedOffer, RejectionLearningOutcome


def _cabin_rank(cabin: str | None) -> float:
    normalized = (cabin or "").strip().lower().replace("_", " ")
    return {
        "economy": 1.0,
        "premium economy": 2.6,
        "business": 5.0,
        "first": 6.2,
    }.get(normalized, 1.4)


def _flight_optionality_bonus(*, watch: TripWatch, offer: NormalizedOffer) -> float:
    if offer.kind.value != "flight":
        return 0.0

    bonus = 0.0
    if not watch.cabin_class:
        bonus += watch.luxury_vs_savings * _cabin_rank(offer.cabin) * 4.2

    if watch.max_stops is None:
        stops = offer.stops or 0
        if stops == 0:
            bonus += 5.5
        elif stops == 1:
            bonus += 0.5
        else:
            bonus -= 4.5

    if watch.max_layover_minutes is None:
        duration = offer.duration_minutes or 0
        if duration and duration <= 430:
            bonus += 2.5
        elif duration and duration <= 510:
            bonus += 0.5
        elif duration and duration > 600:
            bonus -= 2.5

    if watch.min_connection_minutes is not None and offer.raw_payload.get("layover_minutes") is not None:
        layover = int(offer.raw_payload["layover_minutes"] or 0)
        if layover < watch.min_connection_minutes:
            bonus -= 5.0

    return bonus


def score_offer(
    *,
    watch: TripWatch,
    offer: NormalizedOffer,
    price_percentile: float,
    rejection_outcome: RejectionLearningOutcome,
) -> float:
    price_score = max(0.0, 100.0 - price_percentile)
    quality_component = offer.quality_index * 0.48
    price_component = price_score * 0.34
    refund_bonus = 5.0 if watch.prefer_refundable and offer.refundable else 0.0
    loyalty_bonus = watch.loyalty_weighting * 10.0
    savings_tilt = (1.0 - watch.luxury_vs_savings) * (price_score / 10.0)
    luxury_tilt = watch.luxury_vs_savings * (offer.quality_index / 10.0)
    optionality_bonus = _flight_optionality_bonus(watch=watch, offer=offer)
    raw_score = (
        quality_component
        + price_component
        + refund_bonus
        + loyalty_bonus
        + savings_tilt
        + luxury_tilt
        + optionality_bonus
        - (rejection_outcome.penalty * 12.0)
    )
    return round(max(0.0, min(100.0, raw_score)), 1)
