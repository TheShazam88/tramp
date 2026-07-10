from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

os.environ.setdefault("APP_SECRET", "test-master-secret-with-more-than-32-bytes")
os.environ.setdefault("BOOKING_MASTER_KEY_PASSPHRASE", "test-master-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PUBLIC_BASE_URL", "https://tramp.test")
os.environ.setdefault("INITIAL_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("INITIAL_ADMIN_PASSWORD", "test-admin-password")

import app.admin_activity_service as activity_service
from app import booking_service
from app.activity_maintenance import acquire_activity_maintenance_lock
from app.admin_activity_service import (
    PurgePlanChangedError,
    execute_test_data_purge,
    preview_test_data_purge,
)
from app.api.deps import require_admin
from app.api.routes.admin import (
    preview_test_data_purge_record,
    purge_test_data_record,
)
from app.api.schemas.integrations import AdminTestDataPurgeRequest
from app.db.base import Base
from app.db.models import (
    Alliance,
    AuditLog,
    AutoBookMode,
    Booking,
    BookingAttempt,
    BookingAttemptStatus,
    BookingStatus,
    Cancellation,
    CancellationStatus,
    Deal,
    DealFeedback,
    DealFraming,
    DealStatus,
    DestinationMode,
    Disruption,
    DisruptionStatus,
    DisruptionType,
    FeedbackSignalType,
    IntegrationCredentialProfile,
    IntegrationEnvironment,
    LoyaltyAccount,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTransport,
    ObservationKind,
    PaymentMethod,
    PlatformIntegration,
    PriceObservation,
    PriceScopeType,
    PriceStat,
    ProgramType,
    RefreshInterval,
    RejectedFingerprint,
    SpendLedger,
    SuppressedAttribute,
    SuppressedAttributeType,
    TrampStampLedger,
    Traveler,
    TravelerGroup,
    TravelerRelationship,
    TripMode,
    TripTemplate,
    TripWatch,
    TripWatchStatus,
    User,
    UserPreference,
    UserRole,
    WatchTraveler,
)
from app.integrations.types import CancellationExecutionResult

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _migration_database_url() -> str:
    database_url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("MIGRATION_TEST_DATABASE_URL is not configured")
    if os.environ.get("MIGRATION_TEST_ALLOW_RESET") != "1":
        pytest.fail("MIGRATION_TEST_ALLOW_RESET=1 is required for destructive purge tests")

    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        pytest.fail("Test-data purge tests require a dedicated PostgreSQL database")
    return database_url


def _run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_SECRET": "purge-test-secret-with-at-least-thirty-two-bytes",
            "DATABASE_URL": database_url,
            "INITIAL_ADMIN_EMAIL": "admin@example.com",
            "INITIAL_ADMIN_PASSWORD": "test-admin-password",
            "PUBLIC_BASE_URL": "https://tramp-purge.test",
            "REDIS_URL": "redis://localhost:6379/0",
        }
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    database_url = _migration_database_url()
    engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            connection.exec_driver_sql("CREATE SCHEMA public")
    finally:
        engine.dispose()

    _run_alembic(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db(postgres_engine: Engine) -> Session:
    table_names = ", ".join(f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables))
    with postgres_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    with Session(postgres_engine, expire_on_commit=False) as session:
        yield session
        session.rollback()


def _add_user(db: Session, *, label: str, role: UserRole = UserRole.USER) -> User:
    user = User(
        id=uuid4(),
        email=f"{label}-{uuid4()}@example.com",
        password_hash="hashed",
        role=role,
        onboarding_completed=True,
        default_notify_channel=NotificationChannel.EMAIL,
    )
    db.add(user)
    db.flush()
    return user


def _add_watch(
    db: Session,
    *,
    user: User,
    status: TripWatchStatus,
    traveler_group_id: UUID | None = None,
) -> TripWatch:
    watch = TripWatch(
        id=uuid4(),
        user_id=user.id,
        status=status,
        trip_mode=TripMode.FLIGHTS_THEN_HOTELS,
        traveler_group_id=traveler_group_id,
        destination_mode=DestinationMode.FIXED,
        origin_iatas=["HND"],
        destination_iatas=["SIN"],
        avoid_redeye=False,
        glide_start_days=42,
        glide_end_days=3,
        quality_floor=40,
        luxury_vs_savings=0.6,
        prefer_refundable=False,
        loyalty_weighting=0.0,
        band_tolerance=0.1,
        value_pressure=0.0,
        include_airbnb=False,
        refresh_interval=RefreshInterval.DAILY,
        notify_channel=NotificationChannel.INHERIT,
        want_car=False,
        auto_book_mode=AutoBookMode.ALWAYS_CONFIRM,
    )
    db.add(watch)
    db.flush()
    return watch


def _add_deal(
    db: Session,
    *,
    watch: TripWatch,
    source: str,
    label: str,
    status: DealStatus = DealStatus.BOOKED,
) -> Deal:
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source=source,
        total_price=Decimal("640.00"),
        currency="USD",
        framing=DealFraming.BEST_VALUE,
        fingerprint_hash=f"{label}-{uuid4()}",
        status=status,
        payload_json={"title": label},
    )
    db.add(deal)
    db.flush()
    return deal


def _add_booking(
    db: Session,
    *,
    deal: Deal,
    provider: str,
    label: str,
) -> Booking:
    booking = Booking(
        id=uuid4(),
        deal_id=deal.id,
        provider=provider,
        provider_booking_ref=f"{label}-ref",
        status=BookingStatus.TICKETED,
        idempotency_key=f"{label}-{uuid4()}",
        amount_charged=Decimal("640.00"),
        currency="USD",
        loyalty_manual_followup=False,
        booked_at=datetime.now(UTC),
    )
    db.add(booking)
    db.flush()
    return booking


def _add_attempt(
    db: Session,
    *,
    watch: TripWatch,
    deal: Deal,
    booking: Booking,
    label: str,
    simulated: bool,
) -> BookingAttempt:
    attempt = BookingAttempt(
        id=uuid4(),
        deal_id=deal.id,
        booking_id=booking.id,
        watch_id=watch.id,
        idempotency_key=f"{label}-{uuid4()}",
        status=BookingAttemptStatus.BOOKED,
        recovery_required=False,
        provider=booking.provider,
        request_payload_json={"simulated": simulated},
        response_payload_json={"simulated": simulated},
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    return attempt


def _row_count(db: Session, model: type[object]) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_preview_and_execute_remove_only_simulated_activity(db: Session) -> None:
    learned_at = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)
    admin = _add_user(db, label="admin", role=UserRole.ADMIN)
    simulated_user = _add_user(db, label="simulated")
    live_user = _add_user(db, label="live")

    traveler = Traveler(
        id=uuid4(),
        user_id=live_user.id,
        traveler_relationship=TravelerRelationship.SELF,
        display_name="Live Traveler",
        legal_first_name="Live",
        legal_last_name="Traveler",
        dob=date(1990, 1, 1),
        nationality="JP",
    )
    db.add(traveler)
    db.flush()
    loyalty = LoyaltyAccount(
        id=uuid4(),
        traveler_id=traveler.id,
        program_type=ProgramType.AIRLINE,
        program_code="NH",
        alliance=Alliance.STAR,
        account_number="LIVE-123",
        preferred_earning_for_alliance=True,
    )
    group = TravelerGroup(
        id=uuid4(),
        user_id=live_user.id,
        name="Live group",
        traveler_ids=[traveler.id],
    )
    preference = UserPreference(
        id=uuid4(),
        user_id=live_user.id,
        home_airports=["HND"],
        default_luxury_vs_savings=0.6,
        avoid_redeye=False,
        prefer_refundable=True,
        seat_auto_select=False,
        default_notify_channel=NotificationChannel.INHERIT,
    )
    payment = PaymentMethod(
        id=uuid4(),
        user_id=live_user.id,
        label="Live card",
        brand="Visa",
        last4="4242",
        encrypted_blob="encrypted-live-card",
    )
    template = TripTemplate(
        id=uuid4(),
        user_id=live_user.id,
        name="Live template",
        watch_payload_json={"origin_iatas": ["HND"]},
    )
    credential_profile = IntegrationCredentialProfile(
        id=uuid4(),
        provider_key="duffel",
        label="Live Duffel",
        encrypted_credentials="encrypted-profile",
        updated_by=admin.id,
    )
    integration = PlatformIntegration(
        id=uuid4(),
        key="flights_duffel",
        encrypted_credentials="encrypted-integration",
        credential_profile_id=credential_profile.id,
        environment=IntegrationEnvironment.LIVE,
        enabled=True,
        feature_flags_json={"search": True},
        updated_by=admin.id,
    )
    db.add_all(
        [
            loyalty,
            group,
            preference,
            payment,
            template,
            credential_profile,
            integration,
        ]
    )
    db.flush()

    live_watch = _add_watch(
        db,
        user=live_user,
        status=TripWatchStatus.FULFILLED,
        traveler_group_id=group.id,
    )
    eligible_watch = _add_watch(
        db,
        user=simulated_user,
        status=TripWatchStatus.FULFILLED,
    )
    eligible_watch.value_pressure = 0.2
    mixed_watch = _add_watch(
        db,
        user=simulated_user,
        status=TripWatchStatus.FULFILLED,
    )
    watch_traveler = WatchTraveler(
        id=uuid4(),
        watch_id=live_watch.id,
        traveler_id=traveler.id,
    )
    db.add(watch_traveler)

    simulated_observation = PriceObservation(
        id=uuid4(),
        watch_id=eligible_watch.id,
        kind=ObservationKind.FLIGHT,
        source="live-amadeus+mock-hotels",
        observed_at=datetime.now(UTC),
        price=Decimal("300.00"),
        currency="USD",
        payload_json={"title": "Simulated"},
        fingerprint_hash="simulated-observation",
    )
    live_observation = PriceObservation(
        id=uuid4(),
        watch_id=live_watch.id,
        kind=ObservationKind.FLIGHT,
        source="live-amadeus",
        observed_at=datetime.now(UTC),
        price=Decimal("600.00"),
        currency="USD",
        payload_json={"title": "Live"},
        fingerprint_hash="live-observation",
    )
    stats = [
        PriceStat(
            id=uuid4(),
            scope_type=PriceScopeType.ROUTE_CABIN,
            scope_key=f"HND-SIN-{index}",
            month_bucket=date(2026, 7, 1),
            sample_n=1,
        )
        for index in range(2)
    ]
    db.add_all([simulated_observation, live_observation, *stats])

    simulated_deal = _add_deal(
        db,
        watch=eligible_watch,
        source="mock-duffel",
        label="simulated",
    )
    simulated_booking = _add_booking(
        db,
        deal=simulated_deal,
        provider="mock-booking",
        label="simulated",
    )
    simulated_attempt = _add_attempt(
        db,
        watch=eligible_watch,
        deal=simulated_deal,
        booking=simulated_booking,
        label="simulated",
        simulated=True,
    )

    live_deal = _add_deal(
        db,
        watch=live_watch,
        source="live-duffel",
        label="live",
    )
    live_booking = _add_booking(
        db,
        deal=live_deal,
        provider="Duffel",
        label="live",
    )
    live_attempt = _add_attempt(
        db,
        watch=live_watch,
        deal=live_deal,
        booking=live_booking,
        label="live",
        simulated=False,
    )

    mixed_simulated_deal = _add_deal(
        db,
        watch=mixed_watch,
        source="mock-duffel",
        label="mixed-simulated",
    )
    mixed_simulated_booking = _add_booking(
        db,
        deal=mixed_simulated_deal,
        provider="mock-booking",
        label="mixed-simulated",
    )
    mixed_live_deal = _add_deal(
        db,
        watch=mixed_watch,
        source="live-duffel",
        label="mixed-live",
    )
    mixed_live_booking = _add_booking(
        db,
        deal=mixed_live_deal,
        provider="Duffel",
        label="mixed-live",
    )

    simulated_cancellation = Cancellation(
        id=uuid4(),
        booking_id=simulated_booking.id,
        reason="test",
        refund_expected=Decimal("640.00"),
        refund_received=Decimal("640.00"),
        currency="USD",
        status=CancellationStatus.REFUNDED,
        requested_at=datetime.now(UTC),
        resolved_at=datetime.now(UTC),
    )
    simulated_spend = SpendLedger(
        id=uuid4(),
        user_id=simulated_user.id,
        watch_id=eligible_watch.id,
        booking_id=simulated_booking.id,
        amount=Decimal("640.00"),
        currency="USD",
        booked_at=datetime.now(UTC),
    )
    live_spend = SpendLedger(
        id=uuid4(),
        user_id=live_user.id,
        watch_id=live_watch.id,
        booking_id=live_booking.id,
        amount=Decimal("640.00"),
        currency="USD",
        booked_at=datetime.now(UTC),
    )
    simulated_disruption = Disruption(
        id=uuid4(),
        booking_id=simulated_booking.id,
        type=DisruptionType.SCHEDULE_CHANGE,
        detail_json={"message": "simulated"},
        status=DisruptionStatus.NOTIFIED,
        detected_at=datetime.now(UTC),
    )
    manual_live_disruption = Disruption(
        id=uuid4(),
        booking_id=live_booking.id,
        type=DisruptionType.MANUAL_TEST,
        detail_json={"message": "manual test"},
        status=DisruptionStatus.NOTIFIED,
        detected_at=datetime.now(UTC),
    )
    live_disruption = Disruption(
        id=uuid4(),
        booking_id=live_booking.id,
        type=DisruptionType.SCHEDULE_CHANGE,
        detail_json={"message": "live"},
        status=DisruptionStatus.NOTIFIED,
        detected_at=datetime.now(UTC),
    )
    db.add_all(
        [
            simulated_cancellation,
            simulated_spend,
            live_spend,
            simulated_disruption,
            manual_live_disruption,
            live_disruption,
        ]
    )
    db.flush()

    simulated_notification = NotificationDelivery(
        id=uuid4(),
        user_id=simulated_user.id,
        booking_id=simulated_booking.id,
        disruption_id=simulated_disruption.id,
        deal_id=simulated_deal.id,
        channel="email",
        transport=NotificationTransport.LOG_ONLY,
        destination="simulated@example.com",
        message_type="booking.booked",
        status=NotificationDeliveryStatus.SENT,
        attempted_at=datetime.now(UTC),
        payload_json={"body": "simulated"},
    )
    manual_notification = NotificationDelivery(
        id=uuid4(),
        user_id=live_user.id,
        booking_id=live_booking.id,
        disruption_id=manual_live_disruption.id,
        deal_id=live_deal.id,
        channel="email",
        transport=NotificationTransport.LOG_ONLY,
        destination="live@example.com",
        message_type="disruption.created",
        status=NotificationDeliveryStatus.SENT,
        attempted_at=datetime.now(UTC),
        payload_json={"body": "manual"},
    )
    live_notification = NotificationDelivery(
        id=uuid4(),
        user_id=live_user.id,
        booking_id=live_booking.id,
        disruption_id=live_disruption.id,
        deal_id=live_deal.id,
        channel="email",
        transport=NotificationTransport.LOG_ONLY,
        destination="live@example.com",
        message_type="disruption.created",
        status=NotificationDeliveryStatus.SENT,
        attempted_at=datetime.now(UTC),
        payload_json={"body": "live"},
    )
    simulated_feedback = DealFeedback(
        id=uuid4(),
        watch_id=eligible_watch.id,
        deal_id=simulated_deal.id,
        rejected_value_score=10.0,
        reason="wrong_airline",
        signal_type=FeedbackSignalType.PREFERENCE,
        action_taken_json={
            "suppressed": ["airline:ZZ"],
            "value_pressure": 0.2,
            "prior_watch_state": {"value_pressure": 0.0},
        },
        created_at=learned_at,
    )
    live_feedback = DealFeedback(
        id=uuid4(),
        watch_id=live_watch.id,
        deal_id=live_deal.id,
        rejected_value_score=10.0,
        reason="wrong_airline",
        signal_type=FeedbackSignalType.PREFERENCE,
        action_taken_json={"suppressed": ["airline:NH"]},
        created_at=learned_at,
    )
    simulated_suppression = SuppressedAttribute(
        id=uuid4(),
        watch_id=eligible_watch.id,
        attr_type=SuppressedAttributeType.AIRLINE,
        attr_value="ZZ",
        weight=1.0,
        created_at=learned_at,
    )
    live_suppression = SuppressedAttribute(
        id=uuid4(),
        watch_id=live_watch.id,
        attr_type=SuppressedAttributeType.AIRLINE,
        attr_value="NH",
        weight=1.0,
        created_at=learned_at,
    )
    simulated_rejection = RejectedFingerprint(
        id=uuid4(),
        watch_id=eligible_watch.id,
        fingerprint_hash=simulated_deal.fingerprint_hash,
        created_at=learned_at,
    )
    live_rejection = RejectedFingerprint(
        id=uuid4(),
        watch_id=live_watch.id,
        fingerprint_hash=live_deal.fingerprint_hash,
        created_at=learned_at,
    )
    stamp = TrampStampLedger(
        id=uuid4(),
        user_id=live_user.id,
        booking_id=live_booking.id,
        amount=1,
        reason="live_booking",
        awarded_at=datetime.now(UTC),
        meta_json={"deal_id": str(live_deal.id)},
    )
    simulated_audit = AuditLog(
        id=uuid4(),
        actor=f"user:{simulated_user.id}",
        action="booking.booked",
        target=f"deal:{simulated_deal.id}",
        at=datetime.now(UTC),
        meta_json={"booking_id": str(simulated_booking.id)},
    )
    manual_audit = AuditLog(
        id=uuid4(),
        actor=f"user:{live_user.id}",
        action="disruption.created",
        target=f"booking:{live_booking.id}",
        at=datetime.now(UTC),
        meta_json={"disruption_id": str(manual_live_disruption.id)},
    )
    live_audit = AuditLog(
        id=uuid4(),
        actor=f"user:{live_user.id}",
        action="booking.booked",
        target=f"deal:{live_deal.id}",
        at=datetime.now(UTC),
        meta_json={"booking_id": str(live_booking.id)},
    )
    db.add_all(
        [
            simulated_notification,
            manual_notification,
            live_notification,
            simulated_feedback,
            live_feedback,
            simulated_suppression,
            live_suppression,
            simulated_rejection,
            live_rejection,
            stamp,
            simulated_audit,
            manual_audit,
            live_audit,
        ]
    )
    db.commit()

    tracked_models = (
        User,
        Traveler,
        LoyaltyAccount,
        TravelerGroup,
        UserPreference,
        PaymentMethod,
        TripTemplate,
        TripWatch,
        WatchTraveler,
        IntegrationCredentialProfile,
        PlatformIntegration,
        PriceObservation,
        PriceStat,
        SuppressedAttribute,
        RejectedFingerprint,
        Deal,
        DealFeedback,
        Booking,
        BookingAttempt,
        Cancellation,
        SpendLedger,
        TrampStampLedger,
        Disruption,
        NotificationDelivery,
        AuditLog,
    )
    counts_before_preview = {model: _row_count(db, model) for model in tracked_models}

    preview = preview_test_data_purge(db=db)

    assert preview.deleted_counts == {
        "audit_log": 2,
        "booking_attempts": 1,
        "bookings": 2,
        "cancellations": 1,
        "deal_feedback": 1,
        "deals": 2,
        "disruptions": 2,
        "notification_deliveries": 2,
        "price_observations": 1,
        "price_stats": 2,
        "rejected_fingerprints": 1,
        "spend_ledger": 1,
        "suppressed_attributes": 1,
    }
    assert preview.reset_watch_ids == frozenset({eligible_watch.id})
    assert {model: _row_count(db, model) for model in tracked_models} == counts_before_preview
    assert not db.new
    assert not db.dirty
    assert not db.deleted

    with pytest.raises(ValueError, match="PURGE TEST DATA"):
        execute_test_data_purge(
            db=db,
            actor=admin,
            confirmation="purge test data",
        )
    assert {model: _row_count(db, model) for model in tracked_models} == counts_before_preview

    result = execute_test_data_purge(
        db=db,
        actor=admin,
        confirmation="PURGE TEST DATA",
        preview_digest=preview.plan_digest,
    )

    assert result.deleted_counts == preview.deleted_counts
    assert result.reset_watch_ids == preview.reset_watch_ids

    deleted_records = (
        (PriceObservation, simulated_observation.id),
        (Deal, simulated_deal.id),
        (Deal, mixed_simulated_deal.id),
        (Booking, simulated_booking.id),
        (Booking, mixed_simulated_booking.id),
        (BookingAttempt, simulated_attempt.id),
        (Cancellation, simulated_cancellation.id),
        (SpendLedger, simulated_spend.id),
        (Disruption, simulated_disruption.id),
        (Disruption, manual_live_disruption.id),
        (NotificationDelivery, simulated_notification.id),
        (NotificationDelivery, manual_notification.id),
        (DealFeedback, simulated_feedback.id),
        (SuppressedAttribute, simulated_suppression.id),
        (RejectedFingerprint, simulated_rejection.id),
        (AuditLog, simulated_audit.id),
        (AuditLog, manual_audit.id),
    )
    for model, record_id in deleted_records:
        assert db.get(model, record_id) is None

    preserved_records = (
        (User, admin.id),
        (User, simulated_user.id),
        (User, live_user.id),
        (Traveler, traveler.id),
        (LoyaltyAccount, loyalty.id),
        (TravelerGroup, group.id),
        (UserPreference, preference.id),
        (PaymentMethod, payment.id),
        (TripTemplate, template.id),
        (TripWatch, live_watch.id),
        (TripWatch, eligible_watch.id),
        (TripWatch, mixed_watch.id),
        (WatchTraveler, watch_traveler.id),
        (IntegrationCredentialProfile, credential_profile.id),
        (PlatformIntegration, integration.id),
        (PriceObservation, live_observation.id),
        (Deal, live_deal.id),
        (Deal, mixed_live_deal.id),
        (Booking, live_booking.id),
        (Booking, mixed_live_booking.id),
        (BookingAttempt, live_attempt.id),
        (SpendLedger, live_spend.id),
        (TrampStampLedger, stamp.id),
        (Disruption, live_disruption.id),
        (NotificationDelivery, live_notification.id),
        (DealFeedback, live_feedback.id),
        (SuppressedAttribute, live_suppression.id),
        (RejectedFingerprint, live_rejection.id),
        (AuditLog, live_audit.id),
    )
    for model, record_id in preserved_records:
        assert db.get(model, record_id) is not None

    assert _row_count(db, PriceStat) == 0
    assert db.get(TripWatch, eligible_watch.id).status == TripWatchStatus.ACTIVE
    assert db.get(TripWatch, eligible_watch.id).value_pressure == 0.0
    assert db.get(TripWatch, mixed_watch.id).status == TripWatchStatus.FULFILLED
    assert db.get(TripWatch, live_watch.id).status == TripWatchStatus.FULFILLED

    purge_audits = list(
        db.scalars(select(AuditLog).where(AuditLog.action == "admin.test_data_purged"))
    )
    assert len(purge_audits) == 1
    assert purge_audits[0].actor == f"user:{admin.id}"
    assert purge_audits[0].meta_json == {
        "plan_digest": preview.plan_digest,
        "deleted_counts": preview.deleted_counts,
        "reset_watch_count": 1,
        "warnings": [],
        "unreverted_feedback_count": 0,
    }


def test_execute_rolls_back_every_delete_when_a_late_step_fails(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _add_user(db, label="rollback-admin", role=UserRole.ADMIN)
    user = _add_user(db, label="rollback-user")
    watch = _add_watch(db, user=user, status=TripWatchStatus.FULFILLED)
    deal = _add_deal(db, watch=watch, source="mock-duffel", label="rollback")
    booking = _add_booking(db, deal=deal, provider="mock-booking", label="rollback")
    attempt = _add_attempt(
        db,
        watch=watch,
        deal=deal,
        booking=booking,
        label="rollback",
        simulated=True,
    )
    stat = PriceStat(
        id=uuid4(),
        scope_type=PriceScopeType.ROUTE_CABIN,
        scope_key="rollback",
        month_bucket=date(2026, 7, 1),
        sample_n=1,
    )
    audit = AuditLog(
        id=uuid4(),
        actor=f"user:{user.id}",
        action="booking.booked",
        target=f"deal:{deal.id}",
        at=datetime.now(UTC),
        meta_json={"booking_id": str(booking.id)},
    )
    db.add_all([stat, audit])
    db.commit()

    original_delete_ids = activity_service._delete_ids

    def fail_after_attempt_delete(
        *,
        db: Session,
        model: type[object],
        ids: frozenset[UUID],
    ) -> int:
        deleted = original_delete_ids(db=db, model=model, ids=ids)
        if model is BookingAttempt:
            raise RuntimeError("forced purge failure")
        return deleted

    monkeypatch.setattr(activity_service, "_delete_ids", fail_after_attempt_delete)
    preview = preview_test_data_purge(db=db)

    with pytest.raises(RuntimeError, match="forced purge failure"):
        execute_test_data_purge(
            db=db,
            actor=admin,
            confirmation="PURGE TEST DATA",
            preview_digest=preview.plan_digest,
        )

    for model, record_id in (
        (Deal, deal.id),
        (Booking, booking.id),
        (BookingAttempt, attempt.id),
        (PriceStat, stat.id),
        (AuditLog, audit.id),
    ):
        assert db.get(model, record_id) is not None
    assert db.get(TripWatch, watch.id).status == TripWatchStatus.FULFILLED
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "admin.test_data_purged")
        )
        == 0
    )


@pytest.mark.anyio
async def test_admin_routes_enforce_auth_confirmation_and_global_classification(
    db: Session,
) -> None:
    admin = _add_user(db, label="route-admin", role=UserRole.ADMIN)
    non_admin = _add_user(db, label="route-user")
    simulated_owner = _add_user(db, label="route-simulated-owner")
    live_owner = _add_user(db, label="route-live-owner")
    simulated_watch = _add_watch(
        db,
        user=simulated_owner,
        status=TripWatchStatus.FULFILLED,
    )
    live_watch = _add_watch(db, user=live_owner, status=TripWatchStatus.FULFILLED)
    simulated_deal = _add_deal(
        db,
        watch=simulated_watch,
        source="mock-duffel",
        label="route-simulated",
    )
    simulated_booking = _add_booking(
        db,
        deal=simulated_deal,
        provider="mock-booking",
        label="route-simulated",
    )
    live_deal = _add_deal(
        db,
        watch=live_watch,
        source="live-duffel",
        label="route-live",
    )
    live_booking = _add_booking(
        db,
        deal=live_deal,
        provider="Duffel",
        label="route-live",
    )
    simulated_owner_id = simulated_owner.id
    live_owner_id = live_owner.id
    simulated_watch_id = simulated_watch.id
    live_watch_id = live_watch.id
    simulated_deal_id = simulated_deal.id
    simulated_booking_id = simulated_booking.id
    live_deal_id = live_deal.id
    live_booking_id = live_booking.id
    db.commit()

    with pytest.raises(HTTPException) as forbidden:
        require_admin(non_admin)
    assert forbidden.value.status_code == 403
    assert forbidden.value.detail == "Admin access required."

    preview = await preview_test_data_purge_record(_=admin, db=db)
    assert preview.dry_run is True
    assert preview.deleted_counts["deals"] == 1
    assert preview.deleted_counts["bookings"] == 1
    assert preview.reset_watch_count == 1

    with pytest.raises(HTTPException) as mismatch:
        await purge_test_data_record(
            payload=AdminTestDataPurgeRequest(
                confirmation="purge test data",
                plan_digest=preview.plan_digest,
            ),
            current_user=admin,
            db=db,
        )
    assert mismatch.value.status_code == 400
    assert "PURGE TEST DATA" in mismatch.value.detail

    with pytest.raises(HTTPException) as stale:
        await purge_test_data_record(
            payload=AdminTestDataPurgeRequest(
                confirmation="PURGE TEST DATA",
                plan_digest="0" * 64,
            ),
            current_user=admin,
            db=db,
        )
    assert stale.value.status_code == 400
    assert "preview changed" in stale.value.detail

    executed = await purge_test_data_record(
        payload=AdminTestDataPurgeRequest(
            confirmation="PURGE TEST DATA",
            plan_digest=preview.plan_digest,
        ),
        current_user=admin,
        db=db,
    )
    assert executed.dry_run is False
    assert executed.deleted_counts == preview.deleted_counts
    assert executed.reset_watch_count == 1

    db.expire_all()
    assert db.get(User, simulated_owner_id) is not None
    assert db.get(User, live_owner_id) is not None
    assert db.get(TripWatch, simulated_watch_id).status == TripWatchStatus.ACTIVE
    assert db.get(Deal, simulated_deal_id) is None
    assert db.get(Booking, simulated_booking_id) is None
    assert db.get(TripWatch, live_watch_id).status == TripWatchStatus.FULFILLED
    assert db.get(Deal, live_deal_id) is not None
    assert db.get(Booking, live_booking_id) is not None


def test_mock_cancellation_on_live_booking_is_reversibly_purged(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _add_user(db, label="cancel-admin", role=UserRole.ADMIN)
    user = _add_user(db, label="cancel-user")
    watch = _add_watch(db, user=user, status=TripWatchStatus.FULFILLED)
    deal = _add_deal(db, watch=watch, source="live-duffel", label="cancel-live")
    booking = _add_booking(db, deal=deal, provider="Duffel", label="cancel-live")
    original_charge = SpendLedger(
        id=uuid4(),
        user_id=user.id,
        watch_id=watch.id,
        booking_id=booking.id,
        amount=Decimal("640.00"),
        currency="USD",
        booked_at=datetime.now(UTC),
    )
    db.add(original_charge)
    db.commit()

    resolved_at = datetime.now(UTC)
    provider_result = CancellationExecutionResult(
        provider="mock-booking",
        simulated=True,
        status=CancellationStatus.REFUNDED,
        refund_expected=Decimal("640.00"),
        refund_received=Decimal("640.00"),
        currency="USD",
        resolved_at=resolved_at,
        provider_correlation_id="mock-cancel-correlation",
        provider_payload={"simulated": True, "operation": "cancel"},
    )
    monkeypatch.setattr(booking_service, "get_mock_data_enabled", lambda **_kwargs: True)
    monkeypatch.setattr(
        booking_service,
        "get_booking_connector",
        lambda **_kwargs: SimpleNamespace(
            cancel_booking=lambda **_cancel_kwargs: provider_result
        ),
    )
    monkeypatch.setattr(booking_service, "_enqueue_notification_tasks", lambda _items: None)

    cancellation_response = booking_service.cancel_booking(
        db=db,
        user=user,
        booking_id=booking.id,
        reason="test cancellation",
    )
    cancellation_id = UUID(cancellation_response.id)
    cancellation = db.get(Cancellation, cancellation_id)
    assert cancellation is not None
    assert cancellation.execution_simulated is True
    assert cancellation.provider == "mock-booking"
    assert cancellation.provider_payload_json == {
        "simulated": True,
        "operation": "cancel",
    }
    assert cancellation.prior_booking_status == BookingStatus.TICKETED
    assert cancellation.prior_watch_status == TripWatchStatus.FULFILLED
    refund = db.scalar(
        select(SpendLedger).where(SpendLedger.cancellation_id == cancellation_id)
    )
    notice = db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.cancellation_id == cancellation_id
        )
    )
    assert refund is not None
    assert notice is not None
    assert db.get(Booking, booking.id).status == BookingStatus.CANCELLED
    assert db.get(TripWatch, watch.id).status == TripWatchStatus.ACTIVE

    preview = preview_test_data_purge(db=db)
    assert preview.booking_ids == frozenset()
    assert preview.deal_ids == frozenset()
    assert preview.cancellation_ids == frozenset({cancellation_id})
    assert preview.spend_ledger_ids == frozenset({refund.id})
    assert preview.notification_delivery_ids == frozenset({notice.id})

    execute_test_data_purge(
        db=db,
        actor=admin,
        confirmation="PURGE TEST DATA",
        preview_digest=preview.plan_digest,
    )

    assert db.get(Cancellation, cancellation_id) is None
    assert db.get(SpendLedger, refund.id) is None
    assert db.get(NotificationDelivery, notice.id) is None
    assert db.get(SpendLedger, original_charge.id) is not None
    assert db.get(Booking, booking.id).status == BookingStatus.TICKETED
    assert db.get(Deal, deal.id) is not None
    assert db.get(TripWatch, watch.id).status == TripWatchStatus.FULFILLED
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "booking.cancelled",
                AuditLog.meta_json["cancellation_id"].as_string()
                == str(cancellation_id),
            )
        )
        == 0
    )


def test_simulated_bookings_restore_live_deals_and_guard_watch_resets(
    db: Session,
) -> None:
    admin = _add_user(db, label="restore-admin", role=UserRole.ADMIN)
    user = _add_user(db, label="restore-user")
    valid_watch = _add_watch(db, user=user, status=TripWatchStatus.FULFILLED)
    expired_watch = _add_watch(db, user=user, status=TripWatchStatus.FULFILLED)
    valid_deal = _add_deal(
        db,
        watch=valid_watch,
        source="live-duffel",
        label="restore-valid",
    )
    valid_deal.expires_at = datetime(2099, 1, 1, tzinfo=UTC)
    valid_deal.confirm_token_hash = "consumed-valid-token"
    expired_deal = _add_deal(
        db,
        watch=expired_watch,
        source="live-duffel",
        label="restore-expired",
    )
    expired_deal.expires_at = datetime(2020, 1, 1, tzinfo=UTC)
    expired_deal.confirm_token_hash = "consumed-expired-token"
    valid_booking = _add_booking(
        db,
        deal=valid_deal,
        provider="mock-booking",
        label="restore-valid",
    )
    expired_booking = _add_booking(
        db,
        deal=expired_deal,
        provider="mock-booking",
        label="restore-expired",
    )
    db.commit()

    preview = preview_test_data_purge(db=db)
    assert preview.deal_ids == frozenset()
    assert preview.booking_ids == frozenset({valid_booking.id, expired_booking.id})
    assert dict(preview.deal_status_restorations) == {
        valid_deal.id: DealStatus.PROPOSED,
        expired_deal.id: DealStatus.EXPIRED,
    }

    execute_test_data_purge(
        db=db,
        actor=admin,
        confirmation="PURGE TEST DATA",
        preview_digest=preview.plan_digest,
    )

    assert db.get(Booking, valid_booking.id) is None
    assert db.get(Booking, expired_booking.id) is None
    restored_valid = db.get(Deal, valid_deal.id)
    restored_expired = db.get(Deal, expired_deal.id)
    assert restored_valid is not None
    assert restored_valid.status == DealStatus.PROPOSED
    assert restored_valid.confirm_token_hash is None
    assert restored_expired is not None
    assert restored_expired.status == DealStatus.EXPIRED
    assert restored_expired.confirm_token_hash is None
    assert db.get(TripWatch, valid_watch.id).status == TripWatchStatus.ACTIVE
    assert db.get(TripWatch, expired_watch.id).status == TripWatchStatus.ACTIVE


def test_concurrent_live_booking_blocks_on_lock_and_invalidates_stale_digest(
    db: Session,
    postgres_engine: Engine,
) -> None:
    admin = _add_user(db, label="race-admin", role=UserRole.ADMIN)
    user = _add_user(db, label="race-user")
    watch = _add_watch(db, user=user, status=TripWatchStatus.FULFILLED)
    simulated_deal = _add_deal(
        db,
        watch=watch,
        source="mock-duffel",
        label="race-simulated",
    )
    simulated_booking = _add_booking(
        db,
        deal=simulated_deal,
        provider="mock-booking",
        label="race-simulated",
    )
    watch_id = watch.id
    simulated_deal_id = simulated_deal.id
    simulated_booking_id = simulated_booking.id
    db.commit()

    writer_started = Event()
    writer_acquired = Event()
    with Session(postgres_engine, expire_on_commit=False) as preview_session:
        stale_preview = preview_test_data_purge(db=preview_session)

        def write_live_booking() -> tuple[UUID, UUID]:
            with Session(postgres_engine, expire_on_commit=False) as writer:
                writer_started.set()
                acquire_activity_maintenance_lock(writer)
                writer_acquired.set()
                live_deal = Deal(
                    id=uuid4(),
                    watch_id=watch_id,
                    kind="flight",
                    source="live-duffel",
                    total_price=Decimal("800.00"),
                    currency="USD",
                    framing=DealFraming.BEST_VALUE,
                    fingerprint_hash=f"race-live-{uuid4()}",
                    status=DealStatus.BOOKED,
                )
                writer.add(live_deal)
                writer.flush()
                live_booking = Booking(
                    id=uuid4(),
                    deal_id=live_deal.id,
                    provider="Duffel",
                    status=BookingStatus.TICKETED,
                    idempotency_key=f"race-live-{uuid4()}",
                    loyalty_manual_followup=False,
                )
                writer.add(live_booking)
                writer.commit()
                return live_deal.id, live_booking.id

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(write_live_booking)
            assert writer_started.wait(timeout=5)
            assert writer_acquired.wait(timeout=0.2) is False
            preview_session.rollback()
            live_deal_id, live_booking_id = future.result(timeout=5)

    with Session(postgres_engine, expire_on_commit=False) as execute_session:
        with pytest.raises(PurgePlanChangedError, match="preview changed"):
            execute_test_data_purge(
                db=execute_session,
                actor=admin,
                confirmation="PURGE TEST DATA",
                preview_digest=stale_preview.plan_digest,
            )

        fresh_preview = preview_test_data_purge(db=execute_session)
        assert fresh_preview.plan_digest != stale_preview.plan_digest
        assert watch_id not in fresh_preview.reset_watch_ids
        execute_test_data_purge(
            db=execute_session,
            actor=admin,
            confirmation="PURGE TEST DATA",
            preview_digest=fresh_preview.plan_digest,
        )

    db.expire_all()
    assert db.get(Deal, simulated_deal_id) is None
    assert db.get(Booking, simulated_booking_id) is None
    assert db.get(Deal, live_deal_id) is not None
    assert db.get(Booking, live_booking_id) is not None
    assert db.get(TripWatch, watch_id).status == TripWatchStatus.FULFILLED
