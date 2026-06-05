"""Helper display Cecchino Today — status partita, score, loghi."""

from __future__ import annotations

from typing import Any

from app.models.cecchino_today_fixture import (
    MATCH_CANCELLED,
    MATCH_FINISHED,
    MATCH_LIVE,
    MATCH_POSTPONED,
    MATCH_UNKNOWN,
    MATCH_UPCOMING,
    CecchinoTodayFixture,
)

_LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE"})
_FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})
_POSTPONED_STATUSES = frozenset({"PST", "SUSP", "INT"})
_CANCELLED_STATUSES = frozenset({"CANC", "ABD", "AWD", "WO"})
_UPCOMING_STATUSES = frozenset({"NS", "TBD"})

_STATUS_LABELS = {
    MATCH_UPCOMING: "Da giocare",
    MATCH_LIVE: "Live",
    MATCH_FINISHED: "Conclusa",
    MATCH_POSTPONED: "Rinviata",
    MATCH_CANCELLED: "Annullata",
    MATCH_UNKNOWN: "Da giocare",
}


def map_fixture_display_status(
    api_short_status: str | None,
    elapsed: int | None = None,
) -> tuple[str, str]:
    short = (api_short_status or "NS").upper()
    if short in _LIVE_STATUSES:
        return MATCH_LIVE, _STATUS_LABELS[MATCH_LIVE]
    if short in _FINISHED_STATUSES:
        return MATCH_FINISHED, _STATUS_LABELS[MATCH_FINISHED]
    if short in _POSTPONED_STATUSES:
        return MATCH_POSTPONED, _STATUS_LABELS[MATCH_POSTPONED]
    if short in _CANCELLED_STATUSES:
        return MATCH_CANCELLED, _STATUS_LABELS[MATCH_CANCELLED]
    if short in _UPCOMING_STATUSES:
        return MATCH_UPCOMING, _STATUS_LABELS[MATCH_UPCOMING]
    if elapsed is not None and short not in _FINISHED_STATUSES:
        return MATCH_LIVE, _STATUS_LABELS[MATCH_LIVE]
    return MATCH_UNKNOWN, _STATUS_LABELS[MATCH_UNKNOWN]


def extract_display_assets(api_item: dict[str, Any]) -> dict[str, Any]:
    league = api_item.get("league") or {}
    teams = api_item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    fx = api_item.get("fixture") or {}
    status_block = fx.get("status") or {}
    goals = api_item.get("goals") or {}
    score = api_item.get("score") or {}
    fulltime = score.get("fulltime") or {}
    short_status = str(status_block.get("short") or "NS")
    elapsed_raw = status_block.get("elapsed")
    elapsed = int(elapsed_raw) if elapsed_raw is not None else None
    display_status, status_label = map_fixture_display_status(short_status, elapsed)

    def _int_or_none(val: Any) -> int | None:
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    return {
        "country_flag_url": league.get("flag") or None,
        "league_logo_url": league.get("logo") or None,
        "home_team_logo_url": home.get("logo") or None,
        "away_team_logo_url": away.get("logo") or None,
        "goals_home": _int_or_none(goals.get("home")),
        "goals_away": _int_or_none(goals.get("away")),
        "score_fulltime_home": _int_or_none(fulltime.get("home")),
        "score_fulltime_away": _int_or_none(fulltime.get("away")),
        "elapsed_minutes": elapsed,
        "fixture_status": short_status,
        "match_display_status": display_status,
        "status_label": status_label,
    }


def apply_display_from_api(row: CecchinoTodayFixture, api_item: dict[str, Any]) -> None:
    assets = extract_display_assets(api_item)
    for key in (
        "country_flag_url",
        "league_logo_url",
        "home_team_logo_url",
        "away_team_logo_url",
        "goals_home",
        "goals_away",
        "score_fulltime_home",
        "score_fulltime_away",
        "elapsed_minutes",
        "fixture_status",
        "match_display_status",
    ):
        setattr(row, key, assets[key])


def status_label_for_row(row: CecchinoTodayFixture) -> str:
    status = row.match_display_status or MATCH_UPCOMING
    return _STATUS_LABELS.get(status, _STATUS_LABELS[MATCH_UNKNOWN])


def row_score_payload(row: CecchinoTodayFixture) -> dict[str, Any]:
    if row.match_display_status == MATCH_FINISHED:
        home = row.score_fulltime_home if row.score_fulltime_home is not None else row.goals_home
        away = row.score_fulltime_away if row.score_fulltime_away is not None else row.goals_away
    else:
        home = row.goals_home
        away = row.goals_away
    available = home is not None and away is not None
    return {"home": home, "away": away, "available": available}


def recommended_prediction_placeholder() -> dict[str, Any]:
    return {
        "status": "pending",
        "label": "In arrivo",
        "market": None,
        "confidence": None,
    }
