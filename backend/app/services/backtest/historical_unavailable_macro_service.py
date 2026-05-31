"""Macro Infortuni / indisponibili storica point-in-time (Step K)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.schemas.backtest_historical_fixture_snapshot import (
    HistoricalFixtureOfficialSnapshot,
    HistoricalFixtureSideSnapshot,
)
from app.schemas.backtest_point_in_time import (
    TeamUnavailableAbsenceBrief,
    TeamUnavailableMacroPointInTime,
)
from app.services.backtest.historical_fixture_snapshot_service import side_unavailable_raw
from app.services.backtest.pit_player_rolling_stats import build_player_prior_stats, round4

UNAVAILABLE_MACRO_INDEX_MIN = 0.80
UNAVAILABLE_MACRO_INDEX_MAX = 1.15

_OFFENSIVE_ROLES = {"F", "A", "ATT", "FW", "ST", "CF", "LW", "RW", "AM", "CAM", "SS"}
_DEFENDER_ROLES = {"D", "CB", "LB", "RB", "WB", "LWB", "RWB", "DF"}


def _clamp_unavailable_index(value: float) -> float:
    return round(max(UNAVAILABLE_MACRO_INDEX_MIN, min(UNAVAILABLE_MACRO_INDEX_MAX, float(value))), 4)


def _role_weight(position: str | None) -> float:
    if not position:
        return 0.70
    pos = position.upper().strip()
    if pos in _OFFENSIVE_ROLES or pos.startswith("F") or pos.startswith("A"):
        return 1.00
    if pos in ("M", "C", "MID", "CM", "DM", "LM", "RM") or pos.startswith("M") or pos.startswith("C"):
        return 0.70
    if pos in _DEFENDER_ROLES or pos.startswith("D"):
        return 0.35
    if pos in ("G", "GK") or pos.startswith("G"):
        return 0.00
    return 0.70


def _is_defender(position: str | None) -> bool:
    if not position:
        return False
    pos = position.upper().strip()
    return pos in _DEFENDER_ROLES or pos.startswith("D")


def _is_offensive(position: str | None) -> bool:
    if not position:
        return False
    pos = position.upper().strip()
    return pos in _OFFENSIVE_ROLES or pos.startswith("F") or pos.startswith("A")


def _norm(value: float | None, baseline: float) -> float:
    if value is None or baseline <= 0:
        return 0.0
    return min(1.5, max(0.0, float(value) / baseline))


def offensive_absence_score(
    prior_sot_per90: float | None,
    prior_shots_per90: float | None,
    prior_team_sot_share: float | None,
    *,
    baseline: float,
    role: str | None,
) -> float:
    raw = (
        0.45 * _norm(prior_sot_per90, baseline)
        + 0.30 * _norm(prior_shots_per90, baseline)
        + 0.25 * _norm(prior_team_sot_share, baseline * 0.5 if baseline else 0.15)
    )
    return raw * _role_weight(role)


def key_defender_absence_score(
    prior_minutes: int,
    prior_matches_count: int,
    *,
    role: str | None,
) -> float:
    if not _is_defender(role):
        return 0.0
    minutes_factor = min(1.0, prior_minutes / 900.0)
    matches_factor = min(1.0, prior_matches_count / 10.0)
    return 0.35 * (0.6 * minutes_factor + 0.4 * matches_factor)


def compute_unavailable_macro_index(
    *,
    offensive_penalty: float,
    opponent_defensive_boost: float,
) -> float:
    raw = 1.0 - offensive_penalty + opponent_defensive_boost
    return _clamp_unavailable_index(raw)


class HistoricalUnavailableMacroService:
    def build_team_unavailable_macro(
        self,
        db: Session,
        *,
        snapshot: HistoricalFixtureOfficialSnapshot,
        competition_id: int,
        team_id: int,
        cutoff_time: datetime,
        side: str,
        opponent_side: HistoricalFixtureSideSnapshot,
        league_avg_sot_for: float | None = None,
    ) -> TeamUnavailableMacroPointInTime:
        del team_id
        side_snap = snapshot.home if side == "home" else snapshot.away
        unavailable_raw = side_unavailable_raw(side_snap)
        opponent_unavail = side_unavailable_raw(opponent_side)

        baseline = float(league_avg_sot_for or 1.0)
        warnings: list[str] = []

        if not unavailable_raw:
            return TeamUnavailableMacroPointInTime(
                status="available",
                unavailable_macro_index=1.0,
                unavailable_count=0,
                injured_count=len(side_snap.injured),
                suspended_count=len(side_snap.suspended),
                components={
                    "offensive_absence_penalty": 0.0,
                    "opponent_defensive_absence_boost": 0.0,
                },
                reason="no_unavailable_players_for_fixture",
                source_fixture_id=int(snapshot.fixture_id),
                unavailable_source=side_snap.unavailable_source,
            )

        important_absences: list[TeamUnavailableAbsenceBrief] = []
        top_shooter_absences: list[TeamUnavailableAbsenceBrief] = []
        key_defender_absences: list[TeamUnavailableAbsenceBrief] = []
        offensive_penalties: list[float] = []
        unmapped = 0

        for row in unavailable_raw:
            prior = build_player_prior_stats(
                db,
                row=row,
                competition_id=int(competition_id),
                team_id=int(side_snap.team_id),
                cutoff=cutoff_time,
            )
            score = offensive_absence_score(
                prior.prior_sot_per90,
                prior.prior_shots_per90,
                prior.prior_team_sot_share,
                baseline=baseline,
                role=prior.role,
            )
            brief = TeamUnavailableAbsenceBrief(
                player_name=prior.player_name,
                role=prior.role,
                absence_group=row.absence_group,
                offensive_absence_score=round4(score),
                prior_sot_per90=prior.prior_sot_per90,
                prior_team_sot_share=prior.prior_team_sot_share,
                mapping_status=prior.mapping_status,
            )
            if prior.mapping_status in ("no_provider_id", "unmatched"):
                unmapped += 1
            if _is_offensive(prior.role) or score > 0.05:
                offensive_penalties.append(score)
                important_absences.append(brief)
            if prior.prior_team_sot_share is not None and prior.prior_team_sot_share >= 0.15:
                top_shooter_absences.append(brief)

        opponent_defensive_boost = 0.0
        defender_proxy_limited = False
        for row in opponent_unavail:
            prior = build_player_prior_stats(
                db,
                row=row,
                competition_id=int(competition_id),
                team_id=int(opponent_side.team_id),
                cutoff=cutoff_time,
            )
            d_score = key_defender_absence_score(
                prior.prior_minutes,
                prior.prior_matches_count,
                role=prior.role,
            )
            if d_score > 0:
                opponent_defensive_boost += d_score * 0.04
                key_defender_absences.append(
                    TeamUnavailableAbsenceBrief(
                        player_name=prior.player_name,
                        role=prior.role,
                        absence_group=row.absence_group,
                        offensive_absence_score=round4(d_score),
                        prior_sot_per90=prior.prior_sot_per90,
                        prior_team_sot_share=prior.prior_team_sot_share,
                        mapping_status=prior.mapping_status,
                    ),
                )
            elif _is_defender(prior.role):
                defender_proxy_limited = True

        offensive_penalty = min(0.18, sum(offensive_penalties))
        opponent_defensive_boost = min(0.08, opponent_defensive_boost)
        macro_index = compute_unavailable_macro_index(
            offensive_penalty=offensive_penalty,
            opponent_defensive_boost=opponent_defensive_boost,
        )

        if unmapped > 0 and unmapped >= len(unavailable_raw):
            warnings.append("unavailable_players_mapping_incomplete")
        if side_snap.unavailable_source == "none" and unavailable_raw:
            warnings.append("unavailable_source_missing")
        if defender_proxy_limited:
            warnings.append("defensive_absence_proxy_limited")

        status = "available"
        if warnings:
            status = "partial_low_sample"
        if side_snap.status == "missing":
            status = "neutral_fallback"
            macro_index = 1.0
            warnings.append("target_fixture_lineup_missing")

        return TeamUnavailableMacroPointInTime(
            status=status,
            unavailable_macro_index=macro_index,
            unavailable_count=len(unavailable_raw),
            injured_count=len(side_snap.injured),
            suspended_count=len(side_snap.suspended),
            important_absences=important_absences[:5],
            top_shooter_absences=top_shooter_absences[:3],
            key_defender_absences=key_defender_absences[:3],
            components={
                "offensive_absence_penalty": round4(offensive_penalty) or 0.0,
                "opponent_defensive_absence_boost": round4(opponent_defensive_boost) or 0.0,
            },
            warnings=warnings,
            fallback_variables=[] if status != "neutral_fallback" else ["historical_unavailable_macro"],
            source_fixture_id=int(snapshot.fixture_id),
            unavailable_source=side_snap.unavailable_source,
        )
