"""Filtri partite per split casa/trasferta v1.1."""

from __future__ import annotations

from app.models import Fixture
from app.services.fixture_shared import team_split_fixtures

__all__ = [
    "team_split_fixtures",
    "opponent_split_fixtures",
    "split_context_label",
    "opponent_split_context_label",
]


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
