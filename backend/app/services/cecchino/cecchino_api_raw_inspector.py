"""Ispezione manuale dati raw/cache/API per singola fixture Cecchino Today (Fase 51).

Strumento esplorativo separato dal diagnostics builder Expected Goal Engine.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CecchinoTodayFixture,
    Fixture,
    FixtureLineup,
    FixturePlayerStat,
    FixtureTeamStat,
    League,
    Team,
)
from app.services.api_football_client import ApiFootballClient
from app.services.api_usage_context import ApiUsageContext
from app.services.fixture_team_stats_mapping import _parse_float, statistics_list_to_fields

INSPECTOR_VERSION = "cecchino_api_raw_inspector_v1"

SEARCH_KEYWORDS: list[str] = [
    "xg",
    "expected",
    "expected goals",
    "expected_goal",
    "expected_goals",
    "xga",
    "expected_goals_for",
    "expected_goals_against",
    "npxg",
    "xg_for",
    "xg_against",
]

MAX_WALK_DEPTH = 12
MAX_LIST_ITEMS = 100
MAX_MATCHES = 500

SOURCE_LABELS: dict[str, str] = {
    "today_raw_fixture": "Raw fixture Cecchino Today",
    "stats_snapshot": "Stats snapshot Cecchino",
    "local_fixture": "Fixture DB locale",
    "fixture_team_stats": "Fixture team stats DB",
    "fixture_statistics": "Fixture statistics",
    "fixture_events": "Fixture events",
    "fixture_lineups": "Fixture lineups",
    "fixture_players": "Fixture players statistics",
    "team_statistics_home": "Team statistics (home)",
    "team_statistics_away": "Team statistics (away)",
}

ALL_SOURCE_KEYS = list(SOURCE_LABELS.keys())


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _keyword_matches(text: str, keyword: str) -> bool:
    t = _norm_text(text)
    k = _norm_text(keyword)
    if not t or not k:
        return False
    if k in ("xg", "xga", "npxg"):
        return bool(re.search(rf"\b{re.escape(k)}\b", t))
    return k in t


def _match_keyword_in_text(text: str) -> str | None:
    for kw in SEARCH_KEYWORDS:
        if _keyword_matches(text, kw):
            return kw
    return None


def _compact_raw_item(obj: Any, *, max_depth: int = 3) -> Any:
    if max_depth <= 0:
        return "…"
    if isinstance(obj, dict):
        return {k: _compact_raw_item(v, max_depth=max_depth - 1) for k, v in list(obj.items())[:20]}
    if isinstance(obj, list):
        return [_compact_raw_item(v, max_depth=max_depth - 1) for v in obj[:5]]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def _team_block_from_hint(team_hint: dict[str, Any] | None) -> dict[str, Any] | None:
    if not team_hint:
        return None
    out: dict[str, Any] = {}
    if team_hint.get("id") is not None:
        out["id"] = team_hint.get("id")
    if team_hint.get("name"):
        out["name"] = team_hint.get("name")
    if team_hint.get("side"):
        out["side"] = team_hint.get("side")
    return out or None


def find_fields_by_keywords(
    payload: Any,
    keywords: list[str] | None = None,
    *,
    endpoint: str,
    origin: str,
    team_hint: dict[str, Any] | None = None,
    path_prefix: str = "",
    depth: int = 0,
    matches: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Ricerca ricorsiva di campi xG/expected in un payload JSON."""
    if matches is None:
        matches = []
    if depth > MAX_WALK_DEPTH or len(matches) >= MAX_MATCHES:
        return matches

    kw_list = keywords or SEARCH_KEYWORDS

    def _append_match(
        *,
        path: str,
        key: str,
        matched_keyword: str,
        type_val: Any,
        value: Any,
        raw_item: Any,
        hint: dict[str, Any] | None,
    ) -> None:
        if len(matches) >= MAX_MATCHES:
            return
        matches.append(
            {
                "endpoint": endpoint,
                "source": "db_cache" if origin == "db_cache" else "api_response",
                "path": path,
                "key": key,
                "matched_keyword": matched_keyword,
                "type": type_val,
                "value": value,
                "team": _team_block_from_hint(hint),
                "raw_item": _compact_raw_item(raw_item),
            },
        )

    if isinstance(payload, dict):
        current_hint = team_hint
        team_obj = payload.get("team")
        if isinstance(team_obj, dict):
            merged = dict(team_hint or {})
            if team_obj.get("id") is not None:
                merged["id"] = team_obj.get("id")
            if team_obj.get("name"):
                merged["name"] = team_obj.get("name")
            current_hint = merged or current_hint

        for k, v in payload.items():
            child_path = f"{path_prefix}.{k}" if path_prefix else str(k)
            key_str = str(k)
            mk = _match_keyword_in_text(key_str)
            if mk or any(_keyword_matches(key_str, x) for x in kw_list):
                matched = mk or next((x for x in kw_list if _keyword_matches(key_str, x)), kw_list[0])
                type_val = payload.get("type") if "type" in payload else key_str
                _append_match(
                    path=child_path,
                    key=key_str,
                    matched_keyword=matched,
                    type_val=type_val,
                    value=v if not isinstance(v, (dict, list)) else None,
                    raw_item=payload if k in ("type", "name", "label") else {k: v},
                    hint=current_hint,
                )
            if isinstance(v, str):
                smk = _match_keyword_in_text(v)
                if smk and any(_keyword_matches(v, x) for x in kw_list):
                    _append_match(
                        path=child_path,
                        key=key_str,
                        matched_keyword=smk,
                        type_val=payload.get("type") or key_str,
                        value=v,
                        raw_item=payload,
                        hint=current_hint,
                    )
            find_fields_by_keywords(
                v,
                kw_list,
                endpoint=endpoint,
                origin=origin,
                team_hint=current_hint,
                path_prefix=child_path,
                depth=depth + 1,
                matches=matches,
            )

        for special in ("type", "name", "label"):
            if special in payload:
                sv = payload.get(special)
                smk = _match_keyword_in_text(str(sv))
                if smk and any(_keyword_matches(str(sv), x) for x in kw_list):
                    sp = f"{path_prefix}.{special}" if path_prefix else special
                    _append_match(
                        path=sp,
                        key=special,
                        matched_keyword=smk,
                        type_val=sv,
                        value=payload.get("value"),
                        raw_item=payload,
                        hint=current_hint,
                    )

    elif isinstance(payload, list):
        for i, item in enumerate(payload[:MAX_LIST_ITEMS]):
            child_path = f"{path_prefix}[{i}]"
            find_fields_by_keywords(
                item,
                kw_list,
                endpoint=endpoint,
                origin=origin,
                team_hint=team_hint,
                path_prefix=child_path,
                depth=depth + 1,
                matches=matches,
            )

    return matches


def _parse_endpoints_filter(endpoints: str) -> set[str] | None:
    raw = (endpoints or "all").strip().lower()
    if raw in ("", "all", "*"):
        return None
    keys = {p.strip() for p in raw.split(",") if p.strip()}
    return keys or None


def _endpoint_enabled(key: str, enabled: set[str] | None) -> bool:
    return enabled is None or key in enabled


def _resolve_ids(
    row: CecchinoTodayFixture,
    db: Session,
) -> tuple[dict[str, Any], Fixture | None, Team | None, Team | None, League | None]:
    ids: dict[str, Any] = {
        "today_fixture_id": int(row.id),
        "fixture_id": int(row.local_fixture_id) if row.local_fixture_id is not None else None,
        "provider_fixture_id": int(row.provider_fixture_id) if row.provider_fixture_id else None,
        "league_id": int(row.competition_id) if row.competition_id is not None else None,
        "provider_league_id": int(row.provider_league_id) if row.provider_league_id is not None else None,
        "season": int(row.provider_season) if row.provider_season is not None else None,
        "home_team_id": None,
        "provider_home_team_id": None,
        "away_team_id": None,
        "provider_away_team_id": None,
    }

    fixture: Fixture | None = None
    home_team: Team | None = None
    away_team: Team | None = None
    league: League | None = None

    if row.local_fixture_id:
        fixture = db.scalars(
            select(Fixture)
            .where(Fixture.id == int(row.local_fixture_id))
            .options(joinedload(Fixture.home_team), joinedload(Fixture.away_team), joinedload(Fixture.league)),
        ).first()
        if fixture is not None:
            ids["fixture_id"] = int(fixture.id)
            ids["home_team_id"] = int(fixture.home_team_id)
            ids["away_team_id"] = int(fixture.away_team_id)
            home_team = fixture.home_team
            away_team = fixture.away_team
            if home_team is not None:
                ids["provider_home_team_id"] = int(home_team.api_team_id)
            if away_team is not None:
                ids["provider_away_team_id"] = int(away_team.api_team_id)
            league = fixture.league
            if league is not None:
                ids["league_id"] = int(league.id)
                ids["provider_league_id"] = int(league.api_league_id)

    if ids["provider_league_id"] is None and row.provider_league_id is not None:
        ids["provider_league_id"] = int(row.provider_league_id)

    return ids, fixture, home_team, away_team, league


def _team_side(team_id: Any, home_team: Team | None, away_team: Team | None) -> str | None:
    if team_id is None:
        return None
    try:
        tid = int(team_id)
    except (TypeError, ValueError):
        return None
    if home_team is not None and int(home_team.api_team_id) == tid:
        return "home"
    if away_team is not None and int(away_team.api_team_id) == tid:
        return "away"
    if home_team is not None and int(home_team.id) == tid:
        return "home"
    if away_team is not None and int(away_team.id) == tid:
        return "away"
    return None


def _extract_xg_from_statistics_payload(
    payload: Any,
    *,
    home_team: Team | None,
    away_team: Team | None,
) -> list[dict[str, Any]]:
    """Estrae valori Expected Goals per team da payload stile API-Football statistics."""
    results: list[dict[str, Any]] = []
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("response"), list):
        items = payload["response"]
    elif isinstance(payload, dict) and isinstance(payload.get("statistics"), list):
        items = [payload]
    else:
        return results

    for block in items:
        if not isinstance(block, dict):
            continue
        team_obj = block.get("team") if isinstance(block.get("team"), dict) else {}
        stats = block.get("statistics")
        if not isinstance(stats, list):
            continue
        parsed = statistics_list_to_fields(stats)
        xg = parsed.get("expected_goals")
        if xg is None:
            continue
        team_id = team_obj.get("id")
        team_name = team_obj.get("name")
        side = _team_side(team_id, home_team, away_team)
        results.append(
            {
                "team_id": team_id,
                "team_name": team_name,
                "side": side,
                "value": float(xg),
                "source_field": f"statistics[type=Expected Goals].value",
            },
        )
    return results


def build_suggested_xg_mapping(
    matches: list[dict[str, Any]],
    *,
    home_team: Team | None,
    away_team: Team | None,
    statistics_payloads: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Propone mapping xG senza applicarlo al diagnostics builder."""
    xg_rows: list[dict[str, Any]] = []
    for source_key, payload in statistics_payloads:
        for row in _extract_xg_from_statistics_payload(payload, home_team=home_team, away_team=away_team):
            row = {**row, "source": source_key}
            xg_rows.append(row)

    if not xg_rows:
        for m in matches:
            t = _norm_text(str(m.get("type") or ""))
            if "expected goal" not in t and "expected_goals" not in t:
                continue
            val = m.get("value")
            fv = _parse_float(val)
            if fv is None:
                continue
            team = m.get("team") or {}
            xg_rows.append(
                {
                    "team_id": team.get("id"),
                    "team_name": team.get("name"),
                    "side": team.get("side"),
                    "value": float(fv),
                    "source": m.get("endpoint"),
                    "source_field": m.get("path"),
                },
            )

    home_row = next((r for r in xg_rows if r.get("side") == "home"), None)
    away_row = next((r for r in xg_rows if r.get("side") == "away"), None)

    if home_row is None and away_row is None and len(xg_rows) >= 2:
        home_row, away_row = xg_rows[0], xg_rows[1]
        if home_row.get("side") is None:
            home_row = {**home_row, "side": "home"}
        if away_row.get("side") is None:
            away_row = {**away_row, "side": "away"}

    if home_row is None or away_row is None:
        return {
            "status": "not_found",
            "warnings": ["no_xg_like_fields_found"],
        }

    def _field(row: dict[str, Any], key: str, *, confidence: str, note: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "value": row["value"],
            "source": row.get("source"),
            "source_field": row.get("source_field"),
            "confidence": confidence,
        }
        if note:
            out["note"] = note
        return out

    return {
        "status": "candidate_found",
        "home_xg_for": _field(home_row, "home_xg_for", confidence="high"),
        "away_xg_for": _field(away_row, "away_xg_for", confidence="high"),
        "home_xg_against": _field(
            away_row,
            "home_xg_against",
            confidence="medium",
            note="Single-match xG against inferred from opponent xG for",
        ),
        "away_xg_against": _field(
            home_row,
            "away_xg_against",
            confidence="medium",
            note="Single-match xG against inferred from opponent xG for",
        ),
    }


def _load_fixture_team_stats_payload(
    db: Session,
    fixture: Fixture | None,
    home_team: Team | None,
    away_team: Team | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Restituisce (rows_db, statistics_api_shape)."""
    if fixture is None:
        return [], []

    stats_rows = list(
        db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(fixture.id))).all(),
    )
    db_rows: list[dict[str, Any]] = []
    api_shape: list[dict[str, Any]] = []

    team_by_id = {int(fixture.home_team_id): home_team, int(fixture.away_team_id): away_team}

    for st in stats_rows:
        team = team_by_id.get(int(st.team_id))
        side = st.side or _team_side(team.api_team_id if team else None, home_team, away_team)
        entry = {
            "fixture_id": int(st.fixture_id),
            "team_id": int(st.team_id),
            "side": side,
            "expected_goals_column": st.expected_goals,
            "raw_json": st.raw_json,
        }
        db_rows.append(entry)

        raw = st.raw_json if isinstance(st.raw_json, dict) else {}
        team_block: dict[str, Any] = {}
        if team is not None:
            team_block = {"id": int(team.api_team_id), "name": team.name}
        elif isinstance(raw.get("team"), dict):
            team_block = raw["team"]
        block = dict(raw) if raw else {"statistics": []}
        if team_block and "team" not in block:
            block["team"] = team_block
        if st.expected_goals is not None and isinstance(block.get("statistics"), list):
            has_xg = any(
                "expected goal" in _norm_text(str(s.get("type") or ""))
                for s in block["statistics"]
                if isinstance(s, dict)
            )
            if not has_xg:
                block = {
                    **block,
                    "statistics": [
                        *block["statistics"],
                        {"type": "Expected Goals", "value": str(st.expected_goals)},
                    ],
                }
        api_shape.append(block)

    return db_rows, api_shape


def build_api_raw_inspector(
    db: Session,
    today_fixture_id: int,
    *,
    force_refresh: bool = False,
    include_raw: bool = False,
    endpoints: str = "all",
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    row = db.get(CecchinoTodayFixture, int(today_fixture_id))
    if row is None:
        return {"status": "not_found", "message": f"CecchinoTodayFixture {today_fixture_id} not found"}

    ids, fixture, home_team, away_team, _league = _resolve_ids(row, db)
    enabled = _parse_endpoints_filter(endpoints)

    match_label = f"{row.home_team_name or '?'} vs {row.away_team_name or '?'}"

    base: dict[str, Any] = {
        "version": INSPECTOR_VERSION,
        "fixture": {
            "today_fixture_id": int(row.id),
            "provider_fixture_id": ids.get("provider_fixture_id"),
            "match": match_label,
            "league": row.league_name,
            "season": ids.get("season"),
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
        },
        "ids": ids,
        "searched_keywords": list(SEARCH_KEYWORDS),
        "sources_checked": [],
        "matches_found": [],
        "warnings": [],
    }

    provider_fixture_id = ids.get("provider_fixture_id")
    if not provider_fixture_id:
        base["status"] = "missing_provider_fixture_id"
        base["warnings"] = ["provider_fixture_id_not_found"]
        base["api_usage"] = {
            "force_refresh": bool(force_refresh),
            "external_calls_made": 0,
            "endpoints_called": [],
            "note": "Manual inspection only",
        }
        base["suggested_xg_mapping"] = {
            "status": "not_found",
            "warnings": ["provider_fixture_id_not_found"],
        }
        if include_raw:
            base["raw_payloads"] = {}
        return base

    api_client = client
    if api_client is None and force_refresh:
        api_client = ApiFootballClient(
            usage_db=db,
            usage_context=ApiUsageContext(record_events=False),
        )

    external_calls: list[str] = []
    raw_payloads: dict[str, Any] = {}
    statistics_payloads: list[tuple[str, Any]] = []
    all_matches: list[dict[str, Any]] = []

    def _check_source(
        key: str,
        *,
        available: bool,
        origin: str,
        records_count: int = 0,
        called: bool = False,
    ) -> None:
        base["sources_checked"].append(
            {
                "key": key,
                "label": SOURCE_LABELS.get(key, key),
                "available": available,
                "origin": origin,
                "records_count": records_count,
                "called": called,
            },
        )

    def _scan(key: str, payload: Any, origin: str) -> None:
        if payload is None:
            return
        found = find_fields_by_keywords(
            payload,
            SEARCH_KEYWORDS,
            endpoint=key,
            origin=origin,
            team_hint={
                "id": ids.get("provider_home_team_id"),
                "name": row.home_team_name,
                "side": "home",
            },
        )
        all_matches.extend(found)

    # 1. today_raw_fixture
    if _endpoint_enabled("today_raw_fixture", enabled):
        cache = row.raw_fixture_json
        cache_avail = cache is not None and cache != {}
        if cache_avail and not force_refresh:
            _check_source("today_raw_fixture", available=True, origin="db_cache", records_count=1)
            if include_raw:
                raw_payloads["today_raw_fixture"] = cache
            _scan("today_raw_fixture", cache, "db_cache")
        elif force_refresh and api_client is not None:
            try:
                live = api_client.get_fixture_by_id(int(provider_fixture_id))
                external_calls.append("today_raw_fixture")
                avail = live is not None
                _check_source(
                    "today_raw_fixture",
                    available=avail,
                    origin="provider_api",
                    records_count=1 if avail else 0,
                    called=True,
                )
                if avail:
                    if include_raw:
                        raw_payloads["today_raw_fixture"] = live
                    _scan("today_raw_fixture", live, "api_response")
            except Exception as exc:
                base["warnings"].append(f"today_raw_fixture_api_error:{exc}")
        elif cache_avail:
            _check_source("today_raw_fixture", available=True, origin="db_cache", records_count=1)
            if include_raw:
                raw_payloads["today_raw_fixture"] = cache
            _scan("today_raw_fixture", cache, "db_cache")
        else:
            _check_source("today_raw_fixture", available=False, origin="db_cache", records_count=0)
            base["warnings"].append("today_raw_fixture_not_in_cache")

    # 2. stats_snapshot
    if _endpoint_enabled("stats_snapshot", enabled):
        snap = row.stats_snapshot_json
        avail = snap is not None and snap != {}
        _check_source("stats_snapshot", available=avail, origin="db_cache", records_count=1 if avail else 0)
        if avail:
            if include_raw:
                raw_payloads["stats_snapshot"] = snap
            _scan("stats_snapshot", snap, "db_cache")

    # 3. local_fixture
    if _endpoint_enabled("local_fixture", enabled):
        fx_raw = fixture.raw_json if fixture is not None else None
        avail = fx_raw is not None and fx_raw != {}
        _check_source("local_fixture", available=avail, origin="db_cache", records_count=1 if avail else 0)
        if avail:
            if include_raw:
                raw_payloads["local_fixture"] = fx_raw
            _scan("local_fixture", fx_raw, "db_cache")

    # 4. fixture_team_stats + fixture_statistics from DB
    db_stats_rows: list[dict[str, Any]] = []
    api_stats_shape: list[dict[str, Any]] = []
    if fixture is not None and _endpoint_enabled("fixture_team_stats", enabled):
        db_stats_rows, api_stats_shape = _load_fixture_team_stats_payload(db, fixture, home_team, away_team)
        avail = len(db_stats_rows) > 0
        _check_source(
            "fixture_team_stats",
            available=avail,
            origin="db_cache",
            records_count=len(db_stats_rows),
        )
        if avail:
            payload = {"rows": db_stats_rows}
            if include_raw:
                raw_payloads["fixture_team_stats"] = payload
            _scan("fixture_team_stats", payload, "db_cache")

    if _endpoint_enabled("fixture_statistics", enabled):
        cache_avail = len(api_stats_shape) > 0
        if cache_avail and not force_refresh:
            _check_source(
                "fixture_statistics",
                available=True,
                origin="db_cache",
                records_count=len(api_stats_shape),
            )
            statistics_payloads.append(("fixture_statistics", api_stats_shape))
            if include_raw:
                raw_payloads["fixture_statistics"] = api_stats_shape
            _scan("fixture_statistics", api_stats_shape, "db_cache")
        elif force_refresh and api_client is not None:
            try:
                live_stats = api_client.get_fixture_statistics(int(provider_fixture_id))
                external_calls.append("fixture_statistics")
                avail = len(live_stats) > 0
                _check_source(
                    "fixture_statistics",
                    available=avail,
                    origin="provider_api",
                    records_count=len(live_stats),
                    called=True,
                )
                if avail:
                    statistics_payloads.append(("fixture_statistics", live_stats))
                    if include_raw:
                        raw_payloads["fixture_statistics"] = live_stats
                    _scan("fixture_statistics", live_stats, "api_response")
            except Exception as exc:
                base["warnings"].append(f"fixture_statistics_api_error:{exc}")
        elif cache_avail:
            _check_source(
                "fixture_statistics",
                available=True,
                origin="db_cache",
                records_count=len(api_stats_shape),
            )
            statistics_payloads.append(("fixture_statistics", api_stats_shape))
            if include_raw:
                raw_payloads["fixture_statistics"] = api_stats_shape
            _scan("fixture_statistics", api_stats_shape, "db_cache")
        else:
            _check_source("fixture_statistics", available=False, origin="db_cache", records_count=0)
            base["warnings"].append("fixture_statistics_not_in_cache")

    # 5. fixture_lineups
    if _endpoint_enabled("fixture_lineups", enabled) and fixture is not None:
        lineups = list(
            db.scalars(select(FixtureLineup).where(FixtureLineup.fixture_id == int(fixture.id))).all(),
        )
        payloads = [
            lu.raw_json or lu.lineup_json or {"formation": lu.formation, "team_id": lu.team_id}
            for lu in lineups
        ]
        avail = len(payloads) > 0
        _check_source("fixture_lineups", available=avail, origin="db_cache", records_count=len(payloads))
        if avail:
            if include_raw:
                raw_payloads["fixture_lineups"] = payloads
            _scan("fixture_lineups", payloads, "db_cache")
        elif force_refresh and api_client is not None:
            try:
                live = api_client.get_fixture_lineups(int(provider_fixture_id))
                external_calls.append("fixture_lineups")
                avail = len(live) > 0
                _check_source(
                    "fixture_lineups",
                    available=avail,
                    origin="provider_api",
                    records_count=len(live),
                    called=True,
                )
                if avail:
                    if include_raw:
                        raw_payloads["fixture_lineups"] = live
                    _scan("fixture_lineups", live, "api_response")
            except Exception as exc:
                base["warnings"].append(f"fixture_lineups_api_error:{exc}")

    # 6. fixture_players
    if _endpoint_enabled("fixture_players", enabled) and fixture is not None:
        players = list(
            db.scalars(select(FixturePlayerStat).where(FixturePlayerStat.fixture_id == int(fixture.id))).all(),
        )
        payloads = [p.raw_json or {"player_id": p.player_id, "team_id": p.team_id} for p in players]
        avail = len(payloads) > 0
        _check_source("fixture_players", available=avail, origin="db_cache", records_count=len(payloads))
        if avail:
            if include_raw:
                raw_payloads["fixture_players"] = payloads
            _scan("fixture_players", payloads, "db_cache")
        elif force_refresh and api_client is not None:
            try:
                live = api_client.get_fixture_players(int(provider_fixture_id))
                external_calls.append("fixture_players")
                avail = len(live) > 0
                _check_source(
                    "fixture_players",
                    available=avail,
                    origin="provider_api",
                    records_count=len(live),
                    called=True,
                )
                if avail:
                    if include_raw:
                        raw_payloads["fixture_players"] = live
                    _scan("fixture_players", live, "api_response")
            except Exception as exc:
                base["warnings"].append(f"fixture_players_api_error:{exc}")

    # 7. fixture_events
    if _endpoint_enabled("fixture_events", enabled):
        _check_source("fixture_events", available=False, origin="db_cache", records_count=0)
        if force_refresh and api_client is not None:
            try:
                live = api_client.get_fixture_events(int(provider_fixture_id))
                external_calls.append("fixture_events")
                avail = len(live) > 0
                base["sources_checked"][-1] = {
                    **base["sources_checked"][-1],
                    "available": avail,
                    "origin": "provider_api",
                    "records_count": len(live),
                    "called": True,
                }
                if avail:
                    if include_raw:
                        raw_payloads["fixture_events"] = live
                    _scan("fixture_events", live, "api_response")
            except Exception as exc:
                base["warnings"].append(f"fixture_events_api_error:{exc}")

    # 8. team statistics
    league_id = ids.get("provider_league_id")
    season = ids.get("season")
    for side_key, team, provider_team_id in (
        ("team_statistics_home", home_team, ids.get("provider_home_team_id")),
        ("team_statistics_away", away_team, ids.get("provider_away_team_id")),
    ):
        if not _endpoint_enabled(side_key, enabled):
            continue
        _check_source(side_key, available=False, origin="db_cache", records_count=0)
        if force_refresh and api_client is not None and league_id and season and provider_team_id:
            try:
                body = api_client.get(
                    "teams/statistics",
                    {"league": int(league_id), "season": int(season), "team": int(provider_team_id)},
                )
                external_calls.append(side_key)
                resp = body.get("response")
                avail = resp is not None and resp != {}
                base["sources_checked"][-1] = {
                    **base["sources_checked"][-1],
                    "available": avail,
                    "origin": "provider_api",
                    "records_count": 1 if avail else 0,
                    "called": True,
                }
                if avail:
                    if include_raw:
                        raw_payloads[side_key] = resp
                    _scan(side_key, resp, "api_response")
            except Exception as exc:
                base["warnings"].append(f"{side_key}_api_error:{exc}")

    base["matches_found"] = all_matches[:MAX_MATCHES]
    base["suggested_xg_mapping"] = build_suggested_xg_mapping(
        base["matches_found"],
        home_team=home_team,
        away_team=away_team,
        statistics_payloads=statistics_payloads,
    )
    base["api_usage"] = {
        "force_refresh": bool(force_refresh),
        "external_calls_made": len(external_calls),
        "endpoints_called": external_calls,
        "note": "Manual inspection only",
    }

    any_available = any(s.get("available") for s in base["sources_checked"])
    base["status"] = "available" if any_available or base["matches_found"] else "partial"

    if include_raw:
        base["raw_payloads"] = raw_payloads

    if force_refresh and not external_calls and not any_available:
        base["warnings"].append("no_cached_data_and_no_api_calls")

    return base
