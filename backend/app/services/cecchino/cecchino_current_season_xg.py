"""Profilo xG storico campionato corrente — anti-leakage per Expected Goal Engine (Fase 52)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Competition, Fixture, FixtureTeamStat, League, Season, Team
from app.services.api_football_client import ApiFootballClient
from app.services.api_usage_context import ApiUsageContext
from app.services.cecchino.cecchino_fixture_history import load_finished_fixtures_for_team
from app.services.fixture_team_stats_mapping import (
    _parse_float,
    apply_parsed_to_row,
    backfill_shot_columns_from_raw_json_if_null,
    statistics_list_to_fields,
)
from app.services.predictions_v10.v10_prior_context import _team_stats_map

SOURCE_NAME = "current_season_fixture_statistics"
SOURCE_FIELD_XG = "statistics[type=expected_goals].value"
SOURCE_FIELD_FOR = f"{SOURCE_FIELD_XG} averaged as team xG For"
SOURCE_FIELD_AGAINST = "opponent statistics[type=expected_goals].value averaged as team xG Against"
ANTI_LEAKAGE_NOTE = (
    "Calcolato solo su partite precedenti della stagione corrente. "
    "La partita analizzata è esclusa per evitare leakage."
)
MIN_XG_SAMPLE_AVAILABLE = 3


def _is_expected_goals_type(raw_type: Any) -> bool:
    t = " ".join(str(raw_type or "").strip().lower().split())
    if t in ("expected goals", "expected_goals", "xg"):
        return True
    return "expected" in t and "goal" in t


def _expected_goals_from_statistics_list(statistics: list[dict[str, Any]] | None) -> float | None:
    if not statistics:
        return None
    for item in statistics:
        if not isinstance(item, dict):
            continue
        if not _is_expected_goals_type(item.get("type")):
            continue
        val = _parse_float(item.get("value"))
        if val is not None:
            return float(val)
    parsed = statistics_list_to_fields(statistics)
    ev = parsed.get("expected_goals")
    return float(ev) if ev is not None else None


def extract_expected_goals_from_fixture_statistics(
    statistics_payload: Any,
    *,
    fixture: Fixture | None = None,
) -> dict[str, Any]:
    """Estrae xG home/away da payload fixture_statistics API-Football."""
    out: dict[str, Any] = {
        "home": None,
        "away": None,
        "home_team_id": None,
        "away_team_id": None,
    }

    if fixture is not None:
        out["home_team_id"] = int(fixture.home_team_id)
        out["away_team_id"] = int(fixture.away_team_id)

    blocks: list[dict[str, Any]] = []
    if isinstance(statistics_payload, list):
        blocks = [b for b in statistics_payload if isinstance(b, dict)]
    elif isinstance(statistics_payload, dict):
        if isinstance(statistics_payload.get("statistics"), list):
            blocks = [statistics_payload]
        elif isinstance(statistics_payload.get("response"), list):
            blocks = [b for b in statistics_payload["response"] if isinstance(b, dict)]

    if not blocks:
        return out

    team_xg: dict[int, float] = {}
    for block in blocks:
        team_obj = block.get("team") if isinstance(block.get("team"), dict) else {}
        team_api_id = team_obj.get("id")
        stats = block.get("statistics")
        xg = _expected_goals_from_statistics_list(stats if isinstance(stats, list) else None)
        if xg is None or team_api_id is None:
            continue
        try:
            team_xg[int(team_api_id)] = float(xg)
        except (TypeError, ValueError):
            continue

    if fixture is not None:
        home_api = getattr(fixture.home_team, "api_team_id", None) if hasattr(fixture, "home_team") else None
        away_api = getattr(fixture.away_team, "api_team_id", None) if hasattr(fixture, "away_team") else None
        if home_api is not None and int(home_api) in team_xg:
            out["home"] = team_xg[int(home_api)]
        if away_api is not None and int(away_api) in team_xg:
            out["away"] = team_xg[int(away_api)]
        if out["home"] is None or out["away"] is None:
            hid = int(fixture.home_team_id)
            aid = int(fixture.away_team_id)
            home_st_xg = team_xg.get(hid)
            away_st_xg = team_xg.get(aid)
            if home_st_xg is not None:
                out["home"] = home_st_xg
            if away_st_xg is not None:
                out["away"] = away_st_xg
    elif len(team_xg) >= 2:
        vals = list(team_xg.values())[:2]
        ids = list(team_xg.keys())[:2]
        out["home"] = vals[0]
        out["away"] = vals[1]
        out["home_team_id"] = ids[0]
        out["away_team_id"] = ids[1]
    elif len(team_xg) == 1:
        only_id = next(iter(team_xg))
        only_val = team_xg[only_id]
        out["home"] = only_val
        out["home_team_id"] = only_id

    return out


def _xg_from_team_stat(st: FixtureTeamStat | None) -> float | None:
    if st is None:
        return None
    if st.expected_goals is not None:
        try:
            v = float(st.expected_goals)
            if v == v:
                return v
        except (TypeError, ValueError):
            pass
    raw = st.raw_json if isinstance(st.raw_json, dict) else None
    if raw is not None:
        stats = raw.get("statistics")
        if isinstance(stats, list):
            xg = _expected_goals_from_statistics_list(stats)
            if xg is not None:
                return xg
    return None


def _fixture_pair_xg(
    fx: Fixture,
    stats_map: dict[tuple[int, int], FixtureTeamStat],
) -> tuple[float | None, float | None]:
    home_st = stats_map.get((int(fx.id), int(fx.home_team_id)))
    away_st = stats_map.get((int(fx.id), int(fx.away_team_id)))
    home_xg = _xg_from_team_stat(home_st)
    away_xg = _xg_from_team_stat(away_st)
    if home_xg is not None and away_xg is not None:
        return home_xg, away_xg
    extracted = extract_expected_goals_from_fixture_statistics(
        [home_st.raw_json, away_st.raw_json] if home_st and away_st else [],
        fixture=fx,
    )
    return extracted.get("home"), extracted.get("away")


def _resolve_season_league_ids(db: Session, target_fixture: Fixture) -> tuple[int | None, int | None, int | None]:
    season_year: int | None = None
    league_id: int | None = None
    provider_league_id: int | None = None

    if target_fixture.season_id is not None:
        season_row = db.get(Season, int(target_fixture.season_id))
        if season_row is not None:
            season_year = int(season_row.year)
            league_id = int(season_row.league_id)
            league = db.get(League, league_id)
            if league is not None:
                provider_league_id = int(league.api_league_id)

    if target_fixture.competition_id is not None:
        comp = db.get(Competition, int(target_fixture.competition_id))
        if comp is not None:
            season_year = season_year or int(comp.season)
            provider_league_id = provider_league_id or int(comp.provider_league_id)
            league_id = league_id or (int(comp.league_id) if comp.league_id is not None else None)

    return season_year, league_id, provider_league_id


def build_current_season_team_xg_profile(
    db: Session,
    target_fixture: Fixture,
    team_id: int,
    *,
    exclude_provider_fixture_id: int | None = None,
) -> dict[str, Any]:
    """Media xG For/Against su tutte le partite prior del campionato corrente."""
    season_year, league_id, provider_league_id = _resolve_season_league_ids(db, target_fixture)
    prior = load_finished_fixtures_for_team(db, target_fixture, int(team_id))

    warnings: list[str] = []
    excluded_current = False
    target_api_id = int(target_fixture.api_fixture_id)
    target_id = int(target_fixture.id)
    exclude_api = int(exclude_provider_fixture_id) if exclude_provider_fixture_id else None

    filtered: list[Fixture] = []
    for fx in prior:
        if int(fx.id) == target_id:
            excluded_current = True
            continue
        if exclude_api is not None and int(fx.api_fixture_id) == exclude_api:
            excluded_current = True
            continue
        if int(fx.api_fixture_id) == target_api_id:
            excluded_current = True
            continue
        filtered.append(fx)

    if excluded_current and "current_fixture_xg_excluded_to_prevent_leakage" not in warnings:
        warnings.append("current_fixture_xg_excluded_to_prevent_leakage")

    fixture_ids = [int(fx.id) for fx in filtered]
    stats_map = _team_stats_map(db, fixture_ids)

    xg_for_vals: list[float] = []
    xg_against_vals: list[float] = []
    matches_checked = len(filtered)
    matches_with_xg = 0
    matches_missing_xg = 0
    tid = int(team_id)

    for fx in filtered:
        home_xg, away_xg = _fixture_pair_xg(fx, stats_map)
        if home_xg is None or away_xg is None:
            matches_missing_xg += 1
            continue
        is_home = int(fx.home_team_id) == tid
        if is_home:
            xg_for_vals.append(float(home_xg))
            xg_against_vals.append(float(away_xg))
        elif int(fx.away_team_id) == tid:
            xg_for_vals.append(float(away_xg))
            xg_against_vals.append(float(home_xg))
        else:
            continue
        matches_with_xg += 1

    sample_size = matches_with_xg
    xg_for_avg = sum(xg_for_vals) / len(xg_for_vals) if xg_for_vals else None
    xg_against_avg = sum(xg_against_vals) / len(xg_against_vals) if xg_against_vals else None

    cutoff = target_fixture.kickoff_at.isoformat() if target_fixture.kickoff_at else None

    return {
        "xg_for_avg": round(xg_for_avg, 4) if xg_for_avg is not None else None,
        "xg_against_avg": round(xg_against_avg, 4) if xg_against_avg is not None else None,
        "xg_for_total": round(sum(xg_for_vals), 4) if xg_for_vals else None,
        "xg_against_total": round(sum(xg_against_vals), 4) if xg_against_vals else None,
        "sample_size": sample_size,
        "matches_checked": matches_checked,
        "matches_with_xg": matches_with_xg,
        "matches_missing_xg": matches_missing_xg,
        "source": SOURCE_NAME,
        "source_field": SOURCE_FIELD_XG,
        "season": season_year,
        "league_id": league_id,
        "provider_league_id": provider_league_id,
        "warnings": warnings,
        "anti_leakage": {
            "current_fixture_excluded": True,
            "fixture_date_cutoff": cutoff,
            "scope": "current season matches before fixture",
        },
    }


def _prior_fixtures_both_teams(
    db: Session,
    target_fixture: Fixture,
    *,
    exclude_provider_fixture_id: int | None = None,
) -> list[Fixture]:
    """Union deduplicata fixture prior home+away per backfill."""
    hid = int(target_fixture.home_team_id)
    aid = int(target_fixture.away_team_id)
    home_prior = load_finished_fixtures_for_team(db, target_fixture, hid)
    away_prior = load_finished_fixtures_for_team(db, target_fixture, aid)

    target_id = int(target_fixture.id)
    exclude_api = int(exclude_provider_fixture_id) if exclude_provider_fixture_id else None
    target_api_id = int(target_fixture.api_fixture_id)

    seen: set[int] = set()
    out: list[Fixture] = []
    for fx in home_prior + away_prior:
        fid = int(fx.id)
        if fid in seen:
            continue
        if fid == target_id:
            continue
        if int(fx.api_fixture_id) == target_api_id:
            continue
        if exclude_api is not None and int(fx.api_fixture_id) == exclude_api:
            continue
        seen.add(fid)
        out.append(fx)
    out.sort(key=lambda f: (f.kickoff_at, f.id))
    return out


def _fixture_has_xg(db: Session, fx: Fixture) -> bool:
    stats_map = _team_stats_map(db, [int(fx.id)])
    home_xg, away_xg = _fixture_pair_xg(fx, stats_map)
    return home_xg is not None and away_xg is not None


def _persist_fixture_statistics(
    db: Session,
    fx: Fixture,
    stats_payload: list[dict[str, Any]],
) -> int:
    updated = 0
    for block in stats_payload:
        if not isinstance(block, dict):
            continue
        team_api = (block.get("team") or {}).get("id")
        if team_api is None:
            continue
        team = db.scalar(select(Team).where(Team.api_team_id == int(team_api)))
        if team is None:
            continue
        parsed = statistics_list_to_fields(block.get("statistics"))
        side = (
            "home"
            if int(team.id) == int(fx.home_team_id)
            else "away"
            if int(team.id) == int(fx.away_team_id)
            else None
        )
        row = db.scalar(
            select(FixtureTeamStat).where(
                FixtureTeamStat.fixture_id == int(fx.id),
                FixtureTeamStat.team_id == int(team.id),
            ),
        )
        if row is None:
            row = FixtureTeamStat(
                fixture_id=int(fx.id),
                team_id=int(team.id),
                side=side,
                raw_json=block,
                competition_id=fx.competition_id,
            )
            db.add(row)
        else:
            row.side = side
            row.raw_json = block
            if fx.competition_id is not None:
                row.competition_id = int(fx.competition_id)
        apply_parsed_to_row(row, parsed)
        backfill_shot_columns_from_raw_json_if_null(row)
        updated += 1
    return updated


def backfill_current_season_xg_for_today_fixture(
    db: Session,
    today_fixture_id: int,
    *,
    force_refresh: bool = False,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    """Backfill manuale statistiche xG per fixture prior del campionato corrente."""
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"status": "not_found", "message": f"CecchinoTodayFixture {today_fixture_id} not found"}
    if not row.local_fixture_id:
        return {"status": "error", "message": "missing_local_fixture_id"}

    target = db.get(Fixture, int(row.local_fixture_id))
    if target is None:
        return {"status": "error", "message": "local_fixture_not_found"}

    prior = _prior_fixtures_both_teams(
        db,
        target,
        exclude_provider_fixture_id=int(row.provider_fixture_id) if row.provider_fixture_id else None,
    )

    api_client = client
    if api_client is None:
        api_client = ApiFootballClient(
            usage_db=db,
            usage_context=ApiUsageContext(record_events=False),
        )

    fixtures_checked = len(prior)
    fixtures_backfilled = 0
    api_calls = 0
    errors: list[str] = []

    for fx in prior:
        has_xg = _fixture_has_xg(db, fx)
        if has_xg and not force_refresh:
            continue
        try:
            stats_payload = api_client.get_fixture_statistics(int(fx.api_fixture_id))
            api_calls += 1
            if stats_payload:
                _persist_fixture_statistics(db, fx, stats_payload)
                fixtures_backfilled += 1
        except Exception as exc:
            errors.append(f"fixture_{fx.id}:{exc}")

    db.commit()
    fixtures_with_xg = sum(1 for p in prior if _fixture_has_xg(db, p))

    return {
        "status": "ok",
        "today_fixture_id": int(today_fixture_id),
        "fixtures_checked": fixtures_checked,
        "fixtures_backfilled": fixtures_backfilled,
        "fixtures_with_xg": fixtures_with_xg,
        "api_calls_made": api_calls,
        "force_refresh": bool(force_refresh),
        "errors": errors,
        "note": "Manual backfill only — current season prior fixtures",
    }
