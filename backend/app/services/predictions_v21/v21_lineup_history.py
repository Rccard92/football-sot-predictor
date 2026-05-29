"""Storico formazioni SportAPI per derivazioni lineup v2.1."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture
from app.models.fixture_provider_lineup import FixtureProviderLineup
from app.models.fixture_provider_lineup_player import FixtureProviderLineupPlayer
from app.services.predictions_v21.v21_constants import LINEUP_HISTORY_MATCHES, LINEUP_HISTORY_MIN_FIXTURES

PROVIDER_SPORTAPI = "sportapi"


def _normalize_formation(formation: str | None) -> str | None:
    if not formation:
        return None
    cleaned = str(formation).strip().replace(" ", "")
    return cleaned or None


def _team_side_for_fixture(fixture: Fixture, team_id: int) -> str | None:
    if int(fixture.home_team_id) == int(team_id):
        return "home"
    if int(fixture.away_team_id) == int(team_id):
        return "away"
    return None


def build_lineup_history(
    db: Session,
    *,
    team_id: int,
    prior_fixtures: list[Fixture],
    limit: int = LINEUP_HISTORY_MATCHES,
) -> dict[str, Any]:
    """Aggregati storici lineups SportAPI per una squadra (fixture prior alla partita corrente)."""
    fx_list = prior_fixtures[-limit:] if len(prior_fixtures) > limit else list(prior_fixtures)
    fixture_ids = [int(f.id) for f in fx_list]
    empty: dict[str, Any] = {
        "fixture_count": 0,
        "lineup_fixture_count": 0,
        "dominant_formation": None,
        "starter_frequency_by_api_id": {},
        "typical_starter_api_ids": set(),
    }
    if not fixture_ids:
        return empty

    lineups = {
        int(row.fixture_id): row
        for row in db.scalars(
            select(FixtureProviderLineup).where(
                FixtureProviderLineup.fixture_id.in_(fixture_ids),
                FixtureProviderLineup.provider_name == PROVIDER_SPORTAPI,
            ),
        ).all()
    }
    players = db.scalars(
        select(FixtureProviderLineupPlayer).where(
            FixtureProviderLineupPlayer.fixture_id.in_(fixture_ids),
            FixtureProviderLineupPlayer.provider_name == PROVIDER_SPORTAPI,
            FixtureProviderLineupPlayer.is_substitute.is_(False),
        ),
    ).all()

    formation_counts: Counter[str] = Counter()
    starter_counts: Counter[int] = Counter()
    lineup_fixture_count = 0

    for fx in fx_list:
        side = _team_side_for_fixture(fx, team_id)
        if side is None:
            continue
        lu = lineups.get(int(fx.id))
        if lu is None:
            continue
        formation = lu.home_formation if side == "home" else lu.away_formation
        norm_form = _normalize_formation(formation)
        if norm_form:
            formation_counts[norm_form] += 1
            lineup_fixture_count += 1

        for p in players:
            if int(p.fixture_id) != int(fx.id) or p.team_side != side:
                continue
            starter_counts[int(p.provider_player_id)] += 1

    dominant = formation_counts.most_common(1)[0][0] if formation_counts else None
    freq: dict[int, float] = {}
    if lineup_fixture_count > 0:
        for api_id, cnt in starter_counts.items():
            freq[api_id] = round(float(cnt) / float(lineup_fixture_count), 4)

    typical = {api_id for api_id, f in freq.items() if f >= 0.5}
    if not typical and freq:
        sorted_ids = sorted(freq.keys(), key=lambda k: freq[k], reverse=True)
        typical = set(sorted_ids[:8])

    return {
        "fixture_count": len(fx_list),
        "lineup_fixture_count": lineup_fixture_count,
        "dominant_formation": dominant,
        "starter_frequency_by_api_id": freq,
        "typical_starter_api_ids": typical,
    }


def lineup_history_sufficient(history: dict[str, Any], *, min_fixtures: int = LINEUP_HISTORY_MIN_FIXTURES) -> bool:
    return int(history.get("lineup_fixture_count") or 0) >= min_fixtures
