from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

os.environ.setdefault("APP_SECRET", "test-master-secret-with-more-than-32-bytes")
os.environ.setdefault("BOOKING_MASTER_KEY_PASSPHRASE", "test-master-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://user:pass@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("PUBLIC_BASE_URL", "https://tramp.test")

from app.api.routes.profile import create_traveler, update_traveler
from app.api.schemas.profile import LoyaltyProgramModel, TravelerCreateRequest, TravelerUpdateRequest
from app.db.models import Alliance, LoyaltyAccount, Traveler, TravelerRelationship, User, UserRole


def _session() -> Session:
    db_path = Path("test_profile_loyalty.sqlite3")
    if db_path.exists():
        db_path.unlink()
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    User.__table__.create(bind=engine)
    Traveler.__table__.create(bind=engine)
    LoyaltyAccount.__table__.create(bind=engine)
    return Session(engine)


@pytest.mark.anyio
async def test_traveler_can_store_multiple_loyalty_programs_and_choose_favorite() -> None:
    db = _session()
    try:
        user = User(
            id=uuid4(),
            email="traveler@example.com",
            password_hash="hashed",
            role=UserRole.USER,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        created = await create_traveler(
            payload=TravelerCreateRequest(
                traveler_relationship=TravelerRelationship.SELF,
                display_name="Matt",
                legal_first_name="Matt",
                legal_last_name="Traveler",
                dob=date(1990, 1, 1),
                nationality="BE",
                residency_country="JP",
                loyalty_programs=[
                    LoyaltyProgramModel(
                        program_code="AF",
                        account_number="FB-2048",
                        alliance=Alliance.SKYTEAM,
                        status_tier="Gold",
                        is_favorite=True,
                    ),
                    LoyaltyProgramModel(
                        program_code="UA",
                        account_number="MP-9",
                        alliance=Alliance.STAR,
                        status_tier="Silver",
                        is_favorite=False,
                    ),
                ],
            ),
            current_user=user,
            db=db,
        )

        assert len(created.loyalty_programs) == 2
        assert created.loyalty_program_code == "AF"
        assert created.loyalty_account_number == "FB-2048"
        assert created.preferred_earning_for_alliance is True

        updated = await update_traveler(
            traveler_id=UUID(created.id),
            payload=TravelerUpdateRequest(
                loyalty_programs=[
                    LoyaltyProgramModel(
                        program_code="UA",
                        account_number="MP-99",
                        alliance=Alliance.STAR,
                        status_tier="1K",
                        is_favorite=True,
                    )
                ]
            ),
            current_user=user,
            db=db,
        )
        assert len(updated.loyalty_programs) == 1
        assert updated.loyalty_program_code == "UA"
        assert updated.loyalty_account_number == "MP-99"
        assert updated.loyalty_status_tier == "1K"
        stored_accounts = list(
            db.scalars(select(LoyaltyAccount).where(LoyaltyAccount.traveler_id == UUID(created.id)))
        )
        assert len(stored_accounts) == 1
        assert stored_accounts[0].program_code == "UA"
    finally:
        db.close()
