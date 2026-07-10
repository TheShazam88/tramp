from __future__ import annotations

import ast
import os
import runpy
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    Disruption,
    DisruptionStatus,
    DisruptionType,
    IntegrationEnvironment,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTransport,
    PlatformIntegration,
    RefreshInterval,
    TripMode,
    TripWatch,
    TripWatchStatus,
    User,
    UserRole,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_ROOT = BACKEND_ROOT / "alembic" / "versions"
POSTGRES_RUNNER = BACKEND_ROOT / "scripts" / "test-migrations.sh"
INITIAL_REVISION = MIGRATION_ROOT / "20260629_0001_initial_schema.py"
RECOVERY_REVISION = MIGRATION_ROOT / "20260710_0007_booking_recovery_required.py"
PROVENANCE_REVISION = MIGRATION_ROOT / "20260710_0008_cancellation_provenance.py"
CANCELLATION_CLASSIFICATION_REVISION = (
    MIGRATION_ROOT / "20260710_0009_cancellation_classification.py"
)

PRE_V2_TABLES = {
    "audit_log",
    "bookings",
    "cancellations",
    "deal_feedback",
    "deals",
    "loyalty_accounts",
    "payment_methods",
    "platform_integrations",
    "price_observations",
    "price_stats",
    "rejected_fingerprints",
    "spend_ledger",
    "suppressed_attributes",
    "travelers",
    "traveler_groups",
    "trip_templates",
    "trip_watches",
    "user_preferences",
    "users",
    "watch_travelers",
}
POST_V1_TABLES = {
    "booking_attempts",
    "disruptions",
    "integration_credential_profiles",
    "notification_deliveries",
    "tramp_stamp_ledger",
}
POST_V1_COLUMNS = {
    "calendar_detail",
    "cancellation_id",
    "credential_profile_id",
    "execution_simulated",
    "prior_booking_status",
    "prior_watch_status",
    "provenance",
    "provider_payload_json",
    "provider_correlation_id",
    "ticketing_state",
}
POST_V1_ENUMS = {
    "booking_attempt_status",
    "cancellation_provenance",
    "disruption_status",
    "disruption_type",
    "notification_delivery_status",
    "notification_transport",
}


def _migration_operations(path: Path, operation: str) -> list[str]:
    tree = ast.parse(path.read_text())
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "op"
            and node.func.attr == operation
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.append(node.args[0].value)
    return names


def _migration_column_names(path: Path, operation: str) -> list[str]:
    tree = ast.parse(path.read_text())
    names: list[str] = []
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Attribute)
            or node.func.attr != operation
            or len(node.args) < 2
        ):
            continue
        column_arg = node.args[1]
        if operation == "add_column" and isinstance(column_arg, ast.Call):
            column_arg = column_arg.args[0]
        if isinstance(column_arg, ast.Constant) and isinstance(column_arg.value, str):
            names.append(column_arg.value)
    return names


def _safe_pre_provider_codes() -> tuple[str, ...]:
    namespace = runpy.run_path(str(RECOVERY_REVISION))
    return tuple(namespace["SAFE_PRE_PROVIDER_CODES"])


def test_historical_migrations_do_not_import_live_orm_metadata() -> None:
    violations: list[str] = []
    for migration in sorted(MIGRATION_ROOT.glob("*.py")):
        source = migration.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app.db"):
                violations.append(f"{migration.name}: imports {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.db"):
                        violations.append(f"{migration.name}: imports {alias.name}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"create_all", "drop_all"}:
                    violations.append(f"{migration.name}: calls {node.func.attr}")
        if "Base.metadata" in source:
            violations.append(f"{migration.name}: references Base.metadata")

    assert violations == []


def test_initial_revision_explicitly_owns_only_pre_v2_schema() -> None:
    source = INITIAL_REVISION.read_text()

    assert set(_migration_operations(INITIAL_REVISION, "create_table")) == PRE_V2_TABLES
    assert set(_migration_operations(INITIAL_REVISION, "drop_table")) == PRE_V2_TABLES
    assert POST_V1_TABLES.isdisjoint(source.split('"'))
    assert POST_V1_COLUMNS.isdisjoint(source.split('"'))


def test_required_postgres_runner_includes_purge_race_suite() -> None:
    source = POSTGRES_RUNNER.read_text()

    assert "tests/test_admin_activity_postgres.py" in source
    assert "--junitxml=/tmp/postgres-results.xml" in source


def test_0007_safe_pre_provider_allowlist_is_explicit() -> None:
    assert _safe_pre_provider_codes() == ("deal_expired",)


def test_0008_cancellation_provenance_is_fully_reversible() -> None:
    added_tables = set(_migration_operations(PROVENANCE_REVISION, "add_column"))
    added_columns = set(_migration_column_names(PROVENANCE_REVISION, "add_column"))
    dropped_columns = set(_migration_column_names(PROVENANCE_REVISION, "drop_column"))

    assert added_tables == {
        "cancellations",
        "notification_deliveries",
        "spend_ledger",
    }
    expected_columns = {
        "cancellation_id",
        "execution_simulated",
        "prior_booking_status",
        "prior_watch_status",
        "provider",
        "provider_correlation_id",
        "provider_payload_json",
    }
    assert added_columns == expected_columns
    assert dropped_columns == expected_columns


def test_0009_cancellation_classification_is_reversible() -> None:
    source = CANCELLATION_CLASSIFICATION_REVISION.read_text()

    assert 'revision = "20260710_0009"' in source
    assert 'down_revision = "20260710_0008"' in source
    assert 'op.add_column("cancellations"' in source
    assert 'op.drop_column("cancellations", "provenance")' in source


def _migration_database_url() -> str:
    database_url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("MIGRATION_TEST_DATABASE_URL is not configured")
    if os.environ.get("MIGRATION_TEST_ALLOW_RESET") != "1":
        pytest.fail("MIGRATION_TEST_ALLOW_RESET=1 is required for destructive migration tests")

    parsed = make_url(database_url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        pytest.fail("Migration tests require a dedicated PostgreSQL database")
    return database_url


def _run_alembic(
    database_url: str,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_SECRET": "migration-test-secret-with-at-least-thirty-two-bytes",
            "DATABASE_URL": database_url,
            "INITIAL_ADMIN_EMAIL": "admin@example.com",
            "INITIAL_ADMIN_PASSWORD": "test-admin-password",
            "PUBLIC_BASE_URL": "https://tramp-migration.test",
            "REDIS_URL": "redis://localhost:6379/0",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        check=check,
        capture_output=True,
        text=True,
    )


def _reset_database(database_url: str) -> None:
    engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("DROP SCHEMA IF EXISTS public CASCADE")
            connection.exec_driver_sql("CREATE SCHEMA public")
    finally:
        engine.dispose()


def _revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        engine.dispose()


def _enum_labels(database_url: str, enum_name: str) -> list[str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return list(
                connection.scalars(
                    text(
                        """
                        SELECT enumlabel
                        FROM pg_enum
                        JOIN pg_type ON pg_type.oid = pg_enum.enumtypid
                        WHERE pg_type.typname = :enum_name
                        ORDER BY enumsortorder
                        """
                    ),
                    {"enum_name": enum_name},
                )
            )
    finally:
        engine.dispose()


def _enum_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return set(
                connection.scalars(
                    text(
                        """
                        SELECT typname
                        FROM pg_type
                        JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace
                        WHERE pg_type.typtype = 'e'
                          AND pg_namespace.nspname = 'public'
                        """
                    )
                )
            )
    finally:
        engine.dispose()


def _table_names(database_url: str) -> list[str]:
    engine = create_engine(database_url)
    try:
        return inspect(engine).get_table_names()
    finally:
        engine.dispose()


def _column_names(database_url: str, table_name: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {column["name"] for column in inspect(engine).get_columns(table_name)}
    finally:
        engine.dispose()


def _unique_constraint_names(database_url: str, table_name: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {
            constraint["name"]
            for constraint in inspect(engine).get_unique_constraints(table_name)
        }
    finally:
        engine.dispose()


def _index_names(database_url: str, table_name: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {
            index["name"]
            for index in inspect(engine).get_indexes(table_name)
        }
    finally:
        engine.dispose()


def _seed_operational_rows(database_url: str) -> dict[str, UUID]:
    ids = {
        "user": uuid4(),
        "watch": uuid4(),
        "deal": uuid4(),
        "booking": uuid4(),
        "attempt": uuid4(),
        "disruption": uuid4(),
        "delivery": uuid4(),
    }
    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            db.add(
                User(
                    id=ids["user"],
                    email=f"migration-{ids['user']}@example.com",
                    password_hash="hashed",
                    role=UserRole.USER,
                    onboarding_completed=False,
                    default_notify_channel=NotificationChannel.EMAIL,
                )
            )
            db.flush()
            db.add(
                PlatformIntegration(
                    key=f"migration-{ids['user']}",
                    encrypted_credentials="encrypted",
                    environment=IntegrationEnvironment.OFF,
                    enabled=False,
                    updated_by=ids["user"],
                )
            )
            db.add(
                TripWatch(
                    id=ids["watch"],
                    user_id=ids["user"],
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
            )
            db.flush()
            db.add(
                Deal(
                    id=ids["deal"],
                    watch_id=ids["watch"],
                    kind="flight",
                    source="migration-test",
                    total_price=Decimal("123.45"),
                    currency="USD",
                    framing=DealFraming.BEST_VALUE,
                    fingerprint_hash=f"migration-{ids['deal']}",
                    status=DealStatus.PROPOSED,
                )
            )
            db.flush()
            db.add(
                Booking(
                    id=ids["booking"],
                    deal_id=ids["deal"],
                    provider="migration-test",
                    status=BookingStatus.TICKETED,
                    idempotency_key=f"migration-{ids['booking']}",
                    loyalty_manual_followup=False,
                )
            )
            db.flush()
            db.execute(
                BookingAttempt.__table__.insert().values(
                    id=ids["attempt"],
                    deal_id=ids["deal"],
                    booking_id=ids["booking"],
                    watch_id=ids["watch"],
                    idempotency_key=f"migration-{ids['attempt']}",
                    status=BookingAttemptStatus.STARTED,
                    started_at=datetime.now(UTC),
                )
            )
            db.add(
                Disruption(
                    id=ids["disruption"],
                    booking_id=ids["booking"],
                    type=DisruptionType.SCHEDULE_CHANGE,
                    status=DisruptionStatus.NEW,
                    detected_at=datetime.now(UTC),
                )
            )
            db.flush()
            db.execute(
                NotificationDelivery.__table__.insert().values(
                    id=ids["delivery"],
                    user_id=ids["user"],
                    booking_id=ids["booking"],
                    disruption_id=ids["disruption"],
                    deal_id=ids["deal"],
                    channel="log",
                    transport=NotificationTransport.LOG_ONLY,
                    message_type="migration.test",
                    status=NotificationDeliveryStatus.PENDING,
                    attempted_at=datetime.now(UTC),
                )
            )
            db.commit()
    finally:
        engine.dispose()
    return ids


def _assert_operational_rows(database_url: str, ids: dict[str, UUID]) -> None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text("SELECT count(*) FROM users WHERE id = :id"),
                {"id": ids["user"]},
            ) == 1
            assert connection.scalar(
                text("SELECT count(*) FROM bookings WHERE id = :id"),
                {"id": ids["booking"]},
            ) == 1
            assert connection.scalar(
                text("SELECT count(*) FROM notification_deliveries WHERE id = :id"),
                {"id": ids["delivery"]},
            ) == 1
    finally:
        engine.dispose()


def test_blank_postgres_upgrade_and_full_round_trip() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)

    _run_alembic(database_url, "upgrade", "20260629_0001")
    assert set(_table_names(database_url)) == PRE_V2_TABLES | {"alembic_version"}
    assert POST_V1_TABLES.isdisjoint(_table_names(database_url))
    assert POST_V1_COLUMNS.isdisjoint(_column_names(database_url, "bookings"))
    assert "credential_profile_id" not in _column_names(
        database_url, "platform_integrations"
    )
    assert POST_V1_ENUMS.isdisjoint(_enum_names(database_url))
    assert _enum_labels(database_url, "integration_environment") == ["TEST", "LIVE"]

    _run_alembic(database_url, "upgrade", "head")
    assert _revision(database_url) == "20260710_0009"
    assert "tramp_stamp_ledger" in _table_names(database_url)
    assert "PENDING_TICKETING" not in _enum_labels(
        database_url, "booking_attempt_status"
    )
    assert "provider_booking_ref" in _column_names(
        database_url, "booking_attempts"
    )
    assert "recovery_required" in _column_names(database_url, "booking_attempts")
    assert "uq_booking_attempts_idempotency_key" in _unique_constraint_names(
        database_url,
        "booking_attempts",
    )
    assert "ix_booking_attempts_idempotency_key" not in _index_names(
        database_url, "booking_attempts"
    )
    assert "ux_booking_attempts_unresolved_deal" in _index_names(
        database_url, "booking_attempts"
    )
    _seed_operational_rows(database_url)

    second_upgrade = _run_alembic(database_url, "upgrade", "head")
    assert "Running upgrade" not in second_upgrade.stdout + second_upgrade.stderr
    check_result = _run_alembic(database_url, "check")
    assert "No new upgrade operations detected" in check_result.stdout + check_result.stderr

    _run_alembic(database_url, "downgrade", "base")
    assert _revision(database_url) is None
    assert _table_names(database_url) == ["alembic_version"]

    _run_alembic(database_url, "upgrade", "head")
    assert _revision(database_url) == "20260710_0009"


def test_0009_backfills_simulated_parent_and_marks_live_parent_unknown() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260710_0008")
    rows = _seed_operational_rows(database_url)
    simulated_deal_id = uuid4()
    simulated_booking_id = uuid4()
    simulated_cancellation_id = uuid4()
    unknown_cancellation_id = uuid4()

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO deals (
                        id, watch_id, kind, source, total_price, currency,
                        framing, fingerprint_hash, status
                    ) VALUES (
                        :id, :watch_id, 'flight', 'mock-duffel', 123.45, 'USD',
                        'BEST_VALUE', :fingerprint, 'BOOKED'
                    )
                    """
                ),
                {
                    "id": simulated_deal_id,
                    "watch_id": rows["watch"],
                    "fingerprint": f"legacy-simulated-{simulated_deal_id}",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO bookings (
                        id, deal_id, provider, status, idempotency_key,
                        loyalty_manual_followup
                    ) VALUES (
                        :id, :deal_id, 'mock-booking', 'TICKETED',
                        :idempotency_key, false
                    )
                    """
                ),
                {
                    "id": simulated_booking_id,
                    "deal_id": simulated_deal_id,
                    "idempotency_key": f"legacy-simulated-{simulated_booking_id}",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO cancellations (
                        id, booking_id, status, requested_at
                    ) VALUES
                        (:simulated_id, :simulated_booking_id, 'REQUESTED', now()),
                        (:unknown_id, :live_booking_id, 'REQUESTED', now())
                    """
                ),
                {
                    "simulated_id": simulated_cancellation_id,
                    "simulated_booking_id": simulated_booking_id,
                    "unknown_id": unknown_cancellation_id,
                    "live_booking_id": rows["booking"],
                },
            )
    finally:
        engine.dispose()

    _run_alembic(database_url, "upgrade", "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            provenance = {
                row.id: row.provenance
                for row in connection.execute(
                    text(
                        "SELECT id, provenance FROM cancellations "
                        "WHERE id IN (:simulated_id, :unknown_id)"
                    ),
                    {
                        "simulated_id": simulated_cancellation_id,
                        "unknown_id": unknown_cancellation_id,
                    },
                )
            }
    finally:
        engine.dispose()

    assert provenance[simulated_cancellation_id] == "simulated"
    assert provenance[unknown_cancellation_id] == "unknown"

    _run_alembic(database_url, "downgrade", "20260710_0008")
    assert "provenance" not in _column_names(database_url, "cancellations")


def test_0005_rejects_duplicate_attempt_claims_without_data_loss() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260710_0004")
    rows = _seed_operational_rows(database_url)

    duplicate_id = uuid4()
    duplicate_key = f"migration-{rows['attempt']}"
    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            db.execute(
                BookingAttempt.__table__.insert().values(
                    id=duplicate_id,
                    deal_id=rows["deal"],
                    booking_id=rows["booking"],
                    watch_id=rows["watch"],
                    idempotency_key=duplicate_key,
                    status=BookingAttemptStatus.STARTED,
                    started_at=datetime.now(UTC),
                )
            )
            db.commit()
    finally:
        engine.dispose()

    result = _run_alembic(database_url, "upgrade", "head", check=False)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "Duplicate booking attempt idempotency keys prevent migration" in output
    assert duplicate_key in output
    assert _revision(database_url) == "20260710_0004"
    assert "provider_booking_ref" not in _column_names(
        database_url, "booking_attempts"
    )

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM booking_attempts "
                    "WHERE idempotency_key = :idempotency_key"
                ),
                {"idempotency_key": duplicate_key},
            ) == 2
    finally:
        engine.dispose()


def test_0005_cleans_interrupted_concurrent_index_before_retry() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260710_0004")
    rows = _seed_operational_rows(database_url)
    temporary_index = "ux_booking_attempts_idempotency_key_claim"
    duplicate_id = uuid4()
    duplicate_key = f"migration-{rows['attempt']}"

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            db.execute(
                BookingAttempt.__table__.insert().values(
                    id=duplicate_id,
                    deal_id=rows["deal"],
                    booking_id=rows["booking"],
                    watch_id=rows["watch"],
                    idempotency_key=duplicate_key,
                    status=BookingAttemptStatus.STARTED,
                    started_at=datetime.now(UTC),
                )
            )
            db.commit()
    finally:
        engine.dispose()

    engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql(
                    f"CREATE UNIQUE INDEX CONCURRENTLY {temporary_index} "
                    "ON booking_attempts (idempotency_key)"
                )
    finally:
        engine.dispose()

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            assert connection.scalar(
                text(
                    """
                    SELECT idx.indisvalid
                    FROM pg_index AS idx
                    JOIN pg_class AS relation ON relation.oid = idx.indexrelid
                    WHERE relation.relname = :index_name
                    """
                ),
                {"index_name": temporary_index},
            ) is False
            connection.execute(
                text("DELETE FROM booking_attempts WHERE id = :duplicate_id"),
                {"duplicate_id": duplicate_id},
            )
    finally:
        engine.dispose()

    _run_alembic(database_url, "upgrade", "head")

    assert _revision(database_url) == "20260710_0009"
    assert temporary_index not in _index_names(database_url, "booking_attempts")
    assert "uq_booking_attempts_idempotency_key" in _unique_constraint_names(
        database_url,
        "booking_attempts",
    )
    assert "provider_booking_ref" in _column_names(
        database_url, "booking_attempts"
    )


def test_0006_rejects_duplicate_unresolved_deal_claims_without_data_loss() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260710_0005")
    rows = _seed_operational_rows(database_url)
    duplicate_id = uuid4()

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            db.execute(
                BookingAttempt.__table__.insert().values(
                    id=duplicate_id,
                    deal_id=rows["deal"],
                    booking_id=None,
                    watch_id=rows["watch"],
                    idempotency_key=f"other-key-{duplicate_id}",
                    status=BookingAttemptStatus.REVALIDATED,
                    started_at=datetime.now(UTC),
                )
            )
            db.commit()
    finally:
        engine.dispose()

    result = _run_alembic(database_url, "upgrade", "head", check=False)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "Duplicate unresolved booking attempts prevent migration" in output
    assert str(rows["deal"]) in output
    assert _revision(database_url) == "20260710_0005"
    assert "ux_booking_attempts_unresolved_deal" not in _index_names(
        database_url, "booking_attempts"
    )

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM booking_attempts "
                    "WHERE deal_id = :deal_id "
                    "AND status IN ('STARTED', 'REVALIDATED')"
                ),
                {"deal_id": rows["deal"]},
            ) == 2
    finally:
        engine.dispose()


def test_0007_fails_closed_for_code_less_failures_and_allows_safe_codes() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260710_0006")
    rows = _seed_operational_rows(database_url)
    safe_attempt_id = uuid4()
    safe_deal_id = uuid4()
    safe_code = _safe_pre_provider_codes()[0]

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            db.add(
                Deal(
                    id=safe_deal_id,
                    watch_id=rows["watch"],
                    kind="flight",
                    source="safe-pre-provider",
                    total_price=Decimal("321.00"),
                    currency="USD",
                    framing=DealFraming.BEST_VALUE,
                    fingerprint_hash=f"safe-pre-provider-{safe_deal_id}",
                    status=DealStatus.PROPOSED,
                )
            )
            db.flush()
            db.execute(
                BookingAttempt.__table__.update()
                .where(BookingAttempt.id == rows["attempt"])
                .values(
                    status=BookingAttemptStatus.FAILED,
                    provider=None,
                    provider_booking_ref=None,
                    provider_correlation_id=None,
                    response_payload_json=None,
                    error_text="legacy connector timeout",
                    finished_at=datetime.now(UTC),
                )
            )
            db.execute(
                BookingAttempt.__table__.insert().values(
                    id=safe_attempt_id,
                    deal_id=safe_deal_id,
                    booking_id=None,
                    watch_id=rows["watch"],
                    idempotency_key=f"safe-pre-provider-{safe_attempt_id}",
                    status=BookingAttemptStatus.FAILED,
                    provider=None,
                    provider_correlation_id=None,
                    response_payload_json={
                        "conflict_code": safe_code,
                        "safe_to_retry": True,
                    },
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                )
            )
            db.commit()
    finally:
        engine.dispose()

    _run_alembic(database_url, "upgrade", "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            recovery_states = {
                row.id: row.recovery_required
                for row in connection.execute(
                    text(
                        "SELECT id, recovery_required FROM booking_attempts "
                        "WHERE id IN (:provider_attempt_id, :safe_attempt_id)"
                    ),
                    {
                        "provider_attempt_id": rows["attempt"],
                        "safe_attempt_id": safe_attempt_id,
                    },
                )
            }
    finally:
        engine.dispose()

    assert recovery_states[rows["attempt"]] is True
    assert recovery_states[safe_attempt_id] is False


def test_0007_rejects_duplicate_recovery_claims_without_data_loss() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260710_0006")
    rows = _seed_operational_rows(database_url)
    duplicate_id = uuid4()
    provider_failure = {
        "conflict_code": "provider_failed",
        "safe_to_retry": False,
    }

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            db.execute(
                BookingAttempt.__table__.update()
                .where(BookingAttempt.id == rows["attempt"])
                .values(
                    status=BookingAttemptStatus.FAILED,
                    response_payload_json=provider_failure,
                    finished_at=datetime.now(UTC),
                )
            )
            db.execute(
                BookingAttempt.__table__.insert().values(
                    id=duplicate_id,
                    deal_id=rows["deal"],
                    booking_id=None,
                    watch_id=rows["watch"],
                    idempotency_key=f"recovery-key-{duplicate_id}",
                    status=BookingAttemptStatus.FAILED,
                    response_payload_json=provider_failure,
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                )
            )
            db.commit()
    finally:
        engine.dispose()

    result = _run_alembic(database_url, "upgrade", "head", check=False)
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "Duplicate active booking recovery attempts prevent migration" in output
    assert str(rows["deal"]) in output
    assert _revision(database_url) == "20260710_0006"
    assert "recovery_required" not in _column_names(database_url, "booking_attempts")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT count(*) FROM booking_attempts "
                    "WHERE deal_id = :deal_id "
                    "AND response_payload_json->>'conflict_code' = 'provider_failed'"
                ),
                {"deal_id": rows["deal"]},
            ) == 2
    finally:
        engine.dispose()


def test_existing_0003_enum_layout_upgrades_for_current_orm() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260630_0003")
    rows = _seed_operational_rows(database_url)

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE notification_deliveries "
                "ALTER COLUMN transport TYPE text USING transport::text, "
                "ALTER COLUMN status TYPE text USING status::text"
            )
            connection.exec_driver_sql("DROP TYPE notification_transport")
            connection.exec_driver_sql("DROP TYPE notification_delivery_status")
            connection.exec_driver_sql(
                "CREATE TYPE notification_transport AS ENUM "
                "('LOG_ONLY', 'SMTP_DEV', 'TELEGRAM_BOT')"
            )
            connection.exec_driver_sql(
                "CREATE TYPE notification_delivery_status AS ENUM "
                "('PENDING', 'SENT', 'FAILED')"
            )
            connection.exec_driver_sql(
                "ALTER TABLE notification_deliveries "
                "ALTER COLUMN transport TYPE notification_transport "
                "USING upper(transport)::notification_transport, "
                "ALTER COLUMN status TYPE notification_delivery_status "
                "USING upper(status)::notification_delivery_status"
            )
    finally:
        engine.dispose()

    _run_alembic(database_url, "upgrade", "head")
    assert "log_only" in _enum_labels(database_url, "notification_transport")
    assert "pending" in _enum_labels(database_url, "notification_delivery_status")
    _assert_operational_rows(database_url, rows)

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            delivery = db.get(NotificationDelivery, rows["delivery"])
            assert delivery is not None
            assert delivery.transport == NotificationTransport.LOG_ONLY
            assert delivery.status == NotificationDeliveryStatus.PENDING
    finally:
        engine.dispose()


def test_0003_stamp_round_trip_preserves_seeded_data() -> None:
    database_url = _migration_database_url()
    _reset_database(database_url)
    _run_alembic(database_url, "upgrade", "20260630_0003")
    rows = _seed_operational_rows(database_url)

    _run_alembic(database_url, "upgrade", "20260710_0004")
    _assert_operational_rows(database_url, rows)
    _run_alembic(database_url, "downgrade", "20260630_0003")
    _assert_operational_rows(database_url, rows)
    _run_alembic(database_url, "upgrade", "20260710_0004")
    _assert_operational_rows(database_url, rows)
