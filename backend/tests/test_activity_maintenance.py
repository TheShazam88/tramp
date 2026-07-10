from __future__ import annotations

import inspect
import os
from types import SimpleNamespace

os.environ.setdefault("APP_SECRET", "test-master-secret-with-more-than-32-bytes")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PUBLIC_BASE_URL", "https://tramp.test")

from app import (
    booking_service,
    deal_service,
    disruption_service,
    notification_service,
    tramp_stamp_service,
    watch_service,
)
from app.activity_maintenance import (
    acquire_activity_maintenance_lock,
    acquire_activity_writer_lock,
)


class FakeSession:
    def __init__(self, dialect_name: str) -> None:
        self.bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect_name))
        self.executions: list[tuple[object, object]] = []

    def get_bind(self):
        return self.bind

    def execute(self, statement, parameters=None):
        self.executions.append((statement, parameters))


def test_postgres_purge_uses_exclusive_transaction_lock() -> None:
    session = FakeSession("postgresql")

    acquire_activity_maintenance_lock(session)

    assert len(session.executions) == 1
    statement, parameters = session.executions[0]
    assert "pg_advisory_xact_lock" in str(statement)
    assert parameters == {"lock_key": 6072351297463113037}


def test_postgres_writer_uses_shared_transaction_lock() -> None:
    session = FakeSession("postgresql")

    acquire_activity_writer_lock(session)

    assert len(session.executions) == 1
    statement, parameters = session.executions[0]
    assert "pg_advisory_xact_lock_shared" in str(statement)
    assert parameters == {"lock_key": 6072351297463113037}


def test_non_postgres_test_sessions_do_not_execute_postgres_lock_sql() -> None:
    session = FakeSession("sqlite")

    acquire_activity_maintenance_lock(session)

    assert session.executions == []


def test_every_purge_racing_activity_writer_uses_shared_lock() -> None:
    writers = (
        watch_service.create_watch,
        watch_service.update_watch,
        watch_service.pause_watch,
        watch_service.resume_watch,
        watch_service.search_now,
        booking_service.approve_and_book,
        booking_service.cancel_booking,
        deal_service.create_approval_token,
        deal_service.confirm_deal_intent,
        deal_service.reject_deal,
        disruption_service.create_disruption,
        disruption_service.resolve_disruption,
        notification_service.queue_notification,
        notification_service.send_notification_delivery,
        tramp_stamp_service.award_for_live_booking,
    )

    for writer in writers:
        assert "acquire_activity_writer_lock" in inspect.getsource(writer), writer
