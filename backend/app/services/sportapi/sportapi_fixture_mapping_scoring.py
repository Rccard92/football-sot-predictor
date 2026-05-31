"""Scoring K.3 matching sicuro fixture interna ↔ SportAPI (Step K.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Literal

from app.services.sportapi.sportapi_normalize import extract_round_number, team_names_match_fuzzy
from app.services.sportapi.sportapi_payload import (
    event_home_away_names,
    event_id,
    event_start_timestamp,
    event_tournament_info,
)

MatchConfidence = Literal["high", "medium", "low", "none"]

HIGH_SCORE_THRESHOLD = 85.0
MEDIUM_SCORE_THRESHOLD = 70.0
LOW_SCORE_THRESHOLD = 50.0
AMBIGUITY_DELTA = 5.0
KICKOFF_15M_S = 900
KICKOFF_120M_S = 7200


@dataclass(frozen=True)
class ScoredMappingCandidate:
    provider_event_id: int
    score: float
    confidence: MatchConfidence
    home_team_name: str
    away_team_name: str
    start_timestamp: int | None
    round_number: int | None
    tournament_name: str | None
    breakdown: dict[str, Any] = field(default_factory=dict)
    raw_event: dict[str, Any] = field(default_factory=dict)


def _same_utc_date(ts: int, match_date: date) -> bool:
    dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return dt.date() == match_date


def score_mapping_candidate(
    *,
    fixture_ts: int,
    match_date: date,
    home_name: str,
    away_name: str,
    round_num: int | None,
    ev: dict[str, Any],
) -> ScoredMappingCandidate:
    """Score K.3: stesso giorno obbligatorio, rubric team/kickoff/round."""
    ev_ts = event_start_timestamp(ev)
    eid = event_id(ev) or 0
    ev_home, ev_away = event_home_away_names(ev)
    info = event_tournament_info(ev)
    ev_round_raw = info.get("round")
    try:
        ev_round_n = int(ev_round_raw) if ev_round_raw is not None else None
    except (TypeError, ValueError):
        ev_round_n = None

    breakdown: dict[str, Any] = {}
    score = 0.0

    if ev_ts is None or not _same_utc_date(ev_ts, match_date):
        breakdown["same_day"] = False
        return ScoredMappingCandidate(
            provider_event_id=int(eid),
            score=0.0,
            confidence="none",
            home_team_name=ev_home,
            away_team_name=ev_away,
            start_timestamp=ev_ts,
            round_number=ev_round_n,
            tournament_name=str(info.get("tournament_name") or "") or None,
            breakdown=breakdown,
            raw_event=ev if isinstance(ev, dict) else {},
        )

    breakdown["same_day"] = True

    if team_names_match_fuzzy(home_name, ev_home):
        breakdown["home_team"] = 35
        score += 35
    else:
        breakdown["home_team"] = 0

    if team_names_match_fuzzy(away_name, ev_away):
        breakdown["away_team"] = 35
        score += 35
    else:
        breakdown["away_team"] = 0

    delta_s = abs(int(ev_ts) - int(fixture_ts))
    if delta_s <= KICKOFF_15M_S:
        breakdown["kickoff_within_15m"] = 20
        score += 20
    elif delta_s <= KICKOFF_120M_S:
        breakdown["kickoff_within_120m"] = 10
        score += 10
    else:
        breakdown["kickoff"] = 0

    if round_num is not None and ev_round_n is not None and round_num == ev_round_n:
        breakdown["round"] = 10
        score += 10
    else:
        breakdown["round"] = 0

    score = round(score, 2)
    if score >= HIGH_SCORE_THRESHOLD:
        confidence: MatchConfidence = "high"
    elif score >= MEDIUM_SCORE_THRESHOLD:
        confidence = "medium"
    elif score >= LOW_SCORE_THRESHOLD:
        confidence = "low"
    else:
        confidence = "none"

    return ScoredMappingCandidate(
        provider_event_id=int(eid),
        score=score,
        confidence=confidence,
        home_team_name=ev_home,
        away_team_name=ev_away,
        start_timestamp=ev_ts,
        round_number=ev_round_n,
        tournament_name=str(info.get("tournament_name") or "") or None,
        breakdown=breakdown,
        raw_event=ev if isinstance(ev, dict) else {},
    )


def pick_best_candidate(
    candidates: list[ScoredMappingCandidate],
) -> tuple[ScoredMappingCandidate | None, bool, list[str]]:
    """Restituisce best, ambiguous_high, warnings."""
    warnings: list[str] = []
    if not candidates:
        return None, False, warnings

    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    best = ranked[0]
    high = [c for c in ranked if c.score >= HIGH_SCORE_THRESHOLD]

    ambiguous = False
    if len(high) >= 2:
        delta = high[0].score - high[1].score
        if delta < AMBIGUITY_DELTA:
            ambiguous = True
            warnings.append(
                f"Match ambiguo: {len(high)} candidate con score >= {HIGH_SCORE_THRESHOLD} "
                f"(delta top-2={delta:.1f})",
            )

    return best, ambiguous, warnings


def effective_confidence(
    best: ScoredMappingCandidate | None,
    *,
    ambiguous: bool,
) -> MatchConfidence:
    if best is None:
        return "none"
    if ambiguous and best.confidence == "high":
        return "none"
    return best.confidence


def extract_round_from_fixture(fixture_round: str | None) -> int | None:
    return extract_round_number(fixture_round)
