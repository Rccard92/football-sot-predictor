"""Indici in-memoria per audit Intensità Goal v5 — Fase 1A.3 (preload batch)."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.models.fixture_team_stat import FixtureTeamStat
from app.models.team import Team
from app.services.cecchino.cecchino_current_season_xg import _fixture_pair_xg
from app.services.datetime_utils import ensure_datetime_utc, fixture_key_before_safe

logger = logging.getLogger(__name__)


@dataclass
class XgEvent:
    kickoff: datetime
    fixture_id: int
    api_fixture_id: int | None
    xg_for: float
    xg_against: float


@dataclass
class AuditIndexes:
    """Indici pre-caricati: nessun DB nel loop target."""

    fixtures_by_comp_team: dict[tuple[int | None, int], list[Fixture]] = field(default_factory=dict)
    today_by_local_fixture_id: dict[int, list[CecchinoTodayFixture]] = field(default_factory=dict)
    today_by_provider_fixture_id: dict[int, list[CecchinoTodayFixture]] = field(default_factory=dict)
    team_name_by_id: dict[int, str] = field(default_factory=dict)
    country_by_competition_id: dict[int, str] = field(default_factory=dict)
    xg_by_comp_team: dict[tuple[int | None, int], list[XgEvent]] = field(default_factory=dict)
    timings_ms: dict[str, float] = field(default_factory=dict)

    @property
    def history_index_teams(self) -> int:
        return len({tid for (_, tid) in self.fixtures_by_comp_team})

    @property
    def today_index_local_keys(self) -> int:
        return len(self.today_by_local_fixture_id)

    @property
    def today_index_provider_keys(self) -> int:
        return len(self.today_by_provider_fixture_id)

    @property
    def xg_index_teams(self) -> int:
        return len({tid for (_, tid) in self.xg_by_comp_team})


def _fixture_sort_key(fx: Fixture) -> tuple[datetime, int]:
    ko = ensure_datetime_utc(fx.kickoff_at, field_name="fx.kickoff") or datetime.min.replace(
        tzinfo=timezone.utc
    )
    return (ko, int(fx.id))


def build_today_indexes(
    today_rows: list[CecchinoTodayFixture],
) -> tuple[dict[int, list[CecchinoTodayFixture]], dict[int, list[CecchinoTodayFixture]]]:
    by_local: dict[int, list[CecchinoTodayFixture]] = defaultdict(list)
    by_provider: dict[int, list[CecchinoTodayFixture]] = defaultdict(list)
    for row in today_rows:
        lid = getattr(row, "local_fixture_id", None)
        if lid is not None:
            by_local[int(lid)].append(row)
        pfid = getattr(row, "provider_fixture_id", None)
        if pfid is not None:
            by_provider[int(pfid)].append(row)
    return dict(by_local), dict(by_provider)


def _series_for_team(
    index: dict[tuple[int | None, int], list[Fixture]],
    *,
    competition_id: int | None,
    team_id: int,
) -> list[Fixture]:
    key = (competition_id, int(team_id))
    series = list(index.get(key) or [])
    if competition_id is not None:
        return series
    merged: dict[int, Fixture] = {}
    for (_comp, tid), lst in index.items():
        if tid == int(team_id):
            for fx in lst:
                merged[int(fx.id)] = fx
    return sorted(merged.values(), key=_fixture_sort_key)


def priors_for_team_from_index(
    index: dict[tuple[int | None, int], list[Fixture]],
    *,
    competition_id: int | None,
    team_id: int,
    target_ko: datetime | None,
    target_id: int,
    target_api: int | None,
) -> tuple[list[Fixture], bool, bool, str | None, list[int]]:
    """Prior competition-scoped; esclude target/futuro senza flaggare (attesi nell'indice pieno).

    current/future flags solo se una fixture leaky finisce in `out` (difesa).
    """
    series = _series_for_team(index, competition_id=competition_id, team_id=team_id)
    if target_ko is None:
        return [], False, False, None, []

    max_ko: str | None = None
    source_ids: list[int] = []
    out: list[Fixture] = []

    for fx in series:
        fid = int(fx.id)
        api = int(fx.api_fixture_id) if fx.api_fixture_id is not None else None
        if fid == target_id or (target_api is not None and api == target_api):
            continue
        prior_before = fixture_key_before_safe(
            fx.kickoff_at,
            fid,
            target_ko,
            target_id,
            field_name_a=f"prior_{fid}.kickoff",
            field_name_b="target.kickoff",
        )
        if prior_before is not True:
            continue
        out.append(fx)
        source_ids.append(fid)
        fx_ko = ensure_datetime_utc(fx.kickoff_at, field_name="prior.ko")
        if fx_ko is not None:
            iso = fx_ko.isoformat()
            if max_ko is None or iso > max_ko:
                max_ko = iso

    current_hit = False
    future_hit = False
    for fx in out:
        fid = int(fx.id)
        api = int(fx.api_fixture_id) if fx.api_fixture_id is not None else None
        if fid == target_id or (target_api is not None and api == target_api):
            current_hit = True
            continue
        prior_before = fixture_key_before_safe(
            fx.kickoff_at,
            fid,
            target_ko,
            target_id,
            field_name_a=f"out_{fid}.kickoff",
            field_name_b="target.kickoff",
        )
        if prior_before is not True:
            future_hit = True
    return out, current_hit, future_hit, max_ko, source_ids


def _xg_series_for_team(
    index: dict[tuple[int | None, int], list[XgEvent]],
    *,
    competition_id: int | None,
    team_id: int,
) -> list[XgEvent]:
    key = (competition_id, int(team_id))
    series = list(index.get(key) or [])
    if competition_id is not None:
        return series
    merged: list[XgEvent] = []
    for (_comp, tid), lst in index.items():
        if tid == int(team_id):
            merged.extend(lst)
    return sorted(merged, key=lambda e: (e.kickoff, e.fixture_id))


def xg_avg_from_index(
    index: dict[tuple[int | None, int], list[XgEvent]],
    *,
    competition_id: int | None,
    team_id: int,
    target_ko: datetime | None,
    target_id: int,
    target_api: int | None,
) -> tuple[float | None, float | None]:
    """Media xG pre-kickoff; arrotondamento a 4 decimali come build_current_season_team_xg_profile."""
    if target_ko is None:
        return None, None
    series = _xg_series_for_team(index, competition_id=competition_id, team_id=team_id)
    fors: list[float] = []
    againsts: list[float] = []
    for ev in series:
        if ev.fixture_id == target_id:
            continue
        if target_api is not None and ev.api_fixture_id == target_api:
            continue
        prior_before = fixture_key_before_safe(
            ev.kickoff,
            ev.fixture_id,
            target_ko,
            target_id,
            field_name_a="xg.kickoff",
            field_name_b="target.kickoff",
        )
        if prior_before is not True:
            continue
        fors.append(ev.xg_for)
        againsts.append(ev.xg_against)
    if not fors:
        return None, None
    return round(sum(fors) / len(fors), 4), round(sum(againsts) / len(againsts), 4)


def preload_audit_indexes(
    db: Session,
    targets: list[Fixture],
    today_rows: list[CecchinoTodayFixture],
) -> AuditIndexes:
    idx = AuditIndexes()
    if not targets:
        return idx

    t0 = time.perf_counter()
    by_local, by_provider = build_today_indexes(today_rows)
    idx.today_by_local_fixture_id = by_local
    idx.today_by_provider_fixture_id = by_provider
    idx.timings_ms["today_snapshots_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    team_ids: set[int] = set()
    comp_ids: set[int] = set()
    max_ko: datetime | None = None
    for fx in targets:
        if fx.home_team_id is not None:
            team_ids.add(int(fx.home_team_id))
        if fx.away_team_id is not None:
            team_ids.add(int(fx.away_team_id))
        if fx.competition_id is not None:
            comp_ids.add(int(fx.competition_id))
        ko = ensure_datetime_utc(fx.kickoff_at, field_name="t.ko")
        if ko is not None and (max_ko is None or ko > max_ko):
            max_ko = ko

    # --- historical fixtures (competition-scoped come load_finished quando competition_id presente) ---
    t1 = time.perf_counter()
    hist: list[Fixture] = []
    if team_ids and max_ko is not None:
        clauses = [
            Fixture.status.in_(tuple(FINISHED_STATUSES)),
            Fixture.home_team_id.is_not(None),
            Fixture.away_team_id.is_not(None),
            Fixture.kickoff_at <= max_ko,
            or_(Fixture.home_team_id.in_(list(team_ids)), Fixture.away_team_id.in_(list(team_ids))),
        ]
        if comp_ids:
            clauses.append(Fixture.competition_id.in_(list(comp_ids)))
        hist = list(db.scalars(select(Fixture).where(*clauses)).all())

    by_comp_team: dict[tuple[int | None, int], list[Fixture]] = defaultdict(list)
    hist_ids: list[int] = []
    for fx in hist:
        hist_ids.append(int(fx.id))
        comp = int(fx.competition_id) if fx.competition_id is not None else None
        hid = int(fx.home_team_id)
        aid = int(fx.away_team_id)
        by_comp_team[(comp, hid)].append(fx)
        by_comp_team[(comp, aid)].append(fx)
        team_ids.add(hid)
        team_ids.add(aid)
        if comp is not None:
            comp_ids.add(comp)

    for key in by_comp_team:
        by_comp_team[key].sort(key=_fixture_sort_key)
    idx.fixtures_by_comp_team = dict(by_comp_team)
    idx.timings_ms["historical_fixtures_ms"] = round((time.perf_counter() - t1) * 1000, 2)

    # --- teams + competitions ---
    t2 = time.perf_counter()
    if team_ids:
        for team in db.scalars(select(Team).where(Team.id.in_(list(team_ids)))).all():
            idx.team_name_by_id[int(team.id)] = str(team.name)
    if comp_ids:
        for comp in db.scalars(select(Competition).where(Competition.id.in_(list(comp_ids)))).all():
            if comp.country:
                idx.country_by_competition_id[int(comp.id)] = str(comp.country)
    idx.timings_ms["teams_competitions_ms"] = round((time.perf_counter() - t2) * 1000, 2)

    # --- FixtureTeamStat batch ---
    t3 = time.perf_counter()
    xg_by: dict[tuple[int | None, int], list[XgEvent]] = defaultdict(list)
    if hist_ids:
        stats = list(
            db.scalars(
                select(FixtureTeamStat).where(
                    FixtureTeamStat.fixture_id.in_(hist_ids),
                    FixtureTeamStat.team_id.in_(list(team_ids)),
                )
            ).all()
        )
        stats_map: dict[tuple[int, int], FixtureTeamStat] = {
            (int(st.fixture_id), int(st.team_id)): st for st in stats
        }
        for fx in hist:
            home_xg, away_xg = _fixture_pair_xg(fx, stats_map)
            if home_xg is None or away_xg is None:
                continue
            ko = ensure_datetime_utc(fx.kickoff_at, field_name="xg.ko")
            if ko is None:
                continue
            comp = int(fx.competition_id) if fx.competition_id is not None else None
            api = int(fx.api_fixture_id) if fx.api_fixture_id is not None else None
            fid = int(fx.id)
            hid = int(fx.home_team_id)
            aid = int(fx.away_team_id)
            xg_by[(comp, hid)].append(
                XgEvent(
                    kickoff=ko,
                    fixture_id=fid,
                    api_fixture_id=api,
                    xg_for=float(home_xg),
                    xg_against=float(away_xg),
                )
            )
            xg_by[(comp, aid)].append(
                XgEvent(
                    kickoff=ko,
                    fixture_id=fid,
                    api_fixture_id=api,
                    xg_for=float(away_xg),
                    xg_against=float(home_xg),
                )
            )
        for key in xg_by:
            xg_by[key].sort(key=lambda e: (e.kickoff, e.fixture_id))
    idx.xg_by_comp_team = dict(xg_by)
    idx.timings_ms["fixture_team_stats_ms"] = round((time.perf_counter() - t3) * 1000, 2)

    logger.info(
        "goal_intensity_v5_audit preload teams=%s hist_fixtures=%s today_local=%s xg_teams=%s",
        len(team_ids),
        len(hist),
        len(by_local),
        idx.xg_index_teams,
    )
    return idx
