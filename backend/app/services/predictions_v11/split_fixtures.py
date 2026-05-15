"""Filtri partite per split casa/trasferta v1.1."""

from __future__ import annotations

from app.models import Fixture


def team_split_fixtures(
    fixtures: list[Fixture],
    team_id: int,
    *,
    is_home_context: bool,
) -> list[Fixture]:
    tid = int(team_id)
    if is_home_context:
        return [f for f in fixtures if int(f.home_team_id) == tid]
    return [f for f in fixtures if int(f.away_team_id) == tid]


def opponent_split_fixtures(
    opponent_fixtures: list[Fixture],
    opponent_id: int,
    *,
    team_is_home: bool,
) -> list[Fixture]:
    """Split avversario opposto al contesto della squadra analizzata."""
    oid = int(opponent_id)
    if team_is_home:
        return [f for f in opponent_fixtures if int(f.away_team_id) == oid]
    return [f for f in opponent_fixtures if int(f.home_team_id) == oid]


def split_context_label(*, is_home: bool) -> str:
    return "home" if is_home else "away"


def opponent_split_context_label(*, team_is_home: bool) -> str:
    return "away" if team_is_home else "home"
