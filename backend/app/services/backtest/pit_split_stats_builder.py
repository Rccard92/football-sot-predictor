"""Split casa/trasferta point-in-time per backtest SOT v2.1 PIT (Step G1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import Fixture
from app.schemas.backtest_point_in_time import TeamSplitPointInTimeStats
from app.services.predictions_v10.v10_prior_context import V10PriorContext
from app.services.predictions_v11.opponent_stats_agg import agg_conceded_by_opponent, agg_xg_conceded_by_opponent
from app.services.predictions_v11.shared_stats import agg_for_team, expected_goals_from_team_stat
from app.services.predictions_v11.split_fixtures import team_split_fixtures


def _split_status(matches_count: int) -> str:
    if matches_count >= 5:
        return "available"
    if matches_count >= 1:
        return "partial_low_sample"
    return "neutral_fallback"


def _split_warnings(*, split_context: str, matches_count: int) -> list[str]:
    prefix = "home" if split_context == "home" else "away"
    if matches_count == 0:
        return [f"{prefix}_split_missing"]
    if matches_count < 5:
        return [f"{prefix}_split_low_sample"]
    return []


def _latest_kickoff(fixtures: list[Fixture]) -> datetime | None:
    kicks = [f.kickoff_at for f in fixtures if f.kickoff_at is not None]
    return max(kicks) if kicks else None


def _split_stats_from_fixtures(
    *,
    team_id: int,
    split_context: str,
    fixtures: list[Fixture],
    stats_map: dict[tuple[int, int], Any],
) -> TeamSplitPointInTimeStats:
    team_agg = agg_for_team(fixtures=fixtures, stats_map=stats_map, team_id=int(team_id))
    conceded_agg = agg_conceded_by_opponent(
        fixtures=fixtures,
        stats_map=stats_map,
        opponent_id=int(team_id),
    )
    xg_conceded_agg = agg_xg_conceded_by_opponent(
        fixtures=fixtures,
        stats_map=stats_map,
        opponent_id=int(team_id),
    )

    xg_against_vals: list[float] = []
    for f in fixtures:
        opp_id = int(f.away_team_id) if int(f.home_team_id) == int(team_id) else int(f.home_team_id)
        st_opp = stats_map.get((int(f.id), opp_id))
        if st_opp:
            xg, _ = expected_goals_from_team_stat(st_opp)
            if xg is not None:
                xg_against_vals.append(float(xg))

    matches_count = int(team_agg.get("matches_count") or len(fixtures))
    status = _split_status(matches_count)

    return TeamSplitPointInTimeStats(
        team_id=int(team_id),
        split_context=split_context,
        matches_count=matches_count,
        avg_sot_for=team_agg.get("sot_mean"),
        avg_sot_against=conceded_agg.get("sot_mean"),
        avg_total_shots_for=team_agg.get("shots_mean"),
        avg_total_shots_against=conceded_agg.get("shots_mean"),
        avg_xg_for=team_agg.get("xg_mean"),
        avg_xg_against=(sum(xg_against_vals) / len(xg_against_vals)) if xg_against_vals else xg_conceded_agg.get("xg_mean"),
        latest_fixture_used_at=_latest_kickoff(fixtures),
        status=status,
    )


def build_pit_split_stats(
    home_prior_ctx: V10PriorContext,
    away_prior_ctx: V10PriorContext,
    *,
    home_team_id: int,
    away_team_id: int,
) -> tuple[TeamSplitPointInTimeStats, TeamSplitPointInTimeStats, list[Fixture], list[str]]:
    """Calcola split casa (home team) e trasferta (away team) da prior strict PIT."""
    home_split_fixtures = team_split_fixtures(
        home_prior_ctx.team_prior_fixtures,
        int(home_team_id),
        is_home_context=True,
    )
    away_split_fixtures = team_split_fixtures(
        away_prior_ctx.team_prior_fixtures,
        int(away_team_id),
        is_home_context=False,
    )

    home_split = _split_stats_from_fixtures(
        team_id=int(home_team_id),
        split_context="home",
        fixtures=home_split_fixtures,
        stats_map=home_prior_ctx.stats_map,
    )
    away_split = _split_stats_from_fixtures(
        team_id=int(away_team_id),
        split_context="away",
        fixtures=away_split_fixtures,
        stats_map=away_prior_ctx.stats_map,
    )

    warnings: list[str] = []
    warnings.extend(_split_warnings(split_context="home", matches_count=home_split.matches_count))
    warnings.extend(_split_warnings(split_context="away", matches_count=away_split.matches_count))

    all_split_fixtures = list({int(f.id): f for f in home_split_fixtures + away_split_fixtures}.values())
    return home_split, away_split, all_split_fixtures, warnings
