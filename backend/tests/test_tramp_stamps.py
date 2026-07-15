from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app import tramp_stamp_service
from app.db.models import BookingStatus, TrampStampLedger
from app.tramp_stamp_service import stamp_balance


class FakeScalarSession:
    def __init__(self, scalar_result: int) -> None:
        self.scalar_result = scalar_result

    def scalar(self, _statement):
        return self.scalar_result


class FakeStampSession:
    def __init__(self, scalar_result: object | None = None) -> None:
        self.scalar_result = scalar_result
        self.statements: list[object] = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_result

    def add(self, _value: object) -> None:
        raise AssertionError("Stamp awards must use an atomic PostgreSQL insert.")


def test_stamp_ledger_records_single_stamp_reason() -> None:
    award = TrampStampLedger(
        user_id=uuid4(),
        booking_id=uuid4(),
        amount=1,
        reason="live_booking_completed",
        awarded_at=datetime.now(UTC),
        meta_json={},
    )

    assert award.amount == 1
    assert award.reason == "live_booking_completed"


def test_stamp_ledger_constrains_the_only_valid_reason() -> None:
    check_sql = {
        str(constraint.sqltext)
        for constraint in TrampStampLedger.__table__.constraints
        if hasattr(constraint, "sqltext")
    }

    assert "reason = 'live_booking_completed'" in check_sql


def test_stamp_balance_returns_sum() -> None:
    db = FakeScalarSession(scalar_result=3)

    assert stamp_balance(db=db, user_id=uuid4()) == 3


@pytest.mark.parametrize(
    (
        "status",
        "deal_source",
        "provider",
        "payload",
        "execution_simulated",
        "scalar_result",
        "expected",
        "expected_statements",
    ),
    [
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {},
            False,
            uuid4(),
            1,
            1,
            id="ticketed-live-booking",
        ),
        pytest.param(
            BookingStatus.BOOKED,
            "live-amadeus",
            "duffel",
            {},
            False,
            uuid4(),
            1,
            1,
            id="booked-live-booking",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "mock-amadeus",
            "duffel",
            {},
            False,
            uuid4(),
            0,
            0,
            id="simulated-deal-source",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "mock-booking",
            {},
            False,
            uuid4(),
            0,
            0,
            id="simulated-provider",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {"simulated": True},
            False,
            uuid4(),
            0,
            0,
            id="simulated-provider-payload",
        ),
        pytest.param(
            BookingStatus.FAILED,
            "live-amadeus",
            "duffel",
            {},
            False,
            uuid4(),
            0,
            0,
            id="failed-booking",
        ),
        pytest.param(
            BookingStatus.PENDING_TICKETING,
            "live-amadeus",
            "duffel",
            {},
            False,
            uuid4(),
            0,
            0,
            id="pending-booking",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {},
            False,
            None,
            0,
            1,
            id="concurrent-booking-ledger",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {},
            True,
            uuid4(),
            0,
            0,
            id="explicitly-simulated-execution",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {},
            None,
            uuid4(),
            0,
            0,
            id="missing-execution-provenance",
        ),
    ],
)
def test_stamp_award_eligibility(
    status: BookingStatus,
    deal_source: str,
    provider: str,
    payload: dict[str, object],
    execution_simulated: bool | None,
    scalar_result: object | None,
    expected: int,
    expected_statements: int,
) -> None:
    db = FakeStampSession(scalar_result=scalar_result)
    user = SimpleNamespace(id=uuid4())
    deal = SimpleNamespace(id=uuid4(), watch_id=uuid4(), source=deal_source)
    booking = SimpleNamespace(id=uuid4(), status=status, provider=provider)

    awarded = tramp_stamp_service.award_for_live_booking(
        db=db,
        user=user,
        booking=booking,
        deal=deal,
        provider_payload=payload,
        execution_simulated=execution_simulated,
    )

    assert awarded == expected
    assert len(db.statements) == expected_statements
    if expected_statements == 1:
        params = db.statements[0].compile(dialect=postgresql.dialect()).params
        assert params["user_id"] == user.id
        assert params["booking_id"] == booking.id
        assert params["amount"] == 1
        assert params["reason"] == "live_booking_completed"
        assert params["awarded_at"].tzinfo is UTC
        assert params["meta_json"] == {
            "deal_id": str(deal.id),
            "watch_id": str(deal.watch_id),
            "provider": provider,
        }
