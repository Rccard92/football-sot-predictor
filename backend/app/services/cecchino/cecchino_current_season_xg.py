"""Profilo xG storico campionato corrente — anti-leakage per Expected Goal Engine (Fase 52/53)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Competition, Fixture, FixtureTeamStat, League, Season, Team
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.api_usage_context import ApiUsageContext
from app.services.cecchino.cecchino_fixture_history import load_finished_fixtures_for_team
from app.services.datetime_utils import ensure_datetime_utc, safe_isoformat, utc_now
from app.services.fixture_team_stats_mapping import (
    _parse_float,
    apply_parsed_to_row,
    backfill_shot_columns_from_raw_json_if_null,
    statistics_list_to_fields,
)
from app.services.predictions_v10.v10_prior_context import _team_stats_map

logger = logging.getLogger(__name__)

PROFILE_VERSION = "cecchino_xg_profiles_v1"
SOURCE_NAME = "current_season_historical_xg"
SOURCE_FIELD_XG = "fixture_statistics.statistics[type=expected_goals].value"
SOURCE_FIELD_FOR = f"{SOURCE_FIELD_XG} averaged as team xG For"
SOURCE_FIELD_AGAINST = f"{SOURCE_FIELD_XG} averaged as team xG Against"
ANTI_LEAKAGE_NOTE = (
    "Calcolato automaticamente sulle partite precedenti della stagione corrente. "
    "La partita analizzata è esclusa per evitare leakage."
)
MIN_XG_SAMPLE_AVAILABLE = 3
CACHE_KICKOFF_TOLERANCE = timedelta(minutes=1)


def _parse_cached_cutoff(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return ensure_datetime_utc(value, field_name="xg.fixture_date_cutoff")
    try:
        s = str(value).replace("Z", "+00:00")
        return ensure_datetime_utc(datetime.fromisoformat(s), field_name="xg.fixture_date_cutoff")
    except (TypeError, ValueError):
        return None


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
        "home_xg": None,
        "away_xg": None,
        "home_team_id": None,
        "away_team_id": None,
        "warning": None,
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

    out["home_xg"] = out["home"]
    out["away_xg"] = out["away"]
    if out["home"] is None and out["away"] is None:
        out["warning"] = "expected_goals_not_found"

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

    cutoff = safe_isoformat(target_fixture.kickoff_at, field_name="target.kickoff_at")

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
    out.sort(
        key=lambda f: (
            ensure_datetime_utc(f.kickoff_at, field_name=f"prior_fixture_{f.id}.kickoff_at")
            or datetime.min.replace(tzinfo=timezone.utc),
            f.id,
        ),
    )
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


def _team_display_from_profile(profile: dict[str, Any], team_name: str | None) -> dict[str, Any]:
    return {
        "team": team_name,
        "xg_for_avg": profile.get("xg_for_avg"),
        "xg_against_avg": profile.get("xg_against_avg"),
        "xg_for_total": profile.get("xg_for_total"),
        "xg_against_total": profile.get("xg_against_total"),
        "sample_size": profile.get("sample_size"),
        "matches_checked": profile.get("matches_checked"),
        "matches_with_xg": profile.get("matches_with_xg"),
        "matches_missing_xg": profile.get("matches_missing_xg"),
        "warnings": list(profile.get("warnings") or []),
    }


def _cached_team_to_profile(cached: dict[str, Any], anti_leakage: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "xg_for_avg": cached.get("xg_for_avg"),
        "xg_against_avg": cached.get("xg_against_avg"),
        "xg_for_total": cached.get("xg_for_total"),
        "xg_against_total": cached.get("xg_against_total"),
        "sample_size": cached.get("sample_size"),
        "matches_checked": cached.get("matches_checked"),
        "matches_with_xg": cached.get("matches_with_xg"),
        "matches_missing_xg": cached.get("matches_missing_xg"),
        "source": SOURCE_NAME,
        "source_field": SOURCE_FIELD_XG,
        "warnings": list(cached.get("warnings") or []),
        "anti_leakage": anti_leakage,
    }


def _profile_cache_fresh(
    row: CecchinoTodayFixture,
    *,
    prior_count: int,
    force_refresh: bool,
    target_kickoff: datetime | None = None,
) -> bool:
    if force_refresh:
        return False
    cached = row.xg_profiles_json if isinstance(row.xg_profiles_json, dict) else None
    if not cached:
        return False
    if cached.get("profile_version") != PROFILE_VERSION:
        return False
    if cached.get("local_fixture_id") != int(row.local_fixture_id or 0):
        return False
    usage = cached.get("xg_api_usage") or {}
    if int(usage.get("fixtures_checked") or 0) != prior_count:
        return False

    # Cutoff vs kickoff corrente (UTC normalizzati, tolleranza 1 minuto)
    anti = cached.get("anti_leakage") if isinstance(cached.get("anti_leakage"), dict) else {}
    cached_cutoff = _parse_cached_cutoff(anti.get("fixture_date_cutoff") if anti else None)
    target_ko = ensure_datetime_utc(target_kickoff, field_name="target.kickoff_at") if target_kickoff else None
    if target_ko is None or cached_cutoff is None:
        return False
    if abs(target_ko - cached_cutoff) > CACHE_KICKOFF_TOLERANCE:
        return False
    return True


def _backfill_prior_statistics(
    db: Session,
    prior: list[Fixture],
    *,
    force_refresh: bool,
    client: ApiFootballClient,
) -> tuple[int, int, int, list[str]]:
    """Cache-first backfill FixtureTeamStat per fixture prior. Returns calls, hits, backfilled, warnings."""
    external_calls = 0
    cache_hits = 0
    backfilled = 0
    warnings: list[str] = []

    for fx in prior:
        has_xg = _fixture_has_xg(db, fx)
        if has_xg and not force_refresh:
            cache_hits += 1
            continue
        try:
            stats_payload = client.get_fixture_statistics(int(fx.api_fixture_id))
            external_calls += 1
            if stats_payload:
                _persist_fixture_statistics(db, fx, stats_payload)
                backfilled += 1
                db.flush()
        except ApiFootballError as exc:
            msg = str(exc).lower()
            if "429" in msg or "rate" in msg:
                warnings.append("xg_api_rate_limited")
            else:
                warnings.append("xg_provider_error")
            logger.warning("xg stats fetch failed fixture=%s: %s", fx.id, exc)
        except Exception as exc:
            warnings.append("xg_provider_error")
            logger.warning("xg stats fetch failed fixture=%s: %s", fx.id, exc)

    if backfilled == 0 and external_calls == 0 and prior and cache_hits < len(prior):
        if "missing_xg_in_current_season_history" not in warnings:
            warnings.append("xg_partial_cache_only")

    return external_calls, cache_hits, backfilled, warnings


def ensure_current_season_xg_profile_for_fixture(
    db: Session,
    today_fixture_id: int,
    *,
    force_refresh: bool = False,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    """Recupero automatico profilo xG storico current season (cache-first, idempotente)."""
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"status": "not_found", "message": f"CecchinoTodayFixture {today_fixture_id} not found"}
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return {"status": "skipped", "reason": "not_eligible"}
    if not row.local_fixture_id:
        return {"status": "skipped", "reason": "missing_local_fixture_id"}

    target = db.get(Fixture, int(row.local_fixture_id))
    if target is None:
        return {"status": "skipped", "reason": "local_fixture_not_found"}

    exclude_api = int(row.provider_fixture_id) if row.provider_fixture_id else None
    prior = _prior_fixtures_both_teams(db, target, exclude_provider_fixture_id=exclude_api)
    prior_count = len(prior)

    if _profile_cache_fresh(
        row,
        prior_count=prior_count,
        force_refresh=force_refresh,
        target_kickoff=target.kickoff_at,
    ):
        cached = row.xg_profiles_json or {}
        return {
            "status": "cached",
            "today_fixture_id": int(today_fixture_id),
            "xg_profiles": cached,
            "xg_api_usage": cached.get("xg_api_usage"),
        }

    api_client = client or ApiFootballClient(
        usage_db=db,
        usage_context=ApiUsageContext(record_events=False),
    )

    external_calls, cache_hits, backfilled, fetch_warnings = _backfill_prior_statistics(
        db,
        prior,
        force_refresh=force_refresh,
        client=api_client,
    )

    home_profile = build_current_season_team_xg_profile(
        db,
        target,
        int(target.home_team_id),
        exclude_provider_fixture_id=exclude_api,
    )
    away_profile = build_current_season_team_xg_profile(
        db,
        target,
        int(target.away_team_id),
        exclude_provider_fixture_id=exclude_api,
    )

    anti_leakage = home_profile.get("anti_leakage") or away_profile.get("anti_leakage") or {
        "current_fixture_excluded": True,
        "fixture_date_cutoff": safe_isoformat(target.kickoff_at, field_name="target.kickoff_at"),
        "scope": "current season matches before fixture",
    }

    all_warnings = list(fetch_warnings)
    for p in (home_profile, away_profile):
        for w in p.get("warnings") or []:
            if w not in all_warnings:
                all_warnings.append(w)
    if home_profile.get("sample_size", 0) == 0:
        all_warnings.append("missing_xg_in_current_season_history")
    if away_profile.get("sample_size", 0) == 0 and "missing_xg_in_current_season_history" not in all_warnings:
        all_warnings.append("missing_xg_in_current_season_history")
    for p in (home_profile, away_profile):
        ss = int(p.get("sample_size") or 0)
        if 0 < ss < MIN_XG_SAMPLE_AVAILABLE and "insufficient_xg_sample" not in all_warnings:
            all_warnings.append("insufficient_xg_sample")

    xg_api_usage = {
        "automatic": True,
        "external_calls_made": external_calls,
        "cache_hits": cache_hits,
        "fixtures_checked": prior_count,
        "fixtures_backfilled": backfilled,
        "endpoint": "fixture_statistics",
    }

    profiles_payload = {
        "profile_version": PROFILE_VERSION,
        "local_fixture_id": int(row.local_fixture_id),
        "home_team": _team_display_from_profile(home_profile, row.home_team_name),
        "away_team": _team_display_from_profile(away_profile, row.away_team_name),
        "anti_leakage": anti_leakage,
        "xg_api_usage": xg_api_usage,
        "updated_at": utc_now().isoformat(),
        "warnings": all_warnings,
    }

    row.xg_profiles_json = profiles_payload
    db.flush()

    return {
        "status": "ok",
        "today_fixture_id": int(today_fixture_id),
        "xg_profiles": profiles_payload,
        "xg_api_usage": xg_api_usage,
        "warnings": all_warnings,
    }


def _filtered_prior_fixture_ids_for_team(
    db: Session,
    target: Fixture,
    team_id: int,
    *,
    exclude_provider_fixture_id: int | None,
) -> list[int]:
    """Stessa esclusione anti-leakage di build_current_season_team_xg_profile (solo id)."""
    prior = load_finished_fixtures_for_team(db, target, int(team_id))
    target_id = int(target.id)
    target_api_id = int(target.api_fixture_id)
    exclude_api = int(exclude_provider_fixture_id) if exclude_provider_fixture_id else None
    ids: list[int] = []
    for fx in prior:
        if int(fx.id) == target_id:
            continue
        if exclude_api is not None and int(fx.api_fixture_id) == exclude_api:
            continue
        if int(fx.api_fixture_id) == target_api_id:
            continue
        ids.append(int(fx.id))
    return ids


def rebuild_current_season_xg_profile_from_cache(
    db: Session,
    today_fixture_id: int,
) -> dict[str, Any]:
    """Rigenera xg_profiles_json solo da FixtureTeamStat già in DB — zero API esterne."""
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"status": "not_found", "message": f"CecchinoTodayFixture {today_fixture_id} not found"}
    if not row.local_fixture_id:
        return {"status": "skipped", "reason": "missing_local_fixture_id"}

    target = db.get(Fixture, int(row.local_fixture_id))
    if target is None:
        return {"status": "skipped", "reason": "local_fixture_not_found"}

    exclude_api = int(row.provider_fixture_id) if row.provider_fixture_id else None
    cutoff_before = None
    old = row.xg_profiles_json if isinstance(row.xg_profiles_json, dict) else {}
    if isinstance(old.get("anti_leakage"), dict):
        cutoff_before = old["anti_leakage"].get("fixture_date_cutoff")

    home_ids = _filtered_prior_fixture_ids_for_team(
        db, target, int(target.home_team_id), exclude_provider_fixture_id=exclude_api
    )
    away_ids = _filtered_prior_fixture_ids_for_team(
        db, target, int(target.away_team_id), exclude_provider_fixture_id=exclude_api
    )

    home_profile = build_current_season_team_xg_profile(
        db,
        target,
        int(target.home_team_id),
        exclude_provider_fixture_id=exclude_api,
    )
    away_profile = build_current_season_team_xg_profile(
        db,
        target,
        int(target.away_team_id),
        exclude_provider_fixture_id=exclude_api,
    )

    anti_leakage = {
        "current_fixture_excluded": True,
        "fixture_date_cutoff": safe_isoformat(target.kickoff_at, field_name="target.kickoff_at"),
        "scope": "current season matches before fixture",
    }
    # Prefer explicit anti_leakage from profiles if present (same cutoff)
    for p in (home_profile, away_profile):
        al = p.get("anti_leakage")
        if isinstance(al, dict) and al.get("fixture_date_cutoff"):
            anti_leakage = {
                "current_fixture_excluded": True,
                "fixture_date_cutoff": al.get("fixture_date_cutoff"),
                "scope": al.get("scope") or anti_leakage["scope"],
            }
            break

    all_warnings: list[str] = []
    for p in (home_profile, away_profile):
        for w in p.get("warnings") or []:
            if w not in all_warnings:
                all_warnings.append(str(w))
    if int(home_profile.get("matches_missing_xg") or 0) > 0 or int(
        away_profile.get("matches_missing_xg") or 0
    ) > 0:
        if "cache_only_partial" not in all_warnings:
            all_warnings.append("cache_only_partial")
    if home_profile.get("sample_size", 0) == 0 or away_profile.get("sample_size", 0) == 0:
        if "cache_only_partial" not in all_warnings:
            all_warnings.append("cache_only_partial")
        if "missing_xg_in_current_season_history" not in all_warnings:
            all_warnings.append("missing_xg_in_current_season_history")
    for p in (home_profile, away_profile):
        ss = int(p.get("sample_size") or 0)
        if 0 < ss < MIN_XG_SAMPLE_AVAILABLE and "insufficient_xg_sample" not in all_warnings:
            all_warnings.append("insufficient_xg_sample")

    prior_union = _prior_fixtures_both_teams(db, target, exclude_provider_fixture_id=exclude_api)
    max_ko = None
    for fx in prior_union:
        ko = ensure_datetime_utc(fx.kickoff_at, field_name=f"prior_{fx.id}.kickoff_at")
        if ko is not None and (max_ko is None or ko > max_ko):
            max_ko = ko

    xg_api_usage = {
        "automatic": False,
        "cache_only": True,
        "external_calls_made": 0,
        "cache_hits": len(prior_union),
        "fixtures_checked": len(prior_union),
        "fixtures_backfilled": 0,
        "endpoint": None,
    }

    profiles_payload = {
        "profile_version": PROFILE_VERSION,
        "local_fixture_id": int(row.local_fixture_id),
        "home_team": _team_display_from_profile(home_profile, row.home_team_name),
        "away_team": _team_display_from_profile(away_profile, row.away_team_name),
        "anti_leakage": anti_leakage,
        "xg_api_usage": xg_api_usage,
        "updated_at": utc_now().isoformat(),
        "warnings": all_warnings,
    }

    row.xg_profiles_json = profiles_payload
    db.flush()

    excluded_ids = [int(target.id)]
    excluded_provider = [int(exclude_api)] if exclude_api is not None else []

    return {
        "status": "ok",
        "today_fixture_id": int(today_fixture_id),
        "local_fixture_id": int(target.id),
        "cutoff_before": cutoff_before,
        "cutoff_after": anti_leakage.get("fixture_date_cutoff"),
        "xg_profiles": profiles_payload,
        "xg_api_usage": xg_api_usage,
        "warnings": all_warnings,
        "anti_leakage_report": {
            "current_fixture_excluded": True,
            "excluded_fixture_ids": excluded_ids,
            "excluded_provider_fixture_ids": excluded_provider,
            "home_fixture_ids_used": home_ids,
            "away_fixture_ids_used": away_ids,
            "max_historical_kickoff": safe_isoformat(max_ko, field_name="max_historical_kickoff")
            if max_ko
            else None,
            "external_calls_made": 0,
        },
    }


def maybe_ensure_xg_for_eligible_row(
    db: Session,
    row: CecchinoTodayFixture,
    *,
    force_refresh: bool = False,
) -> dict[str, Any] | None:
    """Hook pipeline: non blocca eleggibilità su errori provider."""
    if row.eligibility_status != ELIGIBILITY_ELIGIBLE:
        return None
    try:
        return ensure_current_season_xg_profile_for_fixture(
            db,
            int(row.id),
            force_refresh=force_refresh,
        )
    except Exception as exc:
        logger.exception("maybe_ensure_xg_for_eligible_row failed today_fixture_id=%s", row.id)
        return {"status": "error", "warnings": ["xg_provider_error"], "message": str(exc)[:200]}


def backfill_current_season_xg_for_today_fixture(
    db: Session,
    today_fixture_id: int,
    *,
    force_refresh: bool = False,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    """Backfill/manuale — delega a ensure_current_season_xg_profile_for_fixture."""
    result = ensure_current_season_xg_profile_for_fixture(
        db,
        today_fixture_id,
        force_refresh=force_refresh,
        client=client,
    )
    if result.get("status") in ("not_found", "skipped"):
        return result

    usage = result.get("xg_api_usage") or {}
    profiles = result.get("xg_profiles") or {}
    home = profiles.get("home_team") or {}
    away = profiles.get("away_team") or {}

    db.commit()

    return {
        "status": result.get("status", "ok"),
        "today_fixture_id": int(today_fixture_id),
        "fixtures_checked": usage.get("fixtures_checked", 0),
        "fixtures_backfilled": usage.get("fixtures_backfilled", 0),
        "fixtures_with_xg": int(home.get("matches_with_xg") or 0) + int(away.get("matches_with_xg") or 0),
        "api_calls_made": usage.get("external_calls_made", 0),
        "cache_hits": usage.get("cache_hits", 0),
        "force_refresh": bool(force_refresh),
        "errors": [],
        "warnings": result.get("warnings") or [],
        "xg_profiles": profiles,
        "note": "Manual or automatic xG ensure — current season prior fixtures",
    }
