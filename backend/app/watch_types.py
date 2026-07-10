from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.db.models import ObservationKind


@dataclass(slots=True)
class NormalizedOffer:
    fingerprint_hash: str
    kind: ObservationKind
    source: str
    title: str
    total_price: Decimal
    currency: str
    quality_index: float
    attributes: list[str]
    raw_payload: dict[str, Any]
    supplier: str | None = None
    cabin: str | None = None
    refundable: bool = False
    stops: int | None = None
    duration_minutes: int | None = None
    hotel_rating: float | None = None
    price_percentile: float | None = None
    value_score: float | None = None
    timing_advice: str | None = None


@dataclass(slots=True)
class CoverageReport:
    confidence: str
    searched_sources: list[str]
    gaps: list[str]
    notes: list[str]


@dataclass(slots=True)
class ValidationWarning:
    code: str
    severity: str
    message: str
    traveler_name: str | None = None


@dataclass(slots=True)
class LoyaltyPlanEntry:
    traveler_name: str
    program_code: str
    alliance: str
    note: str


@dataclass(slots=True)
class RejectionLearningOutcome:
    rejected: bool = False
    penalty: float = 0.0
    reasons: list[str] = field(default_factory=list)
    suppressed_attributes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchNowArtifacts:
    observed_at: datetime
    offers: list[NormalizedOffer]
    coverage_report: CoverageReport
    validation_warnings: list[ValidationWarning]
    loyalty_plan: list[LoyaltyPlanEntry]
