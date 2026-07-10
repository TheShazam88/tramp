# ruff: noqa: E501
from __future__ import annotations

from datetime import date, timedelta

from app.db.models import Traveler, TripWatch
from app.watch_types import ValidationWarning


def validate_passport_expiry(
    *, watch: TripWatch, travelers: list[Traveler]
) -> list[ValidationWarning]:
    travel_end = _derive_travel_end_date(watch)
    if travel_end is None:
        return []

    warnings: list[ValidationWarning] = []
    for traveler in travelers:
        if traveler.passport_expiry is None:
            continue
        days_after_travel = (traveler.passport_expiry - travel_end).days
        if days_after_travel < 0:
            warnings.append(
                ValidationWarning(
                    code="passport_expired_before_return",
                    severity="high",
                    traveler_name=traveler.display_name,
                    message=(
                        f"{traveler.display_name}'s passport expires before the trip would end."
                    ),
                )
            )
        elif days_after_travel < 180:
            warnings.append(
                ValidationWarning(
                    code="passport_low_validity",
                    severity="medium",
                    traveler_name=traveler.display_name,
                    message=(
                        f"{traveler.display_name}'s passport expires only {days_after_travel} days "
                        "after the planned trip."
                    ),
                )
            )
    return warnings


def _derive_travel_end_date(watch: TripWatch) -> date | None:
    if watch.return_date_to is not None:
        return watch.return_date_to
    if watch.return_date_from is not None:
        return watch.return_date_from
    if watch.depart_date_to is not None and watch.trip_max_nights is not None:
        return watch.depart_date_to + timedelta(days=watch.trip_max_nights)
    if watch.depart_date_from is not None and watch.trip_min_nights is not None:
        return watch.depart_date_from + timedelta(days=watch.trip_min_nights)
    return watch.depart_date_to or watch.depart_date_from
