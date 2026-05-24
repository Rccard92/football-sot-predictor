"""Parser cartellini da statistiche API-Football o righe fixture_team_stats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.fixture_team_stats_mapping import _parse_int, _norm_label, statistics_list_to_fields


CARD_LABEL_ALIASES: dict[str, str] = {
    "yellow cards": "yellow_cards",
    "red cards": "red_cards",
    "cartellini gialli": "yellow_cards",
    "cartellini rossi": "red_cards",
    "second yellow card": "second_yellow_red_cards",
    "second yellow cards": "second_yellow_red_cards",
}


EVENT_YELLOW_TYPES = frozenset({"yellow card", "yellowcard"})
EVENT_RED_TYPES = frozenset({"red card", "redcard"})
EVENT_SECOND_YELLOW_TYPES = frozenset({"second yellow card", "second yellow"})


@dataclass
class MatchCardsBySide:
    total_yellow: int | None
    total_red: int | None
    home_yellow: int | None
    home_red: int | None
    away_yellow: int | None
    away_red: int | None

    def has_data(self) -> bool:
        return any(
            v is not None
            for v in (
                self.total_yellow,
                self.total_red,
                self.home_yellow,
                self.home_red,
                self.away_yellow,
                self.away_red,
            )
        )


@dataclass
class MatchCards:
    yellow_cards: int | None
    red_cards: int | None
    straight_red_cards: int | None
    second_yellow_red_cards: int | None

    @property
    def red_cards_total(self) -> int | None:
        parts = [self.red_cards, self.straight_red_cards, self.second_yellow_red_cards]
        vals = [int(v) for v in parts if v is not None]
        if not vals and self.red_cards is None:
            return None
        return sum(vals)


def _sum_optional(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return int(a or 0) + int(b or 0)


def _cards_from_statistics_list(statistics: list[dict[str, Any]] | None) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for item in statistics or []:
        label = _norm_label(str(item.get("type") or ""))
        key = CARD_LABEL_ALIASES.get(label)
        if not key:
            continue
        out[key] = _parse_int(item.get("value"))
    return out


def cards_from_team_stat_row(row: Any) -> dict[str, int | None]:
    return {
        "yellow_cards": getattr(row, "yellow_cards", None),
        "red_cards": getattr(row, "red_cards", None),
        "second_yellow_red_cards": None,
    }


def match_cards_from_team_stats_rows(home_row: Any | None, away_row: Any | None) -> MatchCards:
    home = cards_from_team_stat_row(home_row) if home_row is not None else {}
    away = cards_from_team_stat_row(away_row) if away_row is not None else {}
    yellow = _sum_optional(home.get("yellow_cards"), away.get("yellow_cards"))
    red = _sum_optional(home.get("red_cards"), away.get("red_cards"))
    return MatchCards(
        yellow_cards=yellow,
        red_cards=red,
        straight_red_cards=None,
        second_yellow_red_cards=None,
    )


def match_cards_from_statistics_response(blocks: list[dict[str, Any]] | None) -> MatchCards:
    """Somma home + away da payload GET /fixtures/statistics."""
    total_yellow = 0
    total_red = 0
    total_second_yellow = 0
    has_yellow = False
    has_red = False
    has_sy = False

    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        parsed = _cards_from_statistics_list(block.get("statistics"))
        y = parsed.get("yellow_cards")
        r = parsed.get("red_cards")
        sy = parsed.get("second_yellow_red_cards")
        if y is not None:
            has_yellow = True
            total_yellow += int(y)
        if r is not None:
            has_red = True
            total_red += int(r)
        if sy is not None:
            has_sy = True
            total_second_yellow += int(sy)

    return MatchCards(
        yellow_cards=total_yellow if has_yellow else None,
        red_cards=total_red if has_red else None,
        straight_red_cards=None,
        second_yellow_red_cards=total_second_yellow if has_sy else None,
    )


def match_cards_from_statistics_blocks_using_mapping(blocks: list[dict[str, Any]] | None) -> MatchCards:
    """Fallback via mapping condiviso fixture_team_stats."""
    total_yellow = 0
    total_red = 0
    found = False
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        fields = statistics_list_to_fields(block.get("statistics"))
        y = fields.get("yellow_cards")
        r = fields.get("red_cards")
        if y is not None:
            found = True
            total_yellow += int(y)
        if r is not None:
            found = True
            total_red += int(r)
    if not found:
        return match_cards_from_statistics_response(blocks)
    return MatchCards(yellow_cards=total_yellow, red_cards=total_red, straight_red_cards=None, second_yellow_red_cards=None)


def _norm_event_type(val: Any) -> str:
    return _norm_label(str(val or ""))


def _team_api_id(team_obj: Any) -> int | None:
    if not isinstance(team_obj, dict):
        return None
    tid = team_obj.get("id")
    try:
        return int(tid) if tid is not None else None
    except (TypeError, ValueError):
        return None


def match_cards_from_events(
    events: list[dict[str, Any]] | None,
    *,
    home_team_api_id: int | None,
    away_team_api_id: int | None,
) -> MatchCardsBySide:
    """Conta cartellini da GET /fixtures/events per squadra."""
    home_yellow = home_red = away_yellow = away_red = 0
    has_home = home_team_api_id is not None
    has_away = away_team_api_id is not None
    found = False

    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        et = _norm_event_type(ev.get("type"))
        team_id = _team_api_id(ev.get("team"))
        if team_id is None:
            continue

        is_yellow = et in EVENT_YELLOW_TYPES
        is_red = et in EVENT_RED_TYPES or et in EVENT_SECOND_YELLOW_TYPES
        if not is_yellow and not is_red:
            continue

        found = True
        if has_home and int(team_id) == int(home_team_api_id):
            if is_yellow:
                home_yellow += 1
            if is_red:
                home_red += 1
        elif has_away and int(team_id) == int(away_team_api_id):
            if is_yellow:
                away_yellow += 1
            if is_red:
                away_red += 1

    if not found:
        return MatchCardsBySide(
            total_yellow=None,
            total_red=None,
            home_yellow=None,
            home_red=None,
            away_yellow=None,
            away_red=None,
        )

    total_yellow = home_yellow + away_yellow
    total_red = home_red + away_red
    return MatchCardsBySide(
        total_yellow=total_yellow,
        total_red=total_red,
        home_yellow=home_yellow,
        home_red=home_red,
        away_yellow=away_yellow,
        away_red=away_red,
    )


def match_cards_by_side_from_statistics_blocks(
    blocks: list[dict[str, Any]] | None,
    *,
    home_team_api_id: int | None,
    away_team_api_id: int | None,
) -> MatchCardsBySide:
    """Cartellini per lato da blocchi statistics (team.id nel blocco)."""
    home_yellow = home_red = away_yellow = away_red = 0
    found = False
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        team_id = _team_api_id(block.get("team"))
        parsed = _cards_from_statistics_list(block.get("statistics"))
        y = parsed.get("yellow_cards")
        r = parsed.get("red_cards")
        sy = parsed.get("second_yellow_red_cards")
        red_total = int(r or 0) + int(sy or 0) if (r is not None or sy is not None) else None
        if y is None and red_total is None:
            continue
        found = True
        if home_team_api_id is not None and team_id == home_team_api_id:
            home_yellow += int(y or 0)
            home_red += int(red_total or 0)
        elif away_team_api_id is not None and team_id == away_team_api_id:
            away_yellow += int(y or 0)
            away_red += int(red_total or 0)
    if not found:
        agg = match_cards_from_statistics_blocks_using_mapping(blocks)
        if agg.yellow_cards is None and agg.red_cards_total is None:
            return MatchCardsBySide(None, None, None, None, None, None)
        return MatchCardsBySide(
            total_yellow=agg.yellow_cards,
            total_red=agg.red_cards_total,
            home_yellow=None,
            home_red=None,
            away_yellow=None,
            away_red=None,
        )
    return MatchCardsBySide(
        total_yellow=home_yellow + away_yellow,
        total_red=home_red + away_red,
        home_yellow=home_yellow,
        home_red=home_red,
        away_yellow=away_yellow,
        away_red=away_red,
    )


def cards_by_side_from_team_stats_rows(home_row: Any | None, away_row: Any | None) -> MatchCardsBySide:
    home = cards_from_team_stat_row(home_row) if home_row is not None else {}
    away = cards_from_team_stat_row(away_row) if away_row is not None else {}
    hy, hr = home.get("yellow_cards"), home.get("red_cards")
    ay, ar = away.get("yellow_cards"), away.get("red_cards")
    if hy is None and hr is None and ay is None and ar is None:
        return MatchCardsBySide(None, None, None, None, None, None)
    return MatchCardsBySide(
        total_yellow=int(hy or 0) + int(ay or 0),
        total_red=int(hr or 0) + int(ar or 0),
        home_yellow=hy,
        home_red=hr,
        away_yellow=ay,
        away_red=ar,
    )
