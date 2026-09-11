"""Helper condivisi per il recupero storico fixture.

Estratti dallo stack predizioni SOT (v1.0/v1.1) perche' riusati anche da
Cecchino (cecchino_fixture_history.py, cecchino_current_season_xg.py,
next_round_selection.py, prediction_readiness.py). Nessuna logica di
modello SOT qui dentro: solo query/filtri generici su Fixture.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture, FixtureTeamStat, League, Season
from app.services.datetime_utils import ensure_datetime_utc, fixture_key_before_safe

logger = logging.getLogger(__name__)


def resolve_fixture_season_id(db: Session, fixture: Fixture) -> int:
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


def prior_fixtures_for_team(
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


def team_stats_map(db: Session, fixture_ids: list[int]) -> dict[tuple[int, int], FixtureTeamStat]:
    if not fixture_ids:
        return {}
    rows = db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(fixture_ids))).all()
    return {(int(r.fixture_id), int(r.team_id)): r for r in rows}


def last_n(fixtures: list[Fixture], n: int) -> list[Fixture]:
    xs = sorted(fixtures, key=lambda f: (f.kickoff_at, f.id), reverse=True)[:n]
    return sorted(xs, key=lambda f: (f.kickoff_at, f.id))


def team_split_fixtures(
    fixtures: list[Fixture],
    team_id: int,
    *,
    is_home_context: bool,
) -> list[Fixture]:
    tid = int(team_id)
    if is_home_context:
        return [f for f in fixtures if int(f.home_team_id) == tid]
    return [f for f in fixtures if int(f.away_team_id) == tid]


def fixture_round_display(fx: Fixture) -> str | None:
    if fx.round and str(fx.round).strip():
        return str(fx.round).strip()[:64]
    raw = fx.raw_json if isinstance(fx.raw_json, dict) else None
    if not raw:
        return None
    fr = (raw.get("fixture") or {}).get("round")
    if fr is not None and str(fr).strip():
        return str(fr).strip()[:64]
    lr = (raw.get("league") or {}).get("round")
    if lr is not None and str(lr).strip():
        return str(lr).strip()[:64]
    return None
