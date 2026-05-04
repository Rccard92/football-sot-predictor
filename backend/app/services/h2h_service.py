"""Scontri diretti (head-to-head): dati API-Football + integrazione SOT da DB locale."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureTeamStat, Team
from app.services.api_football_client import ApiFootballClient, ApiFootballError


def _parse_ko(item: dict[str, Any]) -> datetime | None:
    fx = item.get("fixture") or {}
    dt = fx.get("date")
    if not dt:
        return None
    s = str(dt).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _total_goals(item: dict[str, Any]) -> int | None:
    g = item.get("goals") or {}
    try:
        h = g.get("home")
        a = g.get("away")
        if h is None or a is None:
            return None
        return int(h) + int(a)
    except (TypeError, ValueError):
        return None


def build_h2h_summary_for_fixture(
    db: Session,
    fixture_id: int,
    client: ApiFootballClient | None = None,
) -> dict[str, Any]:
    c = client or ApiFootballClient()
    fx = db.get(Fixture, fixture_id)
    if fx is None:
        return {"error": "fixture_not_found", "fixture_id": fixture_id}

    home = db.get(Team, fx.home_team_id)
    away = db.get(Team, fx.away_team_id)
    if home is None or away is None:
        return {"error": "teams_not_found", "fixture_id": fixture_id}

    api_home_cur = int(home.api_team_id)
    api_away_cur = int(away.api_team_id)

    try:
        items = c.get_head_to_head(api_home_cur, api_away_cur)
    except ApiFootballError as exc:
        return {
            "fixture_id": fixture_id,
            "h2h_fetch_ok": False,
            "error": str(exc),
            "matches_total": 0,
            "last_5": [],
        }

    sorted_items = sorted(
        (i for i in items if isinstance(i, dict)),
        key=lambda x: _parse_ko(x) or datetime.min,
        reverse=True,
    )

    home_wins = away_wins = draws = 0
    goals_list: list[int] = []
    sot_totals: list[int] = []
    sot_for_home_team_vals: list[int] = []
    sot_for_away_team_vals: list[int] = []

    for it in sorted_items:
        te = it.get("teams") or {}
        th = te.get("home") or {}
        ta = te.get("away") or {}
        try:
            hid = int(th.get("id"))
            aid = int(ta.get("id"))
        except (TypeError, ValueError):
            continue

        h_win = th.get("winner") is True
        a_win = ta.get("winner") is True

        cur_home_won = (hid == api_home_cur and h_win) or (aid == api_home_cur and a_win)
        cur_away_won = (hid == api_away_cur and h_win) or (aid == api_away_cur and a_win)
        if cur_home_won:
            home_wins += 1
        elif cur_away_won:
            away_wins += 1
        else:
            draws += 1

        tg = _total_goals(it)
        if tg is not None:
            goals_list.append(tg)

        fx_obj = it.get("fixture") or {}
        api_fid = fx_obj.get("id")
        if api_fid is None:
            continue
        try:
            local = db.scalar(select(Fixture).where(Fixture.api_fixture_id == int(api_fid)))
        except (TypeError, ValueError):
            local = None
        if not local:
            continue

        team_row_h = db.scalar(select(Team).where(Team.api_team_id == hid))
        team_row_a = db.scalar(select(Team).where(Team.api_team_id == aid))
        if team_row_h is None or team_row_a is None:
            continue
        st_h = db.scalar(
            select(FixtureTeamStat).where(
                FixtureTeamStat.fixture_id == local.id,
                FixtureTeamStat.team_id == team_row_h.id,
            ),
        )
        st_a = db.scalar(
            select(FixtureTeamStat).where(
                FixtureTeamStat.fixture_id == local.id,
                FixtureTeamStat.team_id == team_row_a.id,
            ),
        )
        s_h = int(st_h.shots_on_target) if st_h and st_h.shots_on_target is not None else None
        s_a = int(st_a.shots_on_target) if st_a and st_a.shots_on_target is not None else None
        if s_h is not None and s_a is not None:
            sot_totals.append(s_h + s_a)
            if hid == api_home_cur:
                sot_for_home_team_vals.append(s_h)
                sot_for_away_team_vals.append(s_a)
            elif aid == api_home_cur:
                sot_for_home_team_vals.append(s_a)
                sot_for_away_team_vals.append(s_h)

    n = len(sorted_items)
    avg_goals = round(sum(goals_list) / len(goals_list), 3) if goals_list else None
    h2h_sot_available = len(sot_totals) > 0
    avg_total_sot = round(sum(sot_totals) / len(sot_totals), 3) if sot_totals else None
    avg_home_sot = (
        round(sum(sot_for_home_team_vals) / len(sot_for_home_team_vals), 3)
        if sot_for_home_team_vals
        else None
    )
    avg_away_sot = (
        round(sum(sot_for_away_team_vals) / len(sot_for_away_team_vals), 3)
        if sot_for_away_team_vals
        else None
    )

    last5_compact: list[dict[str, Any]] = []
    for it in sorted_items[:5]:
        fx_o = it.get("fixture") or {}
        goals = it.get("goals") or {}
        last5_compact.append(
            {
                "date": fx_o.get("date"),
                "home_team": (it.get("teams") or {}).get("home", {}).get("name"),
                "away_team": (it.get("teams") or {}).get("away", {}).get("name"),
                "goals_home": goals.get("home"),
                "goals_away": goals.get("away"),
            },
        )

    return {
        "fixture_id": fixture_id,
        "home_team": home.name,
        "away_team": away.name,
        "h2h_fetch_ok": True,
        "matches_total": n,
        "home_team_wins": home_wins,
        "away_team_wins": away_wins,
        "draws": draws,
        "avg_total_goals": avg_goals,
        "avg_home_sot": avg_home_sot,
        "avg_away_sot": avg_away_sot,
        "avg_total_sot": avg_total_sot,
        "h2h_sot_available": h2h_sot_available,
        "same_venue_matches": None,
        "last_5": last5_compact,
    }
