"""Resolver valori actual post-match per confronto componenti (solo diagnosi)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FixtureTeamStat
from app.services.backtest.v31_component_actual_registry import (
    ActualComparisonType,
    get_variable_spec,
)

Side = Literal["home", "away", "match"]


@dataclass
class ResolvedActual:
    value: float | None
    source: str
    status: str
    actual_comparison_type: ActualComparisonType


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _load_team_stat(db: Session, fixture_id: int, team_id: int) -> FixtureTeamStat | None:
    return db.scalar(
        select(FixtureTeamStat).where(
            FixtureTeamStat.fixture_id == int(fixture_id),
            FixtureTeamStat.team_id == int(team_id),
        ),
    )


def _stat_field(st: FixtureTeamStat | None, field: str) -> float | None:
    if st is None:
        return None
    return _f(getattr(st, field, None))


def resolve_actual_component_value(
    db: Session,
    *,
    fixture_id: int,
    team_id: int,
    opponent_team_id: int,
    variable_key: str,
    side: Side = "home",
) -> ResolvedActual:
    """Actual post-match only — mai usato in predizione."""
    spec = get_variable_spec(variable_key)
    if spec is None:
        return ResolvedActual(None, "unknown", "unavailable", "unavailable")

    cmp_type = spec.actual_comparison_type
    if cmp_type == "diagnostic_only":
        return ResolvedActual(None, spec.source, "diagnostic_only", "diagnostic_only")

    tid = int(opponent_team_id) if spec.uses_opponent else int(team_id)
    st = _load_team_stat(db, fixture_id, tid)
    opp_st = _load_team_stat(db, fixture_id, opponent_team_id) if spec.uses_opponent else None

    if variable_key == "avg_sot_for":
        v = _stat_field(st, "shots_on_target")
        return ResolvedActual(v, "fixture_team_stats.shots_on_target", _avail(v), "direct")

    if variable_key in ("avg_total_shots_for",):
        v = _stat_field(st, "total_shots")
        return ResolvedActual(v, "fixture_team_stats.total_shots", _avail(v), "direct")

    if variable_key == "avg_xg_for":
        v = _stat_field(st, "expected_goals")
        return ResolvedActual(v, "fixture_team_stats.expected_goals", _avail(v), "direct")

    if variable_key in ("avg_sot_against", "opponent_conceded_sot_avg"):
        v = _stat_field(opp_st or st, "shots_on_target")
        return ResolvedActual(v, "fixture_team_stats.opponent_shots_on_target", _avail(v), "direct")

    if variable_key == "avg_total_shots_against":
        v = _stat_field(opp_st or st, "total_shots")
        return ResolvedActual(v, "fixture_team_stats.opponent_total_shots", _avail(v), "direct")

    if variable_key == "last5_avg_sot_for":
        return ResolvedActual(None, "not_in_match_stats", "unavailable", "unavailable")

    if variable_key == "home_away_split_sot_for":
        return ResolvedActual(None, "season_split_only", "unavailable", "unavailable")

    if variable_key == "shots_inside_box":
        v = _stat_field(st, "shots_inside_box")
        return ResolvedActual(v, "fixture_team_stats.shots_inside_box", _avail(v), "direct")

    if variable_key == "shots_outside_box":
        v = _stat_field(st, "shots_outside_box")
        return ResolvedActual(v, "fixture_team_stats.shots_outside_box", _avail(v), "direct")

    if variable_key == "blocked_shots":
        v = _stat_field(st, "blocked_shots")
        return ResolvedActual(v, "fixture_team_stats.blocked_shots", _avail(v), "direct")

    if variable_key == "shots_off_goal":
        v = _stat_field(st, "shots_off_goal")
        return ResolvedActual(v, "fixture_team_stats.shots_off_goal", _avail(v), "direct")

    if variable_key == "shot_accuracy":
        sot = _stat_field(st, "shots_on_target")
        tot = _stat_field(st, "total_shots")
        if sot is not None and tot and tot > 0:
            v = round(sot / tot, 4)
            return ResolvedActual(v, "derived.shots_on_target/total_shots", "available", "derived")
        return ResolvedActual(None, "derived.shots_on_target/total_shots", "unavailable", "derived")

    if variable_key == "xg_per_shot":
        xg = _stat_field(st, "expected_goals")
        tot = _stat_field(st, "total_shots")
        if xg is not None and tot and tot > 0:
            v = round(xg / tot, 4)
            return ResolvedActual(v, "derived.expected_goals/total_shots", "available", "derived")
        return ResolvedActual(None, "derived.expected_goals/total_shots", "unavailable", "derived")

    if variable_key == "xg_to_sot":
        xg = _stat_field(st, "expected_goals")
        sot = _stat_field(st, "shots_on_target")
        if xg is not None and sot and sot > 0:
            v = round(xg / sot, 4)
            return ResolvedActual(v, "derived.xg_per_sot_proxy", "available", "derived")
        return ResolvedActual(None, "derived.xg_to_sot", "unavailable", "derived")

    if variable_key == "shots_to_sot":
        sot = _stat_field(st, "shots_on_target")
        tot = _stat_field(st, "total_shots")
        if sot is not None and tot and tot > 0:
            v = round(sot / tot, 4)
            return ResolvedActual(v, "derived.shots_to_sot_proxy", "available", "derived")
        return ResolvedActual(None, "derived.shots_to_sot", "unavailable", "derived")

    return ResolvedActual(None, "unmapped", "unavailable", "unavailable")


def _avail(v: float | None) -> str:
    return "available" if v is not None else "unavailable"
