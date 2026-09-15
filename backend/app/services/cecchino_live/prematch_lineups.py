"""Formazioni ufficiali e assenti prima del calcio d'inizio, per le partite di Cecchino Today.

Sostituisce il vecchio job pre-match del motore SOT (solo Serie A, formazioni da SportAPI): qui
tutte le partite eleggibili di Cecchino Today, fonte unica API-Football.

Ogni esecuzione (cron ogni 10 minuti):
1. partite eleggibili che iniziano entro LOOKAHEAD e non hanno ancora la formazione ufficiale di
   entrambe le squadre;
2. fixtures?ids a blocchi da 20: una chiamata porta le formazioni di tutte le partite del blocco
   (API-Football le pubblica di solito 20-40 minuti prima del calcio d'inizio);
3. injuries?ids a blocchi da 20: assenti (infortuni, squalifiche, in dubbio), una volta ogni
   INJURIES_REFRESH per partita.

Dati salvati nelle tabelle gia' esistenti: fixture_lineups + fixture_lineup_players (formazioni) e
fixture_missing_players con provider "api_football" (assenti). Nessun dato esistente viene cancellato.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Fixture, Season, Team
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.models.fixture_lineup import FixtureLineup
from app.models.fixture_missing_player import FixtureMissingPlayer
from app.services.api_football_client import ApiFootballClient
from app.services.cecchino_live.data_connector import BATCH_SIZE, Budget
from app.services.lineups.lineup_persist import upsert_lineup_from_api_block

logger = logging.getLogger(__name__)

PROVIDER = "api_football"
LOOKAHEAD = timedelta(minutes=75)
FORCE_LOOKAHEAD = timedelta(hours=24)
GRACE_AFTER_KICKOFF = timedelta(minutes=5)
INJURIES_REFRESH = timedelta(hours=3)
ELIGIBLE = "eligible"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def target_fixtures(db: Session, now: datetime, lookahead: timedelta = LOOKAHEAD) -> list[Fixture]:
    """Partite eleggibili di Today nella finestra, senza formazione ufficiale di entrambe le squadre."""
    local_ids = db.scalars(
        select(CecchinoTodayFixture.local_fixture_id).where(
            CecchinoTodayFixture.eligibility_status == ELIGIBLE,
            CecchinoTodayFixture.local_fixture_id.is_not(None),
            CecchinoTodayFixture.kickoff >= now - GRACE_AFTER_KICKOFF,
            CecchinoTodayFixture.kickoff <= now + lookahead,
        )
    ).all()
    ids = sorted({int(i) for i in local_ids})
    if not ids:
        return []
    complete = set(
        db.scalars(
            select(FixtureLineup.fixture_id)
            .where(FixtureLineup.fixture_id.in_(ids), FixtureLineup.is_official.is_(True))
            .group_by(FixtureLineup.fixture_id)
            .having(func.count(FixtureLineup.id) >= 2)
        ).all()
    )
    fixtures = db.scalars(select(Fixture).where(Fixture.id.in_(ids))).all()
    return [f for f in fixtures if int(f.id) not in complete and f.status not in FINISHED_STATUSES]


def _injuries_recent(db: Session, fixture_ids: list[int], now: datetime) -> set[int]:
    if not fixture_ids:
        return set()
    return set(
        db.scalars(
            select(FixtureMissingPlayer.fixture_id).where(
                FixtureMissingPlayer.fixture_id.in_(fixture_ids),
                FixtureMissingPlayer.provider_name == PROVIDER,
                FixtureMissingPlayer.updated_at >= now - INJURIES_REFRESH,
            )
        ).all()
    )


def store_lineups(db: Session, fixture: Fixture, blocks: list[dict[str, Any]], now: datetime) -> int:
    season_row = db.get(Season, int(fixture.season_id))
    if season_row is None:
        return 0
    stored = 0
    for block in blocks or []:
        team_api = (block.get("team") or {}).get("id") if isinstance(block, dict) else None
        if team_api is None:
            continue
        team = db.scalar(select(Team).where(Team.api_team_id == int(team_api)))
        if team is None:
            continue
        row, _players = upsert_lineup_from_api_block(
            db, fixture=fixture, season_row=season_row, team=team, block=block, fetched_at=now
        )
        if row is not None:
            if getattr(row, "competition_id", None) is None and fixture.competition_id is not None:
                row.competition_id = fixture.competition_id
            stored += 1
    return stored


def store_injuries(db: Session, fixture: Fixture, items: list[dict[str, Any]]) -> int:
    home = db.get(Team, int(fixture.home_team_id))
    away = db.get(Team, int(fixture.away_team_id))
    sides = {}
    if home is not None:
        sides[int(home.api_team_id)] = "home"
    if away is not None:
        sides[int(away.api_team_id)] = "away"
    stored = 0
    seen: dict[tuple[int, str], Any] = {}
    for item in items:
        player = item.get("player") or {}
        team = item.get("team") or {}
        if player.get("id") is None or team.get("id") is None:
            continue
        side = sides.get(int(team["id"]))
        if side is None:
            continue
        key = (int(player["id"]), side)
        if key in seen:
            # API-Football a volte ripete lo stesso giocatore: un solo record per giocatore e lato
            continue
        row = db.scalar(
            select(FixtureMissingPlayer).where(
                FixtureMissingPlayer.fixture_id == int(fixture.id),
                FixtureMissingPlayer.provider_name == PROVIDER,
                FixtureMissingPlayer.provider_player_id == int(player["id"]),
                FixtureMissingPlayer.team_side == side,
            )
        )
        if row is None:
            row = FixtureMissingPlayer(
                fixture_id=int(fixture.id),
                provider_name=PROVIDER,
                provider_player_id=int(player["id"]),
                team_side=side,
                player_name=str(player.get("name") or "")[:255],
            )
            db.add(row)
        row.provider_team_id = int(team["id"])
        row.player_name = str(player.get("name") or row.player_name)[:255]
        row.reason = (str(player.get("reason"))[:64] if player.get("reason") else None)
        row.external_type = (str(player.get("type"))[:64] if player.get("type") else None)
        row.raw_payload = item
        row.updated_at = _now()
        if getattr(row, "competition_id", None) is None and fixture.competition_id is not None:
            row.competition_id = fixture.competition_id
        seen[key] = row
        stored += 1
    return stored


def run_prematch_lineups(
    db: Session,
    *,
    client: ApiFootballClient | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """force=True: tutte le partite eleggibili delle prossime 24 ore e assenti riletti comunque."""
    now = now or _now()
    fixtures = target_fixtures(db, now, FORCE_LOOKAHEAD if force else LOOKAHEAD)
    out: dict[str, Any] = {
        "force": force,
        "fixtures_in_window": len(fixtures),
        "calls": 0,
        "lineups_stored": 0,
        "injuries_stored": 0,
    }
    if not fixtures:
        return out
    client = client or ApiFootballClient()
    budget = Budget(client)
    budget.refresh()
    by_api = {int(f.api_fixture_id): f for f in fixtures}
    api_ids = list(by_api)

    with_lineups = 0
    for start in range(0, len(api_ids), BATCH_SIZE):
        if not budget.can_spend():
            out["stopped_budget"] = True
            break
        chunk = api_ids[start : start + BATCH_SIZE]
        items = client.get("fixtures", {"ids": "-".join(str(i) for i in chunk)}).get("response") or []
        out["calls"] += 1
        budget.spent(1)
        for item in items:
            fx = by_api.get(int(((item.get("fixture") or {}).get("id")) or 0))
            if fx is None:
                continue
            n = store_lineups(db, fx, item.get("lineups") or [], now)
            out["lineups_stored"] += n
            with_lineups += 1 if n >= 2 else 0
        db.commit()

    recent = set() if force else _injuries_recent(db, [int(f.id) for f in fixtures], now)
    injury_ids = [aid for aid, f in by_api.items() if int(f.id) not in recent]
    for start in range(0, len(injury_ids), BATCH_SIZE):
        if not budget.can_spend():
            out["stopped_budget"] = True
            break
        chunk = injury_ids[start : start + BATCH_SIZE]
        body = client.get("injuries", {"ids": "-".join(str(i) for i in chunk)})
        out["calls"] += 1
        budget.spent(1)
        items, _errors = ApiFootballClient.injuries_response_items(body)
        per_fixture: dict[int, list[dict[str, Any]]] = {}
        for item in items:
            api_id = int(((item.get("fixture") or {}).get("id")) or 0)
            per_fixture.setdefault(api_id, []).append(item)
        for api_id, rows in per_fixture.items():
            fx = by_api.get(api_id)
            if fx is not None:
                out["injuries_stored"] += store_injuries(db, fx, rows)
        db.commit()
    out["fixtures_with_both_lineups"] = with_lineups
    return out
