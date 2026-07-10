from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app import admin_activity_service, deal_service
from app.admin_activity_service import ActivitySnapshot, classify_activity
from app.api.schemas.bookings import CancellationResponse
from app.api.schemas.integrations import (
    AdminTestDataPurgeRequest,
    AdminTestDataPurgeResponse,
)
from app.db import models as db_models
from app.db.models import (
    AuditLog,
    Booking,
    BookingStatus,
    Cancellation,
    CancellationStatus,
    Deal,
    DealFeedback,
    DealStatus,
    NotificationDelivery,
    RejectedFingerprint,
    SpendLedger,
    SuppressedAttribute,
    TripWatch,
    TripWatchStatus,
    User,
)
from app.integrations.types import CancellationExecutionResult


def _watch(*, status: TripWatchStatus = TripWatchStatus.FULFILLED) -> TripWatch:
    return TripWatch(
        id=uuid4(),
        status=status,
        value_pressure=0.2,
        quality_floor=45,
        max_layover_minutes=90,
    )


def _deal(
    *,
    watch: TripWatch,
    source: str,
    status: DealStatus = DealStatus.BOOKED,
) -> Deal:
    return Deal(
        id=uuid4(),
        watch_id=watch.id,
        source=source,
        fingerprint_hash=f"fingerprint-{uuid4()}",
        status=status,
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
    )


def test_plan_digest_is_deterministic_and_schema_required() -> None:
    watch = _watch()
    deal = _deal(watch=watch, source="mock-duffel")

    first = classify_activity(ActivitySnapshot(watches=(watch,), deals=(deal,)))
    second = classify_activity(ActivitySnapshot(watches=(watch,), deals=(deal,)))

    assert first.plan_digest == second.plan_digest
    assert len(first.plan_digest) == 64
    int(first.plan_digest, 16)
    assert AdminTestDataPurgeRequest.model_fields["plan_digest"].is_required()
    assert "plan_digest" in AdminTestDataPurgeResponse.model_fields
    assert "warnings" in AdminTestDataPurgeResponse.model_fields
    assert "unreverted_feedback_count" in AdminTestDataPurgeResponse.model_fields


def test_audit_matching_is_typed_by_prefix_and_metadata_key() -> None:
    watch = _watch()
    simulated_deal = _deal(watch=watch, source="mock-duffel")
    correct_target = AuditLog(id=uuid4(), target=f"deal:{simulated_deal.id}", meta_json={})
    wrong_target_type = AuditLog(
        id=uuid4(),
        target=f"booking:{simulated_deal.id}",
        meta_json={},
    )
    wrong_metadata_type = AuditLog(
        id=uuid4(),
        target="maintenance:unrelated",
        meta_json={"booking_id": str(simulated_deal.id)},
    )
    unknown_target_type = AuditLog(
        id=uuid4(),
        target=f"other:{simulated_deal.id}",
        meta_json={},
    )

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(simulated_deal,),
            audit_logs=(
                correct_target,
                wrong_target_type,
                wrong_metadata_type,
                unknown_target_type,
            ),
        )
    )

    assert plan.audit_log_ids == frozenset({correct_target.id})


def test_simulated_cancellation_on_live_booking_selects_only_its_effects() -> None:
    watch = _watch(status=TripWatchStatus.ACTIVE)
    live_deal = _deal(watch=watch, source="live-duffel")
    live_booking = Booking(
        id=uuid4(),
        deal_id=live_deal.id,
        provider="Duffel",
        status=BookingStatus.CANCELLED,
    )
    cancellation = Cancellation(id=uuid4(), booking_id=live_booking.id)
    cancellation.provider = "mock-booking"
    cancellation.provider_payload_json = {"simulated": True}
    cancellation.execution_simulated = True
    cancellation.status = CancellationStatus.REFUNDED
    cancellation.prior_booking_status = BookingStatus.TICKETED
    cancellation.prior_watch_status = TripWatchStatus.FULFILLED

    refund = SpendLedger(id=uuid4(), booking_id=live_booking.id)
    refund.cancellation_id = cancellation.id
    original_charge = SpendLedger(id=uuid4(), booking_id=live_booking.id)
    original_charge.cancellation_id = None
    cancellation_notice = NotificationDelivery(id=uuid4(), booking_id=live_booking.id)
    cancellation_notice.cancellation_id = cancellation.id
    booking_notice = NotificationDelivery(id=uuid4(), booking_id=live_booking.id)
    booking_notice.cancellation_id = None
    cancellation_audit = AuditLog(
        id=uuid4(),
        target=f"booking:{live_booking.id}",
        meta_json={"cancellation_id": str(cancellation.id)},
    )
    booking_audit = AuditLog(
        id=uuid4(),
        target=f"booking:{live_booking.id}",
        meta_json={},
    )

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(live_deal,),
            bookings=(live_booking,),
            cancellations=(cancellation,),
            spend_ledger=(refund, original_charge),
            notification_deliveries=(cancellation_notice, booking_notice),
            audit_logs=(cancellation_audit, booking_audit),
        )
    )

    assert plan.booking_ids == frozenset()
    assert plan.deal_ids == frozenset()
    assert plan.cancellation_ids == frozenset({cancellation.id})
    assert plan.spend_ledger_ids == frozenset({refund.id})
    assert plan.notification_delivery_ids == frozenset({cancellation_notice.id})
    assert plan.audit_log_ids == frozenset({cancellation_audit.id})
    assert plan.booking_status_restorations == ((live_booking.id, BookingStatus.TICKETED),)
    assert plan.watch_status_restorations == ((watch.id, TripWatchStatus.FULFILLED),)


def test_cancellation_restore_preserves_subsequent_booking_and_watch_changes() -> None:
    watch = _watch(status=TripWatchStatus.PAUSED)
    live_deal = _deal(watch=watch, source="live-duffel")
    live_booking = Booking(
        id=uuid4(),
        deal_id=live_deal.id,
        provider="Duffel",
        status=BookingStatus.TICKETED,
    )
    cancellation = Cancellation(
        id=uuid4(),
        booking_id=live_booking.id,
        provider="mock-booking",
        execution_simulated=True,
        status=CancellationStatus.REFUNDED,
        prior_booking_status=BookingStatus.BOOKED,
        prior_watch_status=TripWatchStatus.FULFILLED,
    )

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(live_deal,),
            bookings=(live_booking,),
            cancellations=(cancellation,),
        )
    )

    assert plan.cancellation_ids == frozenset({cancellation.id})
    assert plan.booking_status_restorations == ()
    assert plan.watch_status_restorations == ()
    assert any("subsequently changed" in warning for warning in plan.warnings)


def test_unknown_legacy_cancellation_is_retained_and_reported() -> None:
    watch = _watch(status=TripWatchStatus.FULFILLED)
    live_deal = _deal(watch=watch, source="live-duffel")
    live_booking = Booking(
        id=uuid4(),
        deal_id=live_deal.id,
        provider="Duffel",
        status=BookingStatus.TICKETED,
    )
    cancellation = Cancellation(
        id=uuid4(),
        booking_id=live_booking.id,
        status=CancellationStatus.REQUESTED,
    )
    cancellation.provenance = "unknown"

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(live_deal,),
            bookings=(live_booking,),
            cancellations=(cancellation,),
        )
    )

    assert cancellation.id not in plan.cancellation_ids
    assert plan.unknown_cancellation_count == 1
    assert any("unknown provenance" in warning for warning in plan.warnings)


def test_simulated_booking_restores_retained_live_deal_state() -> None:
    watch = _watch()
    live_deal = _deal(watch=watch, source="live-duffel", status=DealStatus.BOOKED)
    simulated_booking = Booking(
        id=uuid4(),
        deal_id=live_deal.id,
        provider="mock-booking",
        status=BookingStatus.TICKETED,
    )

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(live_deal,),
            bookings=(simulated_booking,),
        )
    )

    assert plan.booking_ids == frozenset({simulated_booking.id})
    assert plan.deal_ids == frozenset()
    assert plan.deal_status_restorations == ((live_deal.id, DealStatus.PROPOSED),)
    assert plan.reset_watch_ids == frozenset({watch.id})


def test_unprovable_simulated_feedback_is_reported_without_guessing() -> None:
    watch = _watch(status=TripWatchStatus.ACTIVE)
    simulated_deal = _deal(
        watch=watch,
        source="mock-duffel",
        status=DealStatus.REJECTED,
    )
    feedback = DealFeedback(
        id=uuid4(),
        watch_id=watch.id,
        deal_id=simulated_deal.id,
        action_taken_json={"value_pressure": 0.2},
        created_at=datetime(2026, 7, 10, tzinfo=UTC),
    )

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(simulated_deal,),
            deal_feedback=(feedback,),
        )
    )

    assert plan.watch_state_restorations == ()
    assert feedback.id not in plan.deal_feedback_ids
    assert simulated_deal.id not in plan.deal_ids
    assert plan.unreverted_feedback_count == 1
    assert any("could not be safely reverted" in warning for warning in plan.warnings)


def test_provable_simulated_feedback_restores_prior_watch_state() -> None:
    watch = _watch(status=TripWatchStatus.ACTIVE)
    simulated_deal = _deal(
        watch=watch,
        source="mock-duffel",
        status=DealStatus.REJECTED,
    )
    feedback = DealFeedback(
        id=uuid4(),
        watch_id=watch.id,
        deal_id=simulated_deal.id,
        action_taken_json={
            "value_pressure": 0.2,
            "prior_watch_state": {"value_pressure": 0.0},
        },
        created_at=datetime(2026, 7, 10, tzinfo=UTC),
    )

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(simulated_deal,),
            deal_feedback=(feedback,),
        )
    )

    assert plan.watch_state_restorations == ((watch.id, "value_pressure", 0.0),)
    assert plan.unreverted_feedback_count == 0
    assert plan.warnings == ()


def test_production_has_no_whole_table_snapshot_loader() -> None:
    assert not hasattr(admin_activity_service, "_load_activity_snapshot")


def test_cancellation_effect_models_expose_explicit_provenance_links() -> None:
    assert {
        "provider",
        "provider_correlation_id",
        "provider_payload_json",
        "execution_simulated",
        "prior_booking_status",
        "prior_watch_status",
    }.issubset(Cancellation.__table__.c.keys())
    assert "cancellation_id" in SpendLedger.__table__.c
    assert "cancellation_id" in NotificationDelivery.__table__.c


def test_cancellation_provenance_and_unknown_count_are_explicit() -> None:
    assert hasattr(db_models, "CancellationProvenance")
    assert "provenance" in Cancellation.__table__.c
    assert "unknown_cancellation_count" in AdminTestDataPurgeResponse.model_fields


def test_cancellation_connector_and_response_require_execution_provenance() -> None:
    result = CancellationExecutionResult(
        provider="mock-booking",
        simulated=True,
        status=SimpleNamespace(value="refunded"),
        refund_expected=1,
        refund_received=1,
        currency="USD",
        resolved_at=None,
        provider_payload={"simulated": True},
    )

    assert result.provider == "mock-booking"
    assert result.simulated is True
    assert "provider" in CancellationResponse.model_fields
    assert "execution_simulated" in CancellationResponse.model_fields


def test_simulated_rejection_records_feedback_without_durable_learning(
    monkeypatch,
) -> None:
    user = User(id=uuid4())
    watch = _watch(status=TripWatchStatus.ACTIVE)
    simulated_deal = _deal(
        watch=watch,
        source="mock-duffel",
        status=DealStatus.PROPOSED,
    )
    added: list[object] = []
    lock_calls: list[object] = []
    db = SimpleNamespace(
        add=added.append,
        commit=lambda: None,
        refresh=lambda _value: None,
    )
    monkeypatch.setattr(
        deal_service,
        "acquire_activity_writer_lock",
        lambda session: lock_calls.append(session),
    )
    monkeypatch.setattr(
        deal_service,
        "get_owned_deal_record",
        lambda **_kwargs: simulated_deal,
    )
    monkeypatch.setattr(
        deal_service,
        "get_owned_watch_for_deal",
        lambda **_kwargs: watch,
    )

    response = deal_service.reject_deal(
        db=db,
        user=user,
        deal_id=simulated_deal.id,
        reason="too_pricey",
    )

    feedback = next(value for value in added if isinstance(value, DealFeedback))
    assert lock_calls == [db]
    assert response.action_taken == {
        "reason": "too_pricey",
        "durable_learning_applied": False,
        "simulated_deal": True,
    }
    assert feedback.action_taken_json == response.action_taken
    assert "without changing durable learning" in response.detail
    assert watch.value_pressure == 0.2
    assert not any(isinstance(value, (RejectedFingerprint, SuppressedAttribute)) for value in added)
