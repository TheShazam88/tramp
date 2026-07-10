# ruff: noqa: E501
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.db.models import PriceStat, TripWatch
from app.watch_types import NormalizedOffer


def percentile_rank(*, offer: NormalizedOffer, comparable_prices: list[Decimal]) -> float:
    if not comparable_prices:
        return 50.0
    sorted_prices = sorted(comparable_prices)
    rank = sum(price <= offer.total_price for price in sorted_prices)
    return round((rank / len(sorted_prices)) * 100, 1)


def historical_percentile_rank(
    *,
    offer: NormalizedOffer,
    comparable_prices: list[Decimal],
    stat: PriceStat | None = None,
) -> float:
    if stat is None or stat.sample_n < 4:
        return percentile_rank(offer=offer, comparable_prices=comparable_prices)

    price = offer.total_price
    p10 = stat.p10 or stat.p25 or stat.median or price
    p25 = stat.p25 or stat.median or p10
    median = stat.median or p25
    p75 = stat.p75 or median

    if price <= p10:
        return 10.0
    if price <= p25:
        return _interpolate(price=price, low=p10, high=p25, low_pct=10, high_pct=25)
    if price <= median:
        return _interpolate(price=price, low=p25, high=median, low_pct=25, high_pct=50)
    if price <= p75:
        return _interpolate(price=price, low=median, high=p75, low_pct=50, high_pct=75)
    if p75 == median:
        return 85.0
    return min(
        99.0,
        _interpolate(price=price, low=p75, high=(p75 * Decimal("1.25")), low_pct=75, high_pct=95),
    )


def target_price_for_offer(*, watch: TripWatch, stat: PriceStat | None = None) -> Decimal | None:
    if watch.ideal_price is not None:
        return watch.ideal_price
    if stat is None:
        return None
    if stat.sample_n >= 4 and stat.p25 is not None:
        return stat.p25
    if stat.median is not None:
        return (stat.median * Decimal("0.92")).quantize(Decimal("0.01"))
    return None


def glide_price_limit(
    *,
    watch: TripWatch,
    offer: NormalizedOffer,
    stat: PriceStat | None = None,
    now: datetime | None = None,
) -> Decimal | None:
    target = target_price_for_offer(watch=watch, stat=stat)
    ceiling = _ceiling_for_offer(watch=watch, offer=offer)
    if ceiling is None:
        return target
    if target is None or target >= ceiling:
        return ceiling

    current_time = now or datetime.now(UTC)
    departure_anchor = watch.depart_date_from or watch.depart_date_to
    if departure_anchor is None:
        return target

    days_out = (
        datetime.combine(departure_anchor, datetime.min.time(), tzinfo=UTC) - current_time
    ).days
    if days_out >= watch.glide_start_days:
        return target
    if days_out <= watch.glide_end_days:
        return ceiling

    window = max(watch.glide_start_days - watch.glide_end_days, 1)
    progressed = watch.glide_start_days - days_out
    ratio = Decimal(str(max(min(progressed / window, 1), 0)))
    return (target + ((ceiling - target) * ratio)).quantize(Decimal("0.01"))


def pricing_signal(
    *,
    watch: TripWatch,
    offer: NormalizedOffer,
    percentile: float,
    stat: PriceStat | None = None,
    now: datetime | None = None,
) -> str:
    target = target_price_for_offer(watch=watch, stat=stat)
    glide_limit = glide_price_limit(watch=watch, offer=offer, stat=stat, now=now)
    if target is not None and offer.total_price <= target:
        return "Below your active historical target."
    if glide_limit is not None and offer.total_price <= glide_limit:
        return "Inside the current glide-adjusted acceptance band."
    if watch.max_total_trip_spend is not None and offer.total_price > watch.max_total_trip_spend:
        return "Above your configured trip budget."
    if percentile <= 20:
        return "Pricing is near the bottom of the stored historical band."
    if percentile <= 40:
        return "Pricing is comfortably within the historical target zone."
    if percentile >= 75:
        return "Pricing is currently rich versus recent history."
    return "Pricing is mid-band relative to recent history."


def timing_advice(
    *,
    watch: TripWatch,
    offer: NormalizedOffer,
    percentile: float,
    stat: PriceStat | None = None,
    now: datetime | None = None,
) -> str:
    current_time = now or datetime.now(UTC)
    target = target_price_for_offer(watch=watch, stat=stat)
    glide_limit = glide_price_limit(watch=watch, offer=offer, stat=stat, now=current_time)
    departure_anchor = watch.depart_date_from or watch.depart_date_to
    if departure_anchor is None:
        if target is not None and offer.total_price <= target:
            return "Flexible dates plus a price under target make this a strong moment to act."
        if percentile <= 25:
            return "Good historical price signal; safe to keep watching briefly if dates stay flexible."
        return "Dates are still flexible, so history matters more than urgency."

    days_out = (
        datetime.combine(departure_anchor, datetime.min.time(), tzinfo=UTC) - current_time
    ).days
    if (
        days_out <= watch.glide_end_days
        and glide_limit is not None
        and offer.total_price <= glide_limit
    ):
        return "Inside the late-booking window and within the relaxed acceptance band; favor acting soon."
    if days_out <= watch.glide_end_days:
        return (
            "Inside the late-booking window, but pricing still sits above the current glide limit."
        )
    if target is not None and offer.total_price <= target:
        return "This is already beating the current target, so waiting adds more risk than reward."
    if (
        days_out <= watch.glide_start_days
        and glide_limit is not None
        and offer.total_price <= glide_limit
    ):
        return "Inside the glide window with acceptable pricing; this is a credible approval candidate."
    if days_out > watch.glide_start_days and percentile <= 20:
        return (
            "Well ahead of departure with unusually low pricing; lock this in if the schedule fits."
        )
    return "Monitoring can continue; the stored history does not yet show strong urgency."


def price_context(
    *,
    offer: NormalizedOffer,
    stat: PriceStat | None = None,
    percentile: float,
    watch: TripWatch,
) -> str:
    if stat is not None and stat.sample_n >= 2 and stat.median is not None:
        parts = [
            f"Historical percentile ~{round(percentile)} for this pattern.",
            f"Typical median {stat.median:.2f} {offer.currency}.",
        ]
        if stat.p25 is not None:
            parts.append(f"Target around {stat.p25:.2f} {offer.currency}.")
        return " ".join(parts)
    target = target_price_for_offer(watch=watch, stat=stat)
    if target is not None:
        return f"Current target is about {target:.2f} {offer.currency}; more history will sharpen this band."
    return "History is still thin, so this price is being judged mostly from the current observed band."


def month_bucket_for_watch(watch: TripWatch) -> date:
    anchor = watch.depart_date_from or watch.depart_date_to or date.today()
    return date(anchor.year, anchor.month, 1)


def _ceiling_for_offer(*, watch: TripWatch, offer: NormalizedOffer) -> Decimal | None:
    if offer.kind.value == "flight":
        return watch.flight_budget_max or watch.max_total_trip_spend
    if offer.kind.value == "hotel":
        return watch.hotel_budget_per_night_max or watch.max_total_trip_spend
    return watch.max_total_trip_spend


def _interpolate(
    *,
    price: Decimal,
    low: Decimal,
    high: Decimal,
    low_pct: float,
    high_pct: float,
) -> float:
    if high <= low:
        return round(high_pct, 1)
    progress = float((price - low) / (high - low))
    return round(low_pct + ((high_pct - low_pct) * max(min(progress, 1.0), 0.0)), 1)
