"""Builder read-only PointInTimeContext SOT (Step D)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.backtest.errors import raise_backtest_http
from app.core.constants import FINISHED_STATUSES
from app.models import (
    Competition,
    Fixture,
    FixtureLineup,
    FixturePlayerStat,
    FixtureProviderLineup,
    FixtureTeamStat,
    Team,
)
from app.schemas.backtest_point_in_time import (
    ActualsForScoring,
    LeaguePointInTimeBaselines,
    LineupDiagnostic,
    PlayerStatsDiagnostic,
    PointInTimeContextResponse,
    TeamLast5Form,
    TeamPointInTimeStats,
)
from app.services.backtest.pit_leakage import compute_leakage_guard, pit_strict_kickoff_before
from app.services.backtest.pit_player_rolling_stats import load_sportapi_missing_by_side, resolve_side_lineup
from app.services.backtest.pit_split_stats_builder import build_pit_split_stats
from app.services.predictions_v10.v10_league_offensive_baselines import compute_league_offensive_baselines
from app.services.predictions_v10.v10_prior_context import (
    V10PriorContext,
    _resolve_fixture_season_id,
    build_prior_context,
)
from app.services.predictions_v11.shared_stats import expected_goals_from_team_stat
from app.services.predictions_v21.v21_xg_league_features import (
    compute_v21_xg_league_baselines,
    latest_prior_kickoff,
)
from app.services.sot_feature_math import PriorMatch

SUPPORTED_MARKET = "shots_on_target"
SOURCE_PATHS = [
    "fixture_team_stats.shots_on_target",
    "fixture_team_stats.total_shots",
    "fixture_team_stats.expected_goals",
    "fixture_player_stats.shots_on_target",
    "fixture_provider_lineups",
    "fixture_lineups",
    "point_in_time_context.split_stats",
]


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _fixture_has_team_stats(db: Session, fixture_id: int) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(FixtureTeamStat)
        .where(FixtureTeamStat.fixture_id == int(fixture_id)),
    )
    return int(count or 0) >= 1


def _league_prior_fixtures(
    db: Session,
    *,
    competition_id: int,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
) -> list[Fixture]:
    clauses = [
        Fixture.competition_id == int(competition_id),
        Fixture.status.in_(FINISHED_STATUSES),
    ]
    fixtures = db.scalars(select(Fixture).where(*clauses)).all()
    prior = [
        f
        for f in fixtures
        if pit_strict_kickoff_before(f.kickoff_at, cutoff_kickoff)
    ]
    return [f for f in prior if _fixture_has_team_stats(db, int(f.id))]


def _latest_from_fixtures(fixtures: list[Fixture]) -> datetime | None:
    return latest_prior_kickoff(fixtures)


def _team_stats_from_prior_ctx(
    prior_ctx: V10PriorContext,
    *,
    team_id: int,
    team_name: str,
) -> TeamPointInTimeStats:
    stats_map = prior_ctx.stats_map
    prior_fixtures = prior_ctx.team_prior_fixtures

    sot_for_vals: list[float] = []
    sot_against_vals: list[float] = []
    shots_for_vals: list[float] = []
    shots_against_vals: list[float] = []
    xg_for_vals: list[float] = []
    xg_against_vals: list[float] = []

    for pm in prior_ctx.team_priors:
        if pm.sot_for is not None:
            sot_for_vals.append(float(pm.sot_for))
        if pm.sot_against is not None:
            sot_against_vals.append(float(pm.sot_against))

    for f in prior_fixtures:
        st = stats_map.get((int(f.id), int(team_id)))
        opp_id = int(f.away_team_id) if int(f.home_team_id) == int(team_id) else int(f.home_team_id)
        st_opp = stats_map.get((int(f.id), opp_id))
        if st and st.total_shots is not None:
            shots_for_vals.append(float(st.total_shots))
        if st_opp and st_opp.total_shots is not None:
            shots_against_vals.append(float(st_opp.total_shots))
        if st:
            xg_for, _ = expected_goals_from_team_stat(st)
            if xg_for is not None:
                xg_for_vals.append(float(xg_for))
        if st_opp:
            xg_against, _ = expected_goals_from_team_stat(st_opp)
            if xg_against is not None:
                xg_against_vals.append(float(xg_against))

    last5 = _last5_from_priors(prior_ctx.team_priors, prior_fixtures, stats_map, int(team_id))

    return TeamPointInTimeStats(
        team_id=int(team_id),
        team_name=team_name,
        avg_sot_for=_mean(sot_for_vals),
        avg_sot_against=_mean(sot_against_vals),
        avg_total_shots_for=_mean(shots_for_vals),
        avg_total_shots_against=_mean(shots_against_vals),
        avg_xg_for=_mean(xg_for_vals),
        avg_xg_against=_mean(xg_against_vals),
        sample_count=len(prior_fixtures),
        latest_fixture_used_at=_latest_from_fixtures(prior_fixtures),
        last5=last5,
    )


def _last5_from_priors(
    priors: list[PriorMatch],
    prior_fixtures: list[Fixture],
    stats_map: dict[tuple[int, int], FixtureTeamStat],
    team_id: int,
) -> TeamLast5Form:
    last5_priors = priors[-5:]
    last5_fx = prior_fixtures[-5:]
    sot_for: list[float] = []
    sot_against: list[float] = []
    xg_for: list[float] = []
    xg_against: list[float] = []

    for pm in last5_priors:
        if pm.sot_for is not None:
            sot_for.append(float(pm.sot_for))
        if pm.sot_against is not None:
            sot_against.append(float(pm.sot_against))

    for f in last5_fx:
        st = stats_map.get((int(f.id), int(team_id)))
        opp_id = int(f.away_team_id) if int(f.home_team_id) == int(team_id) else int(f.home_team_id)
        st_opp = stats_map.get((int(f.id), opp_id))
        if st:
            xg, _ = expected_goals_from_team_stat(st)
            if xg is not None:
                xg_for.append(float(xg))
        if st_opp:
            xg_a, _ = expected_goals_from_team_stat(st_opp)
            if xg_a is not None:
                xg_against.append(float(xg_a))

    count = len(last5_priors)
    status = "ok" if count >= 5 else "partial_low_sample"
    return TeamLast5Form(
        last5_avg_sot_for=_mean(sot_for),
        last5_avg_sot_against=_mean(sot_against),
        last5_avg_xg_for=_mean(xg_for),
        last5_avg_xg_against=_mean(xg_against),
        last5_count=count,
        status=status,
    )


def _player_stats_diagnostic(
    db: Session,
    prior_fixture_ids: list[int],
    team_id: int,
) -> PlayerStatsDiagnostic:
    if not prior_fixture_ids:
        return PlayerStatsDiagnostic()
    rows = db.scalars(
        select(FixturePlayerStat).where(
            FixturePlayerStat.fixture_id.in_(prior_fixture_ids),
            FixturePlayerStat.team_id == int(team_id),
        ),
    ).all()
    if not rows:
        return PlayerStatsDiagnostic()
    fx_ids = {int(r.fixture_id) for r in rows}
    player_ids = {int(r.player_id) for r in rows}
    latest_fx_id = max(fx_ids)
    latest_fx = db.get(Fixture, latest_fx_id)
    return PlayerStatsDiagnostic(
        player_match_stats_prior_count=len(rows),
        unique_players_prior_count=len(player_ids),
        latest_player_stat_fixture_used_at=latest_fx.kickoff_at if latest_fx else None,
    )


def _lineup_diagnostic(
    db: Session,
    fixture: Fixture,
    *,
    mode: str,
    cutoff: datetime,
) -> tuple[LineupDiagnostic, list[str]]:
    fixture_id = int(fixture.id)
    warnings: list[str] = []

    if mode == "pre_lineup":
        probables = db.scalars(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id == fixture_id,
                FixtureProviderLineup.confirmed.is_(False),
            ),
        ).all()
        safe_probables = [
            pl
            for pl in probables
            if pl.fetched_at is None or pl.fetched_at <= cutoff
        ]
        if not safe_probables:
            warnings.append("no_historical_probable_lineups")
        return (
            LineupDiagnostic(
                lineup_mode="pre_lineup_no_official",
                lineups_available=len(safe_probables) > 0,
                lineups_count=len(safe_probables),
            ),
            warnings,
        )

    if mode == BACKTEST_MODE_HISTORICAL_OFFICIAL_XI:
        home_missing, away_missing = load_sportapi_missing_by_side(db, fixture_id)
        home_cov, home_starters, _, _ = resolve_side_lineup(
            db,
            fixture=fixture,
            team_id=int(fixture.home_team_id),
            side="home",
            missing_rows=home_missing,
        )
        away_cov, away_starters, _, _ = resolve_side_lineup(
            db,
            fixture=fixture,
            team_id=int(fixture.away_team_id),
            side="away",
            missing_rows=away_missing,
        )
        has_xi = home_cov.has_official_xi or away_cov.has_official_xi
        starters_count = len(home_starters) + len(away_starters)
        warnings.extend(home_cov.warnings)
        warnings.extend(away_cov.warnings)
        return (
            LineupDiagnostic(
                lineup_mode="historical_official_xi",
                lineups_available=has_xi,
                lineups_count=starters_count,
            ),
            list(dict.fromkeys(warnings)),
        )

    official_lineups = db.scalars(
        select(FixtureLineup).where(FixtureLineup.fixture_id == fixture_id),
    ).all()
    provider_official = db.scalars(
        select(FixtureProviderLineup).where(
            FixtureProviderLineup.fixture_id == fixture_id,
            FixtureProviderLineup.confirmed.is_(True),
        ),
    ).all()
    safe_count = 0
    for lu in official_lineups:
        if lu.fetched_at is not None and lu.fetched_at <= cutoff:
            safe_count += 1
        elif lu.fetched_at is None:
            warnings.append("official_lineup_missing_timestamp")
    for pl in provider_official:
        if pl.fetched_at is not None and pl.fetched_at <= cutoff:
            safe_count += 1
        elif pl.fetched_at is None:
            warnings.append("provider_lineup_missing_timestamp")
    return (
        LineupDiagnostic(
            lineup_mode="post_lineup_official_candidate",
            lineups_available=safe_count > 0,
            lineups_count=safe_count,
        ),
        warnings,
    )


def _actuals_for_scoring(db: Session, fixture: Fixture) -> ActualsForScoring:
    home_st = db.scalar(
        select(FixtureTeamStat).where(
            FixtureTeamStat.fixture_id == int(fixture.id),
            FixtureTeamStat.team_id == int(fixture.home_team_id),
        ),
    )
    away_st = db.scalar(
        select(FixtureTeamStat).where(
            FixtureTeamStat.fixture_id == int(fixture.id),
            FixtureTeamStat.team_id == int(fixture.away_team_id),
        ),
    )
    home_sot = int(home_st.shots_on_target) if home_st and home_st.shots_on_target is not None else None
    away_sot = int(away_st.shots_on_target) if away_st and away_st.shots_on_target is not None else None
    total = None
    if home_sot is not None and away_sot is not None:
        total = home_sot + away_sot
    score = None
    if fixture.goals_home is not None and fixture.goals_away is not None:
        score = f"{fixture.goals_home}-{fixture.goals_away}"
    return ActualsForScoring(
        actual_home_sot=home_sot,
        actual_away_sot=away_sot,
        actual_total_sot=total,
        final_score=score,
        fixture_status=fixture.status,
    )


def _leakage_warnings(cutoff: datetime, latest: datetime | None) -> list[str]:
    if latest is None:
        return []
    if latest >= cutoff:
        return ["possible_leakage"]
    return []


class PointInTimeContextService:
    def build_sot_context(
        self,
        db: Session,
        *,
        competition_id: int,
        fixture_id: int,
        mode: str = "pre_lineup",
        market_key: str = SUPPORTED_MARKET,
    ) -> PointInTimeContextResponse:
        if market_key != SUPPORTED_MARKET:
            raise_backtest_http(
                422,
                "market_not_supported_for_context_yet",
                f"PointInTimeContext preview supports only {SUPPORTED_MARKET} for now.",
                market_key=market_key,
            )
        if mode not in ("pre_lineup", "post_lineup", BACKTEST_MODE_HISTORICAL_OFFICIAL_XI):
            raise_backtest_http(
                422,
                "invalid_mode",
                "mode must be pre_lineup, post_lineup or historical_official_xi",
                mode=mode,
            )

        comp = db.get(Competition, int(competition_id))
        if comp is None:
            raise_backtest_http(404, "competition_not_found", f"Competition {competition_id} not found")

        fixture = db.get(Fixture, int(fixture_id))
        if fixture is None:
            raise_backtest_http(404, "fixture_not_found", f"Fixture {fixture_id} not found")

        if fixture.competition_id is None or int(fixture.competition_id) != int(competition_id):
            raise_backtest_http(
                422,
                "fixture_competition_mismatch",
                f"Fixture {fixture_id} does not belong to competition {competition_id}",
                fixture_competition_id=fixture.competition_id,
            )

        if fixture.kickoff_at is None:
            raise_backtest_http(
                422,
                "fixture_kickoff_missing",
                f"Fixture {fixture_id} has no kickoff_at",
            )

        cutoff = fixture.kickoff_at
        cutoff_fixture_id = int(fixture.id)
        season_id = _resolve_fixture_season_id(db, fixture)

        home_team = db.get(Team, int(fixture.home_team_id))
        away_team = db.get(Team, int(fixture.away_team_id))
        home_name = home_team.name if home_team else str(fixture.home_team_id)
        away_name = away_team.name if away_team else str(fixture.away_team_id)

        league_prior = _league_prior_fixtures(
            db,
            competition_id=int(competition_id),
            season_id=season_id,
            cutoff_kickoff=cutoff,
            cutoff_fixture_id=cutoff_fixture_id,
        )

        home_prior_ctx = build_prior_context(
            db,
            fixture,
            team_id=int(fixture.home_team_id),
            opponent_id=int(fixture.away_team_id),
            competition_id=int(competition_id),
            competition_scoped_only=True,
            strict_kickoff_only=True,
        )
        away_prior_ctx = build_prior_context(
            db,
            fixture,
            team_id=int(fixture.away_team_id),
            opponent_id=int(fixture.home_team_id),
            competition_id=int(competition_id),
            competition_scoped_only=True,
            strict_kickoff_only=True,
        )

        home_stats = _team_stats_from_prior_ctx(
            home_prior_ctx,
            team_id=int(fixture.home_team_id),
            team_name=home_name,
        )
        away_stats = _team_stats_from_prior_ctx(
            away_prior_ctx,
            team_id=int(fixture.away_team_id),
            team_name=away_name,
        )

        home_split_stats, away_split_stats, split_fixtures, split_warnings = build_pit_split_stats(
            home_prior_ctx,
            away_prior_ctx,
            home_team_id=int(fixture.home_team_id),
            away_team_id=int(fixture.away_team_id),
        )

        xg_lb = compute_v21_xg_league_baselines(
            db,
            season_id=season_id,
            cutoff_kickoff=cutoff,
            cutoff_fixture_id=cutoff_fixture_id,
            competition_id=int(competition_id),
            strict_kickoff_only=True,
        )
        off_lb = compute_league_offensive_baselines(
            db,
            season_id=season_id,
            cutoff_kickoff=cutoff,
            cutoff_fixture_id=cutoff_fixture_id,
            competition_id=int(competition_id),
            strict_kickoff_only=True,
        )

        xg_latest_raw = xg_lb.get("latest_fixture_used_at")
        xg_latest = datetime.fromisoformat(str(xg_latest_raw)) if xg_latest_raw else None

        league_baselines = LeaguePointInTimeBaselines(
            league_avg_sot_for=xg_lb.get("league_avg_sot_for") or off_lb.get("league_avg_sot_for"),
            league_avg_sot_against=xg_lb.get("league_avg_sot_conceded"),
            league_avg_total_shots=off_lb.get("league_avg_total_shots_for"),
            league_avg_xg_for=xg_lb.get("league_avg_xg_for"),
            league_avg_xg_conceded=xg_lb.get("league_avg_xg_conceded"),
            sample_count=int(xg_lb.get("sample_fixtures") or 0),
            latest_fixture_used_at=xg_latest,
        )

        all_prior_ids = list({int(f.id) for f in league_prior})
        home_player = _player_stats_diagnostic(db, all_prior_ids, int(fixture.home_team_id))
        away_player = _player_stats_diagnostic(db, all_prior_ids, int(fixture.away_team_id))

        lineup_diag, lineup_warnings = _lineup_diagnostic(db, fixture, mode=mode, cutoff=cutoff)
        actuals = _actuals_for_scoring(db, fixture)

        all_used_fixtures = (
            home_prior_ctx.team_prior_fixtures
            + away_prior_ctx.team_prior_fixtures
            + league_prior
            + split_fixtures
        )
        latest_fixture_used_at = _latest_from_fixtures(all_used_fixtures)

        leakage_guard = compute_leakage_guard(
            cutoff,
            latest_fixture_used_at,
            xg_latest,
            home_stats.latest_fixture_used_at,
            away_stats.latest_fixture_used_at,
            home_split_stats.latest_fixture_used_at,
            away_split_stats.latest_fixture_used_at,
        )

        warnings: list[str] = []
        missing: list[str] = []
        fallbacks: list[str] = []

        if not league_prior:
            warnings.append("no_prior_fixtures")
        if home_stats.sample_count == 0:
            missing.append("home_team_prior_stats")
        if away_stats.sample_count == 0:
            missing.append("away_team_prior_stats")
        if home_stats.last5.status == "partial_low_sample":
            warnings.append("home_last5_partial_low_sample")
        if away_stats.last5.status == "partial_low_sample":
            warnings.append("away_last5_partial_low_sample")
        if mode != BACKTEST_MODE_HISTORICAL_OFFICIAL_XI:
            warnings.append("player_profiles_point_in_time_not_built_yet")
        if xg_lb.get("season_id_fallback_used"):
            fallbacks.append("xg_league_baselines_season_id_fallback")
        warnings.extend(lineup_warnings)
        warnings.extend(split_warnings)
        warnings.extend(_leakage_warnings(cutoff, latest_fixture_used_at))

        xg_sample = int(xg_lb.get("sample_team_stat_rows") or 0)
        player_sample = home_player.player_match_stats_prior_count + away_player.player_match_stats_prior_count

        feature_snapshot: dict[str, Any] = {
            "cutoff_time": cutoff.isoformat(),
            "fixture_kickoff_at": cutoff.isoformat(),
            "latest_fixture_used_at": latest_fixture_used_at.isoformat() if latest_fixture_used_at else None,
            "team_stats_sample_count": home_stats.sample_count + away_stats.sample_count,
            "xg_sample_count": xg_sample,
            "player_profiles_sample_count": player_sample,
            "lineup_mode": lineup_diag.lineup_mode,
            "leakage_guard": leakage_guard,
            "missing_variables": missing,
            "fallback_variables": fallbacks,
            "source_paths": SOURCE_PATHS,
            "home_split_matches_count": home_split_stats.matches_count,
            "away_split_matches_count": away_split_stats.matches_count,
            "home_split_status": home_split_stats.status,
            "away_split_status": away_split_stats.status,
        }

        return PointInTimeContextResponse(
            competition_id=int(competition_id),
            competition_key=comp.key,
            competition_name=comp.name,
            fixture_id=int(fixture_id),
            fixture_kickoff_at=cutoff,
            fixture_round=fixture.round,
            fixture_status=fixture.status,
            home_team_id=int(fixture.home_team_id),
            home_team_name=home_name,
            away_team_id=int(fixture.away_team_id),
            away_team_name=away_name,
            mode=mode,
            market_key=market_key,
            cutoff_time=cutoff,
            leakage_guard=leakage_guard,
            latest_fixture_used_at=latest_fixture_used_at,
            prior_fixtures_count=len(league_prior),
            home_prior_matches_count=home_prior_ctx.team_prior_count,
            away_prior_matches_count=away_prior_ctx.team_prior_count,
            league_prior_matches_count=len(league_prior),
            home_team_stats=home_stats,
            away_team_stats=away_stats,
            home_split_stats=home_split_stats,
            away_split_stats=away_split_stats,
            league_baselines=league_baselines,
            home_player_stats=home_player,
            away_player_stats=away_player,
            lineup_diagnostic=lineup_diag,
            actuals_for_scoring=actuals,
            actuals_used_as_input=False,
            source_paths=SOURCE_PATHS,
            missing_variables=missing,
            fallback_variables=fallbacks,
            warnings=warnings,
            feature_snapshot_json=feature_snapshot,
        )

    def build_sot_context_with_historical(
        self,
        db: Session,
        *,
        competition_id: int,
        fixture_id: int,
        mode: str = "pre_lineup",
        market_key: str = "shots_on_target",
    ) -> PointInTimeContextResponse:
        ctx = self.build_sot_context(
            db,
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
            mode=mode,
            market_key=market_key,
        )
        if mode != BACKTEST_MODE_HISTORICAL_OFFICIAL_XI:
            return ctx
        from app.services.backtest.historical_pit_extensions_builder import HistoricalPitExtensionsBuilder

        return HistoricalPitExtensionsBuilder().build_historical_extensions(
            db,
            competition_id=int(competition_id),
            fixture_id=int(fixture_id),
            ctx=ctx,
        )
