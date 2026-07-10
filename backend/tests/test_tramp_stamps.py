from datetime import UTC, datetime
from uuid import uuid4

from app.db.models import TrampStampLedger
from app.tramp_stamp_service import stamp_balance


class FakeScalarSession:
    def __init__(self, scalar_result: int) -> None:
        self.scalar_result = scalar_result

    def scalar(self, _statement):
        return self.scalar_result


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


def test_stamp_balance_returns_sum() -> None:
    db = FakeScalarSession(scalar_result=3)

    assert stamp_balance(db=db, user_id=uuid4()) == 3
