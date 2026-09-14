"""Statistiche extra pre-partita in live (tiri, tiri in porta, corner, falli, cartellini, arbitro).

Stesso registro della RUN V2 (`ExtraStatsRegistry`), alimentato dalle partite gia' giocate
della stessa competizione e stagione con le statistiche squadra salvate (fixture_team_stats).
Le classi (quintili) usano le soglie della stagione di scoperta 2021/22, come nelle verifiche
dei pattern: stessa scala dello storico.

Limite dichiarato: le statistiche squadra sono presenti solo per le competizioni e le partite
per cui API-Football le fornisce e sono state scaricate. Dove mancano, la colonna resta vuota
e i pattern che la usano non si possono valutare.
"""

from __future__ import annotations

from functools import lru_cache
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture
from app.models.fixture_team_stat import FixtureTeamStat
from app.services.cecchino_data_lab.run_v2.extra_stats import ExtraStatsRegistry
from app.services.cecchino_data_lab.run_v2_grid_dataset import load_season_binners
from app.services.cecchino_data_lab.run_v2_grid_vocabulary import CONTINUOUS_FEATURE_COLUMNS, QuantileBinner

_STAT_COLUMNS = {
    "shots": "total_shots",
    "shots_on_target": "shots_on_target",
    "corners": "corner_kicks",
    "fouls": "fouls",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
}


def _stat(row: FixtureTeamStat | None, name: str) -> float | None:
    if row is None:
        return None
    value = getattr(row, _STAT_COLUMNS[name], None)
    if value is None and name == "shots":
        value = row.shots
    return float(value) if value is not None else None


def _proxy_match(f: Fixture, stats: dict[int, FixtureTeamStat]) -> SimpleNamespace:
    home, away = stats.get(int(f.home_team_id)), stats.get(int(f.away_team_id))
    return SimpleNamespace(
        id=int(f.id),
        home_team=str(f.home_team_id),
        away_team=str(f.away_team_id),
        referee=f.referee,
        home_shots=_stat(home, "shots"),
        away_shots=_stat(away, "shots"),
        home_shots_on_target=_stat(home, "shots_on_target"),
        away_shots_on_target=_stat(away, "shots_on_target"),
        home_corners=_stat(home, "corners"),
        away_corners=_stat(away, "corners"),
        home_fouls=_stat(home, "fouls"),
        away_fouls=_stat(away, "fouls"),
        home_yellow_cards=_stat(home, "yellow_cards"),
        away_yellow_cards=_stat(away, "yellow_cards"),
        home_red_cards=_stat(home, "red_cards"),
        away_red_cards=_stat(away, "red_cards"),
    )


def live_extra_features(db: Session, target: Fixture) -> dict[str, Any]:
    prior = db.scalars(
        select(Fixture)
        .where(
            Fixture.competition_id == target.competition_id,
            Fixture.season_id == target.season_id,
            Fixture.status.in_(FINISHED_STATUSES),
            Fixture.kickoff_at < target.kickoff_at,
        )
        .order_by(Fixture.kickoff_at, Fixture.id)
    ).all()
    ids = [int(f.id) for f in prior]
    stats_rows = (
        db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id.in_(ids))).all() if ids else []
    )
    by_fixture: dict[int, dict[int, FixtureTeamStat]] = {}
    for s in stats_rows:
        by_fixture.setdefault(int(s.fixture_id), {})[int(s.team_id)] = s
    registry = ExtraStatsRegistry()
    with_stats = 0
    for f in prior:
        stats = by_fixture.get(int(f.id)) or {}
        if len(stats) == 2:
            with_stats += 1
            registry.ingest_match(_proxy_match(f, stats), competition="live", season_label="live")
    features = registry.build_prematch_features(
        competition="live",
        season_label="live",
        home_team=str(target.home_team_id),
        away_team=str(target.away_team_id),
        referee=target.referee,
        target_kickoff=target.kickoff_at,
    )
    features["prior_matches"] = len(prior)
    features["prior_matches_with_stats"] = with_stats
    return features


@lru_cache(maxsize=4)
def _binners(run_id: int) -> dict[str, QuantileBinner]:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        return load_season_binners(db, run_id=run_id)
    finally:
        db.close()


def delta_classes(features: dict[str, Any], *, discovery_run_id: int) -> dict[str, str | None]:
    """Colonne *_delta_class e referee_cards_avg_class come nella ricerca pattern."""
    binners = _binners(int(discovery_run_id))
    raw: dict[str, float | None] = {}
    for side in ("home", "away"):
        stats = ((features.get("teams") or {}).get(side) or {}).get("stats") or {}
        for stat in ("shots", "sot", "corners", "fouls", "yellow_cards", "red_cards"):
            raw[f"{side}_{stat}_delta_class"] = (stats.get(stat) or {}).get("competition_delta_for")
    referee = features.get("referee") or {}
    raw["referee_cards_avg_class"] = referee.get("previous_cards_avg") if referee.get("available") else None
    out: dict[str, str | None] = {}
    for col in CONTINUOUS_FEATURE_COLUMNS:
        value, binner = raw.get(col), binners.get(col)
        out[col] = binner.label_for(float(value)) if (binner is not None and value is not None) else None
    return out
