# ruff: noqa: E501
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alliance, LoyaltyAccount, ProgramType, Traveler
from app.watch_types import LoyaltyPlanEntry, NormalizedOffer


def build_loyalty_plan(
    *,
    db: Session,
    travelers: list[Traveler],
    offer: NormalizedOffer,
) -> list[LoyaltyPlanEntry]:
    if offer.kind.value != "flight":
        return []

    airline_code = str(offer.raw_payload.get("airline_code", "")).upper()
    airline_alliance = str(offer.raw_payload.get("alliance", "none")).lower()
    plan: list[LoyaltyPlanEntry] = []

    for traveler in travelers:
        accounts = list(
            db.scalars(
                select(LoyaltyAccount)
                .where(
                    LoyaltyAccount.traveler_id == traveler.id,
                    LoyaltyAccount.program_type == ProgramType.AIRLINE,
                )
                .order_by(
                    LoyaltyAccount.preferred_earning_for_alliance.desc(), LoyaltyAccount.id.asc()
                )
            )
        )
        chosen = _choose_account(
            accounts=accounts, airline_code=airline_code, airline_alliance=airline_alliance
        )
        if chosen is None:
            continue
        note = f"Credit this itinerary to {chosen.program_code}"
        if chosen.preferred_earning_for_alliance:
            note += " based on your alliance preference."
        elif airline_code and chosen.program_code.upper() == airline_code:
            note += " because it matches the operating carrier."
        else:
            note += " as the closest available loyalty match."
        plan.append(
            LoyaltyPlanEntry(
                traveler_name=traveler.display_name,
                program_code=chosen.program_code,
                alliance=chosen.alliance.value,
                note=note,
            )
        )
    return plan


def _choose_account(
    *,
    accounts: list[LoyaltyAccount],
    airline_code: str,
    airline_alliance: str,
) -> LoyaltyAccount | None:
    if not accounts:
        return None

    for account in accounts:
        if account.program_code.upper() == airline_code:
            return account

    for account in accounts:
        if account.alliance != Alliance.NONE and account.alliance.value == airline_alliance:
            return account

    return accounts[0]
