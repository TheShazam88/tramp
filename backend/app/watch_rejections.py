# ruff: noqa: E501
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    RejectedFingerprint,
    SuppressedAttribute,
    SuppressedAttributeType,
    TripWatch,
)
from app.watch_types import NormalizedOffer, RejectionLearningOutcome


def apply_rejection_learning(
    *,
    db: Session,
    watch: TripWatch,
    offer: NormalizedOffer,
) -> RejectionLearningOutcome:
    exact_rejection = db.scalar(
        select(RejectedFingerprint).where(
            RejectedFingerprint.watch_id == watch.id,
            RejectedFingerprint.fingerprint_hash == offer.fingerprint_hash,
        )
    )
    if exact_rejection is not None:
        return RejectionLearningOutcome(
            rejected=True,
            penalty=1.0,
            reasons=["This exact offer fingerprint was previously rejected."],
        )

    suppressed = list(
        db.scalars(select(SuppressedAttribute).where(SuppressedAttribute.watch_id == watch.id))
    )
    outcome = RejectionLearningOutcome()
    for suppression in suppressed:
        if _offer_matches_suppression(offer=offer, suppression=suppression):
            outcome.penalty += min(max(suppression.weight, 0.0), 2.0) / 2.0
            outcome.reasons.append(
                f"Suppressed {suppression.attr_type.value.replace('_', ' ')} matched {suppression.attr_value}."
            )
            outcome.suppressed_attributes.append(
                f"{suppression.attr_type.value}:{suppression.attr_value}"
            )

    if outcome.penalty >= 1.5:
        outcome.rejected = True
    return outcome


def _offer_matches_suppression(*, offer: NormalizedOffer, suppression: SuppressedAttribute) -> bool:
    value = suppression.attr_value.strip().lower()
    payload = offer.raw_payload

    candidate_values: list[str] = []
    if suppression.attr_type == SuppressedAttributeType.AIRLINE:
        candidate_values.extend(
            [
                str(payload.get("airline_code", "")).lower(),
                str(payload.get("supplier", "")).lower(),
            ]
        )
    elif suppression.attr_type == SuppressedAttributeType.HOTEL_PROPERTY:
        candidate_values.append(str(payload.get("hotel_name", "")).lower())
    elif suppression.attr_type == SuppressedAttributeType.HOTEL_CHAIN:
        candidate_values.append(str(payload.get("hotel_chain", "")).lower())
    elif suppression.attr_type == SuppressedAttributeType.AREA_CLUSTER:
        candidate_values.append(str(payload.get("area_cluster", "")).lower())
    elif suppression.attr_type == SuppressedAttributeType.ROUTING_TRAIT:
        candidate_values.extend(item.lower() for item in offer.attributes)
    return value in candidate_values
