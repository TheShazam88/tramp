from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.activity_maintenance import acquire_activity_maintenance_lock
from app.db.models import (
    AuditLog,
    BookingStatus,
    CancellationProvenance,
    CancellationStatus,
    DealStatus,
    DisruptionType,
    SuppressedAttributeType,
    TripWatchStatus,
    User,
)
from app.integrations.service import (
    payload_is_simulated,
    provider_is_simulated,
    source_is_simulated,
)

PURGE_CONFIRMATION = "PURGE TEST DATA"
PLAN_ID_EXPORT_LIMIT = 1_000
PLAN_STREAM_BATCH_SIZE = 500
TARGET_TABLE = "purge_activity_targets"
RESTORATION_TABLE = "purge_activity_restorations"
SIMULATED_COMPONENT_PATTERN = r"(^|\+)[[:space:]]*(mock-|local-safe-|off-)"
TARGET_KIND_FIELDS = (
    ("audit_log", "audit_log_ids"),
    ("booking_attempts", "booking_attempt_ids"),
    ("bookings", "booking_ids"),
    ("cancellations", "cancellation_ids"),
    ("deal_feedback", "deal_feedback_ids"),
    ("deals", "deal_ids"),
    ("disruptions", "disruption_ids"),
    ("notification_deliveries", "notification_delivery_ids"),
    ("price_observations", "observation_ids"),
    ("price_stats", "price_stat_ids"),
    ("rejected_fingerprints", "rejected_fingerprint_ids"),
    ("spend_ledger", "spend_ledger_ids"),
    ("suppressed_attributes", "suppressed_attribute_ids"),
)
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
    provenance: CancellationProvenance
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
    unknown_cancellation_count: int = 0
    deleted_count_overrides: tuple[tuple[str, int], ...] = ()
    plan_digest_override: str | None = None
    reset_watch_count_override: int | None = None
    uses_server_targets: bool = False

    @property
    def deleted_counts(self) -> dict[str, int]:
        if self.deleted_count_overrides:
            return dict(self.deleted_count_overrides)
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
        if self.plan_digest_override is not None:
            return self.plan_digest_override
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
            "unknown_cancellation_count": self.unknown_cancellation_count,
        }
        encoded = json.dumps(
            payload,
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    @property
    def reset_watch_count(self) -> int:
        if self.reset_watch_count_override is not None:
            return self.reset_watch_count_override
        return len(self.reset_watch_ids)


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
    simulated_deal_candidate_ids = frozenset(
        item.id for item in snapshot.deals if source_is_simulated(item.source)
    )

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
        if item.deal_id in simulated_deal_candidate_ids
        or provider_is_simulated(item.provider)
        or item.id in simulated_attempt_booking_ids
    )
    booking_attempt_ids = frozenset(
        item.id
        for item in snapshot.booking_attempts
        if item.deal_id in simulated_deal_candidate_ids
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
    unknown_cancellation_ids: set[UUID] = set()
    booking_status_restorations: dict[UUID, BookingStatus] = {}
    watch_status_restorations: dict[UUID, TripWatchStatus] = {}
    for cancellation in snapshot.cancellations:
        if cancellation.booking_id in booking_ids:
            cancellation_ids.add(cancellation.id)
            continue
        provenance = _cancellation_provenance(cancellation)
        if provenance == CancellationProvenance.UNKNOWN:
            unknown_cancellation_ids.add(cancellation.id)
            continue
        if provenance != CancellationProvenance.SIMULATED:
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
    if unknown_cancellation_ids:
        warnings.append(
            f"{len(unknown_cancellation_ids)} cancellation record(s) with unknown provenance "
            "were retained."
        )

    feedback_candidate_ids = frozenset(
        item.id for item in snapshot.deal_feedback if item.deal_id in simulated_deal_candidate_ids
    )
    (
        provisional_feedback_ids,
        feedback_restoration_records,
    ) = _provable_feedback_candidates(
        snapshot=snapshot,
        candidate_ids=feedback_candidate_ids,
        watches_by_id=watches_by_id,
    )
    provisional_suppression_ids = _test_derived_suppression_ids(
        snapshot=snapshot,
        selected_feedback_ids=provisional_feedback_ids,
    )
    provisional_rejection_ids = _test_derived_rejected_fingerprint_ids(
        snapshot=snapshot,
        selected_feedback_ids=provisional_feedback_ids,
        selected_deal_ids=simulated_deal_candidate_ids,
        selected_observation_ids=observation_ids,
        deals_by_id=deals_by_id,
        observations_by_id=observations_by_id,
    )
    unresolved_evidence_ids = _feedback_ids_with_unreverted_evidence(
        snapshot=snapshot,
        feedback_ids=provisional_feedback_ids,
        selected_suppression_ids=provisional_suppression_ids,
        selected_rejection_ids=provisional_rejection_ids,
        deals_by_id=deals_by_id,
    )
    deal_feedback_ids = frozenset(provisional_feedback_ids - unresolved_evidence_ids)
    unreverted_feedback_ids = feedback_candidate_ids - deal_feedback_ids
    protected_deal_ids = {
        item.deal_id for item in snapshot.deal_feedback if item.id in unreverted_feedback_ids
    }
    deal_ids = frozenset(simulated_deal_candidate_ids - protected_deal_ids)
    watch_state_restorations = tuple(
        sorted(
            (
                (watch_id, field, prior_value)
                for feedback_id, watch_id, field, prior_value in feedback_restoration_records
                if feedback_id in deal_feedback_ids
            ),
            key=lambda item: (str(item[0]), item[1]),
        )
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
    unreverted_feedback_count = len(unreverted_feedback_ids)
    if unreverted_feedback_count:
        warnings.append(
            f"{unreverted_feedback_count} simulated feedback record(s) could not be "
            "safely reverted; feedback evidence and durable watch state were preserved."
        )

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
        unknown_cancellation_count=len(unknown_cancellation_ids),
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


def _cancellation_provenance(cancellation: object) -> CancellationProvenance:
    raw_provenance = getattr(cancellation, "provenance", None)
    if raw_provenance is not None:
        try:
            return CancellationProvenance(raw_provenance)
        except ValueError:
            return CancellationProvenance.UNKNOWN
    payload_marker = getattr(cancellation, "provider_payload_simulated", None)
    if payload_marker is None:
        payload_marker = payload_is_simulated(getattr(cancellation, "provider_payload_json", None))
    if (
        getattr(cancellation, "execution_simulated", None)
        or provider_is_simulated(getattr(cancellation, "provider", None))
        or payload_marker
    ):
        return CancellationProvenance.SIMULATED
    if getattr(cancellation, "execution_simulated", None) is False:
        return CancellationProvenance.LIVE
    return CancellationProvenance.UNKNOWN


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


def _provable_feedback_candidates(
    *,
    snapshot: ActivitySnapshot,
    candidate_ids: frozenset[UUID],
    watches_by_id: dict[UUID, Any],
) -> tuple[frozenset[UUID], tuple[tuple[UUID, UUID, str, Any], ...]]:
    touch_counts: dict[tuple[UUID, str], int] = defaultdict(int)
    for feedback in snapshot.deal_feedback:
        action = feedback.action_taken_json if isinstance(feedback.action_taken_json, dict) else {}
        for field in WATCH_LEARNING_FIELDS:
            if field in action:
                touch_counts[(feedback.watch_id, field)] += 1

    provable_ids: set[UUID] = set()
    restorations: list[tuple[UUID, UUID, str, Any]] = []
    for feedback in snapshot.deal_feedback:
        if feedback.id not in candidate_ids:
            continue
        action = feedback.action_taken_json if isinstance(feedback.action_taken_json, dict) else {}
        if action.get("durable_learning_applied") is False:
            provable_ids.add(feedback.id)
            continue
        touched_fields = [field for field in WATCH_LEARNING_FIELDS if field in action]
        prior_state = action.get("prior_watch_state")
        watch = watches_by_id.get(feedback.watch_id)
        if (
            not touched_fields
            or not isinstance(prior_state, dict)
            or watch is None
            or any(field not in prior_state for field in touched_fields)
            or any(touch_counts[(feedback.watch_id, field)] != 1 for field in touched_fields)
            or any(getattr(watch, field) != action.get(field) for field in touched_fields)
        ):
            continue
        provable_ids.add(feedback.id)
        restorations.extend(
            (feedback.id, feedback.watch_id, field, prior_state[field]) for field in touched_fields
        )
    return (
        frozenset(provable_ids),
        tuple(
            sorted(
                restorations,
                key=lambda item: (str(item[0]), str(item[1]), item[2]),
            )
        ),
    )


def _feedback_ids_with_unreverted_evidence(
    *,
    snapshot: ActivitySnapshot,
    feedback_ids: frozenset[UUID],
    selected_suppression_ids: frozenset[UUID],
    selected_rejection_ids: frozenset[UUID],
    deals_by_id: dict[UUID, Any],
) -> frozenset[UUID]:
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

    unresolved_ids: set[UUID] = set()
    for feedback in snapshot.deal_feedback:
        if feedback.id not in feedback_ids:
            continue
        if any(
            suppression.id not in selected_suppression_ids
            for key in _suppression_keys(feedback)
            for suppression in suppressions_by_key.get(key, ())
        ):
            unresolved_ids.add(feedback.id)
        deal = deals_by_id.get(feedback.deal_id)
        if deal is not None and any(
            rejection.id not in selected_rejection_ids
            for rejection in rejections_by_key.get(
                (deal.watch_id, deal.fingerprint_hash),
                (),
            )
        ):
            unresolved_ids.add(feedback.id)
    return frozenset(unresolved_ids)


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


def _prepare_target_tables(*, db: Session) -> None:
    db.execute(
        text(
            f"""
            CREATE TEMP TABLE IF NOT EXISTS {TARGET_TABLE} (
                kind text NOT NULL,
                id uuid NOT NULL,
                PRIMARY KEY (kind, id)
            ) ON COMMIT DROP
            """
        )
    )
    db.execute(
        text(
            f"""
            CREATE TEMP TABLE IF NOT EXISTS {RESTORATION_TABLE} (
                kind text NOT NULL,
                id uuid NOT NULL,
                field text NOT NULL,
                value jsonb,
                source_id uuid,
                PRIMARY KEY (kind, id, field)
            ) ON COMMIT DROP
            """
        )
    )
    db.execute(text(f"TRUNCATE {TARGET_TABLE}, {RESTORATION_TABLE}"))


def _insert_target_select(
    *,
    db: Session,
    kind: str,
    select_sql: str,
    parameters: dict[str, Any] | None = None,
) -> None:
    db.execute(
        text(
            f"""
            INSERT INTO {TARGET_TABLE} (kind, id)
            SELECT :target_kind, selected.id
            FROM ({select_sql}) AS selected
            ON CONFLICT DO NOTHING
            """
        ),
        {"target_kind": kind, **(parameters or {})},
    )


def _populate_base_targets(*, db: Session) -> None:
    simulated_parameters = {"simulated_pattern": SIMULATED_COMPONENT_PATTERN}
    _insert_target_select(
        db=db,
        kind="price_observations",
        select_sql="""
            SELECT observation.id
            FROM price_observations AS observation
            WHERE lower(COALESCE(observation.source, '')) ~ :simulated_pattern
        """,
        parameters=simulated_parameters,
    )
    _insert_target_select(
        db=db,
        kind="price_stats",
        select_sql="SELECT price_stat.id FROM price_stats AS price_stat",
    )
    _insert_target_select(
        db=db,
        kind="_deal_candidates",
        select_sql="""
            SELECT deal.id
            FROM deals AS deal
            WHERE lower(COALESCE(deal.source, '')) ~ :simulated_pattern
        """,
        parameters=simulated_parameters,
    )
    _insert_target_select(
        db=db,
        kind="_attempt_explicit",
        select_sql="""
            SELECT attempt.id
            FROM booking_attempts AS attempt
            WHERE attempt.request_payload_json->'simulated' = 'true'::jsonb
               OR attempt.response_payload_json->'simulated' = 'true'::jsonb
        """,
    )
    _insert_target_select(
        db=db,
        kind="bookings",
        select_sql=f"""
            SELECT booking.id
            FROM bookings AS booking
            WHERE lower(COALESCE(booking.provider, '')) ~ :simulated_pattern
               OR EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = '_deal_candidates'
                      AND target.id = booking.deal_id
               )
               OR EXISTS (
                    SELECT 1
                    FROM booking_attempts AS attempt
                    JOIN {TARGET_TABLE} AS target
                      ON target.kind = '_attempt_explicit'
                     AND target.id = attempt.id
                    WHERE attempt.booking_id = booking.id
               )
        """,
        parameters=simulated_parameters,
    )
    _insert_target_select(
        db=db,
        kind="booking_attempts",
        select_sql=f"""
            SELECT attempt.id
            FROM booking_attempts AS attempt
            WHERE EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = '_attempt_explicit'
                      AND target.id = attempt.id
                )
               OR EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = '_deal_candidates'
                      AND target.id = attempt.deal_id
                )
               OR EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'bookings'
                      AND target.id = attempt.booking_id
                )
        """,
    )


def _ensure_no_stamped_booking_targets(*, db: Session) -> None:
    stamped_ids = list(
        db.scalars(
            text(
                f"""
                SELECT stamp.booking_id
                FROM tramp_stamp_ledger AS stamp
                JOIN {TARGET_TABLE} AS target
                  ON target.kind = 'bookings'
                 AND target.id = stamp.booking_id
                ORDER BY stamp.booking_id
                LIMIT 10
                """
            )
        )
    )
    if stamped_ids:
        formatted = ", ".join(str(value) for value in stamped_ids)
        raise PurgeSafetyError(
            "Purge would delete a booking referenced by TrampStampLedger: "
            f"{formatted}. Stamped bookings must be preserved."
        )


def _populate_cancellation_targets(*, db: Session) -> tuple[int, list[str]]:
    _insert_target_select(
        db=db,
        kind="cancellations",
        select_sql=f"""
            SELECT cancellation.id
            FROM cancellations AS cancellation
            WHERE EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'bookings'
                      AND target.id = cancellation.booking_id
                )
               OR (
                    cancellation.provenance = 'simulated'
                    AND cancellation.prior_booking_status IS NOT NULL
               )
        """,
    )
    unknown_count = int(
        db.scalar(
            text(
                f"""
                SELECT count(*)
                FROM cancellations AS cancellation
                WHERE cancellation.provenance = 'unknown'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS target
                      WHERE target.kind = 'bookings'
                        AND target.id = cancellation.booking_id
                  )
                """
            )
        )
        or 0
    )
    missing_prior_count = int(
        db.scalar(
            text(
                f"""
                SELECT count(*)
                FROM cancellations AS cancellation
                WHERE cancellation.provenance = 'simulated'
                  AND cancellation.prior_booking_status IS NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS target
                      WHERE target.kind = 'bookings'
                        AND target.id = cancellation.booking_id
                  )
                """
            )
        )
        or 0
    )
    db.execute(
        text(
            f"""
            INSERT INTO {RESTORATION_TABLE} (
                kind, id, field, value, source_id
            )
            SELECT
                'booking_status',
                booking.id,
                'status',
                to_jsonb(cancellation.prior_booking_status::text),
                cancellation.id
            FROM cancellations AS cancellation
            JOIN {TARGET_TABLE} AS target
              ON target.kind = 'cancellations'
             AND target.id = cancellation.id
            JOIN bookings AS booking ON booking.id = cancellation.booking_id
            WHERE cancellation.status = 'REFUNDED'
              AND booking.status = 'CANCELLED'
              AND cancellation.prior_booking_status IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM {TARGET_TABLE} AS booking_target
                  WHERE booking_target.kind = 'bookings'
                    AND booking_target.id = booking.id
              )
            ON CONFLICT DO NOTHING
            """
        )
    )
    db.execute(
        text(
            f"""
            INSERT INTO {RESTORATION_TABLE} (
                kind, id, field, value, source_id
            )
            SELECT
                'watch_status',
                watch.id,
                'status',
                to_jsonb(cancellation.prior_watch_status::text),
                cancellation.id
            FROM cancellations AS cancellation
            JOIN {TARGET_TABLE} AS target
              ON target.kind = 'cancellations'
             AND target.id = cancellation.id
            JOIN bookings AS booking ON booking.id = cancellation.booking_id
            JOIN deals AS deal ON deal.id = booking.deal_id
            JOIN trip_watches AS watch ON watch.id = deal.watch_id
            WHERE cancellation.status = 'REFUNDED'
              AND watch.status = 'ACTIVE'
              AND cancellation.prior_watch_status IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM {TARGET_TABLE} AS booking_target
                  WHERE booking_target.kind = 'bookings'
                    AND booking_target.id = booking.id
              )
            ON CONFLICT DO NOTHING
            """
        )
    )
    changed_booking_count = int(
        db.scalar(
            text(
                f"""
                SELECT count(*)
                FROM cancellations AS cancellation
                JOIN {TARGET_TABLE} AS target
                  ON target.kind = 'cancellations'
                 AND target.id = cancellation.id
                JOIN bookings AS booking ON booking.id = cancellation.booking_id
                WHERE cancellation.status = 'REFUNDED'
                  AND cancellation.prior_booking_status IS NOT NULL
                  AND booking.status <> 'CANCELLED'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS booking_target
                      WHERE booking_target.kind = 'bookings'
                        AND booking_target.id = booking.id
                  )
                """
            )
        )
        or 0
    )
    warnings: list[str] = []
    if unknown_count:
        warnings.append(
            f"{unknown_count} cancellation record(s) with unknown provenance were retained."
        )
    if missing_prior_count:
        warnings.append(
            f"{missing_prior_count} simulated cancellation record(s) were retained because "
            "prior booking state is unavailable."
        )
    if changed_booking_count:
        warnings.append(
            f"{changed_booking_count} cancellation booking state(s) were subsequently "
            "changed and preserved."
        )
    return unknown_count, warnings


def _populate_feedback_targets(*, db: Session) -> tuple[int, list[str]]:
    statement = text(
        f"""
        SELECT
            feedback.id,
            feedback.watch_id,
            feedback.deal_id,
            feedback.action_taken_json,
            watch.value_pressure,
            watch.quality_floor,
            watch.max_layover_minutes,
            (
                SELECT count(*)
                FROM deal_feedback AS other
                WHERE other.watch_id = feedback.watch_id
                  AND other.action_taken_json ? 'value_pressure'
            ) AS value_pressure_touches,
            (
                SELECT count(*)
                FROM deal_feedback AS other
                WHERE other.watch_id = feedback.watch_id
                  AND other.action_taken_json ? 'quality_floor'
            ) AS quality_floor_touches,
            (
                SELECT count(*)
                FROM deal_feedback AS other
                WHERE other.watch_id = feedback.watch_id
                  AND other.action_taken_json ? 'max_layover_minutes'
            ) AS max_layover_touches
        FROM deal_feedback AS feedback
        JOIN {TARGET_TABLE} AS candidate
          ON candidate.kind = '_deal_candidates'
         AND candidate.id = feedback.deal_id
        JOIN trip_watches AS watch ON watch.id = feedback.watch_id
        ORDER BY feedback.id
        """
    ).execution_options(
        stream_results=True,
        yield_per=PLAN_STREAM_BATCH_SIZE,
    )
    safe_rows: list[dict[str, Any]] = []
    protected_rows: list[dict[str, Any]] = []
    restoration_rows: list[dict[str, Any]] = []
    unreverted_count = 0

    def flush_rows() -> None:
        if safe_rows:
            db.execute(
                text(
                    f"""
                    INSERT INTO {TARGET_TABLE} (kind, id)
                    VALUES ('deal_feedback', :id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                safe_rows,
            )
            safe_rows.clear()
        if protected_rows:
            db.execute(
                text(
                    f"""
                    INSERT INTO {TARGET_TABLE} (kind, id)
                    VALUES ('_protected_deals', :id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                protected_rows,
            )
            protected_rows.clear()
        if restoration_rows:
            db.execute(
                text(
                    f"""
                    INSERT INTO {RESTORATION_TABLE} (
                        kind, id, field, value, source_id
                    ) VALUES (
                        'watch_state',
                        :watch_id,
                        :field,
                        CAST(:value AS jsonb),
                        :feedback_id
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                restoration_rows,
            )
            restoration_rows.clear()

    for row in db.execute(statement):
        action = row.action_taken_json if isinstance(row.action_taken_json, dict) else {}
        touched_fields = [field for field in WATCH_LEARNING_FIELDS if field in action]
        prior_state = action.get("prior_watch_state")
        current_values = {
            "value_pressure": row.value_pressure,
            "quality_floor": row.quality_floor,
            "max_layover_minutes": row.max_layover_minutes,
        }
        touch_counts = {
            "value_pressure": row.value_pressure_touches,
            "quality_floor": row.quality_floor_touches,
            "max_layover_minutes": row.max_layover_touches,
        }
        provable = action.get("durable_learning_applied") is False
        if not provable:
            provable = bool(
                touched_fields
                and isinstance(prior_state, dict)
                and all(field in prior_state for field in touched_fields)
                and all(touch_counts[field] == 1 for field in touched_fields)
                and all(current_values[field] == action.get(field) for field in touched_fields)
            )
        if provable:
            safe_rows.append({"id": row.id})
            if action.get("durable_learning_applied") is not False:
                restoration_rows.extend(
                    {
                        "watch_id": row.watch_id,
                        "field": field,
                        "value": json.dumps(prior_state[field]),
                        "feedback_id": row.id,
                    }
                    for field in touched_fields
                )
        else:
            unreverted_count += 1
            protected_rows.append({"id": row.deal_id})
        if len(safe_rows) + len(protected_rows) + len(restoration_rows) >= PLAN_STREAM_BATCH_SIZE:
            flush_rows()
    flush_rows()

    _insert_target_select(
        db=db,
        kind="deals",
        select_sql=f"""
            SELECT candidate.id
            FROM {TARGET_TABLE} AS candidate
            WHERE candidate.kind = '_deal_candidates'
              AND NOT EXISTS (
                  SELECT 1
                  FROM {TARGET_TABLE} AS protected
                  WHERE protected.kind = '_protected_deals'
                    AND protected.id = candidate.id
              )
        """,
    )
    _populate_learning_targets(db=db)
    unreverted_count += _protect_unrevertable_feedback_evidence(db=db)
    warnings: list[str] = []
    if unreverted_count:
        warnings.append(
            f"{unreverted_count} simulated feedback record(s) could not be safely "
            "reverted; feedback evidence and durable watch state were preserved."
        )
    return unreverted_count, warnings


def _protect_unrevertable_feedback_evidence(*, db: Session) -> int:
    protected_count = 0
    while True:
        result = db.execute(
            text(
                f"""
                INSERT INTO {TARGET_TABLE} (kind, id)
                SELECT '_feedback_unreverted', feedback.id
                FROM {TARGET_TABLE} AS feedback_target
                JOIN deal_feedback AS feedback
                  ON feedback_target.kind = 'deal_feedback'
                 AND feedback_target.id = feedback.id
                JOIN deals AS deal ON deal.id = feedback.deal_id
                WHERE EXISTS (
                    SELECT 1
                    FROM rejected_fingerprints AS rejection
                    WHERE rejection.watch_id = deal.watch_id
                      AND rejection.fingerprint_hash = deal.fingerprint_hash
                      AND NOT EXISTS (
                          SELECT 1
                          FROM {TARGET_TABLE} AS rejection_target
                          WHERE rejection_target.kind = 'rejected_fingerprints'
                            AND rejection_target.id = rejection.id
                      )
                )
                   OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        COALESCE(
                            feedback.action_taken_json->'suppressed',
                            '[]'::jsonb
                        )
                    ) AS expected(value)
                    JOIN suppressed_attributes AS suppression
                      ON suppression.watch_id = feedback.watch_id
                     AND lower(suppression.attr_type::text) =
                         split_part(expected.value, ':', 1)
                     AND suppression.attr_value =
                         substring(
                             expected.value
                             from position(':' in expected.value) + 1
                         )
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM {TARGET_TABLE} AS suppression_target
                        WHERE suppression_target.kind = 'suppressed_attributes'
                          AND suppression_target.id = suppression.id
                    )
                )
                ON CONFLICT DO NOTHING
                """
            )
        )
        new_count = int(getattr(result, "rowcount", 0) or 0)
        if new_count == 0:
            return protected_count
        protected_count += new_count
        db.execute(
            text(
                f"""
                INSERT INTO {TARGET_TABLE} (kind, id)
                SELECT '_protected_deals', feedback.deal_id
                FROM {TARGET_TABLE} AS unsafe
                JOIN deal_feedback AS feedback ON feedback.id = unsafe.id
                WHERE unsafe.kind = '_feedback_unreverted'
                ON CONFLICT DO NOTHING
                """
            )
        )
        db.execute(
            text(
                f"""
                DELETE FROM {RESTORATION_TABLE} AS restoration
                USING {TARGET_TABLE} AS unsafe
                WHERE unsafe.kind = '_feedback_unreverted'
                  AND restoration.source_id = unsafe.id
                """
            )
        )
        db.execute(
            text(
                f"""
                DELETE FROM {TARGET_TABLE} AS feedback_target
                USING {TARGET_TABLE} AS unsafe
                WHERE feedback_target.kind = 'deal_feedback'
                  AND unsafe.kind = '_feedback_unreverted'
                  AND feedback_target.id = unsafe.id
                """
            )
        )
        db.execute(
            text(
                f"""
                DELETE FROM {TARGET_TABLE}
                WHERE kind IN (
                    'deals',
                    'suppressed_attributes',
                    'rejected_fingerprints'
                )
                """
            )
        )
        _insert_target_select(
            db=db,
            kind="deals",
            select_sql=f"""
                SELECT candidate.id
                FROM {TARGET_TABLE} AS candidate
                WHERE candidate.kind = '_deal_candidates'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS protected
                      WHERE protected.kind = '_protected_deals'
                        AND protected.id = candidate.id
                  )
            """,
        )
        _populate_learning_targets(db=db)


def _populate_learning_targets(*, db: Session) -> None:
    _insert_target_select(
        db=db,
        kind="suppressed_attributes",
        select_sql=f"""
            SELECT DISTINCT suppression.id
            FROM {TARGET_TABLE} AS feedback_target
            JOIN deal_feedback AS feedback
              ON feedback_target.kind = 'deal_feedback'
             AND feedback_target.id = feedback.id
            CROSS JOIN LATERAL jsonb_array_elements_text(
                COALESCE(feedback.action_taken_json->'suppressed', '[]'::jsonb)
            ) AS suppressed(value)
            JOIN suppressed_attributes AS suppression
              ON suppression.watch_id = feedback.watch_id
             AND lower(suppression.attr_type::text) =
                 split_part(suppressed.value, ':', 1)
             AND suppression.attr_value =
                 substring(suppressed.value from position(':' in suppressed.value) + 1)
             AND suppression.created_at = feedback.created_at
            WHERE NOT EXISTS (
                SELECT 1
                FROM deal_feedback AS retained_feedback
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    COALESCE(
                        retained_feedback.action_taken_json->'suppressed',
                        '[]'::jsonb
                    )
                ) AS retained_suppressed(value)
                WHERE retained_feedback.watch_id = feedback.watch_id
                  AND retained_suppressed.value = suppressed.value
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS retained_target
                      WHERE retained_target.kind = 'deal_feedback'
                        AND retained_target.id = retained_feedback.id
                  )
            )
        """,
    )
    _insert_target_select(
        db=db,
        kind="rejected_fingerprints",
        select_sql=f"""
            SELECT rejection.id
            FROM {TARGET_TABLE} AS feedback_target
            JOIN deal_feedback AS feedback
              ON feedback_target.kind = 'deal_feedback'
             AND feedback_target.id = feedback.id
            JOIN deals AS deal ON deal.id = feedback.deal_id
            JOIN rejected_fingerprints AS rejection
              ON rejection.watch_id = deal.watch_id
             AND rejection.fingerprint_hash = deal.fingerprint_hash
             AND rejection.created_at = feedback.created_at
            WHERE NOT EXISTS (
                SELECT 1
                FROM deals AS retained_deal
                WHERE retained_deal.watch_id = rejection.watch_id
                  AND retained_deal.fingerprint_hash = rejection.fingerprint_hash
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS deal_target
                      WHERE deal_target.kind = 'deals'
                        AND deal_target.id = retained_deal.id
                  )
            )
              AND NOT EXISTS (
                SELECT 1
                FROM price_observations AS retained_observation
                WHERE retained_observation.watch_id = rejection.watch_id
                  AND retained_observation.fingerprint_hash = rejection.fingerprint_hash
                  AND NOT EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS observation_target
                      WHERE observation_target.kind = 'price_observations'
                        AND observation_target.id = retained_observation.id
                  )
            )
        """,
    )


def _populate_dependent_targets(*, db: Session) -> None:
    _insert_target_select(
        db=db,
        kind="spend_ledger",
        select_sql=f"""
            SELECT spend.id
            FROM spend_ledger AS spend
            WHERE EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'bookings'
                      AND target.id = spend.booking_id
                )
               OR EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'cancellations'
                      AND target.id = spend.cancellation_id
                )
        """,
    )
    _insert_target_select(
        db=db,
        kind="disruptions",
        select_sql=f"""
            SELECT disruption.id
            FROM disruptions AS disruption
            WHERE disruption.type = 'MANUAL_TEST'
               OR EXISTS (
                    SELECT 1
                    FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'bookings'
                      AND target.id = disruption.booking_id
               )
        """,
    )
    _insert_target_select(
        db=db,
        kind="notification_deliveries",
        select_sql=f"""
            SELECT delivery.id
            FROM notification_deliveries AS delivery
            WHERE EXISTS (
                    SELECT 1 FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'bookings'
                      AND target.id = delivery.booking_id
                )
               OR EXISTS (
                    SELECT 1 FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'cancellations'
                      AND target.id = delivery.cancellation_id
                )
               OR EXISTS (
                    SELECT 1 FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'disruptions'
                      AND target.id = delivery.disruption_id
                )
               OR EXISTS (
                    SELECT 1 FROM {TARGET_TABLE} AS target
                    WHERE target.kind = 'deals'
                      AND target.id = delivery.deal_id
                )
        """,
    )
    db.execute(
        text(
            f"""
            INSERT INTO {RESTORATION_TABLE} (
                kind, id, field, value, source_id
            )
            SELECT
                'deal_status',
                deal.id,
                'status',
                to_jsonb(
                    CASE
                        WHEN deal.expires_at IS NOT NULL
                         AND deal.expires_at <= now()
                        THEN 'EXPIRED'
                        ELSE 'PROPOSED'
                    END
                ),
                booking.id
            FROM {TARGET_TABLE} AS booking_target
            JOIN bookings AS booking
              ON booking_target.kind = 'bookings'
             AND booking_target.id = booking.id
            JOIN deals AS deal ON deal.id = booking.deal_id
            WHERE deal.status IN ('BOOKED', 'CONFIRMED')
              AND NOT EXISTS (
                  SELECT 1
                  FROM {TARGET_TABLE} AS deal_target
                  WHERE deal_target.kind = 'deals'
                    AND deal_target.id = deal.id
              )
            ON CONFLICT DO NOTHING
            """
        )
    )
    _insert_target_select(
        db=db,
        kind="reset_watches",
        select_sql=f"""
            SELECT watch.id
            FROM trip_watches AS watch
            WHERE watch.status = 'FULFILLED'
              AND (
                  EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS booking_target
                      JOIN bookings AS booking ON booking.id = booking_target.id
                      JOIN deals AS deal ON deal.id = booking.deal_id
                      WHERE booking_target.kind = 'bookings'
                        AND deal.watch_id = watch.id
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM {TARGET_TABLE} AS deal_target
                      JOIN deals AS deal ON deal.id = deal_target.id
                      WHERE deal_target.kind = 'deals'
                        AND deal.watch_id = watch.id
                        AND deal.status = 'BOOKED'
                  )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM bookings AS retained_booking
                  JOIN deals AS retained_deal
                    ON retained_deal.id = retained_booking.deal_id
                  WHERE retained_deal.watch_id = watch.id
                    AND NOT EXISTS (
                        SELECT 1
                        FROM {TARGET_TABLE} AS booking_target
                        WHERE booking_target.kind = 'bookings'
                          AND booking_target.id = retained_booking.id
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM deals AS retained_deal
                  WHERE retained_deal.watch_id = watch.id
                    AND retained_deal.status IN ('BOOKED', 'CONFIRMED')
                    AND NOT EXISTS (
                        SELECT 1
                        FROM {TARGET_TABLE} AS deal_target
                        WHERE deal_target.kind = 'deals'
                          AND deal_target.id = retained_deal.id
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM {RESTORATION_TABLE} AS restoration
                        WHERE restoration.kind = 'deal_status'
                          AND restoration.id = retained_deal.id
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM tramp_stamp_ledger AS stamp
                  JOIN bookings AS stamped_booking
                    ON stamped_booking.id = stamp.booking_id
                  JOIN deals AS stamped_deal
                    ON stamped_deal.id = stamped_booking.deal_id
                  WHERE stamped_deal.watch_id = watch.id
              )
        """,
    )
    _populate_audit_targets(db=db)


def _populate_audit_targets(*, db: Session) -> None:
    target_conditions = [
        (f"audit.target = '{prefix}:' || target.id::text AND target.kind = '{field_name}'")
        for prefix, plan_field in AUDIT_TARGET_PREFIX_FIELDS.items()
        for field_name, mapped_field in TARGET_KIND_FIELDS
        if mapped_field == plan_field
    ]
    metadata_conditions = [
        (f"audit.meta_json->>'{metadata_key}' = target.id::text AND target.kind = '{field_name}'")
        for metadata_key, plan_field in AUDIT_METADATA_FIELDS.items()
        for field_name, mapped_field in TARGET_KIND_FIELDS
        if mapped_field == plan_field
    ]
    condition_sql = " OR ".join([*target_conditions, *metadata_conditions])
    _insert_target_select(
        db=db,
        kind="audit_log",
        select_sql=f"""
            SELECT audit.id
            FROM audit_log AS audit
            WHERE EXISTS (
                SELECT 1
                FROM {TARGET_TABLE} AS target
                WHERE {condition_sql}
            )
        """,
    )


def _build_database_plan(*, db: Session) -> PurgePlan:
    _prepare_target_tables(db=db)
    _populate_base_targets(db=db)
    _ensure_no_stamped_booking_targets(db=db)
    unknown_cancellation_count, cancellation_warnings = _populate_cancellation_targets(db=db)
    unreverted_feedback_count, feedback_warnings = _populate_feedback_targets(db=db)
    _populate_dependent_targets(db=db)
    warnings = tuple(sorted({*cancellation_warnings, *feedback_warnings}))
    counts = _database_target_counts(db=db)
    reset_watch_count = _target_count(db=db, kind="reset_watches")
    plan_digest = _database_plan_digest(
        db=db,
        counts=counts,
        reset_watch_count=reset_watch_count,
        warnings=warnings,
        unreverted_feedback_count=unreverted_feedback_count,
        unknown_cancellation_count=unknown_cancellation_count,
    )
    id_fields = {
        field_name: _export_target_ids(
            db=db,
            kind=kind,
            count=counts[kind],
        )
        for kind, field_name in TARGET_KIND_FIELDS
    }
    id_fields["reset_watch_ids"] = _export_target_ids(
        db=db,
        kind="reset_watches",
        count=reset_watch_count,
    )
    restorations = _export_restorations(db=db)
    return PurgePlan(
        **id_fields,
        booking_status_restorations=restorations["booking_status"],
        deal_status_restorations=restorations["deal_status"],
        watch_status_restorations=restorations["watch_status"],
        watch_state_restorations=restorations["watch_state"],
        warnings=warnings,
        unreverted_feedback_count=unreverted_feedback_count,
        unknown_cancellation_count=unknown_cancellation_count,
        deleted_count_overrides=tuple((kind, counts[kind]) for kind, _ in TARGET_KIND_FIELDS),
        plan_digest_override=plan_digest,
        reset_watch_count_override=reset_watch_count,
        uses_server_targets=True,
    )


def _database_target_counts(*, db: Session) -> dict[str, int]:
    counts = {kind: 0 for kind, _ in TARGET_KIND_FIELDS}
    target_kinds = ", ".join(f"'{kind}'" for kind in counts)
    for kind, count in db.execute(
        text(
            f"""
            SELECT kind, count(*)
            FROM {TARGET_TABLE}
            WHERE kind IN ({target_kinds})
            GROUP BY kind
            """
        )
    ):
        counts[kind] = int(count)
    return counts


def _target_count(*, db: Session, kind: str) -> int:
    return int(
        db.scalar(
            text(f"SELECT count(*) FROM {TARGET_TABLE} WHERE kind = :kind"),
            {"kind": kind},
        )
        or 0
    )


def _database_plan_digest(
    *,
    db: Session,
    counts: dict[str, int],
    reset_watch_count: int,
    warnings: tuple[str, ...],
    unreverted_feedback_count: int,
    unknown_cancellation_count: int,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(
        json.dumps(
            {
                "counts": counts,
                "reset_watch_count": reset_watch_count,
                "warnings": warnings,
                "unreverted_feedback_count": unreverted_feedback_count,
                "unknown_cancellation_count": unknown_cancellation_count,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    target_kinds = ", ".join(
        f"'{kind}'" for kind in [*(kind for kind, _ in TARGET_KIND_FIELDS), "reset_watches"]
    )
    target_statement = text(
        f"""
        SELECT kind, id
        FROM {TARGET_TABLE}
        WHERE kind IN ({target_kinds})
        ORDER BY kind, id
        """
    ).execution_options(
        stream_results=True,
        yield_per=PLAN_STREAM_BATCH_SIZE,
    )
    for kind, target_id in db.execute(target_statement):
        hasher.update(f"\n{kind}:{target_id}".encode())
    restoration_statement = text(
        f"""
        SELECT kind, id, field, value::text, source_id
        FROM {RESTORATION_TABLE}
        ORDER BY kind, id, field
        """
    ).execution_options(
        stream_results=True,
        yield_per=PLAN_STREAM_BATCH_SIZE,
    )
    for kind, target_id, field, value, source_id in db.execute(restoration_statement):
        hasher.update(f"\nrestore:{kind}:{target_id}:{field}:{value}:{source_id}".encode())
    return hasher.hexdigest()


def _export_target_ids(
    *,
    db: Session,
    kind: str,
    count: int,
) -> frozenset[UUID]:
    if count > PLAN_ID_EXPORT_LIMIT:
        return frozenset()
    return frozenset(
        db.scalars(
            text(
                f"""
                SELECT id
                FROM {TARGET_TABLE}
                WHERE kind = :kind
                ORDER BY id
                """
            ),
            {"kind": kind},
        )
    )


def _export_restorations(
    *,
    db: Session,
) -> dict[str, tuple[Any, ...]]:
    counts = {
        row.kind: row[1]
        for row in db.execute(
            text(
                f"""
                SELECT kind, count(*)
                FROM {RESTORATION_TABLE}
                GROUP BY kind
                """
            )
        )
    }
    exported: dict[str, tuple[Any, ...]] = {
        "booking_status": (),
        "deal_status": (),
        "watch_status": (),
        "watch_state": (),
    }
    for kind, count in counts.items():
        if count > PLAN_ID_EXPORT_LIMIT:
            continue
        rows = list(
            db.execute(
                text(
                    f"""
                    SELECT id, field, value
                    FROM {RESTORATION_TABLE}
                    WHERE kind = :kind
                    ORDER BY id, field
                    """
                ),
                {"kind": kind},
            )
        )
        if kind == "booking_status":
            exported[kind] = tuple((row.id, BookingStatus(str(row.value).lower())) for row in rows)
        elif kind == "deal_status":
            exported[kind] = tuple((row.id, DealStatus(str(row.value).lower())) for row in rows)
        elif kind == "watch_status":
            exported[kind] = tuple(
                (row.id, TripWatchStatus(str(row.value).lower())) for row in rows
            )
        elif kind == "watch_state":
            exported[kind] = tuple((row.id, row.field, row.value) for row in rows)
    return exported


def preview_test_data_purge(*, db: Session) -> PurgePlan:
    acquire_activity_maintenance_lock(db)
    return _build_database_plan(db=db)


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
        plan = _build_database_plan(db=db)
        if plan.plan_digest != preview_digest:
            raise PurgePlanChangedError(
                "Purge preview changed. Request a new preview and confirm that plan_digest."
            )

        actual_counts = _execute_server_deletes(db=db)
        if actual_counts != plan.deleted_counts:
            raise PurgeSafetyError(
                "Purge target counts changed during execution; all changes were rolled back."
            )
        _apply_server_restorations(db=db)
        reset_watch_count = _reset_server_watches(db=db)
        if reset_watch_count != plan.reset_watch_count:
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
                    "unknown_cancellation_count": plan.unknown_cancellation_count,
                },
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.expunge_all()
    return plan


def _execute_server_deletes(*, db: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for kind in (
        "audit_log",
        "notification_deliveries",
        "spend_ledger",
        "deal_feedback",
        "cancellations",
        "disruptions",
        "booking_attempts",
        "bookings",
        "deals",
        "price_observations",
        "suppressed_attributes",
        "rejected_fingerprints",
        "price_stats",
    ):
        table_name = kind
        result = db.execute(
            text(
                f"""
                DELETE FROM {table_name} AS record
                USING {TARGET_TABLE} AS target
                WHERE target.kind = :kind
                  AND target.id = record.id
                """
            ),
            {"kind": kind},
        )
        counts[kind] = int(getattr(result, "rowcount", 0) or 0)
    return counts


def _apply_server_restorations(*, db: Session) -> None:
    restoration_statements = {
        "booking_status": f"""
            UPDATE bookings AS booking
            SET status = (restoration.value #>> '{{}}')::booking_status
            FROM {RESTORATION_TABLE} AS restoration
            WHERE restoration.kind = 'booking_status'
              AND restoration.id = booking.id
        """,
        "deal_status": f"""
            UPDATE deals AS deal
            SET
                status = (restoration.value #>> '{{}}')::deal_status,
                confirm_token_hash = NULL,
                rejected_reason = NULL
            FROM {RESTORATION_TABLE} AS restoration
            WHERE restoration.kind = 'deal_status'
              AND restoration.id = deal.id
        """,
        "watch_status": f"""
            UPDATE trip_watches AS watch
            SET status = (restoration.value #>> '{{}}')::trip_watch_status
            FROM {RESTORATION_TABLE} AS restoration
            WHERE restoration.kind = 'watch_status'
              AND restoration.id = watch.id
        """,
    }
    for kind, statement in restoration_statements.items():
        expected = int(
            db.scalar(
                text(f"SELECT count(*) FROM {RESTORATION_TABLE} WHERE kind = :kind"),
                {"kind": kind},
            )
            or 0
        )
        result = db.execute(text(statement))
        if int(getattr(result, "rowcount", 0) or 0) != expected:
            raise PurgeSafetyError(f"A {kind} restoration target changed.")
    field_casts = {
        "value_pressure": "double precision",
        "quality_floor": "integer",
        "max_layover_minutes": "integer",
    }
    for field, cast_type in field_casts.items():
        expected = int(
            db.scalar(
                text(
                    f"""
                    SELECT count(*)
                    FROM {RESTORATION_TABLE}
                    WHERE kind = 'watch_state'
                      AND field = :field
                    """
                ),
                {"field": field},
            )
            or 0
        )
        result = db.execute(
            text(
                f"""
                UPDATE trip_watches AS watch
                SET {field} = CASE
                    WHEN restoration.value = 'null'::jsonb THEN NULL
                    ELSE (restoration.value #>> '{{}}')::{cast_type}
                END
                FROM {RESTORATION_TABLE} AS restoration
                WHERE restoration.kind = 'watch_state'
                  AND restoration.field = :field
                  AND restoration.id = watch.id
                """
            ),
            {"field": field},
        )
        if int(getattr(result, "rowcount", 0) or 0) != expected:
            raise PurgeSafetyError(f"A watch {field} restoration target changed.")


def _reset_server_watches(*, db: Session) -> int:
    result = db.execute(
        text(
            f"""
            UPDATE trip_watches AS watch
            SET status = 'ACTIVE'
            FROM {TARGET_TABLE} AS target
            WHERE target.kind = 'reset_watches'
              AND target.id = watch.id
              AND watch.status = 'FULFILLED'
              AND NOT EXISTS (
                  SELECT 1
                  FROM bookings AS retained_booking
                  JOIN deals AS retained_deal
                    ON retained_deal.id = retained_booking.deal_id
                  WHERE retained_deal.watch_id = watch.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM deals AS retained_deal
                  WHERE retained_deal.watch_id = watch.id
                    AND retained_deal.status IN ('BOOKED', 'CONFIRMED')
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM tramp_stamp_ledger AS stamp
                  JOIN bookings AS stamped_booking
                    ON stamped_booking.id = stamp.booking_id
                  JOIN deals AS stamped_deal
                    ON stamped_deal.id = stamped_booking.deal_id
                  WHERE stamped_deal.watch_id = watch.id
              )
            """
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)
