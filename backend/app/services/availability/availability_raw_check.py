"""Debug raw API-Football injuries vs DB per fixture."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Fixture, PlayerAvailability, PlayerRegistry, PlayerSeasonProfile, Season, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.availability.availability_league import resolve_serie_a_league_context
from app.services.availability.availability_parsing import parse_injuries_item
from app.services.ingestion_service import IngestionService


def _serialize_db_record(row: PlayerAvailability) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "player_name": row.player_name,
        "api_player_id": row.api_player_id,
        "api_team_id": row.api_team_id,
        "api_fixture_id": row.api_fixture_id,
        "fixture_id": row.fixture_id,
        "availability_status": row.availability_status,
        "availability_type": row.availability_type,
        "reason": row.reason,
        "source": row.source,
        "is_active": row.is_active,
        "start_date": row.start_date.isoformat() if row.start_date else None,
        "end_date": row.end_date.isoformat() if row.end_date else None,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
    }


def _compact_player(item: dict[str, Any]) -> dict[str, Any]:
    pl = item.get("player") if isinstance(item.get("player"), dict) else {}
    tm = item.get("team") if isinstance(item.get("team"), dict) else {}
    fx = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
    parsed = parse_injuries_item(item)
    raw_type = pl.get("type") or item.get("type")
    raw_reason = pl.get("reason") or item.get("reason")
    return {
        "name": pl.get("name"),
        "api_player_id": pl.get("id"),
        "api_team_id": tm.get("id"),
        "team_name": tm.get("name"),
        "api_fixture_id": fx.get("id"),
        "type": raw_type,
        "reason": raw_reason,
        "parsed_status": parsed.availability_status if parsed else None,
        "parsed_type": parsed.availability_type if parsed else None,
    }


def _fetch_injuries_block(
    api: ApiFootballClient,
    *,
    label: str,
    request: str,
    fetcher,
) -> dict[str, Any]:
    try:
        body = fetcher()
        if isinstance(body, dict) and "response" in body:
            items, errs = ApiFootballClient.injuries_response_items(body)
        else:
            items = list(body) if isinstance(body, list) else []
            errs = []
        players = [_compact_player(x) for x in items if isinstance(x, dict)]
        return {
            "request": request,
            "results": len(players),
            "errors": errs,
            "players": players,
        }
    except ApiFootballError as exc:
        return {
            "request": request,
            "results": 0,
            "errors": [str(exc)[:500]],
            "players": [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "request": request,
            "results": 0,
            "errors": [f"{exc.__class__.__name__}: {exc!s}"[:500]],
            "players": [],
        }


def _name_matches(name: str | None, query: str) -> bool:
    if not name or not query:
        return False
    return query.lower() in str(name).lower()


def _search_in_players(players: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    return [p for p in players if _name_matches(str(p.get("name") or ""), query)]


def _decimal_float(v: Decimal | float | int | None) -> float | None:
    if v is None:
        return None
    return float(v)


def _serialize_profile_match(prof: PlayerSeasonProfile) -> tuple[dict[str, Any], str | None]:
    """Ritorna (entry possible_matches, warning opzionale se registry assente)."""
    reg = prof.registry
    warning = None
    player_name = reg.name if reg is not None else None
    if reg is None:
        warning = f"Profilo api_player_id={prof.api_player_id} senza player_registry collegato"
    return (
        {
            "source": "player_season_profiles",
            "player_name": player_name,
            "api_player_id": prof.api_player_id,
            "team_id": prof.team_id,
            "api_team_id": prof.api_team_id,
            "shooting_impact_score": _decimal_float(prof.shooting_impact_score),
            "shots_on_per90": _decimal_float(prof.shots_on_per90),
            "team_sot_share": _decimal_float(prof.team_sot_share),
        },
        warning,
    )


def _build_player_search(
    db: Session,
    *,
    query: str,
    api_checks: dict[str, Any],
    season_year: int,
    league_id: int,
    api_home_team_id: int,
    api_away_team_id: int,
    db_fixture: list[dict[str, Any]],
    db_teams: list[dict[str, Any]],
) -> dict[str, Any]:
    q = query.strip()
    by_fixture = _search_in_players(api_checks.get("by_fixture", {}).get("players") or [], q)
    home = _search_in_players(api_checks.get("home_team", {}).get("players") or [], q)
    away = _search_in_players(api_checks.get("away_team", {}).get("players") or [], q)
    league = _search_in_players(api_checks.get("league_season", {}).get("players") or [], q)

    registry_rows = db.scalars(
        select(PlayerRegistry).where(PlayerRegistry.name.ilike(f"%{q}%")),
    ).all()
    db_avail = [
        r
        for r in (db_fixture + db_teams)
        if _name_matches(r.get("player_name"), q)
    ]
    profiles = db.scalars(
        select(PlayerSeasonProfile)
        .join(PlayerRegistry, PlayerRegistry.id == PlayerSeasonProfile.player_id)
        .where(
            PlayerSeasonProfile.season == int(season_year),
            PlayerSeasonProfile.league_id == int(league_id),
            PlayerSeasonProfile.api_team_id.in_([api_home_team_id, api_away_team_id]),
            PlayerRegistry.name.ilike(f"%{q}%"),
        )
        .options(joinedload(PlayerSeasonProfile.registry)),
    ).all()

    possible: list[dict[str, Any]] = []
    profile_warnings: list[str] = []
    for p in by_fixture + home + away + league:
        possible.append({"source": "api", **p})
    for reg in registry_rows:
        possible.append(
            {
                "source": "player_registry",
                "player_name": reg.name,
                "api_player_id": reg.api_player_id,
            },
        )
    for row in db_avail:
        possible.append({"source": "player_availability", **row})
    for prof in profiles:
        entry, warn = _serialize_profile_match(prof)
        possible.append(entry)
        if warn:
            profile_warnings.append(warn)

    return {
        "query": q,
        "found_in_api_by_fixture": len(by_fixture) > 0,
        "found_in_api_home_team": len(home) > 0,
        "found_in_api_away_team": len(away) > 0,
        "found_in_api_league_season": len(league) > 0,
        "found_in_db_availability": len(db_avail) > 0,
        "found_in_player_registry": len(registry_rows) > 0,
        "found_in_player_season_profiles": len(profiles) > 0,
        "profile_warnings": profile_warnings,
        "possible_matches": possible[:50],
    }


def _build_diagnosis(
    *,
    coverage: dict[str, Any],
    api_checks: dict[str, Any],
    db_fixture: list[dict[str, Any]],
    db_teams: list[dict[str, Any]],
    player_search: dict[str, Any] | None,
) -> list[str]:
    diag: list[str] = []
    inj_cov = coverage.get("injuries")
    if inj_cov is False:
        diag.append("coverage.injuries=false: API-Football dichiara injuries non coperti per questa stagione.")
    elif inj_cov is True:
        total_api = sum(int(api_checks.get(k, {}).get("results") or 0) for k in api_checks)
        if total_api == 0:
            diag.append(
                "coverage.injuries=true ma nessun record restituito per questi parametri (risposta vuota).",
            )

    bf = int(api_checks.get("by_fixture", {}).get("results") or 0)
    ht = int(api_checks.get("home_team", {}).get("results") or 0)
    at = int(api_checks.get("away_team", {}).get("results") or 0)
    if bf == 0 and (ht > 0 or at > 0):
        diag.append(
            "by_fixture=0 ma home/away team>0: usare ingest multi-source (team-level), non solo filtro fixture.",
        )
    if ht + at > 0 and not db_teams and not db_fixture:
        diag.append("Dati in API team-level ma assenti in DB: rieseguire POST availability ingest.")

    if db_teams and not db_fixture:
        diag.append(
            f"Record team-level in DB ({len(db_teams)}) senza match fixture_id: audit deve includerli per squadra.",
        )

    if player_search:
        q = player_search.get("query", "")
        any_api = any(
            player_search.get(k)
            for k in (
                "found_in_api_by_fixture",
                "found_in_api_home_team",
                "found_in_api_away_team",
                "found_in_api_league_season",
            )
        )
        if not any_api and not player_search.get("found_in_db_availability"):
            diag.append(
                f"{q} non trovato nella risposta API-Football injuries per questi parametri. "
                "Possibile mancanza della fonte.",
            )
        elif any_api and not player_search.get("found_in_db_availability"):
            diag.append(
                f"{q} presente in API ma assente in player_availability: rieseguire ingest o verificare filtro scope.",
            )

    return diag


def build_availability_raw_check(
    db: Session,
    season_year: int,
    fixture_id: int,
    *,
    player_search: str | None = None,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    ing = IngestionService()
    season_row = ing._serie_a_season_row(db, int(season_year))
    ctx = resolve_serie_a_league_context(db, int(season_year))
    league_internal_id = ctx.league_internal_id
    api_league_id = ctx.api_league_id

    fx = db.scalar(
        select(Fixture)
        .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team))
        .where(
            Fixture.id == int(fixture_id),
            Fixture.season_id == int(season_row.id),
        ),
    )
    if fx is None:
        raise ValueError(f"Fixture {fixture_id} non trovata per stagione {season_year}")

    home = fx.home_team
    away = fx.away_team
    if home is None or away is None:
        raise ValueError("Squadre fixture non risolte")

    api_home = int(home.api_team_id)
    api_away = int(away.api_team_id)
    api_fx = int(fx.api_fixture_id)

    api = client or ApiFootballClient()

    try:
        coverage = api.get_league_season_coverage(api_league_id, int(season_year))
    except Exception as exc:  # noqa: BLE001
        coverage = {"_fetch_error": str(exc)[:300]}

    api_checks = {
        "by_fixture": _fetch_injuries_block(
            api,
            label="by_fixture",
            request=f"injuries?fixture={api_fx}",
            fetcher=lambda: api.get("injuries", {"fixture": api_fx}),
        ),
        "home_team": _fetch_injuries_block(
            api,
            label="home_team",
            request=f"injuries?league={api_league_id}&season={season_year}&team={api_home}",
            fetcher=lambda: api.get("injuries", {"league": api_league_id, "season": season_year, "team": api_home}),
        ),
        "away_team": _fetch_injuries_block(
            api,
            label="away_team",
            request=f"injuries?league={api_league_id}&season={season_year}&team={api_away}",
            fetcher=lambda: api.get("injuries", {"league": api_league_id, "season": season_year, "team": api_away}),
        ),
        "league_season": _fetch_injuries_block(
            api,
            label="league_season",
            request=f"injuries?league={api_league_id}&season={season_year}",
            fetcher=lambda: api.get("injuries", {"league": api_league_id, "season": season_year}),
        ),
    }

    db_fixture_rows = list(
        db.scalars(
            select(PlayerAvailability).where(
                PlayerAvailability.season == int(season_year),
                PlayerAvailability.league_id == league_internal_id,
                PlayerAvailability.is_active.is_(True),
                or_(
                    PlayerAvailability.fixture_id == int(fx.id),
                    PlayerAvailability.api_fixture_id == api_fx,
                ),
            ),
        ).all(),
    )
    db_team_rows = list(
        db.scalars(
            select(PlayerAvailability).where(
                PlayerAvailability.season == int(season_year),
                PlayerAvailability.league_id == league_internal_id,
                PlayerAvailability.is_active.is_(True),
                PlayerAvailability.api_team_id.in_([api_home, api_away]),
            ),
        ).all(),
    )
    db_fixture = [_serialize_db_record(r) for r in db_fixture_rows]
    db_teams = [_serialize_db_record(r) for r in db_team_rows if r not in db_fixture_rows]

    player_search_block = None
    if player_search and player_search.strip():
        player_search_block = _build_player_search(
            db,
            query=player_search.strip(),
            api_checks=api_checks,
            season_year=int(season_year),
            league_id=league_internal_id,
            api_home_team_id=api_home,
            api_away_team_id=api_away,
            db_fixture=db_fixture,
            db_teams=db_teams,
        )

    diagnosis = _build_diagnosis(
        coverage=coverage,
        api_checks=api_checks,
        db_fixture=db_fixture,
        db_teams=db_teams,
        player_search=player_search_block,
    )
    if player_search_block:
        diagnosis = diagnosis + list(player_search_block.get("profile_warnings") or [])

    ko = fx.kickoff_at
    return {
        "status": "success",
        "season": int(season_year),
        "league_internal_id": league_internal_id,
        "api_league_id": api_league_id,
        "fixture": {
            "fixture_id": int(fx.id),
            "api_fixture_id": api_fx,
            "home_team": home.name,
            "api_home_team_id": api_home,
            "away_team": away.name,
            "api_away_team_id": api_away,
            "kickoff_at": ko.isoformat() if isinstance(ko, datetime) else str(ko),
            "status": fx.status,
        },
        "coverage": {
            "injuries": coverage.get("injuries"),
            "lineups": coverage.get("lineups"),
            "players": coverage.get("players"),
            "fixtures_statistics": coverage.get("fixtures", {}).get("statistics")
            if isinstance(coverage.get("fixtures"), dict)
            else coverage.get("fixtures.statistics"),
            "raw": coverage,
        },
        "api_checks": api_checks,
        "db_records_for_fixture": db_fixture,
        "db_records_for_teams": db_teams,
        "player_search": player_search_block,
        "diagnosis": diagnosis,
    }
