"""Contesto dati per side prediction v2.1 (solo lettura, no engine v2.0)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, Team
from app.models.fixture_lineup_refresh_impact import FixtureLineupRefreshImpact
from app.services.predictions_v10.v10_prior_context import V10PriorContext, build_prior_context
from app.services.predictions_v11.opponent_stats_agg import agg_conceded_by_opponent, agg_xg_conceded_by_opponent
from app.services.predictions_v11.shared_stats import agg_for_team
from app.services.predictions_v11.split_fixtures import (
    opponent_split_fixtures,
    team_split_fixtures,
)
from app.services.predictions_common.xg_strict_helpers import StrictXgSnapshot, build_strict_xg_snapshot
from app.services.predictions_v21.v21_constants import RECENT_FORM_MATCHES
from app.services.predictions_v21.v21_lineup_history import build_lineup_history
from app.services.predictions_v21.v21_payload_helpers import missing_ids_from_refresh_payload
from app.services.predictions_v21.v21_xg_coverage import XG_MISSING_WARNING, resolve_league_xg_available
from app.services.predictions_v21.v21_xg_league_features import (
    build_xg_leakage_trace,
    compute_v21_xg_league_baselines,
)
from app.services.sportapi.lineup_player_profile_lookup import LineupProfileEntry, load_team_profile_rows
from app.services.sportapi.sportapi_lineup_present import build_sportapi_lineups_audit


def _agg_pace_for_team(
    *,
    fixtures: list[Fixture],
    stats_map: dict,
    team_id: int,
) -> dict[str, Any]:
    poss_sum = poss_n = 0
    pass_sum = pass_n = 0
    acc_sum = acc_n = 0
    completed_sum = completed_n = 0
    derived_completed_sum = derived_n = 0
    for f in fixtures:
        st = stats_map.get((int(f.id), int(team_id)))
        if st is None:
            continue
        if st.ball_possession_pct is not None:
            poss_sum += float(st.ball_possession_pct)
            poss_n += 1
        if st.total_passes is not None:
            pass_sum += int(st.total_passes)
            pass_n += 1
        if st.accurate_passes is not None:
            completed_sum += int(st.accurate_passes)
            completed_n += 1
        if st.accurate_passes is not None and st.total_passes and int(st.total_passes) > 0:
            acc_sum += 100.0 * float(st.accurate_passes) / float(st.total_passes)
            acc_n += 1
        elif st.pass_accuracy_pct is not None and st.total_passes and int(st.total_passes) > 0:
            acc_sum += float(st.pass_accuracy_pct)
            acc_n += 1
            derived_completed_sum += float(st.total_passes) * float(st.pass_accuracy_pct) / 100.0
            derived_n += 1
        elif st.total_passes and st.accurate_passes is not None:
            pass

    def mean_i(sum_: float | int, n: int) -> float | None:
        return (float(sum_) / n) if n > 0 else None

    poss = mean_i(poss_sum, poss_n)
    passes = mean_i(pass_sum, pass_n)
    pass_acc = mean_i(acc_sum, acc_n)
    passes_completed = mean_i(completed_sum, completed_n)
    passes_completed_derived = mean_i(derived_completed_sum, derived_n)
    passes_completed_source = "column"
    if passes_completed is None and passes_completed_derived is not None:
        passes_completed = passes_completed_derived
        passes_completed_source = "derived"
    elif passes_completed is None and passes is not None and pass_acc is not None:
        passes_completed = float(passes) * float(pass_acc) / 100.0
        passes_completed_source = "derived"
        passes_completed_derived = passes_completed
    territorial = None
    if poss is not None and passes is not None:
        territorial = (poss / 100.0) * (passes / max(passes, 1.0))
    estimated_pace = None
    if passes is not None and poss is not None:
        estimated_pace = passes * (poss / 100.0)

    return {
        "possession_mean": poss,
        "possession_n": poss_n,
        "passes_mean": passes,
        "passes_n": pass_n,
        "passes_completed_mean": passes_completed,
        "passes_completed_n": completed_n or derived_n or pass_n,
        "passes_completed_source": passes_completed_source,
        "pass_accuracy_mean": pass_acc,
        "pass_accuracy_n": acc_n,
        "territorial_control_index": territorial,
        "estimated_pace": estimated_pace,
        "matches_count": len(fixtures),
    }


def _last_n(fixtures: list[Fixture], n: int) -> list[Fixture]:
    if n <= 0:
        return []
    return fixtures[-n:] if len(fixtures) > n else list(fixtures)


@dataclass
class V21SideContext:
    fixture: Fixture
    team_id: int
    opponent_id: int
    is_home: bool
    competition_id: int | None
    prior: V10PriorContext
    team_agg: dict[str, Any]
    opp_conceded_agg: dict[str, Any]
    team_split_agg: dict[str, Any]
    opp_split_conceded_agg: dict[str, Any]
    team_last5_agg: dict[str, Any]
    opp_last5_conceded_agg: dict[str, Any]
    team_pace_agg: dict[str, Any]
    league_baselines: dict[str, float | None]
    league_xg_available: bool
    sportapi_audit: dict[str, Any]
    sportapi_side: dict[str, Any]
    sportapi_opponent_side: dict[str, Any]
    profile_entries: list[LineupProfileEntry]
    lineup_profiles_mode: str
    lineup_history: dict[str, Any]
    refresh_snapshot_missing_api_ids: set[int] | None
    xg_leakage_trace: dict[str, Any] = field(default_factory=dict)
    strict_xg: StrictXgSnapshot | None = None
    warnings: list[str] = field(default_factory=list)


def build_v21_side_context(
    db: Session,
    fixture: Fixture,
    *,
    team_id: int,
    opponent_id: int,
    competition_id: int | None,
) -> V21SideContext:
    scope_comp = competition_id if competition_id is not None else fixture.competition_id
    prior = build_prior_context(
        db,
        fixture,
        team_id=int(team_id),
        opponent_id=int(opponent_id),
        competition_id=competition_id,
        competition_scoped_only=scope_comp is not None,
    )
    is_home = int(fixture.home_team_id) == int(team_id)
    stats_map = prior.stats_map

    team_agg = agg_for_team(
        fixtures=prior.team_prior_fixtures,
        stats_map=stats_map,
        team_id=int(team_id),
    )
    opp_conceded_agg = agg_conceded_by_opponent(
        fixtures=prior.opponent_prior_fixtures,
        stats_map=stats_map,
        opponent_id=int(opponent_id),
    )
    opp_xg_conceded = agg_xg_conceded_by_opponent(
        fixtures=prior.opponent_prior_fixtures,
        stats_map=stats_map,
        opponent_id=int(opponent_id),
    )
    opp_conceded_agg["xg_mean"] = opp_xg_conceded.get("xg_mean")
    opp_conceded_agg["xg_n"] = opp_xg_conceded.get("xg_n")

    split_team_fx = team_split_fixtures(prior.team_prior_fixtures, int(team_id), is_home_context=is_home)
    split_opp_fx = opponent_split_fixtures(
        prior.opponent_prior_fixtures,
        int(opponent_id),
        team_is_home=is_home,
    )
    team_split_agg = agg_for_team(fixtures=split_team_fx, stats_map=stats_map, team_id=int(team_id))
    opp_split_conceded_agg = agg_conceded_by_opponent(
        fixtures=split_opp_fx,
        stats_map=stats_map,
        opponent_id=int(opponent_id),
    )

    last5_team = _last_n(prior.team_prior_fixtures, RECENT_FORM_MATCHES)
    last5_opp = _last_n(prior.opponent_prior_fixtures, RECENT_FORM_MATCHES)
    team_last5_agg = agg_for_team(fixtures=last5_team, stats_map=stats_map, team_id=int(team_id))
    opp_last5_conceded_agg = agg_conceded_by_opponent(
        fixtures=last5_opp,
        stats_map=stats_map,
        opponent_id=int(opponent_id),
    )

    team_pace_agg = _agg_pace_for_team(
        fixtures=prior.team_prior_fixtures,
        stats_map=stats_map,
        team_id=int(team_id),
    )

    league_baselines: dict[str, float | None] = dict(prior.league_baselines or {})
    scope_comp = competition_id if competition_id is not None else fixture.competition_id
    if scope_comp is not None:
        xg_lb = compute_v21_xg_league_baselines(
            db,
            season_id=prior.season_id,
            cutoff_kickoff=prior.cutoff_kickoff,
            cutoff_fixture_id=prior.cutoff_fixture_id,
            competition_id=int(scope_comp),
        )
        league_baselines["league_avg_xg_for"] = xg_lb.get("league_avg_xg_for")
        league_baselines["league_avg_xg_conceded"] = xg_lb.get("league_avg_xg_conceded")
        league_baselines["league_avg_sot_for"] = xg_lb.get("league_avg_sot_for")
        league_baselines["league_avg_sot_conceded"] = xg_lb.get("league_avg_sot_conceded")

    strict_xg = build_strict_xg_snapshot(
        prior_fixtures=prior.team_prior_fixtures,
        opponent_prior_fixtures=prior.opponent_prior_fixtures,
        stats_map=stats_map,
        team_id=int(team_id),
        opponent_id=int(opponent_id),
        league_baselines=league_baselines,
        cutoff_kickoff=prior.cutoff_kickoff,
        cutoff_fixture_id=prior.cutoff_fixture_id,
    )

    xg_leakage_trace = build_xg_leakage_trace(
        team_fixtures=prior.team_prior_fixtures,
        opp_fixtures=prior.opponent_prior_fixtures,
        team_sample_count=strict_xg.team_xg_n or team_agg.get("xg_n"),
        opp_sample_count=strict_xg.opp_xg_n or opp_conceded_agg.get("xg_n"),
    )
    if strict_xg.latest_fixture_used_at:
        xg_leakage_trace["latest_fixture_used_at"] = strict_xg.latest_fixture_used_at

    league_xg_available = strict_xg.status in ("ok", "insufficient_xg_sample") or resolve_league_xg_available(
        db,
        competition_id=scope_comp,
        league_baselines=league_baselines,
        team_agg=team_agg,
        opp_conceded_agg=opp_conceded_agg,
    )

    home_team = db.get(Team, int(fixture.home_team_id))
    away_team = db.get(Team, int(fixture.away_team_id))
    hn = home_team.name if home_team else str(fixture.home_team_id)
    an = away_team.name if away_team else str(fixture.away_team_id)
    sportapi_audit = build_sportapi_lineups_audit(db, int(fixture.id), home_team_name=hn, away_team_name=an)
    sportapi_side = sportapi_audit.get("home" if is_home else "away")
    sportapi_opponent_side = sportapi_audit.get("away" if is_home else "home")
    if not isinstance(sportapi_side, dict):
        sportapi_side = {}
    if not isinstance(sportapi_opponent_side, dict):
        sportapi_opponent_side = {}

    profile_entries: list[LineupProfileEntry] = []
    lineup_profiles_mode = "not_available"
    warnings: list[str] = []
    team_row = db.get(Team, int(team_id))
    if scope_comp is not None and team_row is not None:
        comp = db.get(Competition, int(scope_comp))
        if comp is not None:
            league_id = comp.league_id
            if league_id is None and comp.provider_league_id is not None:
                league_id = int(comp.provider_league_id)
            if league_id is None:
                warnings.append("Profili giocatori non caricati: league_id/provider_league_id assenti sulla competition")
            else:
                try:
                    profile_entries = load_team_profile_rows(
                        db,
                        competition_id=int(scope_comp),
                        season=int(comp.season),
                        league_id=int(league_id),
                        api_team_id=int(team_row.api_team_id),
                        team_id=int(team_id),
                    )
                    if profile_entries:
                        if sportapi_audit.get("available"):
                            lineup_profiles_mode = "lineup_and_profiles"
                        else:
                            lineup_profiles_mode = "fallback_historical_profiles"
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"Profili giocatori non caricati: {exc}")

    if not league_xg_available:
        warnings.append(XG_MISSING_WARNING)
    elif strict_xg.warnings:
        warnings.extend(strict_xg.warnings)

    lineup_history = build_lineup_history(
        db,
        team_id=int(team_id),
        prior_fixtures=prior.team_prior_fixtures,
    )

    side_key = "home" if is_home else "away"
    refresh_snapshot_missing_api_ids: set[int] | None = None
    refresh_row = db.scalars(
        select(FixtureLineupRefreshImpact)
        .where(FixtureLineupRefreshImpact.fixture_id == int(fixture.id))
        .order_by(FixtureLineupRefreshImpact.created_at.desc())
        .limit(1),
    ).first()
    if refresh_row is not None and isinstance(refresh_row.before_payload, dict):
        refresh_snapshot_missing_api_ids = missing_ids_from_refresh_payload(
            refresh_row.before_payload,
            side=side_key,
        )

    return V21SideContext(
        fixture=fixture,
        team_id=int(team_id),
        opponent_id=int(opponent_id),
        is_home=is_home,
        competition_id=int(scope_comp) if scope_comp is not None else None,
        prior=prior,
        team_agg=team_agg,
        opp_conceded_agg=opp_conceded_agg,
        team_split_agg=team_split_agg,
        opp_split_conceded_agg=opp_split_conceded_agg,
        team_last5_agg=team_last5_agg,
        opp_last5_conceded_agg=opp_last5_conceded_agg,
        team_pace_agg=team_pace_agg,
        league_baselines=league_baselines,
        league_xg_available=league_xg_available,
        xg_leakage_trace=xg_leakage_trace,
        strict_xg=strict_xg,
        sportapi_audit=sportapi_audit,
        sportapi_side=sportapi_side,
        sportapi_opponent_side=sportapi_opponent_side,
        profile_entries=profile_entries,
        lineup_profiles_mode=lineup_profiles_mode,
        lineup_history=lineup_history,
        refresh_snapshot_missing_api_ids=refresh_snapshot_missing_api_ids,
        warnings=warnings,
    )
