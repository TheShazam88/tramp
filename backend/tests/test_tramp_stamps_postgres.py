from __future__ import annotations

import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from app import booking_service
from app.api.routes.profile import _build_profile_summary
from app.db.models import (
    AutoBookMode,
    Booking,
    BookingAttempt,
    BookingAttemptStatus,
    BookingStatus,
    Deal,
    DealFraming,
    DealStatus,
    DestinationMode,
    NotificationChannel,
    NotificationDelivery,
    PaymentMethod,
    RefreshInterval,
    SpendLedger,
    TrampStampLedger,
    TripMode,
    TripWatch,
    TripWatchStatus,
    User,
    UserRole,
)
from app.service_errors import ConflictError
from app.tramp_stamp_service import award_for_live_booking, stamp_balance

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _migration_database_url() -> str:
    database_url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("MIGRATION_TEST_DATABASE_URL is not configured")
    if os.environ.get("MIGRATION_TEST_ALLOW_RESET") != "1":
        pytest.fail("MIGRATION_TEST_ALLOW_RESET=1 is required for destructive ledger tests")

    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        pytest.fail("Ledger tests require a dedicated PostgreSQL database")
    return database_url


def _run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_SECRET": "ledger-test-secret-with-at-least-thirty-two-bytes",
            "DATABASE_URL": database_url,
            "INITIAL_ADMIN_EMAIL": "admin@example.com",
            "INITIAL_ADMIN_PASSWORD": "test-admin-password",
            "PUBLIC_BASE_URL": "https://tramp-ledger.test",
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
    with Session(postgres_engine) as session:
        yield session
        session.rollback()


def _add_user(db: Session, *, label: str) -> User:
    user = User(
        id=uuid4(),
        email=f"{label}-{uuid4()}@example.com",
        password_hash="hashed",
        role=UserRole.USER,
        onboarding_completed=False,
        default_notify_channel=NotificationChannel.EMAIL,
    )
    db.add(user)
    db.flush()
    return user


def _add_booking(db: Session, *, user: User, label: str) -> Booking:
    watch = TripWatch(
        id=uuid4(),
        user_id=user.id,
        status=TripWatchStatus.ACTIVE,
        trip_mode=TripMode.FLIGHTS_THEN_HOTELS,
        destination_mode=DestinationMode.FIXED,
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

    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="postgres-ledger-test",
        total_price=Decimal("321.00"),
        currency="USD",
        framing=DealFraming.BEST_VALUE,
        fingerprint_hash=f"{label}-{uuid4()}",
        status=DealStatus.BOOKED,
    )
    db.add(deal)
    db.flush()

    booking = Booking(
        id=uuid4(),
        deal_id=deal.id,
        provider="postgres-ledger-test",
        status=BookingStatus.TICKETED,
        idempotency_key=f"{label}-{uuid4()}",
        loyalty_manual_followup=False,
    )
    db.add(booking)
    db.flush()
    return booking


def _add_live_booking_request(
    db: Session,
    *,
    label: str,
) -> tuple[User, TripWatch, Deal, PaymentMethod]:
    user = _add_user(db, label=label)
    watch = TripWatch(
        id=uuid4(),
        user_id=user.id,
        status=TripWatchStatus.ACTIVE,
        trip_mode=TripMode.FLIGHTS_THEN_HOTELS,
        destination_mode=DestinationMode.FIXED,
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
    deal = Deal(
        id=uuid4(),
        watch_id=watch.id,
        kind="flight",
        source="live-amadeus",
        total_price=Decimal("640.00"),
        currency="USD",
        framing=DealFraming.BEST_VALUE,
        fingerprint_hash=f"{label}-{uuid4()}",
        status=DealStatus.PROPOSED,
    )
    payment_method = PaymentMethod(
        id=uuid4(),
        user_id=user.id,
        label=f"{label} Visa",
        encrypted_blob="encrypted",
        last4="4242",
    )
    db.add_all([deal, payment_method])
    db.flush()
    return user, watch, deal, payment_method


def _provider_result(
    status: BookingStatus,
    *,
    error_text: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        provider="duffel",
        provider_booking_ref=f"DUFFEL-{uuid4()}",
        provider_correlation_id=f"correlation-{uuid4()}",
        status=status.value,
        amount_charged=Decimal("640.00"),
        currency="USD",
        documents={"ticket": "123"} if status == BookingStatus.TICKETED else None,
        loyalty_attached={},
        loyalty_manual_followup=False,
        ticketing_state=status.value,
        booked_at=datetime.now(UTC),
        error_text=error_text,
        provider_payload={"simulated": False, "status": status.value},
    )


class StaticBookingConnector:
    def __init__(self, result: SimpleNamespace, *, blocking: bool = False) -> None:
        self.result = result
        self.blocking = blocking
        self.call_count = 0
        self._lock = threading.Lock()
        self.provider_started = threading.Event()
        self.release_provider = threading.Event()
        if not blocking:
            self.release_provider.set()

    def book_deal(self, **_kwargs) -> SimpleNamespace:
        with self._lock:
            self.call_count += 1
        self.provider_started.set()
        if not self.release_provider.wait(timeout=10):
            raise TimeoutError("Timed out waiting to release the booking provider.")
        return self.result


def _patch_booking_runtime(
    monkeypatch: pytest.MonkeyPatch,
    connector: StaticBookingConnector,
) -> None:
    monkeypatch.setattr(booking_service, "get_mock_data_enabled", lambda *, db: False)
    monkeypatch.setattr(booking_service, "_require_step_up_auth", lambda **_kwargs: None)
    monkeypatch.setattr(booking_service, "verify_approval_token", lambda **_kwargs: None)
    monkeypatch.setattr(booking_service, "consume_approval_token", lambda **_kwargs: None)
    monkeypatch.setattr(
        booking_service,
        "get_booking_connector",
        lambda *, db: connector,
    )
    monkeypatch.setattr(booking_service, "_enqueue_notification_tasks", lambda _items: None)


def _approve_booking_in_session(
    engine: Engine,
    *,
    user_id: UUID,
    deal_id: UUID,
    payment_method_id: UUID,
    idempotency_key: str,
) -> object:
    with Session(engine, expire_on_commit=False) as db:
        user = db.get(User, user_id)
        assert user is not None
        try:
            return booking_service.approve_and_book(
                db=db,
                user=user,
                deal_id=deal_id,
                approval_token="approval-token",
                totp_code="000000",
                master_key_passphrase="unused",
                payment_method_id=payment_method_id,
                idempotency_key=idempotency_key,
                token_service=SimpleNamespace(),
            )
        except ConflictError as exc:
            return exc


class CoordinatedStampSession:
    def __init__(self, db: Session, select_barrier: threading.Barrier) -> None:
        self.db = db
        self.select_barrier = select_barrier

    def scalar(self, statement):
        value = self.db.scalar(statement)
        if isinstance(statement, Select):
            self.select_barrier.wait(timeout=10)
        return value

    def add(self, value: object) -> None:
        self.db.add(value)


def _add_stamp(
    db: Session,
    *,
    user_id: UUID,
    booking_id: UUID,
    amount: int = 1,
) -> TrampStampLedger:
    stamp = TrampStampLedger(
        user_id=user_id,
        booking_id=booking_id,
        amount=amount,
        reason="live_booking_completed",
        awarded_at=datetime.now(UTC),
        meta_json=None,
    )
    db.add(stamp)
    db.flush()
    return stamp


def test_database_rejects_non_single_stamp_amount(db: Session) -> None:
    user = _add_user(db, label="amount")
    booking = _add_booking(db, user=user, label="amount")

    with pytest.raises(IntegrityError, match="ck_tramp_stamp_ledger_single_stamp"):
        _add_stamp(db, user_id=user.id, booking_id=booking.id, amount=2)


def test_database_rejects_duplicate_booking_stamp(db: Session) -> None:
    user = _add_user(db, label="duplicate")
    booking = _add_booking(db, user=user, label="duplicate")
    _add_stamp(db, user_id=user.id, booking_id=booking.id)

    with pytest.raises(IntegrityError, match="uq_tramp_stamp_ledger_booking_id"):
        _add_stamp(db, user_id=user.id, booking_id=booking.id)


@pytest.mark.parametrize("missing_reference", ["user", "booking"])
def test_database_enforces_stamp_foreign_keys(
    db: Session,
    missing_reference: str,
) -> None:
    user = _add_user(db, label=f"foreign-key-{missing_reference}")
    booking = _add_booking(db, user=user, label=f"foreign-key-{missing_reference}")

    with pytest.raises(IntegrityError, match="foreign key"):
        _add_stamp(
            db,
            user_id=uuid4() if missing_reference == "user" else user.id,
            booking_id=uuid4() if missing_reference == "booking" else booking.id,
        )


def test_stamp_balance_is_zero_without_ledger_rows(db: Session) -> None:
    user = _add_user(db, label="empty-balance")

    assert stamp_balance(db=db, user_id=user.id) == 0


def test_stamp_balance_isolated_between_users(db: Session) -> None:
    first_user = _add_user(db, label="first-balance")
    second_user = _add_user(db, label="second-balance")
    first_booking = _add_booking(db, user=first_user, label="first-balance")
    second_booking = _add_booking(db, user=second_user, label="second-balance-one")
    third_booking = _add_booking(db, user=second_user, label="second-balance-two")
    _add_stamp(db, user_id=first_user.id, booking_id=first_booking.id)
    _add_stamp(db, user_id=second_user.id, booking_id=second_booking.id)
    _add_stamp(db, user_id=second_user.id, booking_id=third_booking.id)

    assert stamp_balance(db=db, user_id=first_user.id) == 1
    assert stamp_balance(db=db, user_id=second_user.id) == 2
    assert stamp_balance(db=db, user_id=uuid4()) == 0


def test_profile_summary_serializes_postgres_stamp_balance(db: Session) -> None:
    user = _add_user(db, label="profile-balance")
    booking = _add_booking(db, user=user, label="profile-balance")
    _add_stamp(db, user_id=user.id, booking_id=booking.id)

    summary = _build_profile_summary(db=db, user=user)

    assert summary.tramp_stamp_balance == 1
    assert summary.model_dump()["tramp_stamp_balance"] == 1


def test_failed_provider_status_persists_only_failed_attempt(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, watch, deal, payment_method = _add_live_booking_request(
        db,
        label="failed-provider",
    )
    db.commit()
    connector = StaticBookingConnector(
        _provider_result(
            BookingStatus.FAILED,
            error_text="provider declined booking",
        )
    )
    _patch_booking_runtime(monkeypatch, connector)

    def unexpected_side_effect(**_kwargs):
        raise AssertionError("Failed provider status must not create success side effects.")

    monkeypatch.setattr(booking_service, "queue_notification", unexpected_side_effect)
    monkeypatch.setattr(booking_service, "push_booking_to_calendar", unexpected_side_effect)

    with pytest.raises(ConflictError, match="provider declined booking"):
        booking_service.approve_and_book(
            db=db,
            user=user,
            deal_id=deal.id,
            approval_token="approval-token",
            totp_code="000000",
            master_key_passphrase="unused",
            payment_method_id=payment_method.id,
            idempotency_key=f"failed-provider-{uuid4()}",
            token_service=SimpleNamespace(),
        )

    db.expire_all()
    attempts = list(
        db.scalars(select(BookingAttempt).where(BookingAttempt.deal_id == deal.id))
    )
    assert len(attempts) == 1
    assert attempts[0].status == BookingAttemptStatus.FAILED
    assert attempts[0].provider == "duffel"
    assert attempts[0].response_payload_json == {
        "simulated": False,
        "status": BookingStatus.FAILED.value,
    }
    assert attempts[0].error_text == "provider declined booking"
    assert db.scalar(
        select(func.count()).select_from(Booking).where(Booking.deal_id == deal.id)
    ) == 0
    assert db.scalar(
        select(func.count()).select_from(SpendLedger).where(SpendLedger.watch_id == watch.id)
    ) == 0
    assert db.scalar(
        select(func.count())
        .select_from(TrampStampLedger)
        .where(TrampStampLedger.user_id == user.id)
    ) == 0
    assert db.scalar(
        select(func.count())
        .select_from(NotificationDelivery)
        .where(NotificationDelivery.deal_id == deal.id)
    ) == 0
    assert db.get(Deal, deal.id).status == DealStatus.PROPOSED
    assert db.get(TripWatch, watch.id).status == TripWatchStatus.ACTIVE


def test_pending_provider_status_persists_pending_without_success_side_effects(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, watch, deal, payment_method = _add_live_booking_request(
        db,
        label="pending-provider",
    )
    db.commit()
    connector = StaticBookingConnector(_provider_result(BookingStatus.PENDING_TICKETING))
    _patch_booking_runtime(monkeypatch, connector)
    calendar_calls = 0

    def unexpected_calendar(**_kwargs):
        nonlocal calendar_calls
        calendar_calls += 1
        raise AssertionError("Pending bookings must not be pushed to the calendar.")

    monkeypatch.setattr(booking_service, "push_booking_to_calendar", unexpected_calendar)

    response = booking_service.approve_and_book(
        db=db,
        user=user,
        deal_id=deal.id,
        approval_token="approval-token",
        totp_code="000000",
        master_key_passphrase="unused",
        payment_method_id=payment_method.id,
        idempotency_key=f"pending-provider-{uuid4()}",
        token_service=SimpleNamespace(),
    )

    db.expire_all()
    booking = db.scalar(select(Booking).where(Booking.deal_id == deal.id))
    assert booking is not None
    attempt = db.scalar(
        select(BookingAttempt).where(BookingAttempt.booking_id == booking.id)
    )
    assert attempt is not None
    assert attempt.status.value == "pending_ticketing"
    assert attempt.response_payload_json == {
        "simulated": False,
        "status": BookingStatus.PENDING_TICKETING.value,
    }
    assert booking.status == BookingStatus.PENDING_TICKETING
    assert response.status == BookingStatus.PENDING_TICKETING.value
    assert response.tramp_stamps_awarded == 0
    assert response.tramp_stamp_balance == 0
    assert calendar_calls == 0
    assert db.scalar(
        select(func.count())
        .select_from(SpendLedger)
        .where(SpendLedger.booking_id == booking.id)
    ) == 0
    assert db.scalar(
        select(func.count())
        .select_from(TrampStampLedger)
        .where(TrampStampLedger.booking_id == booking.id)
    ) == 0
    deliveries = list(
        db.scalars(
            select(NotificationDelivery).where(NotificationDelivery.booking_id == booking.id)
        )
    )
    assert len(deliveries) == 1
    assert deliveries[0].message_type == "booking.pending_ticketing"
    assert "pending" in str(deliveries[0].payload_json["subject"]).lower()
    assert "pending" in str(deliveries[0].payload_json["body"]).lower()
    assert db.get(Deal, deal.id).status == DealStatus.CONFIRMED
    assert db.get(TripWatch, watch.id).status == TripWatchStatus.ACTIVE


def test_concurrent_stamp_awards_return_one_winner(
    db: Session,
    postgres_engine: Engine,
) -> None:
    user = _add_user(db, label="concurrent-stamp")
    booking = _add_booking(db, user=user, label="concurrent-stamp")
    user_id = user.id
    booking_id = booking.id
    deal_id = booking.deal_id
    db.commit()
    select_barrier = threading.Barrier(2)

    def award() -> int | str:
        with Session(postgres_engine) as worker_db:
            worker_user = worker_db.get(User, user_id)
            worker_booking = worker_db.get(Booking, booking_id)
            worker_deal = worker_db.get(Deal, deal_id)
            assert worker_user is not None
            assert worker_booking is not None
            assert worker_deal is not None
            coordinated_db = CoordinatedStampSession(worker_db, select_barrier)
            awarded = award_for_live_booking(
                db=coordinated_db,
                user=worker_user,
                booking=worker_booking,
                deal=worker_deal,
                provider_payload={"simulated": False},
            )
            try:
                worker_db.commit()
            except IntegrityError:
                worker_db.rollback()
                return "integrity-error"
            return awarded

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [pool.submit(award), pool.submit(award)]]

    assert results.count(1) == 1
    assert results.count(0) == 1
    with Session(postgres_engine) as verify_db:
        assert verify_db.scalar(
            select(func.count())
            .select_from(TrampStampLedger)
            .where(TrampStampLedger.booking_id == booking_id)
        ) == 1


def test_concurrent_same_idempotency_key_calls_provider_once(
    db: Session,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _watch, deal, payment_method = _add_live_booking_request(
        db,
        label="concurrent-idempotency",
    )
    user_id = user.id
    deal_id = deal.id
    payment_method_id = payment_method.id
    db.commit()
    connector = StaticBookingConnector(
        _provider_result(BookingStatus.TICKETED),
        blocking=True,
    )
    _patch_booking_runtime(monkeypatch, connector)
    monkeypatch.setattr(booking_service, "queue_notification", lambda **_kwargs: [])
    monkeypatch.setattr(
        booking_service,
        "push_booking_to_calendar",
        lambda **_kwargs: {"transport": "test"},
    )
    second_lock_started = threading.Event()
    deal_lock_count = 0
    deal_lock = threading.Lock()

    def observe_deal_lock(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        nonlocal deal_lock_count
        if "FROM deals" not in statement or "FOR UPDATE" not in statement:
            return
        with deal_lock:
            deal_lock_count += 1
            if deal_lock_count == 2:
                second_lock_started.set()

    event.listen(postgres_engine, "before_cursor_execute", observe_deal_lock)
    idempotency_key = f"concurrent-idempotency-{uuid4()}"
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(
                _approve_booking_in_session,
                postgres_engine,
                user_id=user_id,
                deal_id=deal_id,
                payment_method_id=payment_method_id,
                idempotency_key=idempotency_key,
            )
            assert connector.provider_started.wait(timeout=10)
            second_future = pool.submit(
                _approve_booking_in_session,
                postgres_engine,
                user_id=user_id,
                deal_id=deal_id,
                payment_method_id=payment_method_id,
                idempotency_key=idempotency_key,
            )
            try:
                assert second_lock_started.wait(timeout=10)
                assert connector.call_count == 1
            finally:
                connector.release_provider.set()
            results = [first_future.result(), second_future.result()]
    finally:
        connector.release_provider.set()
        event.remove(postgres_engine, "before_cursor_execute", observe_deal_lock)

    assert all(not isinstance(result, Exception) for result in results)
    assert sorted(result.tramp_stamps_awarded for result in results) == [0, 1]
    assert sorted(result.idempotent_replay for result in results) == [False, True]
    assert {result.tramp_stamp_balance for result in results} == {1}
    assert connector.call_count == 1
    with Session(postgres_engine) as verify_db:
        assert verify_db.scalar(
            select(func.count()).select_from(Booking).where(Booking.deal_id == deal_id)
        ) == 1
        assert verify_db.scalar(
            select(func.count())
            .select_from(BookingAttempt)
            .where(BookingAttempt.deal_id == deal_id)
        ) == 1
        assert verify_db.scalar(
            select(func.count())
            .select_from(TrampStampLedger)
            .join(Booking, Booking.id == TrampStampLedger.booking_id)
            .where(Booking.deal_id == deal_id)
        ) == 1


def test_concurrent_distinct_keys_for_same_deal_call_provider_once(
    db: Session,
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _watch, deal, payment_method = _add_live_booking_request(
        db,
        label="concurrent-deal",
    )
    user_id = user.id
    deal_id = deal.id
    payment_method_id = payment_method.id
    db.commit()
    connector = StaticBookingConnector(
        _provider_result(BookingStatus.TICKETED),
        blocking=True,
    )
    _patch_booking_runtime(monkeypatch, connector)
    monkeypatch.setattr(booking_service, "queue_notification", lambda **_kwargs: [])
    monkeypatch.setattr(
        booking_service,
        "push_booking_to_calendar",
        lambda **_kwargs: {"transport": "test"},
    )
    second_lock_started = threading.Event()
    deal_lock_count = 0
    deal_lock = threading.Lock()

    def observe_deal_lock(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        nonlocal deal_lock_count
        if "FROM deals" not in statement or "FOR UPDATE" not in statement:
            return
        with deal_lock:
            deal_lock_count += 1
            if deal_lock_count == 2:
                second_lock_started.set()

    event.listen(postgres_engine, "before_cursor_execute", observe_deal_lock)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(
                _approve_booking_in_session,
                postgres_engine,
                user_id=user_id,
                deal_id=deal_id,
                payment_method_id=payment_method_id,
                idempotency_key=f"concurrent-deal-first-{uuid4()}",
            )
            assert connector.provider_started.wait(timeout=10)
            second_future = pool.submit(
                _approve_booking_in_session,
                postgres_engine,
                user_id=user_id,
                deal_id=deal_id,
                payment_method_id=payment_method_id,
                idempotency_key=f"concurrent-deal-second-{uuid4()}",
            )
            try:
                assert second_lock_started.wait(timeout=10)
                assert connector.call_count == 1
            finally:
                connector.release_provider.set()
            results = [first_future.result(), second_future.result()]
    finally:
        connector.release_provider.set()
        event.remove(postgres_engine, "before_cursor_execute", observe_deal_lock)

    responses = [result for result in results if not isinstance(result, ConflictError)]
    conflicts = [result for result in results if isinstance(result, ConflictError)]
    assert len(responses) == 1
    assert len(conflicts) == 1
    assert "already been booked" in str(conflicts[0])
    assert connector.call_count == 1
    with Session(postgres_engine) as verify_db:
        assert verify_db.scalar(
            select(func.count()).select_from(Booking).where(Booking.deal_id == deal_id)
        ) == 1
        assert verify_db.scalar(
            select(func.count())
            .select_from(BookingAttempt)
            .where(BookingAttempt.deal_id == deal_id)
        ) == 1
        assert verify_db.scalar(
            select(func.count())
            .select_from(TrampStampLedger)
            .join(Booking, Booking.id == TrampStampLedger.booking_id)
            .where(Booking.deal_id == deal_id)
        ) == 1
