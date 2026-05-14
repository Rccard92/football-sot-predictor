"""Scan reale API-Football → catalogo campi diretti (flatten + persistenza)."""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import FINISHED_STATUSES, fixture_eligible_for_upcoming_sot
from app.models import Fixture, FixtureLineup, FixturePlayerStat, FixtureTeamStat, Player, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.api_football_direct_catalog_areas import AREA_ORDER, classify_macro_area
from app.services.api_football_direct_catalog_infer import (
    infer_db_status,
    infer_model_v04,
    refine_db_with_raw_json,
)
from app.services.api_football_direct_catalog_io import save_direct_catalog_cache
from app.services.api_football_direct_catalog_labels import (
    advanced_metric_note,
    description_it,
    label_for_path,
    tooltip_for_name,
)
from app.services.api_football_json_flatten import flatten_json, flatten_response_union
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

CATALOG_VERSION = "api_football_direct_catalog_v0_1"


@dataclass
class _FieldAgg:
    json_path: str
    endpoint: str
    sample_value: Any
    sample_type: str
    examples_count: int
    endpoints: set[str] = field(default_factory=set)

    def merge(self, ep: str, row: dict[str, Any]) -> None:
        self.endpoints.add(ep)
        self.examples_count += int(row.get("examples_count") or 1)
        if self.sample_value is None and row.get("sample_value") is not None:
            self.sample_value = row.get("sample_value")
            self.sample_type = str(row.get("sample_type") or "stringa")


def _stable_id(endpoint: str, json_path: str) -> str:
    return f"{endpoint}::{json_path}"


def _collect_raw_json_path_set(db: Session, season_id: int) -> set[str]:
    """Unione path appiattiti da raw_json su fixture e statistiche collegate."""
    paths: set[str] = set()
    fx_rows = db.scalars(
        select(Fixture)
        .where(Fixture.season_id == season_id, Fixture.raw_json.isnot(None))
        .order_by(Fixture.kickoff_at.desc())
        .limit(4),
    ).all()
    for fx in fx_rows:
        if isinstance(fx.raw_json, dict):
            rows = flatten_json(fx.raw_json, prefix="", max_paths=2500)
            for r in rows:
                paths.add(str(r["json_path"]))
        for r in db.scalars(
            select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == fx.id, FixtureTeamStat.raw_json.isnot(None)),
        ).all():
            if isinstance(r.raw_json, dict):
                for row in flatten_json(r.raw_json, prefix="", max_paths=1200):
                    paths.add(str(row["json_path"]))
        for r in db.scalars(
            select(FixturePlayerStat).where(
                FixturePlayerStat.fixture_id == fx.id,
                FixturePlayerStat.raw_json.isnot(None),
            ),
        ).all():
            if isinstance(r.raw_json, dict):
                for row in flatten_json(r.raw_json, prefix="", max_paths=1200):
                    paths.add(str(row["json_path"]))
        for r in db.scalars(
            select(FixtureLineup).where(FixtureLineup.fixture_id == fx.id, FixtureLineup.raw_json.isnot(None)),
        ).all():
            if isinstance(r.raw_json, dict):
                for row in flatten_json(r.raw_json, prefix="", max_paths=800):
                    paths.add(str(row["json_path"]))
    return paths


def _path_in_raw(json_path: str, raw_paths: set[str]) -> bool:
    if json_path in raw_paths:
        return True
    for rp in raw_paths:
        if rp.endswith(json_path) or json_path.endswith(rp):
            return True
    return False


@dataclass
class _ScanCtx:
    league_api_id: int
    season_year: int
    season_id: int
    completed_api_fixture_ids: list[int]
    upcoming_api_fixture_ids: list[int]
    team_api_ids: list[int]
    player_api_ids: list[int]
    h2h_pair: tuple[int, int] | None


def _build_scan_context(db: Session, season_year: int) -> _ScanCtx:
    ing = IngestionService()
    league = ing._serie_a_league_by_settings(db)
    season_row = ing._serie_a_season_row(db, season_year)
    sid = int(season_row.id)

    completed = db.scalars(
        select(Fixture)
        .where(Fixture.season_id == sid, Fixture.status.in_(FINISHED_STATUSES))
        .order_by(Fixture.kickoff_at.desc())
        .limit(8),
    ).all()
    upcoming_all = db.scalars(
        select(Fixture).where(Fixture.season_id == sid).order_by(Fixture.kickoff_at.asc()).limit(80),
    ).all()
    upcoming: list[Fixture] = []
    for fx in upcoming_all:
        if fixture_eligible_for_upcoming_sot(fx.status, fx.kickoff_at):
            upcoming.append(fx)
        if len(upcoming) >= 8:
            break

    comp_ids = [int(f.api_fixture_id) for f in completed[:5] if f.api_fixture_id]
    up_ids = [int(f.api_fixture_id) for f in upcoming[:5] if f.api_fixture_id]

    team_api_ids: list[int] = []
    seen_t: set[int] = set()
    for t in db.scalars(select(Team).limit(24)):
        tid = int(t.api_team_id)
        if tid not in seen_t:
            seen_t.add(tid)
            team_api_ids.append(tid)

    plist = db.scalars(select(Player).where(Player.team_id.isnot(None)).limit(12)).all()
    player_api_ids = [int(p.api_player_id) for p in plist if p.api_player_id]

    h2h_pair: tuple[int, int] | None = None
    if completed:
        fx0 = completed[0]
        ht = db.get(Team, fx0.home_team_id)
        at = db.get(Team, fx0.away_team_id)
        if ht and at:
            h2h_pair = (int(ht.api_team_id), int(at.api_team_id))

    return _ScanCtx(
        league_api_id=int(league.api_league_id),
        season_year=season_year,
        season_id=sid,
        completed_api_fixture_ids=comp_ids,
        upcoming_api_fixture_ids=up_ids,
        team_api_ids=team_api_ids[:5],
        player_api_ids=player_api_ids[:8],
        h2h_pair=h2h_pair,
    )


def run_serie_a_direct_catalog_scan(db: Session, season_year: int) -> dict[str, Any]:
    settings = get_settings()
    if not (settings.api_football_key or "").strip():
        raise ApiFootballError("API_FOOTBALL_KEY non configurata")

    ctx = _build_scan_context(db, season_year)
    client = ApiFootballClient()
    raw_paths = _collect_raw_json_path_set(db, ctx.season_id)

    aggs: dict[str, _FieldAgg] = {}
    diagnostics: list[dict[str, Any]] = []

    def ingest_flat(endpoint: str, rows: list[dict[str, Any]]) -> int:
        n = 0
        for row in rows:
            jp = str(row["json_path"])
            sid = _stable_id(endpoint, jp)
            if sid not in aggs:
                aggs[sid] = _FieldAgg(
                    json_path=jp,
                    endpoint=endpoint,
                    sample_value=row.get("sample_value"),
                    sample_type=str(row.get("sample_type") or "stringa"),
                    examples_count=int(row.get("examples_count") or 1),
                    endpoints={endpoint},
                )
            else:
                aggs[sid].merge(endpoint, row)
            n += 1
        return n

    def call(name: str, params: dict[str, Any], fn: Callable[[], dict[str, Any]]) -> None:
        try:
            body = fn()
            rows = flatten_response_union(body, max_list_items=5, max_paths_per_item=5000)
            n = ingest_flat(name, rows)
            diagnostics.append(
                {
                    "endpoint": name,
                    "params": params,
                    "status": "ok",
                    "fields_found": n,
                    "error": None,
                },
            )
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(
                {
                    "endpoint": name,
                    "params": params,
                    "status": "error",
                    "fields_found": 0,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "trace": traceback.format_exc()[-2000:],
                },
            )

    lid, sy = ctx.league_api_id, ctx.season_year

    call("status", {}, lambda: client.get("status"))
    call("timezone", {}, lambda: client.get("timezone"))
    call("countries", {}, lambda: client.get("countries", {"search": "Italy"}))
    call("leagues", {"id": lid, "season": sy}, lambda: client.get("leagues", {"id": lid, "season": sy}))
    call("seasons", {"league": lid}, lambda: client.get("seasons", {"league": lid}))

    call("teams", {"league": lid, "season": sy}, lambda: client.get("teams", {"league": lid, "season": sy}))

    for tid in ctx.team_api_ids[:3]:
        call(
            "teams/statistics",
            {"league": lid, "season": sy, "team": tid},
            lambda tid=tid: client.get("teams/statistics", {"league": lid, "season": sy, "team": tid}),
        )

    call("standings", {"league": lid, "season": sy}, lambda: client.get("standings", {"league": lid, "season": sy}))
    call("fixtures", {"league": lid, "season": sy}, lambda: client.get("fixtures", {"league": lid, "season": sy}))
    call("fixtures/rounds", {"league": lid, "season": sy}, lambda: client.get("fixtures/rounds", {"league": lid, "season": sy}))

    if ctx.h2h_pair:
        a, b = ctx.h2h_pair
        call(
            "fixtures/headtohead",
            {"h2h": f"{a}-{b}"},
            lambda: client.get("fixtures/headtohead", {"h2h": f"{a}-{b}"}),
        )

    for fx_id in ctx.completed_api_fixture_ids[:4]:
        call(
            "fixtures/statistics",
            {"fixture": fx_id},
            lambda fx_id=fx_id: client.get("fixtures/statistics", {"fixture": fx_id}),
        )
        call(
            "fixtures/events",
            {"fixture": fx_id},
            lambda fx_id=fx_id: client.get("fixtures/events", {"fixture": fx_id}),
        )
        call(
            "fixtures/lineups",
            {"fixture": fx_id},
            lambda fx_id=fx_id: client.get("fixtures/lineups", {"fixture": fx_id}),
        )
        call(
            "fixtures/players",
            {"fixture": fx_id},
            lambda fx_id=fx_id: client.get("fixtures/players", {"fixture": fx_id}),
        )

    for tid in ctx.team_api_ids[:2]:
        call(
            "players",
            {"league": lid, "season": sy, "team": tid},
            lambda tid=tid: client.get("players", {"league": lid, "season": sy, "team": tid}),
        )
        call(
            "players/squads",
            {"team": tid},
            lambda tid=tid: client.get("players/squads", {"team": tid}),
        )

    if ctx.player_api_ids:
        pid = ctx.player_api_ids[0]
        call("players/seasons", {"player": pid}, lambda: client.get("players/seasons", {"player": pid}))

    for ep_name, extra in (
        ("players/topscorers", {"league": lid, "season": sy}),
        ("players/topassists", {"league": lid, "season": sy}),
        ("players/topyellowcards", {"league": lid, "season": sy}),
        ("players/topredcards", {"league": lid, "season": sy}),
    ):
        call(ep_name, extra, lambda ep_name=ep_name, extra=extra: client.get(ep_name, extra))

    call("injuries", {"league": lid, "season": sy}, lambda: client.get("injuries", {"league": lid, "season": sy}))

    for tid in ctx.team_api_ids[:2]:
        call("transfers", {"team": tid}, lambda tid=tid: client.get("transfers", {"team": tid}))

    if ctx.team_api_ids:
        call("trophies", {"team": ctx.team_api_ids[0]}, lambda: client.get("trophies", {"team": ctx.team_api_ids[0]}))

    if ctx.player_api_ids:
        call(
            "sidelined",
            {"player": ctx.player_api_ids[0]},
            lambda: client.get("sidelined", {"player": ctx.player_api_ids[0]}),
        )

    if ctx.team_api_ids:
        tid0 = ctx.team_api_ids[0]
        for coach_ep in ("coachs", "coaches"):
            try:
                body = client.get(coach_ep, {"team": tid0})
                rows = flatten_response_union(body, max_list_items=5, max_paths_per_item=5000)
                n = ingest_flat(coach_ep, rows)
                diagnostics.append(
                    {
                        "endpoint": coach_ep,
                        "params": {"team": tid0},
                        "status": "ok",
                        "fields_found": n,
                        "error": None,
                    },
                )
                break
            except Exception as exc:  # noqa: BLE001
                diagnostics.append(
                    {
                        "endpoint": coach_ep,
                        "params": {"team": tid0},
                        "status": "error",
                        "fields_found": 0,
                        "error": str(exc),
                    },
                )

    uf = ctx.upcoming_api_fixture_ids[:2]
    if uf:
        call("odds", {"fixture": uf[0]}, lambda: client.get("odds", {"fixture": uf[0]}))
        call("odds/live", {"fixture": uf[0]}, lambda: client.get("odds/live", {"fixture": uf[0]}))
        call("predictions", {"fixture": uf[0]}, lambda: client.get("predictions", {"fixture": uf[0]}))

    # --- build field records ---
    records: list[dict[str, Any]] = []
    for sid_key, agg in aggs.items():
        ep = sorted(agg.endpoints)[0]
        jp = agg.json_path
        area_id = classify_macro_area(ep, jp)
        name_it, auto = label_for_path(jp)
        note = advanced_metric_note(jp, agg.sample_value)
        db_st, hint = infer_db_status(ep, jp)
        db_st = refine_db_with_raw_json(db_st, _path_in_raw(jp, raw_paths))
        m04 = infer_model_v04(ep, jp)
        tip = tooltip_for_name(name_it)
        records.append(
            {
                "stable_id": sid_key,
                "json_path": jp,
                "endpoint": ep,
                "appeared_in_endpoints": sorted(agg.endpoints),
                "area_id": area_id,
                "technical_name": jp.split(".")[-1][:120],
                "name_it": name_it,
                "name_it_auto": auto,
                "description_it": description_it(name_it, jp, ep),
                "tooltip_it": tip,
                "sample_value": agg.sample_value,
                "sample_type": agg.sample_type,
                "examples_count": agg.examples_count,
                "appeared_in_raw_json": _path_in_raw(jp, raw_paths),
                "api_label": "found_in_scan",
                "db_status": db_st,
                "db_location_hint": hint,
                "model_v04_status": m04,
                "note_it": note,
            },
        )

    # macro areas
    by_area: dict[str, list[dict[str, Any]]] = {a[0]: [] for a in AREA_ORDER}
    for r in records:
        by_area.setdefault(r["area_id"], []).append(r)

    areas_out: list[dict[str, Any]] = []
    for aid, title in AREA_ORDER:
        params = by_area.get(aid, [])
        ep_set = sorted({e for p in params for e in p.get("appeared_in_endpoints") or [p["endpoint"]]})
        saved_n = sum(1 for p in params if p.get("db_status") == "saved_column")
        raw_n = sum(1 for p in params if p.get("db_status") == "raw_json_only")
        v04_n = sum(1 for p in params if p.get("model_v04_status") == "used_v04")
        areas_out.append(
            {
                "id": aid,
                "title": title,
                "endpoints": ep_set,
                "direct_fields_found": len(params),
                "fields_saved_in_db": saved_n,
                "fields_raw_json_only": raw_n,
                "fields_used_by_v04": v04_n,
                "parameters": sorted(params, key=lambda x: (x["endpoint"], x["json_path"])),
            },
        )

    summary = {
        "endpoints_scanned": len([d for d in diagnostics if d.get("status") == "ok"]),
        "endpoints_errors": len([d for d in diagnostics if d.get("status") == "error"]),
        "direct_fields_found": len(records),
        "fields_used_by_v04": sum(1 for r in records if r["model_v04_status"] == "used_v04"),
        "fields_saved_in_db": sum(1 for r in records if r["db_status"] == "saved_column"),
        "fields_raw_json_only": sum(1 for r in records if r["db_status"] == "raw_json_only"),
    }

    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "version": CATALOG_VERSION,
        "season": season_year,
        "provider": "API-Football / API-Sports",
        "last_scan_at": now,
        "summary": summary,
        "areas": areas_out,
        "diagnostics": diagnostics,
    }
    save_direct_catalog_cache(payload)
    return payload
