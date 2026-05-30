"""Market Registry — definizioni mercato per Backtest Engine (stub Step A).

Non importato da servizi runtime esistenti finché non si implementa Step B+.
Vedi docs/BACKTEST_ENGINE_ARCHITECTURE.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MarketStatus = Literal["active", "planned", "deprecated"]
BetType = Literal["over_under_total", "team_over_under"]

MARKET_SHOTS_ON_TARGET = "shots_on_target"
MARKET_CORNERS = "corners"
MARKET_CARDS = "cards"
MARKET_GOALS = "goals"
MARKET_FOULS = "fouls"
MARKET_TOTAL_SHOTS = "total_shots"


@dataclass(frozen=True)
class MarketSpec:
    market_key: str
    label: str
    unit: str
    supported_bet_types: tuple[BetType, ...]
    actual_stat_paths: dict[str, str]
    default_lines: tuple[float, ...]
    status: MarketStatus


MARKET_REGISTRY: dict[str, MarketSpec] = {
    MARKET_SHOTS_ON_TARGET: MarketSpec(
        market_key=MARKET_SHOTS_ON_TARGET,
        label="Tiri in porta",
        unit="SOT",
        supported_bet_types=("over_under_total", "team_over_under"),
        actual_stat_paths={
            "home_team": "fixture_team_stats.shots_on_target",
            "away_team": "fixture_team_stats.shots_on_target",
            "match_total": "derived.sum_home_away_shots_on_target",
        },
        default_lines=(5.5, 6.5, 7.5, 8.5, 9.5),
        status="active",
    ),
    MARKET_CORNERS: MarketSpec(
        market_key=MARKET_CORNERS,
        label="Calci d'angolo",
        unit="corners",
        supported_bet_types=("over_under_total", "team_over_under"),
        actual_stat_paths={
            "home_team": "fixture_team_stats.corner_kicks",
            "away_team": "fixture_team_stats.corner_kicks",
            "match_total": "derived.sum_home_away_corner_kicks",
        },
        default_lines=(8.5, 9.5, 10.5, 11.5),
        status="planned",
    ),
    MARKET_CARDS: MarketSpec(
        market_key=MARKET_CARDS,
        label="Cartellini",
        unit="cards",
        supported_bet_types=("over_under_total", "team_over_under"),
        actual_stat_paths={
            "home_team": "derived.sum_yellow_red_cards",
            "away_team": "derived.sum_yellow_red_cards",
            "match_total": "derived.sum_home_away_cards",
        },
        default_lines=(3.5, 4.5, 5.5),
        status="planned",
    ),
    MARKET_GOALS: MarketSpec(
        market_key=MARKET_GOALS,
        label="Gol",
        unit="goals",
        supported_bet_types=("over_under_total", "team_over_under"),
        actual_stat_paths={
            "home_team": "fixtures.goals_home",
            "away_team": "fixtures.goals_away",
            "match_total": "derived.sum_goals",
        },
        default_lines=(1.5, 2.5, 3.5),
        status="planned",
    ),
    MARKET_FOULS: MarketSpec(
        market_key=MARKET_FOULS,
        label="Falli",
        unit="fouls",
        supported_bet_types=("over_under_total",),
        actual_stat_paths={
            "match_total": "derived.sum_home_away_fouls",
        },
        default_lines=(20.5, 22.5, 24.5),
        status="planned",
    ),
    MARKET_TOTAL_SHOTS: MarketSpec(
        market_key=MARKET_TOTAL_SHOTS,
        label="Tiri totali",
        unit="shots",
        supported_bet_types=("over_under_total", "team_over_under"),
        actual_stat_paths={
            "home_team": "fixture_team_stats.total_shots",
            "away_team": "fixture_team_stats.total_shots",
            "match_total": "derived.sum_home_away_total_shots",
        },
        default_lines=(18.5, 20.5, 22.5, 24.5),
        status="planned",
    ),
}


def get_market(market_key: str) -> MarketSpec | None:
    return MARKET_REGISTRY.get(market_key)


def list_active_markets() -> list[MarketSpec]:
    return [m for m in MARKET_REGISTRY.values() if m.status == "active"]
