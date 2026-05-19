"""Confidence e applicabilità candidati availability."""

from __future__ import annotations

from datetime import date

from app.models.player_availability import (
    SCOPE_FIXTURE_LEVEL,
    SCOPE_PROVIDER_CURRENT,
    SCOPE_PROVIDER_DATE_RANGE,
)
from app.services.availability.providers.base import SOURCE_API_FOOTBALL_INJURIES, SOURCE_API_FOOTBALL_SIDELINED
from app.services.availability.providers.types import (
    ApplicabilityStatus,
    ConfidenceLevel,
    NormalizedAvailabilityCandidate,
)

ACTIVE_MARKERS = ("active", "current", "ongoing", "still sidelined")


def _kickoff_date(kickoff) -> date:
    if hasattr(kickoff, "date"):
        return kickoff.date()
    return kickoff  # type: ignore[return-value]


def _in_date_range(kickoff: date, start: date | None, end: date | None) -> bool:
    if start is None:
        return False
    if kickoff < start:
        return False
    if end is not None and kickoff > end:
        return False
    return True


def _raw_indicates_active(raw: dict) -> bool:
    for key in ("status", "state"):
        val = raw.get(key)
        if val is not None and str(val).strip().lower() in ACTIVE_MARKERS:
            return True
    typ = raw.get("type")
    if isinstance(typ, str) and any(m in typ.lower() for m in ACTIVE_MARKERS):
        return True
    return False


def score_injuries_candidate(candidate: NormalizedAvailabilityCandidate) -> None:
    """Injuries fixture-level con api_fixture_id esatto → HIGH."""
    candidate.confidence = "HIGH"
    candidate.applicability_status = "applied"
    candidate.applicability_reason = "injuries_fixture_level_match"
    candidate.record_scope = SCOPE_FIXTURE_LEVEL


def score_sidelined_candidate(
    candidate: NormalizedAvailabilityCandidate,
    *,
    kickoff: date,
) -> None:
    start = candidate.start_date
    end = candidate.end_date
    raw = candidate.raw_json or {}

    if start is not None and end is not None and _in_date_range(kickoff, start, end):
        candidate.confidence = "HIGH"
        candidate.record_scope = SCOPE_PROVIDER_DATE_RANGE
        candidate.applicability_status = "applied"
        candidate.applicability_reason = "sidelined_date_range_covers_kickoff"
        return

    if start is not None and end is None:
        if kickoff >= start and _raw_indicates_active(raw):
            candidate.confidence = "MEDIUM"
            candidate.record_scope = SCOPE_PROVIDER_CURRENT
            candidate.applicability_status = "applied"
            candidate.applicability_reason = "sidelined_open_ended_active"
            return
        if kickoff >= start:
            candidate.confidence = "MEDIUM"
            candidate.record_scope = SCOPE_PROVIDER_CURRENT
            candidate.applicability_status = "applied"
            candidate.applicability_reason = "sidelined_start_no_end"
            return

    if start is None and end is None:
        candidate.confidence = "LOW"
        candidate.applicability_status = "not_applied"
        candidate.applicability_reason = "missing_date_window"
        return

    candidate.confidence = "LOW"
    candidate.applicability_status = "not_applied"
    candidate.applicability_reason = "dates_out_of_range_for_fixture"


def apply_confidence_scores(
    candidates: list[NormalizedAvailabilityCandidate],
    *,
    fx_by_api_id: dict,
) -> list[NormalizedAvailabilityCandidate]:
    for c in candidates:
        fx = fx_by_api_id.get(int(c.api_fixture_id))
        kickoff = _kickoff_date(fx.kickoff_at) if fx is not None else c.fixture_date
        if kickoff is None:
            c.confidence = "LOW"
            c.applicability_status = "not_applied"
            c.applicability_reason = "missing_kickoff"
            continue
        c.fixture_date = c.fixture_date or kickoff
        if c.source == SOURCE_API_FOOTBALL_INJURIES:
            score_injuries_candidate(c)
        elif c.source == SOURCE_API_FOOTBALL_SIDELINED:
            score_sidelined_candidate(c, kickoff=kickoff)
        else:
            c.confidence = "LOW"
            c.applicability_status = "not_applied"
            c.applicability_reason = "unknown_source"
        meta = c.raw_json.setdefault("_meta", {})
        if isinstance(meta, dict):
            meta["confidence"] = c.confidence
            meta["applicability_status"] = c.applicability_status
            meta["applicability_reason"] = c.applicability_reason
    return candidates


def split_applicable(
    candidates: list[NormalizedAvailabilityCandidate],
) -> tuple[list[NormalizedAvailabilityCandidate], list[NormalizedAvailabilityCandidate]]:
    applied: list[NormalizedAvailabilityCandidate] = []
    not_applied: list[NormalizedAvailabilityCandidate] = []
    for c in candidates:
        if c.confidence in ("HIGH", "MEDIUM") and c.applicability_status == "applied":
            applied.append(c)
        else:
            if c.applicability_status != "not_applied":
                c.applicability_status = "not_applied"
            not_applied.append(c)
    return applied, not_applied


def filter_records_for_player_layer(
    records: list,
) -> tuple[list, int, list[str]]:
    """Solo HIGH/MEDIUM; ritorna (filtered, ignored_low_count, sources_used)."""
    from app.models import PlayerAvailability

    filtered: list[PlayerAvailability] = []
    ignored = 0
    sources: set[str] = set()
    for row in records:
        if not isinstance(row, PlayerAvailability):
            continue
        conf = confidence_from_row_raw_json(row.raw_json)
        if conf in ("HIGH", "MEDIUM"):
            filtered.append(row)
            if row.source:
                sources.add(str(row.source))
        else:
            ignored += 1
    return filtered, ignored, sorted(sources)


def confidence_from_row_raw_json(raw_json: dict | None) -> ConfidenceLevel:
    if not raw_json:
        return "HIGH"
    meta = raw_json.get("_meta")
    if isinstance(meta, dict) and meta.get("confidence") in ("HIGH", "MEDIUM", "LOW"):
        return meta["confidence"]  # type: ignore[return-value]
    return "HIGH"
