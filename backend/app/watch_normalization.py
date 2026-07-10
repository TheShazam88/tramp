from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db.models import ObservationKind
from app.watch_types import NormalizedOffer

TWOPLACES = Decimal("0.01")


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def normalize_all_in_price(raw_offer: dict[str, Any]) -> NormalizedOffer:
    base_amount = _to_decimal(raw_offer.get("base_amount", 0))
    tax_amount = _to_decimal(raw_offer.get("tax_amount", 0))
    fee_amount = _to_decimal(raw_offer.get("fee_amount", 0))
    bag_amount = _to_decimal(raw_offer.get("bag_amount", 0))
    other_amount = _to_decimal(raw_offer.get("other_amount", 0))
    total_price = base_amount + tax_amount + fee_amount + bag_amount + other_amount

    quality_index = raw_offer.get("quality_index")
    if quality_index is None:
        quality_index = _estimate_quality_index(raw_offer=raw_offer, total_price=total_price)

    fingerprint_hash = _build_fingerprint_hash(raw_offer)
    payload = {
        **raw_offer,
        "base_amount": str(base_amount),
        "tax_amount": str(tax_amount),
        "fee_amount": str(fee_amount),
        "bag_amount": str(bag_amount),
        "other_amount": str(other_amount),
        "total_price": str(total_price),
        "quality_index": float(quality_index),
    }
    return NormalizedOffer(
        fingerprint_hash=fingerprint_hash,
        kind=ObservationKind(raw_offer["kind"]),
        source=str(raw_offer["source"]),
        title=str(raw_offer["title"]),
        total_price=total_price,
        currency=str(raw_offer["currency"]).upper(),
        quality_index=float(max(0, min(100, quality_index))),
        attributes=list(raw_offer.get("attributes", [])),
        raw_payload=payload,
        supplier=raw_offer.get("supplier"),
        cabin=raw_offer.get("cabin"),
        refundable=bool(raw_offer.get("refundable", False)),
        stops=raw_offer.get("stops"),
        duration_minutes=raw_offer.get("duration_minutes"),
        hotel_rating=raw_offer.get("hotel_rating"),
    )


def scope_key_for_offer(raw_offer: dict[str, Any]) -> str:
    return str(raw_offer.get("scope_key") or raw_offer.get("route_key") or raw_offer["title"])


def _build_fingerprint_hash(raw_offer: dict[str, Any]) -> str:
    stable_payload = {
        "kind": raw_offer["kind"],
        "source": raw_offer["source"],
        "supplier": raw_offer.get("supplier"),
        "title": raw_offer["title"],
        "currency": str(raw_offer["currency"]).upper(),
        "route_key": raw_offer.get("route_key"),
        "stay_key": raw_offer.get("stay_key"),
        "depart_key": raw_offer.get("depart_key"),
        "return_key": raw_offer.get("return_key"),
        "hotel_key": raw_offer.get("hotel_key"),
    }
    return hashlib.sha256(json.dumps(stable_payload, sort_keys=True).encode("utf-8")).hexdigest()


def _estimate_quality_index(*, raw_offer: dict[str, Any], total_price: Decimal) -> float:
    kind = ObservationKind(raw_offer["kind"])
    if kind == ObservationKind.FLIGHT:
        cabin = str(raw_offer.get("cabin", "")).lower()
        cabin_bonus = {
            "economy": 6,
            "premium_economy": 12,
            "premium economy": 12,
            "business": 20,
            "first": 24,
        }.get(cabin, 10)
        stops_penalty = int(raw_offer.get("stops", 0) or 0) * 9
        duration_penalty = max(int(raw_offer.get("duration_minutes", 0) or 0) - 420, 0) / 18
        refund_bonus = 8 if raw_offer.get("refundable") else 0
        price_signal = max(0, 18 - float(total_price / Decimal("40")))
        return 58 + cabin_bonus + refund_bonus + price_signal - stops_penalty - duration_penalty

    if kind == ObservationKind.HOTEL:
        rating = float(raw_offer.get("hotel_rating", 4.0) or 4.0)
        refund_bonus = 5 if raw_offer.get("refundable") else 0
        brand_bonus = 4 if raw_offer.get("preferred_brand_match") else 0
        return 45 + (rating * 9) + refund_bonus + brand_bonus

    refund_bonus = 4 if raw_offer.get("refundable") else 0
    return 42 + refund_bonus
