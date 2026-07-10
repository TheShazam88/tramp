from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Booking,
    BookingAttempt,
    Cancellation,
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


class PurgeSafetyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActivitySnapshot:
    watches: tuple[TripWatch, ...] = ()
    observations: tuple[PriceObservation, ...] = ()
    price_stats: tuple[PriceStat, ...] = ()
    suppressed_attributes: tuple[SuppressedAttribute, ...] = ()
    rejected_fingerprints: tuple[RejectedFingerprint, ...] = ()
    deals: tuple[Deal, ...] = ()
    deal_feedback: tuple[DealFeedback, ...] = ()
    bookings: tuple[Booking, ...] = ()
    booking_attempts: tuple[BookingAttempt, ...] = ()
    cancellations: tuple[Cancellation, ...] = ()
    spend_ledger: tuple[SpendLedger, ...] = ()
    tramp_stamp_ledger: tuple[TrampStampLedger, ...] = ()
    disruptions: tuple[Disruption, ...] = ()
    notification_deliveries: tuple[NotificationDelivery, ...] = ()
    audit_logs: tuple[AuditLog, ...] = ()


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
    reset_watch_ids: frozenset[UUID] = frozenset()

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


def classify_activity(snapshot: ActivitySnapshot) -> PurgePlan:
    """Classify generated activity without reading or mutating the database.

    Learning rows deliberately require positive provenance. A rejected fingerprint must have
    been created in the same transaction as feedback on a selected simulated deal, and it must
    not collide with a retained observation or deal. A suppression additionally must be named
    in that feedback's ``action_taken_json``. Rows with older or mixed provenance are retained.
    """

    observation_ids = frozenset(
        observation.id
        for observation in snapshot.observations
        if source_is_simulated(observation.source)
    )
    deal_ids = frozenset(deal.id for deal in snapshot.deals if source_is_simulated(deal.source))

    explicit_simulated_attempts = tuple(
        attempt
        for attempt in snapshot.booking_attempts
        if payload_is_simulated(attempt.request_payload_json)
        or payload_is_simulated(attempt.response_payload_json)
    )
    simulated_attempt_booking_ids = {
        attempt.booking_id
        for attempt in explicit_simulated_attempts
        if attempt.booking_id is not None
    }
    booking_ids = frozenset(
        booking.id
        for booking in snapshot.bookings
        if booking.deal_id in deal_ids
        or provider_is_simulated(booking.provider)
        or booking.id in simulated_attempt_booking_ids
    )
    booking_attempt_ids = frozenset(
        attempt.id
        for attempt in snapshot.booking_attempts
        if attempt.deal_id in deal_ids
        or attempt.booking_id in booking_ids
        or attempt in explicit_simulated_attempts
    )

    stamped_booking_ids = {stamp.booking_id for stamp in snapshot.tramp_stamp_ledger}
    unsafe_booking_ids = booking_ids & stamped_booking_ids
    if unsafe_booking_ids:
        formatted = ", ".join(str(value) for value in sorted(unsafe_booking_ids, key=str))
        raise PurgeSafetyError(
            "Purge would delete a booking referenced by TrampStampLedger: "
            f"{formatted}. Stamped bookings must be preserved."
        )

    cancellation_ids = frozenset(
        cancellation.id
        for cancellation in snapshot.cancellations
        if cancellation.booking_id in booking_ids
    )
    disruption_ids = frozenset(
        disruption.id
        for disruption in snapshot.disruptions
        if disruption.booking_id in booking_ids or _disruption_is_manual_test(disruption)
    )
    notification_delivery_ids = frozenset(
        delivery.id
        for delivery in snapshot.notification_deliveries
        if delivery.booking_id in booking_ids
        or delivery.deal_id in deal_ids
        or delivery.disruption_id in disruption_ids
    )
    spend_ledger_ids = frozenset(
        entry.id for entry in snapshot.spend_ledger if entry.booking_id in booking_ids
    )
    deal_feedback_ids = frozenset(
        feedback.id for feedback in snapshot.deal_feedback if feedback.deal_id in deal_ids
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
    )
    price_stat_ids = frozenset(stat.id for stat in snapshot.price_stats)

    selected_entity_ids = frozenset().union(
        observation_ids,
        price_stat_ids,
        suppressed_attribute_ids,
        rejected_fingerprint_ids,
        deal_ids,
        deal_feedback_ids,
        booking_ids,
        booking_attempt_ids,
        cancellation_ids,
        spend_ledger_ids,
        disruption_ids,
        notification_delivery_ids,
    )
    audit_log_ids = frozenset(
        audit.id
        for audit in snapshot.audit_logs
        if _value_references_selected_id(audit.target, selected_entity_ids)
        or _value_references_selected_id(audit.meta_json, selected_entity_ids)
    )
    reset_watch_ids = _watch_ids_to_reset(
        snapshot=snapshot,
        booking_ids=booking_ids,
        deal_ids=deal_ids,
    )

    return PurgePlan(
        observation_ids=observation_ids,
        price_stat_ids=price_stat_ids,
        suppressed_attribute_ids=suppressed_attribute_ids,
        rejected_fingerprint_ids=rejected_fingerprint_ids,
        deal_ids=deal_ids,
        deal_feedback_ids=deal_feedback_ids,
        booking_ids=booking_ids,
        booking_attempt_ids=booking_attempt_ids,
        cancellation_ids=cancellation_ids,
        spend_ledger_ids=spend_ledger_ids,
        disruption_ids=disruption_ids,
        notification_delivery_ids=notification_delivery_ids,
        audit_log_ids=audit_log_ids,
        reset_watch_ids=reset_watch_ids,
    )


def _disruption_is_manual_test(disruption: Disruption) -> bool:
    value = disruption.type
    return value == DisruptionType.MANUAL_TEST or str(value).lower() in {
        DisruptionType.MANUAL_TEST.value,
        DisruptionType.MANUAL_TEST.name.lower(),
    }


def _suppression_keys(feedback: DealFeedback) -> frozenset[tuple[UUID, str, str]]:
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
        attr_type = attr_type.strip()
        attr_value = attr_value.strip()
        if attr_type and attr_value:
            keys.add((feedback.watch_id, attr_type, attr_value))
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
        evidence = (*key, suppression.created_at)
        if evidence in selected_evidence and key not in retained_keys:
            selected.add(suppression.id)
    return frozenset(selected)


def _test_derived_rejected_fingerprint_ids(
    *,
    snapshot: ActivitySnapshot,
    selected_feedback_ids: frozenset[UUID],
    selected_deal_ids: frozenset[UUID],
    selected_observation_ids: frozenset[UUID],
) -> frozenset[UUID]:
    deals_by_id = {deal.id: deal for deal in snapshot.deals}
    selected_evidence: set[tuple[UUID, str, object]] = set()
    for feedback in snapshot.deal_feedback:
        deal = deals_by_id.get(feedback.deal_id)
        if (
            feedback.id in selected_feedback_ids
            and deal is not None
            and deal.id in selected_deal_ids
        ):
            selected_evidence.add((deal.watch_id, deal.fingerprint_hash, feedback.created_at))

    retained_fingerprints = {
        (deal.watch_id, deal.fingerprint_hash)
        for deal in snapshot.deals
        if deal.id not in selected_deal_ids
    }
    retained_fingerprints.update(
        (observation.watch_id, observation.fingerprint_hash)
        for observation in snapshot.observations
        if observation.id not in selected_observation_ids
    )

    return frozenset(
        rejection.id
        for rejection in snapshot.rejected_fingerprints
        if (
            rejection.watch_id,
            rejection.fingerprint_hash,
            rejection.created_at,
        )
        in selected_evidence
        and (rejection.watch_id, rejection.fingerprint_hash) not in retained_fingerprints
    )


def _value_references_selected_id(value: Any, selected_ids: frozenset[UUID]) -> bool:
    if isinstance(value, UUID):
        return value in selected_ids
    if isinstance(value, str):
        candidates = [value.strip()]
        if ":" in value:
            candidates.append(value.rsplit(":", 1)[-1].strip())
        for candidate in candidates:
            try:
                if UUID(candidate) in selected_ids:
                    return True
            except ValueError:
                continue
        return False
    if isinstance(value, Mapping):
        return any(_value_references_selected_id(item, selected_ids) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_value_references_selected_id(item, selected_ids) for item in value)
    return False


def _watch_ids_to_reset(
    *,
    snapshot: ActivitySnapshot,
    booking_ids: frozenset[UUID],
    deal_ids: frozenset[UUID],
) -> frozenset[UUID]:
    deals_by_id = {deal.id: deal for deal in snapshot.deals}
    selected_activity_watch_ids = {
        deal.watch_id
        for deal in snapshot.deals
        if deal.id in deal_ids and deal.status == DealStatus.BOOKED
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
    return frozenset(
        watch.id
        for watch in snapshot.watches
        if watch.status == TripWatchStatus.FULFILLED
        and watch.id in selected_activity_watch_ids
        and watch.id not in retained_booking_watch_ids
    )


def _load_activity_snapshot(*, db: Session) -> ActivitySnapshot:
    with db.no_autoflush:
        return ActivitySnapshot(
            watches=tuple(db.scalars(select(TripWatch))),
            observations=tuple(db.scalars(select(PriceObservation))),
            price_stats=tuple(db.scalars(select(PriceStat))),
            suppressed_attributes=tuple(db.scalars(select(SuppressedAttribute))),
            rejected_fingerprints=tuple(db.scalars(select(RejectedFingerprint))),
            deals=tuple(db.scalars(select(Deal))),
            deal_feedback=tuple(db.scalars(select(DealFeedback))),
            bookings=tuple(db.scalars(select(Booking))),
            booking_attempts=tuple(db.scalars(select(BookingAttempt))),
            cancellations=tuple(db.scalars(select(Cancellation))),
            spend_ledger=tuple(db.scalars(select(SpendLedger))),
            tramp_stamp_ledger=tuple(db.scalars(select(TrampStampLedger))),
            disruptions=tuple(db.scalars(select(Disruption))),
            notification_deliveries=tuple(db.scalars(select(NotificationDelivery))),
            audit_logs=tuple(db.scalars(select(AuditLog))),
        )


def preview_test_data_purge(*, db: Session) -> PurgePlan:
    return classify_activity(_load_activity_snapshot(db=db))


def execute_test_data_purge(
    *,
    db: Session,
    actor: User,
    confirmation: str,
) -> PurgePlan:
    if confirmation != PURGE_CONFIRMATION:
        raise ValueError(f"Confirmation must exactly match {PURGE_CONFIRMATION!r}.")

    try:
        plan = classify_activity(_load_activity_snapshot(db=db))
        actual_counts = {
            "audit_log": _delete_ids(db=db, model=AuditLog, ids=plan.audit_log_ids),
            "notification_deliveries": _delete_ids(
                db=db,
                model=NotificationDelivery,
                ids=plan.notification_delivery_ids,
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
            "spend_ledger": _delete_ids(
                db=db,
                model=SpendLedger,
                ids=plan.spend_ledger_ids,
            ),
            "booking_attempts": _delete_ids(
                db=db,
                model=BookingAttempt,
                ids=plan.booking_attempt_ids,
            ),
            "bookings": _delete_ids(
                db=db,
                model=Booking,
                ids=plan.booking_ids,
            ),
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
        if actual_counts != plan.deleted_counts:
            raise PurgeSafetyError(
                "Purge target counts changed during execution; all changes were rolled back."
            )

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
                    "deleted_counts": actual_counts,
                    "reset_watch_count": reset_watch_count,
                },
            )
        )
        db.commit()
        db.expire_all()
        return plan
    except Exception:
        db.rollback()
        raise


def _delete_ids(
    *,
    db: Session,
    model: type[Any],
    ids: frozenset[UUID],
) -> int:
    if not ids:
        return 0
    result = db.execute(delete(model).where(model.id.in_(ids)))
    return int(getattr(result, "rowcount", 0) or 0)


def _reset_watches(*, db: Session, watch_ids: frozenset[UUID]) -> int:
    if not watch_ids:
        return 0
    result = db.execute(
        update(TripWatch)
        .where(
            TripWatch.id.in_(watch_ids),
            TripWatch.status == TripWatchStatus.FULFILLED,
        )
        .values(status=TripWatchStatus.ACTIVE)
    )
    return int(getattr(result, "rowcount", 0) or 0)
