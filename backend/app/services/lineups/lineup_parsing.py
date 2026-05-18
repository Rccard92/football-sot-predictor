"""Parsing puro risposta API-Football fixtures/lineups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedLineupPlayer:
    api_player_id: int | None
    player_name: str
    number: int | None
    position: str | None
    grid: str | None
    is_starter: bool
    is_substitute: bool


def _player_from_entry(entry: Any, *, is_starter: bool) -> ParsedLineupPlayer | None:
    if not isinstance(entry, dict):
        return None
    pl = entry.get("player")
    if not isinstance(pl, dict):
        return None
    name = pl.get("name")
    if not name:
        return None
    api_id = pl.get("id")
    api_player_id: int | None = None
    if api_id is not None:
        try:
            api_player_id = int(api_id)
        except (TypeError, ValueError):
            api_player_id = None
    num = pl.get("number")
    number: int | None = None
    if num is not None:
        try:
            number = int(num)
        except (TypeError, ValueError):
            number = None
    pos = pl.get("pos")
    position = str(pos)[:16] if pos is not None else None
    grid = pl.get("grid")
    grid_str = str(grid)[:16] if grid is not None else None
    return ParsedLineupPlayer(
        api_player_id=api_player_id,
        player_name=str(name)[:255],
        number=number,
        position=position,
        grid=grid_str,
        is_starter=is_starter,
        is_substitute=not is_starter,
    )


def parse_lineup_player_lists(
    start_xi: Any,
    substitutes: Any,
) -> tuple[list[ParsedLineupPlayer], list[ParsedLineupPlayer]]:
    starters: list[ParsedLineupPlayer] = []
    subs: list[ParsedLineupPlayer] = []
    if isinstance(start_xi, list):
        for entry in start_xi:
            row = _player_from_entry(entry, is_starter=True)
            if row:
                starters.append(row)
    if isinstance(substitutes, list):
        for entry in substitutes:
            row = _player_from_entry(entry, is_starter=False)
            if row:
                subs.append(row)
    return starters, subs


def parse_api_lineup_block(block: dict[str, Any]) -> tuple[str | None, str | None, list[ParsedLineupPlayer], list[ParsedLineupPlayer]]:
    """Estrae formation, coach_name, starters, substitutes da un team block API."""
    formation = block.get("formation")
    formation_str = str(formation)[:32] if formation else None
    coach_name: str | None = None
    coach = block.get("coach")
    if isinstance(coach, dict):
        cn = coach.get("name")
        if cn:
            coach_name = str(cn)[:255]
    start_xi = block.get("startXI")
    substitutes = block.get("substitutes")
    starters, subs = parse_lineup_player_lists(start_xi, substitutes)
    return formation_str, coach_name, starters, subs


def block_has_official_lineup(block: dict[str, Any]) -> bool:
    start_xi = block.get("startXI")
    return isinstance(start_xi, list) and len(start_xi) > 0
