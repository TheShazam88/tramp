from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, exists, select, update
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_maintenance_lock
from app.db.models import (
    AuditLog,
    Booking,
    BookingAttempt,
    BookingStatus,
    Cancellation,
    CancellationStatus,
    Deal,
    DealFeedback,
    DealStatus,
    Disruption,
    DisruptionType,
    NotificationDelivery,
    PriceObservation,
    PriceStat,
    RejectedFingerprint,
    SpendLedger,
    SuppressedAttribute,
    SuppressedAttributeType,
    TrampStampLedger,
    TripWatch,
    TripWatchStatus,
    User,
)
from app.integrations.service import (
    payload_is_simulated,
    provider_is_simulated,
    source_is_simulated,
)

PURGE_CONFIRMATION = "PURGE TEST DATA"
DELETE_BATCH_SIZE = 5_000
WATCH_LEARNING_FIELDS = (
    "value_pressure",
    "quality_floor",
    "max_layover_minutes",
)
AUDIT_METADATA_KEYS = (
    "price_observation_id",
    "price_stat_id",
    "suppressed_attribute_id",
    "rejected_fingerprint_id",
    "deal_id",
    "deal_feedback_id",
    "booking_id",
    "booking_attempt_id",
    "cancellation_id",
    "spend_ledger_id",
    "disruption_id",
    "notification_delivery_id",
)
AUDIT_TARGET_PREFIX_FIELDS = {
    "price-observation": "observation_ids",
    "price-stat": "price_stat_ids",
    "suppressed-attribute": "suppressed_attribute_ids",
    "rejected-fingerprint": "rejected_fingerprint_ids",
    "deal": "deal_ids",
    "deal-feedback": "deal_feedback_ids",
    "booking": "booking_ids",
    "booking-attempt": "booking_attempt_ids",
    "cancellation": "cancellation_ids",
    "spend-ledger": "spend_ledger_ids",
    "disruption": "disruption_ids",
    "notification-delivery": "notification_delivery_ids",
}
AUDIT_METADATA_FIELDS = {
    "price_observation_id": "observation_ids",
    "price_stat_id": "price_stat_ids",
    "suppressed_attribute_id": "suppressed_attribute_ids",
    "rejected_fingerprint_id": "rejected_fingerprint_ids",
    "deal_id": "deal_ids",
    "deal_feedback_id": "deal_feedback_ids",
    "booking_id": "booking_ids",
    "booking_attempt_id": "booking_attempt_ids",
    "cancellation_id": "cancellation_ids",
    "spend_ledger_id": "spend_ledger_ids",
    "disruption_id": "disruption_ids",
    "notification_delivery_id": "notification_delivery_ids",
}


class PurgeSafetyError(ValueError):
    pass


class PurgePlanChangedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WatchSnapshot:
    id: UUID
    status: TripWatchStatus
    value_pressure: float
    quality_floor: int
    max_layover_minutes: int | None


@dataclass(frozen=True, slots=True)
class ObservationSnapshot:
    id: UUID
    watch_id: UUID
    source: str
    fingerprint_hash: str


@dataclass(frozen=True, slots=True)
class PriceStatSnapshot:
    id: UUID


@dataclass(frozen=True, slots=True)
class SuppressedAttributeSnapshot:
    id: UUID
    watch_id: UUID
    attr_type: SuppressedAttributeType
    attr_value: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RejectedFingerprintSnapshot:
    id: UUID
    watch_id: UUID
    fingerprint_hash: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DealSnapshot:
    id: UUID
    watch_id: UUID
    source: str
    fingerprint_hash: str
    status: DealStatus
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class DealFeedbackSnapshot:
    id: UUID
    watch_id: UUID
    deal_id: UUID
    action_taken_json: dict[str, Any] | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BookingSnapshot:
    id: UUID
    deal_id: UUID
    provider: str
    status: BookingStatus


@dataclass(frozen=True, slots=True)
class BookingAttemptSnapshot:
    id: UUID
    deal_id: UUID
    booking_id: UUID | None
    request_simulated: bool
    response_simulated: bool


@dataclass(frozen=True, slots=True)
class CancellationSnapshot:
    id: UUID
    booking_id: UUID
    status: CancellationStatus
    provider: str | None
    provider_payload_simulated: bool
    execution_simulated: bool | None
    prior_booking_status: BookingStatus | None
    prior_watch_status: TripWatchStatus | None


@dataclass(frozen=True, slots=True)
class SpendLedgerSnapshot:
    id: UUID
    booking_id: UUID | None
    cancellation_id: UUID | None


@dataclass(frozen=True, slots=True)
class TrampStampSnapshot:
    booking_id: UUID


@dataclass(frozen=True, slots=True)
class DisruptionSnapshot:
    id: UUID
    booking_id: UUID
    type: DisruptionType


@dataclass(frozen=True, slots=True)
class NotificationSnapshot:
    id: UUID
    booking_id: UUID | None
    cancellation_id: UUID | None
    disruption_id: UUID | None
    deal_id: UUID | None


@dataclass(frozen=True, slots=True)
class AuditSnapshot:
    id: UUID
    target: str
    references: tuple[tuple[str, UUID], ...]


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    watches: tuple[WatchSnapshot, ...] = ()
    observations: tuple[ObservationSnapshot, ...] = ()
    price_stats: tuple[PriceStatSnapshot, ...] = ()
    suppressed_attributes: tuple[SuppressedAttributeSnapshot, ...] = ()
    rejected_fingerprints: tuple[RejectedFingerprintSnapshot, ...] = ()
    deals: tuple[DealSnapshot, ...] = ()
    deal_feedback: tuple[DealFeedbackSnapshot, ...] = ()
    bookings: tuple[BookingSnapshot, ...] = ()
    booking_attempts: tuple[BookingAttemptSnapshot, ...] = ()
    cancellations: tuple[CancellationSnapshot, ...] = ()
    spend_ledger: tuple[SpendLedgerSnapshot, ...] = ()
    tramp_stamp_ledger: tuple[TrampStampSnapshot, ...] = ()
    disruptions: tuple[DisruptionSnapshot, ...] = ()
    notification_deliveries: tuple[NotificationSnapshot, ...] = ()
    audit_logs: tuple[AuditSnapshot, ...] = ()


@dataclass(frozen=True, slots=True)
class PurgePlan:
    observation_ids: frozenset[UUID] = frozenset()
    price_stat_ids: frozenset[UUID] = frozenset()
    suppressed_attribute_ids: frozenset[UUID] = frozenset()
    rejected_fingerprint_ids: frozenset[UUID] = frozenset()
    deal_ids: frozenset[UUID] = frozenset()
    deal_feedback_ids: frozenset[UUID] = frozenset()
    booking_ids: frozenset[UUID] = frozenset()
    booking_attempt_ids: frozenset[UUID] = frozenset()
    cancellation_ids: frozenset[UUID] = frozenset()
    spend_ledger_ids: frozenset[UUID] = frozenset()
    disruption_ids: frozenset[UUID] = frozenset()
    notification_delivery_ids: frozenset[UUID] = frozenset()
    audit_log_ids: frozenset[UUID] = frozenset()
    booking_status_restorations: tuple[tuple[UUID, BookingStatus], ...] = ()
    deal_status_restorations: tuple[tuple[UUID, DealStatus], ...] = ()
    watch_status_restorations: tuple[tuple[UUID, TripWatchStatus], ...] = ()
    watch_state_restorations: tuple[tuple[UUID, str, Any], ...] = ()
    reset_watch_ids: frozenset[UUID] = frozenset()
    warnings: tuple[str, ...] = ()
    unreverted_feedback_count: int = 0

    @property
    def deleted_counts(self) -> dict[str, int]:
        return {
            "audit_log": len(self.audit_log_ids),
            "booking_attempts": len(self.booking_attempt_ids),
            "bookings": len(self.booking_ids),
            "cancellations": len(self.cancellation_ids),
            "deal_feedback": len(self.deal_feedback_ids),
            "deals": len(self.deal_ids),
            "disruptions": len(self.disruption_ids),
            "notification_deliveries": len(self.notification_delivery_ids),
            "price_observations": len(self.observation_ids),
            "price_stats": len(self.price_stat_ids),
            "rejected_fingerprints": len(self.rejected_fingerprint_ids),
            "spend_ledger": len(self.spend_ledger_ids),
            "suppressed_attributes": len(self.suppressed_attribute_ids),
        }

    @property
    def plan_digest(self) -> str:
        id_fields = {
            field_name: sorted(str(value) for value in getattr(self, field_name))
            for field_name in (
                "observation_ids",
                "price_stat_ids",
                "suppressed_attribute_ids",
                "rejected_fingerprint_ids",
                "deal_ids",
                "deal_feedback_ids",
                "booking_ids",
                "booking_attempt_ids",
                "cancellation_ids",
                "spend_ledger_ids",
                "disruption_ids",
                "notification_delivery_ids",
                "audit_log_ids",
                "reset_watch_ids",
            )
        }
        payload = {
            "selected_ids": id_fields,
            "deleted_counts": self.deleted_counts,
            "booking_status_restorations": _canonical_restorations(
                self.booking_status_restorations
            ),
            "deal_status_restorations": _canonical_restorations(self.deal_status_restorations),
            "watch_status_restorations": _canonical_restorations(self.watch_status_restorations),
            "watch_state_restorations": _canonical_restorations(self.watch_state_restorations),
            "warnings": list(self.warnings),
            "unreverted_feedback_count": self.unreverted_feedback_count,
        }
        encoded = json.dumps(
            payload,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()


def _canonical_restorations(
    restorations: tuple[tuple[Any, ...], ...],
) -> list[list[str]]:
    return sorted([[str(value) for value in item] for item in restorations])


def classify_activity(
    snapshot: ActivitySnapshot,
    *,
    now: datetime | None = None,
) -> PurgePlan:
    """Purely classify selected IDs and fail-safe reversible state changes."""

    effective_now = now or datetime.now(UTC)
    observations_by_id = {item.id: item for item in snapshot.observations}
    deals_by_id = {item.id: item for item in snapshot.deals}
    bookings_by_id = {item.id: item for item in snapshot.bookings}
    watches_by_id = {item.id: item for item in snapshot.watches}

    observation_ids = frozenset(
        item.id for item in snapshot.observations if source_is_simulated(item.source)
    )
    deal_ids = frozenset(item.id for item in snapshot.deals if source_is_simulated(item.source))

    explicit_simulated_attempt_ids = {
        item.id for item in snapshot.booking_attempts if _attempt_is_simulated(item)
    }
    simulated_attempt_booking_ids = {
        item.booking_id
        for item in snapshot.booking_attempts
        if item.id in explicit_simulated_attempt_ids and item.booking_id is not None
    }
    booking_ids = frozenset(
        item.id
        for item in snapshot.bookings
        if item.deal_id in deal_ids
        or provider_is_simulated(item.provider)
        or item.id in simulated_attempt_booking_ids
    )
    booking_attempt_ids = frozenset(
        item.id
        for item in snapshot.booking_attempts
        if item.deal_id in deal_ids
        or item.booking_id in booking_ids
        or item.id in explicit_simulated_attempt_ids
    )

    stamped_booking_ids = {item.booking_id for item in snapshot.tramp_stamp_ledger}
    unsafe_booking_ids = booking_ids & stamped_booking_ids
    if unsafe_booking_ids:
        formatted = ", ".join(str(value) for value in sorted(unsafe_booking_ids, key=str))
        raise PurgeSafetyError(
            "Purge would delete a booking referenced by TrampStampLedger: "
            f"{formatted}. Stamped bookings must be preserved."
        )

    warnings: list[str] = []
    cancellation_ids: set[UUID] = set()
    booking_status_restorations: dict[UUID, BookingStatus] = {}
    watch_status_restorations: dict[UUID, TripWatchStatus] = {}
    for cancellation in snapshot.cancellations:
        if cancellation.booking_id in booking_ids:
            cancellation_ids.add(cancellation.id)
            continue
        if not _cancellation_is_simulated(cancellation):
            continue
        booking = bookings_by_id.get(cancellation.booking_id)
        deal = deals_by_id.get(booking.deal_id) if booking is not None else None
        if booking is None or deal is None or cancellation.prior_booking_status is None:
            warnings.append(
                f"Simulated cancellation {cancellation.id} was retained because "
                "its prior booking state is unavailable."
            )
            continue
        cancellation_ids.add(cancellation.id)
        if cancellation.status == CancellationStatus.REFUNDED:
            if booking.status == BookingStatus.CANCELLED:
                booking_status_restorations[booking.id] = cancellation.prior_booking_status
            else:
                warnings.append(
                    f"Booking {booking.id} was subsequently changed; its status was preserved."
                )
            watch = watches_by_id.get(deal.watch_id)
            if (
                cancellation.prior_watch_status is not None
                and watch is not None
                and watch.status == TripWatchStatus.ACTIVE
            ):
                watch_status_restorations[deal.watch_id] = cancellation.prior_watch_status
            elif cancellation.prior_watch_status is not None:
                warnings.append(
                    f"Watch {deal.watch_id} was subsequently changed; its status was preserved."
                )
    selected_cancellation_ids = frozenset(cancellation_ids)

    deal_feedback_ids = frozenset(
        item.id for item in snapshot.deal_feedback if item.deal_id in deal_ids
    )
    suppressed_attribute_ids = _test_derived_suppression_ids(
        snapshot=snapshot,
        selected_feedback_ids=deal_feedback_ids,
    )
    rejected_fingerprint_ids = _test_derived_rejected_fingerprint_ids(
        snapshot=snapshot,
        selected_feedback_ids=deal_feedback_ids,
        selected_deal_ids=deal_ids,
        selected_observation_ids=observation_ids,
        deals_by_id=deals_by_id,
        observations_by_id=observations_by_id,
    )
    (
        watch_state_restorations,
        unreverted_feedback_count,
        feedback_warnings,
    ) = _watch_learning_restorations(
        snapshot=snapshot,
        selected_feedback_ids=deal_feedback_ids,
        selected_suppression_ids=suppressed_attribute_ids,
        selected_rejection_ids=rejected_fingerprint_ids,
        watches_by_id=watches_by_id,
        deals_by_id=deals_by_id,
    )
    warnings.extend(feedback_warnings)

    cancellation_record_ids = {
        item.id for item in snapshot.cancellations if item.booking_id in booking_ids
    }
    cancellation_record_ids.update(selected_cancellation_ids)
    cancellation_ids_for_effects = frozenset(cancellation_record_ids)
    spend_ledger_ids = frozenset(
        item.id
        for item in snapshot.spend_ledger
        if item.booking_id in booking_ids
        or _optional_attr(item, "cancellation_id") in cancellation_ids_for_effects
    )
    disruption_ids = frozenset(
        item.id
        for item in snapshot.disruptions
        if item.booking_id in booking_ids or _disruption_is_manual_test(item)
    )
    notification_delivery_ids = frozenset(
        item.id
        for item in snapshot.notification_deliveries
        if item.booking_id in booking_ids
        or item.deal_id in deal_ids
        or item.disruption_id in disruption_ids
        or _optional_attr(item, "cancellation_id") in cancellation_ids_for_effects
    )
    price_stat_ids = frozenset(item.id for item in snapshot.price_stats)

    deal_status_restorations = _retained_deal_restorations(
        snapshot=snapshot,
        booking_ids=booking_ids,
        deal_ids=deal_ids,
        now=effective_now,
    )
    reset_watch_ids = _watch_ids_to_reset(
        snapshot=snapshot,
        booking_ids=booking_ids,
        deal_ids=deal_ids,
        deal_restoration_ids={item[0] for item in deal_status_restorations},
        deals_by_id=deals_by_id,
    )

    partial_plan = PurgePlan(
        observation_ids=observation_ids,
        price_stat_ids=price_stat_ids,
        suppressed_attribute_ids=suppressed_attribute_ids,
        rejected_fingerprint_ids=rejected_fingerprint_ids,
        deal_ids=deal_ids,
        deal_feedback_ids=deal_feedback_ids,
        booking_ids=booking_ids,
        booking_attempt_ids=booking_attempt_ids,
        cancellation_ids=selected_cancellation_ids,
        spend_ledger_ids=spend_ledger_ids,
        disruption_ids=disruption_ids,
        notification_delivery_ids=notification_delivery_ids,
        booking_status_restorations=tuple(
            sorted(booking_status_restorations.items(), key=lambda item: str(item[0]))
        ),
        deal_status_restorations=deal_status_restorations,
        watch_status_restorations=tuple(
            sorted(watch_status_restorations.items(), key=lambda item: str(item[0]))
        ),
        watch_state_restorations=watch_state_restorations,
        reset_watch_ids=reset_watch_ids,
        warnings=tuple(sorted(set(warnings))),
        unreverted_feedback_count=unreverted_feedback_count,
    )
    audit_log_ids = frozenset(
        item.id for item in snapshot.audit_logs if _audit_matches_plan(item, partial_plan)
    )
    return replace(partial_plan, audit_log_ids=audit_log_ids)


def _optional_attr(item: object, name: str) -> Any:
    return getattr(item, name, None)


def _attempt_is_simulated(attempt: object) -> bool:
    if hasattr(attempt, "request_simulated"):
        return bool(attempt.request_simulated or attempt.response_simulated)
    return payload_is_simulated(getattr(attempt, "request_payload_json", None)) or (
        payload_is_simulated(getattr(attempt, "response_payload_json", None))
    )


def _cancellation_is_simulated(cancellation: object) -> bool:
    payload_marker = getattr(cancellation, "provider_payload_simulated", None)
    if payload_marker is None:
        payload_marker = payload_is_simulated(getattr(cancellation, "provider_payload_json", None))
    return bool(
        getattr(cancellation, "execution_simulated", None)
        or provider_is_simulated(getattr(cancellation, "provider", None))
        or payload_marker
    )


def _disruption_is_manual_test(disruption: object) -> bool:
    value = disruption.type
    return value == DisruptionType.MANUAL_TEST or str(value).lower() in {
        DisruptionType.MANUAL_TEST.value,
        DisruptionType.MANUAL_TEST.name.lower(),
    }


def _suppression_keys(feedback: object) -> frozenset[tuple[UUID, str, str]]:
    action = feedback.action_taken_json
    if not isinstance(action, dict):
        return frozenset()
    raw_suppressions = action.get("suppressed")
    if not isinstance(raw_suppressions, list):
        return frozenset()
    keys: set[tuple[UUID, str, str]] = set()
    for raw_value in raw_suppressions:
        if not isinstance(raw_value, str) or ":" not in raw_value:
            continue
        attr_type, attr_value = raw_value.split(":", 1)
        if attr_type.strip() and attr_value.strip():
            keys.add((feedback.watch_id, attr_type.strip(), attr_value.strip()))
    return frozenset(keys)


def _test_derived_suppression_ids(
    *,
    snapshot: ActivitySnapshot,
    selected_feedback_ids: frozenset[UUID],
) -> frozenset[UUID]:
    selected_evidence: set[tuple[UUID, str, str, object]] = set()
    retained_keys: set[tuple[UUID, str, str]] = set()
    for feedback in snapshot.deal_feedback:
        keys = _suppression_keys(feedback)
        if feedback.id in selected_feedback_ids:
            selected_evidence.update((*key, feedback.created_at) for key in keys)
        else:
            retained_keys.update(keys)
    selected: set[UUID] = set()
    for suppression in snapshot.suppressed_attributes:
        attr_type = (
            suppression.attr_type.value
            if hasattr(suppression.attr_type, "value")
            else str(suppression.attr_type).lower()
        )
        key = (suppression.watch_id, attr_type, suppression.attr_value)
        if (*key, suppression.created_at) in selected_evidence and key not in retained_keys:
            selected.add(suppression.id)
    return frozenset(selected)


def _test_derived_rejected_fingerprint_ids(
    *,
    snapshot: ActivitySnapshot,
    selected_feedback_ids: frozenset[UUID],
    selected_deal_ids: frozenset[UUID],
    selected_observation_ids: frozenset[UUID],
    deals_by_id: dict[UUID, Any],
    observations_by_id: dict[UUID, Any],
) -> frozenset[UUID]:
    selected_evidence: set[tuple[UUID, str, object]] = set()
    for feedback in snapshot.deal_feedback:
        deal = deals_by_id.get(feedback.deal_id)
        if feedback.id in selected_feedback_ids and deal is not None:
            selected_evidence.add((deal.watch_id, deal.fingerprint_hash, feedback.created_at))
    retained_fingerprints = {
        (deal.watch_id, deal.fingerprint_hash)
        for deal_id, deal in deals_by_id.items()
        if deal_id not in selected_deal_ids
    }
    retained_fingerprints.update(
        (item.watch_id, item.fingerprint_hash)
        for item_id, item in observations_by_id.items()
        if item_id not in selected_observation_ids
    )
    return frozenset(
        item.id
        for item in snapshot.rejected_fingerprints
        if (item.watch_id, item.fingerprint_hash, item.created_at) in selected_evidence
        and (item.watch_id, item.fingerprint_hash) not in retained_fingerprints
    )


def _watch_learning_restorations(
    *,
    snapshot: ActivitySnapshot,
    selected_feedback_ids: frozenset[UUID],
    selected_suppression_ids: frozenset[UUID],
    selected_rejection_ids: frozenset[UUID],
    watches_by_id: dict[UUID, Any],
    deals_by_id: dict[UUID, Any],
) -> tuple[tuple[tuple[UUID, str, Any], ...], int, list[str]]:
    retained_touches: set[tuple[UUID, str]] = set()
    candidates: dict[tuple[UUID, str], list[tuple[object, Any, Any]]] = defaultdict(list)
    feedback_with_unproven_effects: set[UUID] = set()
    for feedback in snapshot.deal_feedback:
        action = feedback.action_taken_json if isinstance(feedback.action_taken_json, dict) else {}
        touched_fields = [field for field in WATCH_LEARNING_FIELDS if field in action]
        if feedback.id not in selected_feedback_ids:
            retained_touches.update((feedback.watch_id, field) for field in touched_fields)
            continue
        prior_state = action.get("prior_watch_state")
        for field in touched_fields:
            prior_value = prior_state.get(field) if isinstance(prior_state, dict) else None
            candidates[(feedback.watch_id, field)].append(
                (feedback, prior_value, action.get(field))
            )

    restorations: list[tuple[UUID, str, Any]] = []
    for (watch_id, field), values in candidates.items():
        watch = watches_by_id.get(watch_id)
        if len(values) != 1 or (watch_id, field) in retained_touches or watch is None:
            feedback_with_unproven_effects.update(value[0].id for value in values)
            continue
        feedback, prior_value, applied_value = values[0]
        prior_state = (
            feedback.action_taken_json.get("prior_watch_state")
            if isinstance(feedback.action_taken_json, dict)
            else None
        )
        if (
            not isinstance(prior_state, dict)
            or field not in prior_state
            or getattr(watch, field) != applied_value
        ):
            feedback_with_unproven_effects.add(feedback.id)
            continue
        restorations.append((watch_id, field, prior_value))

    suppressions_by_key: dict[tuple[UUID, str, str], list[object]] = defaultdict(list)
    for suppression in snapshot.suppressed_attributes:
        attr_type = (
            suppression.attr_type.value
            if hasattr(suppression.attr_type, "value")
            else str(suppression.attr_type).lower()
        )
        suppressions_by_key[(suppression.watch_id, attr_type, suppression.attr_value)].append(
            suppression
        )
    rejections_by_key: dict[tuple[UUID, str], list[object]] = defaultdict(list)
    for rejection in snapshot.rejected_fingerprints:
        rejections_by_key[(rejection.watch_id, rejection.fingerprint_hash)].append(rejection)
    for feedback in snapshot.deal_feedback:
        if feedback.id not in selected_feedback_ids:
            continue
        if any(
            suppression.id not in selected_suppression_ids
            for key in _suppression_keys(feedback)
            for suppression in suppressions_by_key.get(key, ())
        ):
            feedback_with_unproven_effects.add(feedback.id)
        deal = deals_by_id.get(feedback.deal_id)
        if deal is not None and any(
            rejection.id not in selected_rejection_ids
            for rejection in rejections_by_key.get(
                (deal.watch_id, deal.fingerprint_hash),
                (),
            )
        ):
            feedback_with_unproven_effects.add(feedback.id)

    warnings: list[str] = []
    if feedback_with_unproven_effects:
        warnings.append(
            f"{len(feedback_with_unproven_effects)} simulated feedback record(s) "
            "could not be safely reverted; durable watch state was preserved."
        )
    return (
        tuple(sorted(restorations, key=lambda item: (str(item[0]), item[1]))),
        len(feedback_with_unproven_effects),
        warnings,
    )


def _retained_deal_restorations(
    *,
    snapshot: ActivitySnapshot,
    booking_ids: frozenset[UUID],
    deal_ids: frozenset[UUID],
    now: datetime,
) -> tuple[tuple[UUID, DealStatus], ...]:
    selected_booking_deal_ids = {
        item.deal_id for item in snapshot.bookings if item.id in booking_ids
    }
    restorations: list[tuple[UUID, DealStatus]] = []
    for deal in snapshot.deals:
        if (
            deal.id not in selected_booking_deal_ids
            or deal.id in deal_ids
            or deal.status not in {DealStatus.BOOKED, DealStatus.CONFIRMED}
        ):
            continue
        target = (
            DealStatus.EXPIRED
            if _deadline_has_passed(deal.expires_at, now)
            else DealStatus.PROPOSED
        )
        restorations.append((deal.id, target))
    return tuple(sorted(restorations, key=lambda item: str(item[0])))


def _deadline_has_passed(deadline: datetime | None, now: datetime) -> bool:
    if deadline is None:
        return False
    if deadline.tzinfo is None:
        return deadline <= now.replace(tzinfo=None)
    return deadline <= now


def _watch_ids_to_reset(
    *,
    snapshot: ActivitySnapshot,
    booking_ids: frozenset[UUID],
    deal_ids: frozenset[UUID],
    deal_restoration_ids: set[UUID],
    deals_by_id: dict[UUID, Any],
) -> frozenset[UUID]:
    selected_activity_watch_ids = {
        item.watch_id
        for item in snapshot.deals
        if item.id in deal_ids and item.status == DealStatus.BOOKED
    }
    selected_activity_watch_ids.update(
        deal.watch_id
        for booking in snapshot.bookings
        if booking.id in booking_ids
        for deal in [deals_by_id.get(booking.deal_id)]
        if deal is not None
    )
    retained_booking_watch_ids = {
        deal.watch_id
        for booking in snapshot.bookings
        if booking.id not in booking_ids
        for deal in [deals_by_id.get(booking.deal_id)]
        if deal is not None
    }
    retained_booked_deal_watch_ids = {
        deal.watch_id
        for deal in snapshot.deals
        if deal.id not in deal_ids
        and deal.id not in deal_restoration_ids
        and deal.status in {DealStatus.BOOKED, DealStatus.CONFIRMED}
    }
    return frozenset(
        watch.id
        for watch in snapshot.watches
        if watch.status == TripWatchStatus.FULFILLED
        and watch.id in selected_activity_watch_ids
        and watch.id not in retained_booking_watch_ids
        and watch.id not in retained_booked_deal_watch_ids
    )


def _audit_matches_plan(audit: object, plan: PurgePlan) -> bool:
    target = str(audit.target or "")
    if ":" in target:
        prefix, raw_id = target.split(":", 1)
        field_name = AUDIT_TARGET_PREFIX_FIELDS.get(prefix)
        target_id = _parse_uuid(raw_id)
        if (
            field_name is not None
            and target_id is not None
            and target_id in getattr(plan, field_name)
        ):
            return True

    references = getattr(audit, "references", None)
    if references is None:
        meta = audit.meta_json if isinstance(audit.meta_json, dict) else {}
        references = tuple(
            (key, value)
            for key in AUDIT_METADATA_KEYS
            for value in [_parse_uuid(meta.get(key))]
            if value is not None
        )
    for key, reference_id in references:
        field_name = AUDIT_METADATA_FIELDS.get(key)
        if field_name is not None and reference_id in getattr(plan, field_name):
            return True
    return False


def _parse_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _load_activity_snapshot(*, db: Session) -> ActivitySnapshot:
    with db.no_autoflush:
        watches = tuple(
            WatchSnapshot(*row)
            for row in db.execute(
                select(
                    TripWatch.id,
                    TripWatch.status,
                    TripWatch.value_pressure,
                    TripWatch.quality_floor,
                    TripWatch.max_layover_minutes,
                )
            )
        )
        observations = tuple(
            ObservationSnapshot(*row)
            for row in db.execute(
                select(
                    PriceObservation.id,
                    PriceObservation.watch_id,
                    PriceObservation.source,
                    PriceObservation.fingerprint_hash,
                )
            )
        )
        price_stats = tuple(PriceStatSnapshot(*row) for row in db.execute(select(PriceStat.id)))
        suppressions = tuple(
            SuppressedAttributeSnapshot(*row)
            for row in db.execute(
                select(
                    SuppressedAttribute.id,
                    SuppressedAttribute.watch_id,
                    SuppressedAttribute.attr_type,
                    SuppressedAttribute.attr_value,
                    SuppressedAttribute.created_at,
                )
            )
        )
        rejections = tuple(
            RejectedFingerprintSnapshot(*row)
            for row in db.execute(
                select(
                    RejectedFingerprint.id,
                    RejectedFingerprint.watch_id,
                    RejectedFingerprint.fingerprint_hash,
                    RejectedFingerprint.created_at,
                )
            )
        )
        deals = tuple(
            DealSnapshot(*row)
            for row in db.execute(
                select(
                    Deal.id,
                    Deal.watch_id,
                    Deal.source,
                    Deal.fingerprint_hash,
                    Deal.status,
                    Deal.expires_at,
                )
            )
        )
        feedback = tuple(
            DealFeedbackSnapshot(*row)
            for row in db.execute(
                select(
                    DealFeedback.id,
                    DealFeedback.watch_id,
                    DealFeedback.deal_id,
                    DealFeedback.action_taken_json,
                    DealFeedback.created_at,
                )
            )
        )
        bookings = tuple(
            BookingSnapshot(*row)
            for row in db.execute(
                select(
                    Booking.id,
                    Booking.deal_id,
                    Booking.provider,
                    Booking.status,
                )
            )
        )
        attempts = tuple(
            BookingAttemptSnapshot(*row)
            for row in db.execute(
                select(
                    BookingAttempt.id,
                    BookingAttempt.deal_id,
                    BookingAttempt.booking_id,
                    BookingAttempt.request_payload_json["simulated"].as_boolean(),
                    BookingAttempt.response_payload_json["simulated"].as_boolean(),
                )
            )
        )
        cancellations = tuple(
            CancellationSnapshot(*row)
            for row in db.execute(
                select(
                    Cancellation.id,
                    Cancellation.booking_id,
                    Cancellation.status,
                    Cancellation.provider,
                    Cancellation.provider_payload_json["simulated"].as_boolean(),
                    Cancellation.execution_simulated,
                    Cancellation.prior_booking_status,
                    Cancellation.prior_watch_status,
                )
            )
        )
        spend = tuple(
            SpendLedgerSnapshot(*row)
            for row in db.execute(
                select(
                    SpendLedger.id,
                    SpendLedger.booking_id,
                    SpendLedger.cancellation_id,
                )
            )
        )
        stamps = tuple(
            TrampStampSnapshot(*row) for row in db.execute(select(TrampStampLedger.booking_id))
        )
        disruptions = tuple(
            DisruptionSnapshot(*row)
            for row in db.execute(
                select(
                    Disruption.id,
                    Disruption.booking_id,
                    Disruption.type,
                )
            )
        )
        notifications = tuple(
            NotificationSnapshot(*row)
            for row in db.execute(
                select(
                    NotificationDelivery.id,
                    NotificationDelivery.booking_id,
                    NotificationDelivery.cancellation_id,
                    NotificationDelivery.disruption_id,
                    NotificationDelivery.deal_id,
                )
            )
        )
        audits = _load_audit_snapshots(db=db)
    return ActivitySnapshot(
        watches=watches,
        observations=observations,
        price_stats=price_stats,
        suppressed_attributes=suppressions,
        rejected_fingerprints=rejections,
        deals=deals,
        deal_feedback=feedback,
        bookings=bookings,
        booking_attempts=attempts,
        cancellations=cancellations,
        spend_ledger=spend,
        tramp_stamp_ledger=stamps,
        disruptions=disruptions,
        notification_deliveries=notifications,
        audit_logs=audits,
    )


def _load_audit_snapshots(*, db: Session) -> tuple[AuditSnapshot, ...]:
    metadata_columns = [
        AuditLog.meta_json[key].as_string().label(key) for key in AUDIT_METADATA_KEYS
    ]
    snapshots: list[AuditSnapshot] = []
    for row in db.execute(select(AuditLog.id, AuditLog.target, *metadata_columns)):
        references = tuple(
            (key, value)
            for key, raw_value in zip(AUDIT_METADATA_KEYS, row[2:], strict=True)
            for value in [_parse_uuid(raw_value)]
            if value is not None
        )
        snapshots.append(AuditSnapshot(id=row[0], target=row[1], references=references))
    return tuple(snapshots)


def preview_test_data_purge(*, db: Session) -> PurgePlan:
    acquire_activity_maintenance_lock(db)
    return classify_activity(_load_activity_snapshot(db=db))


def execute_test_data_purge(
    *,
    db: Session,
    actor: User,
    confirmation: str,
    preview_digest: str = "",
) -> PurgePlan:
    if confirmation != PURGE_CONFIRMATION:
        raise ValueError(f"Confirmation must exactly match {PURGE_CONFIRMATION!r}.")
    if len(preview_digest) != 64:
        raise ValueError("A valid purge preview plan_digest is required.")

    try:
        acquire_activity_maintenance_lock(db)
        plan = classify_activity(_load_activity_snapshot(db=db))
        if plan.plan_digest != preview_digest:
            raise PurgePlanChangedError(
                "Purge preview changed. Request a new preview and confirm that plan_digest."
            )

        actual_counts = _execute_deletes(db=db, plan=plan)
        if actual_counts != plan.deleted_counts:
            raise PurgeSafetyError(
                "Purge target counts changed during execution; all changes were rolled back."
            )
        _apply_restorations(db=db, plan=plan)
        reset_watch_count = _reset_watches(db=db, watch_ids=plan.reset_watch_ids)
        if reset_watch_count != len(plan.reset_watch_ids):
            raise PurgeSafetyError(
                "Purge watch reset targets changed during execution; all changes were rolled back."
            )

        db.add(
            AuditLog(
                actor=f"user:{actor.id}",
                action="admin.test_data_purged",
                target="test-data:simulated",
                at=datetime.now(UTC),
                meta_json={
                    "plan_digest": plan.plan_digest,
                    "deleted_counts": actual_counts,
                    "reset_watch_count": reset_watch_count,
                    "warnings": list(plan.warnings),
                    "unreverted_feedback_count": plan.unreverted_feedback_count,
                },
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expire_all()
    return plan


def _execute_deletes(*, db: Session, plan: PurgePlan) -> dict[str, int]:
    return {
        "audit_log": _delete_ids(db=db, model=AuditLog, ids=plan.audit_log_ids),
        "notification_deliveries": _delete_ids(
            db=db,
            model=NotificationDelivery,
            ids=plan.notification_delivery_ids,
        ),
        "spend_ledger": _delete_ids(
            db=db,
            model=SpendLedger,
            ids=plan.spend_ledger_ids,
        ),
        "deal_feedback": _delete_ids(
            db=db,
            model=DealFeedback,
            ids=plan.deal_feedback_ids,
        ),
        "cancellations": _delete_ids(
            db=db,
            model=Cancellation,
            ids=plan.cancellation_ids,
        ),
        "disruptions": _delete_ids(
            db=db,
            model=Disruption,
            ids=plan.disruption_ids,
        ),
        "booking_attempts": _delete_ids(
            db=db,
            model=BookingAttempt,
            ids=plan.booking_attempt_ids,
        ),
        "bookings": _delete_ids(db=db, model=Booking, ids=plan.booking_ids),
        "deals": _delete_ids(db=db, model=Deal, ids=plan.deal_ids),
        "price_observations": _delete_ids(
            db=db,
            model=PriceObservation,
            ids=plan.observation_ids,
        ),
        "suppressed_attributes": _delete_ids(
            db=db,
            model=SuppressedAttribute,
            ids=plan.suppressed_attribute_ids,
        ),
        "rejected_fingerprints": _delete_ids(
            db=db,
            model=RejectedFingerprint,
            ids=plan.rejected_fingerprint_ids,
        ),
        "price_stats": _delete_ids(
            db=db,
            model=PriceStat,
            ids=plan.price_stat_ids,
        ),
    }


def _apply_restorations(*, db: Session, plan: PurgePlan) -> None:
    _restore_statuses(
        db=db,
        model=Booking,
        restorations=plan.booking_status_restorations,
    )
    _restore_deals(db=db, restorations=plan.deal_status_restorations)
    _restore_statuses(
        db=db,
        model=TripWatch,
        restorations=plan.watch_status_restorations,
    )
    for watch_id, field, prior_value in plan.watch_state_restorations:
        result = db.execute(
            update(TripWatch).where(TripWatch.id == watch_id).values({field: prior_value})
        )
        if int(getattr(result, "rowcount", 0) or 0) != 1:
            raise PurgeSafetyError("A watch learning restoration target changed.")


def _restore_statuses(
    *,
    db: Session,
    model: type[Any],
    restorations: tuple[tuple[UUID, Any], ...],
) -> None:
    by_status: dict[Any, set[UUID]] = defaultdict(set)
    for record_id, status in restorations:
        by_status[status].add(record_id)
    for status, ids in by_status.items():
        updated = _update_ids(db=db, model=model, ids=ids, values={"status": status})
        if updated != len(ids):
            raise PurgeSafetyError("A status restoration target changed.")


def _restore_deals(
    *,
    db: Session,
    restorations: tuple[tuple[UUID, DealStatus], ...],
) -> None:
    by_status: dict[DealStatus, set[UUID]] = defaultdict(set)
    for deal_id, status in restorations:
        by_status[status].add(deal_id)
    for status, ids in by_status.items():
        updated = _update_ids(
            db=db,
            model=Deal,
            ids=ids,
            values={
                "status": status,
                "confirm_token_hash": None,
                "rejected_reason": None,
            },
        )
        if updated != len(ids):
            raise PurgeSafetyError("A deal restoration target changed.")


def _delete_ids(
    *,
    db: Session,
    model: type[Any],
    ids: frozenset[UUID] | set[UUID],
) -> int:
    deleted = 0
    for batch in _id_batches(ids):
        result = db.execute(delete(model).where(model.id.in_(batch)))
        deleted += int(getattr(result, "rowcount", 0) or 0)
    return deleted


def _update_ids(
    *,
    db: Session,
    model: type[Any],
    ids: set[UUID],
    values: dict[str, Any],
) -> int:
    updated = 0
    for batch in _id_batches(ids):
        result = db.execute(update(model).where(model.id.in_(batch)).values(values))
        updated += int(getattr(result, "rowcount", 0) or 0)
    return updated


def _id_batches(ids: Iterable[UUID]) -> Iterable[tuple[UUID, ...]]:
    ordered = sorted(ids, key=str)
    for index in range(0, len(ordered), DELETE_BATCH_SIZE):
        yield tuple(ordered[index : index + DELETE_BATCH_SIZE])


def _reset_watches(*, db: Session, watch_ids: frozenset[UUID]) -> int:
    if not watch_ids:
        return 0
    retained_booking = exists(
        select(1)
        .select_from(Booking)
        .join(Deal, Deal.id == Booking.deal_id)
        .where(Deal.watch_id == TripWatch.id)
    )
    retained_booked_deal = exists(
        select(1).where(
            Deal.watch_id == TripWatch.id,
            Deal.status.in_((DealStatus.BOOKED, DealStatus.CONFIRMED)),
        )
    )
    retained_stamp = exists(
        select(1)
        .select_from(TrampStampLedger)
        .join(Booking, Booking.id == TrampStampLedger.booking_id)
        .join(Deal, Deal.id == Booking.deal_id)
        .where(Deal.watch_id == TripWatch.id)
    )
    updated = 0
    for batch in _id_batches(watch_ids):
        result = db.execute(
            update(TripWatch)
            .where(
                TripWatch.id.in_(batch),
                TripWatch.status == TripWatchStatus.FULFILLED,
                ~retained_booking,
                ~retained_booked_deal,
                ~retained_stamp,
            )
            .values(status=TripWatchStatus.ACTIVE)
        )
        updated += int(getattr(result, "rowcount", 0) or 0)
    return updated
