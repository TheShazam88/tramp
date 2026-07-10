from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app import tramp_stamp_service
from app.db.models import BookingStatus, TrampStampLedger
from app.tramp_stamp_service import stamp_balance


class FakeScalarSession:
    def __init__(self, scalar_result: int) -> None:
        self.scalar_result = scalar_result

    def scalar(self, _statement):
        return self.scalar_result


class FakeStampSession:
    def __init__(self, existing: object | None = None) -> None:
        self.existing = existing
        self.added: list[object] = []

    def scalar(self, _statement):
        return self.existing

    def add(self, value: object) -> None:
        self.added.append(value)


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


@pytest.mark.parametrize(
    ("status", "deal_source", "provider", "payload", "existing", "expected"),
    [
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {},
            None,
            1,
            id="ticketed-live-booking",
        ),
        pytest.param(
            BookingStatus.BOOKED,
            "live-amadeus",
            "duffel",
            {},
            None,
            1,
            id="booked-live-booking",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "mock-amadeus",
            "duffel",
            {},
            None,
            0,
            id="simulated-deal-source",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "mock-booking",
            {},
            None,
            0,
            id="simulated-provider",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {"simulated": True},
            None,
            0,
            id="simulated-provider-payload",
        ),
        pytest.param(
            BookingStatus.FAILED,
            "live-amadeus",
            "duffel",
            {},
            None,
            0,
            id="failed-booking",
        ),
        pytest.param(
            BookingStatus.PENDING_TICKETING,
            "live-amadeus",
            "duffel",
            {},
            None,
            0,
            id="pending-booking",
        ),
        pytest.param(
            BookingStatus.TICKETED,
            "live-amadeus",
            "duffel",
            {},
            object(),
            0,
            id="existing-booking-ledger",
        ),
    ],
)
def test_stamp_award_eligibility(
    status: BookingStatus,
    deal_source: str,
    provider: str,
    payload: dict[str, object],
    existing: object | None,
    expected: int,
) -> None:
    db = FakeStampSession(existing=existing)
    user = SimpleNamespace(id=uuid4())
    deal = SimpleNamespace(id=uuid4(), watch_id=uuid4(), source=deal_source)
    booking = SimpleNamespace(id=uuid4(), status=status, provider=provider)

    awarded = tramp_stamp_service.award_for_live_booking(
        db=db,
        user=user,
        booking=booking,
        deal=deal,
        provider_payload=payload,
    )

    assert awarded == expected
    assert len(db.added) == expected
    if expected == 1:
        award = db.added[0]
        assert isinstance(award, TrampStampLedger)
        assert award.user_id == user.id
        assert award.booking_id == booking.id
        assert award.amount == 1
        assert award.reason == "live_booking_completed"
        assert award.awarded_at.tzinfo is UTC
        assert award.meta_json == {
            "deal_id": str(deal.id),
            "watch_id": str(deal.watch_id),
            "provider": provider,
        }
