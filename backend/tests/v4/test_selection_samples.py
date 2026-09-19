"""Payload di esempio scritti a mano sulle forme di docs/v4/API.md, condivisi dai test di selezione, spiegazione e misura.

Nessun test qui: solo dati. Milan (casa) - Inter (ospite), Serie A.
"""

from __future__ import annotations

import copy
from typing import Any

from app.services.cecchino_v4.constants import BOOKMAKER_BET365_ID, BOOKMAKER_BETFAIR_ID

HOME = "Milan"
AWAY = "Inter"

FIXTURE_META: dict[str, Any] = {
    "id": 12,
    "fixture_id": 12,
    "api_fixture_id": 1234567,
    "league_code": "I1",
    "competition": "Serie A",
    "season_label": "2025/2026",
    "kickoff_at": "2026-09-21T18:45:00+00:00",
    "home_team": HOME,
    "away_team": AWAY,
    "status": "NS",
    "lineups_status": "non_note",
}


def _m(p: float, width: float = 0.04) -> dict[str, float]:
    return {"p": p, "lo": round(p - width, 4), "hi": round(p + width, 4)}


GOALS_PAYLOAD: dict[str, Any] = {
    "engine_version": "cecchino_v4_goals_v1",
    "lambda_home": 1.2,
    "lambda_away": 1.6,
    "rho": -0.05,
    "ht_share": 0.44,
    "dispersion": {"home": None, "away": None},
    "uncertainty": {
        "score": 0.22,
        "level": "bassa",
        "home_evidence": 34.2,
        "away_evidence": 12.1,
        "disagreement": 0.08,
        "new_team_home": False,
        "new_team_away": False,
    },
    "markets": {
        "HOME": _m(0.30),
        "DRAW": _m(0.28),
        "AWAY": _m(0.42),
        "ONE_X": _m(0.58),
        "X_TWO": _m(0.70),
        "ONE_TWO": _m(0.72),
        "OVER_0_5": _m(0.93, 0.02),
        "UNDER_0_5": _m(0.07, 0.02),
        "OVER_1_5": _m(0.76),
        "UNDER_1_5": _m(0.24),
        "OVER_2_5": _m(0.51),
        "UNDER_2_5": _m(0.49),
        "OVER_3_5": _m(0.29),
        "UNDER_3_5": _m(0.71),
        "HOME_PT": _m(0.27),
        "DRAW_PT": _m(0.45),
        "AWAY_PT": _m(0.28),
        "AH_HOME:-0.5": _m(0.30),
        "AH_AWAY:-0.5": _m(0.42),
        "AH_HOME:+0.25": _m(0.62),
    },
    "ratings": {
        "home": {"attack": 0.05, "defence": 0.02, "attack_rank": 7, "defence_rank": 9, "teams_in_division": 20, "home_advantage": 0.18},
        "away": {"attack": 0.30, "defence": -0.12, "attack_rank": 3, "defence_rank": 6, "teams_in_division": 20, "home_advantage": 0.15},
    },
    "specialists": {
        "forza": {"home": 1.2, "away": 1.6},
        "sot": {"home": 1.3, "away": 1.5},
        "shots": {"home": 1.1, "away": 1.7},
        "weights": {"forza": 0.5, "sot": 0.2, "shots": 0.3},
        "form": {"goals_home": -0.1, "goals_away": 0.05, "shots_home": -0.2, "shots_away": 0.1, "matches_home": 5, "matches_away": 5},
        "calendar": {"rest_days_home": 7, "rest_days_away": 4, "final_phase": False},
    },
    "calibration": {"applied": True, "season": "2024/2025"},
}


def _lines(*pairs: tuple[str, float]) -> dict[str, dict[str, float]]:
    return {line: {"over": p, "lo": round(p - 0.05, 4), "hi": round(p + 0.05, 4)} for line, p in pairs}


STATS_PAYLOAD: dict[str, Any] = {
    "engine_version": "cecchino_v4_stats_v1",
    "stats": {
        "sot": {
            "exam": "superato",
            "home": {"mean": 4.9, "dispersion": None, "division_mean": 4.6, "mean_against": 5.1, "rank_for": 8, "rank_against": 11, "teams_in_division": 20, "lines": _lines(("3.5", 0.71), ("4.5", 0.55))},
            "away": {"mean": 6.8, "dispersion": None, "division_mean": 4.6, "mean_against": 4.2, "rank_for": 4, "rank_against": 3, "teams_in_division": 20, "lines": _lines(("6.5", 0.61), ("7.5", 0.40))},
            "total": {"mean": 11.7, "dispersion": None, "division_mean": 9.2, "lines": _lines(("10.5", 0.58))},
        },
        "corners": {
            "exam": "non_superato",
            "home": {"mean": 5.5, "division_mean": 5.0, "mean_against": 4.8, "rank_for": 6, "lines": _lines(("4.5", 0.65))},
            "away": {"mean": 4.4, "division_mean": 5.0, "mean_against": 5.2, "rank_for": 14, "lines": _lines(("4.5", 0.45))},
        },
    },
}

SOT_KEY = "STAT:sot:away:over:6.5"

ODDS: dict[int, dict[str, float]] = {
    BOOKMAKER_BET365_ID: {
        "HOME": 3.20,
        "DRAW": 3.40,
        "AWAY": 2.30,
        "OVER_2_5": 1.90,
        "UNDER_2_5": 1.95,
        "AH_AWAY:-0.5": 2.30,
        SOT_KEY: 2.30,
        "STAT:corners:home:over:4.5": 1.90,
    },
    BOOKMAKER_BETFAIR_ID: {
        "AWAY": 2.40,
        "UNDER_1_5": 4.20,
        SOT_KEY: 2.40,
    },
}

RESULT = {"ft_home": 1, "ft_away": 2, "ht_home": 0, "ht_away": 1}
ACTUAL_STATS = {
    "home": {"shots": 11, "sot": 3, "corners": 6, "yellow": 2, "red": 0, "fouls": 12},
    "away": {"shots": 16, "sot": 8, "corners": 4, "yellow": 1, "red": 1, "fouls": 14},
}


def goals(**overrides: Any) -> dict[str, Any]:
    payload = copy.deepcopy(GOALS_PAYLOAD)
    for key, value in overrides.items():
        payload[key] = value
    return payload


def stats() -> dict[str, Any]:
    return copy.deepcopy(STATS_PAYLOAD)


def odds() -> dict[int, dict[str, float]]:
    return copy.deepcopy(ODDS)
