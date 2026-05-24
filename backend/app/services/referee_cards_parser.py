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
