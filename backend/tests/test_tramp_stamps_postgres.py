from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.profile import _build_profile_summary
from app.db.models import (
    AutoBookMode,
    Booking,
    BookingStatus,
    Deal,
    DealFraming,
    DealStatus,
    DestinationMode,
    NotificationChannel,
    RefreshInterval,
    TrampStampLedger,
    TripMode,
    TripWatch,
    TripWatchStatus,
    User,
    UserRole,
)
from app.tramp_stamp_service import stamp_balance

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
