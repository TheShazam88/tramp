from __future__ import annotations

import importlib
import inspect
from datetime import UTC, datetime
from uuid import uuid4

import pytest

import app.admin_activity_service as activity_service
import app.api.schemas.integrations as integration_schemas
from app.admin_activity_service import (
    ActivitySnapshot,
    PurgeSafetyError,
    classify_activity,
    execute_test_data_purge,
    preview_test_data_purge,
)
from app.config import get_settings
from app.db.models import (
    AuditLog,
    Booking,
    BookingAttempt,
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


def _deal(*, watch: TripWatch, source: str, fingerprint: str, booked: bool = False) -> Deal:
    return Deal(
        id=uuid4(),
        watch_id=watch.id,
        source=source,
        fingerprint_hash=fingerprint,
        status=DealStatus.BOOKED if booked else DealStatus.PROPOSED,
    )


def _booking(*, deal: Deal, provider: str) -> Booking:
    return Booking(id=uuid4(), deal_id=deal.id, provider=provider)


def test_classification_removes_only_proven_simulated_activity() -> None:
    learned_at = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)
    mock_only_watch = TripWatch(id=uuid4(), status=TripWatchStatus.FULFILLED)
    mixed_watch = TripWatch(id=uuid4(), status=TripWatchStatus.FULFILLED)
    active_watch = TripWatch(id=uuid4(), status=TripWatchStatus.ACTIVE)

    mock_deal = _deal(
        watch=mock_only_watch,
        source="live-amadeus+mock-booking",
        fingerprint="mock-fingerprint",
        booked=True,
    )
    mixed_mock_deal = _deal(
        watch=mixed_watch,
        source="mock-duffel",
        fingerprint="mixed-mock-fingerprint",
        booked=True,
    )
    mixed_live_deal = _deal(
        watch=mixed_watch,
        source="live-duffel",
        fingerprint="mixed-live-fingerprint",
        booked=True,
    )
    payload_simulated_deal = _deal(
        watch=active_watch,
        source="live-amadeus",
        fingerprint="payload-simulated-fingerprint",
    )
    live_deal = _deal(
        watch=active_watch,
        source="live-amadeus",
        fingerprint="live-fingerprint",
        booked=True,
    )

    mock_booking = _booking(deal=mock_deal, provider="Duffel")
    mixed_mock_booking = _booking(deal=mixed_mock_deal, provider="mock-booking")
    mixed_live_booking = _booking(deal=mixed_live_deal, provider="Duffel")
    payload_simulated_booking = _booking(deal=payload_simulated_deal, provider="Duffel")
    live_booking = _booking(deal=live_deal, provider="Duffel")

    linked_attempt = BookingAttempt(
        id=uuid4(),
        deal_id=mock_deal.id,
        booking_id=mock_booking.id,
        request_payload_json={},
        response_payload_json={},
    )
    explicit_attempt = BookingAttempt(
        id=uuid4(),
        deal_id=payload_simulated_deal.id,
        booking_id=payload_simulated_booking.id,
        request_payload_json={"simulated": True},
        response_payload_json={},
    )
    live_attempt = BookingAttempt(
        id=uuid4(),
        deal_id=live_deal.id,
        booking_id=live_booking.id,
        request_payload_json={},
        response_payload_json={"simulated": False},
    )

    selected_feedback = DealFeedback(
        id=uuid4(),
        watch_id=mock_only_watch.id,
        deal_id=mock_deal.id,
        action_taken_json={"suppressed": ["airline:ZZ"]},
        created_at=learned_at,
    )
    live_feedback = DealFeedback(
        id=uuid4(),
        watch_id=active_watch.id,
        deal_id=live_deal.id,
        action_taken_json={"suppressed": ["airline:LIVE"]},
        created_at=learned_at,
    )
    selected_suppression = SuppressedAttribute(
        id=uuid4(),
        watch_id=mock_only_watch.id,
        attr_type=SuppressedAttributeType.AIRLINE,
        attr_value="ZZ",
        created_at=learned_at,
    )
    live_suppression = SuppressedAttribute(
        id=uuid4(),
        watch_id=active_watch.id,
        attr_type=SuppressedAttributeType.AIRLINE,
        attr_value="LIVE",
        created_at=learned_at,
    )
    selected_rejection = RejectedFingerprint(
        id=uuid4(),
        watch_id=mock_only_watch.id,
        fingerprint_hash=mock_deal.fingerprint_hash,
        created_at=learned_at,
    )
    live_rejection = RejectedFingerprint(
        id=uuid4(),
        watch_id=active_watch.id,
        fingerprint_hash=live_deal.fingerprint_hash,
        created_at=learned_at,
    )

    manual_disruption = Disruption(
        id=uuid4(),
        booking_id=live_booking.id,
        type=DisruptionType.MANUAL_TEST,
    )
    live_disruption = Disruption(
        id=uuid4(),
        booking_id=live_booking.id,
        type=DisruptionType.SCHEDULE_CHANGE,
    )
    linked_disruption = Disruption(
        id=uuid4(),
        booking_id=mock_booking.id,
        type=DisruptionType.SCHEDULE_CHANGE,
    )
    linked_notification = NotificationDelivery(
        id=uuid4(),
        deal_id=mock_deal.id,
        booking_id=mock_booking.id,
    )
    manual_notification = NotificationDelivery(
        id=uuid4(),
        disruption_id=manual_disruption.id,
        booking_id=live_booking.id,
    )
    live_notification = NotificationDelivery(
        id=uuid4(),
        disruption_id=live_disruption.id,
        booking_id=live_booking.id,
    )
    linked_spend = SpendLedger(id=uuid4(), booking_id=mock_booking.id)
    live_spend = SpendLedger(id=uuid4(), booking_id=live_booking.id)

    selected_audit = AuditLog(
        id=uuid4(),
        target=f"deal:{mock_deal.id}",
        meta_json={"booking_id": str(mock_booking.id)},
    )
    manual_audit = AuditLog(
        id=uuid4(),
        target=f"booking:{live_booking.id}",
        meta_json={"disruption_id": str(manual_disruption.id)},
    )
    live_audit = AuditLog(
        id=uuid4(),
        target=f"deal:{live_deal.id}",
        meta_json={"booking_id": str(live_booking.id)},
    )

    mock_observation = PriceObservation(
        id=uuid4(),
        watch_id=mock_only_watch.id,
        source="mock-hotels",
        fingerprint_hash="mock-observation",
    )
    live_observation = PriceObservation(
        id=uuid4(),
        watch_id=active_watch.id,
        source="live-hotels",
        fingerprint_hash="live-observation",
    )
    price_stat = PriceStat(id=uuid4())

    snapshot = ActivitySnapshot(
        watches=(mock_only_watch, mixed_watch, active_watch),
        observations=(mock_observation, live_observation),
        price_stats=(price_stat,),
        suppressed_attributes=(selected_suppression, live_suppression),
        rejected_fingerprints=(selected_rejection, live_rejection),
        deals=(
            mock_deal,
            mixed_mock_deal,
            mixed_live_deal,
            payload_simulated_deal,
            live_deal,
        ),
        deal_feedback=(selected_feedback, live_feedback),
        bookings=(
            mock_booking,
            mixed_mock_booking,
            mixed_live_booking,
            payload_simulated_booking,
            live_booking,
        ),
        booking_attempts=(linked_attempt, explicit_attempt, live_attempt),
        disruptions=(manual_disruption, live_disruption, linked_disruption),
        notification_deliveries=(
            linked_notification,
            manual_notification,
            live_notification,
        ),
        spend_ledger=(linked_spend, live_spend),
        audit_logs=(selected_audit, manual_audit, live_audit),
    )

    plan = classify_activity(snapshot)

    assert plan.observation_ids == frozenset({mock_observation.id})
    assert plan.deal_ids == frozenset({mixed_mock_deal.id})
    assert plan.booking_ids == frozenset(
        {
            mock_booking.id,
            mixed_mock_booking.id,
            payload_simulated_booking.id,
        }
    )
    assert plan.booking_attempt_ids == frozenset({linked_attempt.id, explicit_attempt.id})
    assert plan.disruption_ids == frozenset({manual_disruption.id, linked_disruption.id})
    assert plan.notification_delivery_ids == frozenset(
        {linked_notification.id, manual_notification.id}
    )
    assert plan.spend_ledger_ids == frozenset({linked_spend.id})
    assert plan.deal_feedback_ids == frozenset()
    assert plan.suppressed_attribute_ids == frozenset()
    assert plan.rejected_fingerprint_ids == frozenset()
    assert plan.audit_log_ids == frozenset({selected_audit.id, manual_audit.id})
    assert plan.price_stat_ids == frozenset({price_stat.id})
    assert plan.reset_watch_ids == frozenset({mock_only_watch.id})

    assert live_deal.id not in plan.deal_ids
    assert mixed_live_booking.id not in plan.booking_ids
    assert live_attempt.id not in plan.booking_attempt_ids
    assert live_disruption.id not in plan.disruption_ids
    assert live_notification.id not in plan.notification_delivery_ids
    assert live_spend.id not in plan.spend_ledger_ids
    assert live_suppression.id not in plan.suppressed_attribute_ids
    assert live_rejection.id not in plan.rejected_fingerprint_ids
    assert live_audit.id not in plan.audit_log_ids
    assert mixed_watch.id not in plan.reset_watch_ids
    assert plan.unreverted_feedback_count == 1


def test_classification_fails_closed_for_ambiguous_learning_state() -> None:
    learned_at = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)
    earlier = datetime(2026, 7, 9, 9, 0, tzinfo=UTC)
    watch = TripWatch(id=uuid4(), status=TripWatchStatus.ACTIVE)
    mock_deal = _deal(watch=watch, source="mock-duffel", fingerprint="shared")
    live_deal = _deal(watch=watch, source="live-duffel", fingerprint="shared")
    selected_feedback = DealFeedback(
        id=uuid4(),
        watch_id=watch.id,
        deal_id=mock_deal.id,
        action_taken_json={"suppressed": ["airline:SHARED"]},
        created_at=learned_at,
    )
    preexisting_suppression = SuppressedAttribute(
        id=uuid4(),
        watch_id=watch.id,
        attr_type=SuppressedAttributeType.AIRLINE,
        attr_value="SHARED",
        created_at=earlier,
    )
    ambiguous_rejection = RejectedFingerprint(
        id=uuid4(),
        watch_id=watch.id,
        fingerprint_hash="shared",
        created_at=learned_at,
    )

    plan = classify_activity(
        ActivitySnapshot(
            watches=(watch,),
            deals=(mock_deal, live_deal),
            deal_feedback=(selected_feedback,),
            suppressed_attributes=(preexisting_suppression,),
            rejected_fingerprints=(ambiguous_rejection,),
        )
    )

    assert plan.suppressed_attribute_ids == frozenset()
    assert plan.rejected_fingerprint_ids == frozenset()
    assert plan.unreverted_feedback_count == 1
    assert any("could not be safely reverted" in warning for warning in plan.warnings)


def test_classification_rejects_a_stamped_simulated_booking() -> None:
    watch = TripWatch(id=uuid4(), status=TripWatchStatus.FULFILLED)
    deal = _deal(watch=watch, source="mock-duffel", fingerprint="stamped", booked=True)
    booking = _booking(deal=deal, provider="mock-booking")
    stamp = TrampStampLedger(id=uuid4(), booking_id=booking.id)

    with pytest.raises(PurgeSafetyError, match="TrampStampLedger"):
        classify_activity(
            ActivitySnapshot(
                watches=(watch,),
                deals=(deal,),
                bookings=(booking,),
                tramp_stamp_ledger=(stamp,),
            )
        )


def test_preview_is_nonmutating(monkeypatch: pytest.MonkeyPatch) -> None:
    session = object()
    snapshot = ActivitySnapshot()
    calls: list[object] = []

    monkeypatch.setattr(
        activity_service,
        "_build_database_plan",
        lambda *, db: (calls.append(db), classify_activity(snapshot))[1],
    )

    plan = preview_test_data_purge(db=session)

    assert calls == [session]
    assert plan.deleted_counts == {
        "audit_log": 0,
        "booking_attempts": 0,
        "bookings": 0,
        "cancellations": 0,
        "deal_feedback": 0,
        "deals": 0,
        "disruptions": 0,
        "notification_deliveries": 0,
        "price_observations": 0,
        "price_stats": 0,
        "rejected_fingerprints": 0,
        "spend_ledger": 0,
        "suppressed_attributes": 0,
    }


@pytest.mark.parametrize(
    "confirmation",
    [
        "",
        "purge test data",
        "PURGE TEST DATA ",
        " PURGE TEST DATA",
        "PURGE  TEST DATA",
    ],
)
def test_execute_requires_exact_confirmation_before_database_access(
    confirmation: str,
) -> None:
    actor = User(id=uuid4())

    with pytest.raises(ValueError, match="PURGE TEST DATA"):
        execute_test_data_purge(
            db=object(),
            actor=actor,
            confirmation=confirmation,
        )


def test_admin_purge_schemas_expose_confirmation_and_counts() -> None:
    assert hasattr(integration_schemas, "AdminTestDataPurgeRequest")
    assert hasattr(integration_schemas, "AdminTestDataPurgeResponse")

    request = integration_schemas.AdminTestDataPurgeRequest(
        confirmation="PURGE TEST DATA",
        plan_digest="a" * 64,
    )
    response = integration_schemas.AdminTestDataPurgeResponse(
        dry_run=True,
        deleted_counts={"deals": 2},
        reset_watch_count=1,
        plan_digest="a" * 64,
        warnings=[],
        unreverted_feedback_count=0,
        unknown_cancellation_count=0,
    )

    assert request.confirmation == "PURGE TEST DATA"
    assert request.plan_digest == "a" * 64
    assert response.model_dump() == {
        "dry_run": True,
        "deleted_counts": {"deals": 2},
        "reset_watch_count": 1,
        "plan_digest": "a" * 64,
        "warnings": [],
        "unreverted_feedback_count": 0,
        "unknown_cancellation_count": 0,
    }


def test_admin_purge_routes_are_registered_with_admin_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_SECRET", "test-master-secret-with-more-than-32-bytes")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://tramp.test")
    get_settings.cache_clear()
    admin_routes = importlib.import_module("app.api.routes.admin")
    require_admin = importlib.import_module("app.api.deps").require_admin

    routes = {
        (route.path, frozenset(route.methods or set())): route
        for route in admin_routes.router.routes
    }

    preview_route = routes[("/test-data/purge-preview", frozenset({"GET"}))]
    execute_route = routes[("/test-data/purge", frozenset({"POST"}))]

    assert require_admin in {dependency.call for dependency in preview_route.dependant.dependencies}
    assert require_admin in {dependency.call for dependency in execute_route.dependant.dependencies}
    assert inspect.iscoroutinefunction(preview_route.endpoint) is False
    assert inspect.iscoroutinefunction(execute_route.endpoint) is False
