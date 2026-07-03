"""
Contesto partite precedenti per resolver v1.0 (anti data-leakage).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture, FixtureTeamStat, League, Season
from app.services.predictions_v10.v10_league_offensive_baselines import compute_league_offensive_baselines
from app.services.datetime_utils import ensure_datetime_utc, fixture_key_before_safe
from app.services.sot_feature_math import PriorMatch, league_avg_sot_from_prior_fixtures


@dataclass
class V10PriorContext:
    season_id: int
    cutoff_kickoff: datetime
    cutoff_fixture_id: int
    team_id: int
    opponent_id: int
    is_home: bool
    team_priors: list[PriorMatch]
    opponent_priors: list[PriorMatch]
    league_avg_sot: float | None
    stats_map: dict[tuple[int, int], FixtureTeamStat]
    team_prior_count: int
    opponent_prior_count: int
    team_prior_fixtures: list[Fixture]
    opponent_prior_fixtures: list[Fixture]
    league_baselines: dict[str, float | None]


def _resolve_fixture_season_id(db: Session, fixture: Fixture) -> int:
    if fixture.season_id is not None:
        return int(fixture.season_id)
    if fixture.competition_id is None:
        raise ValueError("fixture_missing_season_id_and_competition_id")
    comp = db.get(Competition, int(fixture.competition_id))
    if comp is None:
        raise ValueError(f"competition_not_found:{fixture.competition_id}")
    if comp.season_id is not None:
        return int(comp.season_id)
    league_id = comp.league_id
    if league_id is None and comp.provider_league_id is not None:
        league = db.scalar(select(League).where(League.api_league_id == int(comp.provider_league_id)))
        if league is not None:
            league_id = int(league.id)
    if league_id is None:
        raise ValueError("competition_league_not_resolved")
    season = db.scalar(
        select(Season).where(Season.league_id == int(league_id), Season.year == int(comp.season)),
    )
    if season is None:
        raise ValueError(f"season_not_found_for_competition:{comp.id}")
    return int(season.id)


def _prior_fixtures_for_team(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
    team_id: int,
    competition_id: int | None = None,
    competition_scoped_only: bool = False,
    strict_kickoff_only: bool = False,
) -> list[Fixture]:
    cutoff_ko = ensure_datetime_utc(cutoff_kickoff, field_name="cutoff_kickoff")
    if cutoff_ko is None:
        logger.warning(
            "prior_fixtures target_kickoff_invalid season_id=%s team_id=%s cutoff=%r",
            season_id,
            team_id,
            cutoff_kickoff,
        )
        return []

    def _is_prior(f: Fixture) -> bool:
        prior_ko = ensure_datetime_utc(f.kickoff_at, field_name=f"prior_fixture_{f.id}.kickoff_at")
        if prior_ko is None:
            if f.kickoff_at is not None:
                logger.warning(
                    "prior_fixtures skip fixture_id=%s prior_fixture_kickoff_invalid",
                    f.id,
                )
            return False
        if strict_kickoff_only:
            return prior_ko < cutoff_ko
        prior_before = fixture_key_before_safe(
            prior_ko,
            int(f.id),
            cutoff_ko,
            cutoff_fixture_id,
            field_name_a=f"prior_fixture_{f.id}.kickoff_at",
            field_name_b="cutoff_kickoff",
        )
        if prior_before is None:
            logger.warning(
                "prior_fixtures skip fixture_id=%s prior_fixture_kickoff_invalid",
                f.id,
            )
            return False
        return prior_before

    def _query(*, use_season_filter: bool) -> list[Fixture]:
        clauses = [
            Fixture.status.in_(FINISHED_STATUSES),
            (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
        ]
        if use_season_filter:
            clauses.insert(0, Fixture.season_id == season_id)
        if competition_id is not None:
            clauses.append(Fixture.competition_id == int(competition_id))
        q = (
            select(Fixture)
            .where(*clauses)
            .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
        )
        xs = db.scalars(q).all()
        return [f for f in xs if _is_prior(f)]

    if competition_scoped_only and competition_id is not None:
        return _query(use_season_filter=False)

    filtered = _query(use_season_filter=True)
    if not filtered and competition_id is not None:
        logger.info(
            "prior_fixtures season_id fallback (expected competition-scoped prior) "
            "competition_id=%s season_id=%s team_id=%s",
            int(competition_id),
            int(season_id),
            int(team_id),
        )
        return _query(use_season_filter=False)
    return filtered


def _team_stats_map(db: Session, fixture_ids: list[int]) -> dict[tuple[int, int], FixtureTeamStat]:
    if not fixture_ids:
        return {}
    rows = db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fixture_ids))).all()
    return {(int(r.fixture_id), int(r.team_id)): r for r in rows}


def _build_team_history(
    prior_fixtures: list[Fixture],
    stats_map: dict[tuple[int, int], FixtureTeamStat],
    team_id: int,
) -> list[PriorMatch]:
    history: list[PriorMatch] = []
    for f in prior_fixtures:
        is_home = int(f.home_team_id) == int(team_id)
        st = stats_map.get((int(f.id), int(team_id)))
        opp_id = int(f.away_team_id) if is_home else int(f.home_team_id)
        st_opp = stats_map.get((int(f.id), opp_id))
        sot_for = int(st.shots_on_target) if st and st.shots_on_target is not None else None
        sot_against = int(st_opp.shots_on_target) if st_opp and st_opp.shots_on_target is not None else None
        history.append(
            PriorMatch(
                kickoff=f.kickoff_at,
                fixture_id=int(f.id),
                is_home=is_home,
                sot_for=sot_for,
                sot_against=sot_against,
            ),
        )
    return history


def _league_avg_from_prior_fixtures(
    prior_fixtures: list[Fixture],
    stats_map: dict[tuple[int, int], FixtureTeamStat],
) -> float | None:
    rows: list[tuple[int | None, int | None]] = []
    for f in prior_fixtures:
        sh = stats_map.get((int(f.id), int(f.home_team_id)))
        sa = stats_map.get((int(f.id), int(f.away_team_id)))
        h = int(sh.shots_on_target) if sh and sh.shots_on_target is not None else None
        a = int(sa.shots_on_target) if sa and sa.shots_on_target is not None else None
        rows.append((h, a))
    return league_avg_sot_from_prior_fixtures(rows)


def build_prior_context(
    db: Session,
    fixture: Fixture,
    *,
    team_id: int,
    opponent_id: int,
    competition_id: int | None = None,
    competition_scoped_only: bool = False,
    strict_kickoff_only: bool = False,
) -> V10PriorContext:
    scope_competition_id = competition_id if competition_id is not None else fixture.competition_id
    season_id = _resolve_fixture_season_id(db, fixture)
    cutoff_kickoff = fixture.kickoff_at
    cutoff_fixture_id = int(fixture.id)
    is_home = int(fixture.home_team_id) == int(team_id)
    comp_filter = int(scope_competition_id) if scope_competition_id is not None else None
    scoped_only = bool(competition_scoped_only and comp_filter is not None)

    team_prior_fx = _prior_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(team_id),
        competition_id=comp_filter,
        competition_scoped_only=scoped_only,
        strict_kickoff_only=strict_kickoff_only,
    )
    opp_prior_fx = _prior_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(opponent_id),
        competition_id=comp_filter,
        competition_scoped_only=scoped_only,
        strict_kickoff_only=strict_kickoff_only,
    )
    all_ids = list({int(f.id) for f in team_prior_fx + opp_prior_fx})
    stats_map = _team_stats_map(db, all_ids)
    league_baselines = compute_league_offensive_baselines(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        competition_id=comp_filter,
        strict_kickoff_only=strict_kickoff_only,
    )

    return V10PriorContext(
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(team_id),
        opponent_id=int(opponent_id),
        is_home=is_home,
        team_priors=_build_team_history(team_prior_fx, stats_map, int(team_id)),
        opponent_priors=_build_team_history(opp_prior_fx, stats_map, int(opponent_id)),
        league_avg_sot=_league_avg_from_prior_fixtures(team_prior_fx + opp_prior_fx, stats_map),
        stats_map=stats_map,
        team_prior_count=len(team_prior_fx),
        opponent_prior_count=len(opp_prior_fx),
        team_prior_fixtures=team_prior_fx,
        opponent_prior_fixtures=opp_prior_fx,
        league_baselines=league_baselines,
    )
