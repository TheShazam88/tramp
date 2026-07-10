from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.db.models import (
    Deal,
    DealStatus,
    PaymentMethod,
    Traveler,
    TripMode,
    TripWatch,
    TripWatchStatus,
    User,
)
from app.integrations.service import source_is_simulated
from app.watch_passports import validate_passport_expiry


@dataclass(slots=True)
class SemanticBadge:
    label: str
    tone: str


@dataclass(slots=True)
class CtaAction:
    key: str
    label: str
    tone: str
    enabled: bool = True
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessResolution:
    code: str
    label: str
    path: str


@dataclass(slots=True)
class ReadinessAssessment:
    score: int
    label: str
    blockers: list[str]
    warnings: list[str]
    resolutions: list[ReadinessResolution]


@dataclass(slots=True)
class HouseholdWorkspaceSummary:
    traveler_count: int
    traveler_group_count: int
    payment_method_count: int
    template_count: int
    passport_gap_count: int
    has_self_traveler: bool
    has_payment_method: bool
    totp_enabled: bool
    setup_warnings: list[str]
    readiness_label: str


def build_household_workspace_summary(
    *,
    user: User,
    travelers: list[Traveler],
    traveler_group_count: int,
    payment_methods: list[PaymentMethod],
    template_count: int,
) -> HouseholdWorkspaceSummary:
    has_self_traveler = any(
        traveler.traveler_relationship.value == "self" for traveler in travelers
    )
    passport_gap_count = sum(
        1
        for traveler in travelers
        if traveler.passport_number_enc is None
        or traveler.passport_country is None
        or traveler.passport_expiry is None
    )
    warnings: list[str] = []
    if not has_self_traveler:
        warnings.append("Add yourself as a traveler so TRAMP can launch booking-ready trip setups.")
    if not user.totp_secret:
        warnings.append("Finish 2FA setup before using secure booking approval.")
    if not payment_methods:
        warnings.append("Add at least one payment method before you try to book.")
    if passport_gap_count > 0:
        warnings.append(
            f"{passport_gap_count} traveler profile(s) are still missing complete passport details."
        )
    if traveler_group_count == 0 and len(travelers) >= 2:
        warnings.append("Create a traveler group to speed up repeat family or partner trips.")

    readiness_label = (
        "Booking-ready household" if not warnings else "Household setup needs attention"
    )
    return HouseholdWorkspaceSummary(
        traveler_count=len(travelers),
        traveler_group_count=traveler_group_count,
        payment_method_count=len(payment_methods),
        template_count=template_count,
        passport_gap_count=passport_gap_count,
        has_self_traveler=has_self_traveler,
        has_payment_method=bool(payment_methods),
        totp_enabled=bool(user.totp_secret),
        setup_warnings=warnings,
        readiness_label=readiness_label,
    )


def build_deal_readiness_assessment(
    *,
    user: User,
    watch: TripWatch,
    deal: Deal | None,
    travelers: list[Traveler],
    payment_methods: list[PaymentMethod],
    live_inventory_available: bool,
    mock_data_enabled: bool,
) -> ReadinessAssessment:
    blockers: list[str] = []
    warnings: list[str] = []
    resolutions: list[ReadinessResolution] = []
    score = 100

    if watch.status != TripWatchStatus.ACTIVE:
        blockers.append("Watch is paused or fulfilled, so booking should not start from this card.")
        resolutions.append(
            ReadinessResolution(
                code="watch_unavailable",
                label="Open watches",
                path="/watches",
            )
        )
        score -= 30

    if deal is None:
        blockers.append("No live deal is attached to this watch yet.")
        resolutions.append(
            ReadinessResolution(
                code="deal_missing",
                label="Search for a live deal",
                path="/watches",
            )
        )
        score -= 40
    else:
        if deal.status.value not in {"proposed", "confirmed"}:
            blockers.append("This deal is no longer bookable in its current state.")
            resolutions.append(
                ReadinessResolution(
                    code="deal_not_bookable",
                    label="Open watches",
                    path="/watches",
                )
            )
            score -= 30
        if _deal_is_expired(deal):
            blockers.append("This deal has expired and must be refreshed before booking.")
            resolutions.append(
                ReadinessResolution(
                    code="deal_expired",
                    label="Refresh this watch",
                    path="/watches",
                )
            )
            score -= 30
        if source_is_simulated(deal.source):
            warnings.append("This deal uses simulated inventory and is not ready for live booking.")
            score -= 20

    if not user.totp_secret:
        blockers.append("Two-factor authentication is required before secure approval.")
        resolutions.append(
            ReadinessResolution(
                code="two_factor_required",
                label="Set up two-factor authentication",
                path="/setup/2fa",
            )
        )
        score -= 20

    if not payment_methods:
        blockers.append("Add a payment method before booking.")
        resolutions.append(
            ReadinessResolution(
                code="payment_method_required",
                label="Add payment method",
                path="/profile",
            )
        )
        score -= 20

    if not travelers:
        blockers.append("Add at least one traveler to this watch before booking.")
        resolutions.append(
            ReadinessResolution(
                code="traveler_required",
                label="Add traveler",
                path="/profile",
            )
        )
        score -= 20

    requires_passport = watch.trip_mode != TripMode.HOTELS_ONLY
    passport_warnings = (
        validate_passport_expiry(watch=watch, travelers=travelers) if requires_passport else []
    )
    for warning in passport_warnings:
        warnings.append(warning.message)
    if passport_warnings:
        score -= min(20, 10 * len(passport_warnings))

    passport_gaps = (
        [
            traveler.display_name
            for traveler in travelers
            if traveler.passport_number_enc is None
            or traveler.passport_country is None
            or traveler.passport_expiry is None
        ]
        if requires_passport
        else []
    )
    if passport_gaps:
        blockers.append(
            "Complete passport details are missing for: " + ", ".join(passport_gaps) + "."
        )
        resolutions.append(
            ReadinessResolution(
                code="passport_details_required",
                label="Complete passport details",
                path="/profile",
            )
        )
        score -= min(25, 8 * len(passport_gaps))

    if not live_inventory_available:
        if mock_data_enabled:
            warnings.append(
                "Live provider inventory is not connected yet, so pricing confidence is limited."
            )
            score -= 10
        else:
            blockers.append("Live provider inventory is unavailable while mock data is disabled.")
            resolutions.append(
                ReadinessResolution(
                    code="live_inventory_required",
                    label="Review provider integrations",
                    path="/admin/integrations",
                )
            )
            score -= 20

    if deal is not None and deal.expires_at is not None:
        warnings.append(f"Deal expires at {deal.expires_at.isoformat()}.")

    score = max(0, min(100, score))
    if blockers:
        label = "Blocked"
    elif score >= 85:
        label = "Ready"
    elif score >= 60:
        label = "Almost ready"
    else:
        label = "Needs setup"
    return ReadinessAssessment(
        score=score,
        label=label,
        blockers=blockers,
        warnings=warnings,
        resolutions=resolutions,
    )


def build_semantic_badges(
    *,
    deal: Deal | None,
    readiness: ReadinessAssessment | None,
) -> list[SemanticBadge]:
    badges: list[SemanticBadge] = []
    if deal is not None and deal.price_percentile is not None and deal.price_percentile <= 25:
        badges.append(SemanticBadge(label="better than usual", tone="value"))
    target_price = _decimal_from_payload(deal, "target_price") if deal is not None else None
    if deal is not None and target_price is not None and deal.total_price <= target_price:
        badges.append(SemanticBadge(label="target reached", tone="luxury"))
    if deal is not None and (deal.timing_advice or "").lower().find("continue") >= 0:
        badges.append(SemanticBadge(label="timing weak", tone="muted"))
    if readiness is not None and (readiness.blockers or readiness.score < 70):
        badges.append(SemanticBadge(label="action needed", tone="alert"))
    return badges


def build_watch_actions(
    *,
    watch: TripWatch,
    has_current_deal: bool,
    readiness: ReadinessAssessment | None,
) -> list[CtaAction]:
    actions: list[CtaAction] = []
    if has_current_deal:
        actions.append(CtaAction(key="open_deal", label="Open deal", tone="primary"))
        if watch.status == TripWatchStatus.ACTIVE:
            actions.append(
                CtaAction(
                    key="book_now",
                    label="Book now",
                    tone="secondary",
                    enabled=bool(readiness and not readiness.blockers),
                    detail=(readiness.blockers[0] if readiness and readiness.blockers else None),
                )
            )
            actions.append(CtaAction(key="ignore", label="Ignore", tone="ghost"))
    elif watch.status == TripWatchStatus.ACTIVE:
        actions.append(CtaAction(key="search_now", label="Search now", tone="primary"))
    if watch.status == TripWatchStatus.ACTIVE:
        actions.append(CtaAction(key="pause_watch", label="Pause watch", tone="ghost"))
    elif watch.status == TripWatchStatus.PAUSED:
        actions.append(CtaAction(key="resume_watch", label="Resume watch", tone="ghost"))
    return actions


def build_deal_actions(
    *,
    deal: Deal,
    readiness: ReadinessAssessment,
) -> list[CtaAction]:
    return [
        CtaAction(
            key="book_now",
            label="Book now",
            tone="primary",
            enabled=not readiness.blockers and deal.status == DealStatus.PROPOSED,
            detail=readiness.blockers[0] if readiness.blockers else None,
        ),
        CtaAction(
            key="ignore",
            label="Ignore",
            tone="secondary",
            enabled=deal.status == DealStatus.PROPOSED,
        ),
    ]


def _decimal_from_payload(deal: Deal | None, key: str) -> Decimal | None:
    if deal is None or not deal.payload_json:
        return None
    raw_value = deal.payload_json.get(key)
    if raw_value in {None, ""}:
        return None
    try:
        return Decimal(str(raw_value))
    except Exception:  # noqa: BLE001
        return None


def _deal_is_expired(deal: Deal) -> bool:
    if deal.expires_at is None:
        return False
    expires_at = deal.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= datetime.now(UTC)
