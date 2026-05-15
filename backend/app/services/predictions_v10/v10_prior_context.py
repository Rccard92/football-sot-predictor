"""
Contesto partite precedenti per resolver v1.0 (anti data-leakage).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, FixtureTeamStat
from app.services.predictions_v10.v10_league_offensive_baselines import compute_league_offensive_baselines
from app.services.sot_feature_math import PriorMatch, fixture_key_before, league_avg_sot_from_prior_fixtures


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


def _prior_fixtures_for_team(
    db: Session,
    *,
    season_id: int,
    cutoff_kickoff: datetime,
    cutoff_fixture_id: int,
    team_id: int,
) -> list[Fixture]:
    q = (
        select(Fixture)
        .where(
            Fixture.season_id == season_id,
            Fixture.status.in_(FINISHED_STATUSES),
            (Fixture.home_team_id == team_id) | (Fixture.away_team_id == team_id),
        )
        .order_by(Fixture.kickoff_at.asc(), Fixture.id.asc())
    )
    xs = db.scalars(q).all()
    return [f for f in xs if fixture_key_before(f.kickoff_at, f.id, cutoff_kickoff, cutoff_fixture_id)]


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
) -> V10PriorContext:
    season_id = int(fixture.season_id)
    cutoff_kickoff = fixture.kickoff_at
    cutoff_fixture_id = int(fixture.id)
    is_home = int(fixture.home_team_id) == int(team_id)

    team_prior_fx = _prior_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(team_id),
    )
    opp_prior_fx = _prior_fixtures_for_team(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
        team_id=int(opponent_id),
    )
    all_ids = list({int(f.id) for f in team_prior_fx + opp_prior_fx})
    stats_map = _team_stats_map(db, all_ids)
    league_baselines = compute_league_offensive_baselines(
        db,
        season_id=season_id,
        cutoff_kickoff=cutoff_kickoff,
        cutoff_fixture_id=cutoff_fixture_id,
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
