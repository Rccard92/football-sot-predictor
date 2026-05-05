from __future__ import annotations

from typing import Any

from .math_utils import cap, round2


def compute_player_adjustment(
    *,
    team_top5_avg_impact: float | None,
    league_avg_top5_impact: float | None,
) -> tuple[float, dict[str, Any]]:
    if team_top5_avg_impact is None or league_avg_top5_impact is None or league_avg_top5_impact <= 0:
        return 0.0, {
            "status": "not_available",
            "explanation": "Profili giocatore non sufficienti per calcolare adjustment.",
        }
    ratio = team_top5_avg_impact / league_avg_top5_impact
    if ratio >= 1.25:
        adj = 0.35
    elif ratio >= 1.10:
        adj = 0.20
    elif ratio <= 0.75:
        adj = -0.35
    elif ratio <= 0.90:
        adj = -0.20
    else:
        adj = 0.0
    adj = cap(adj, -0.35, 0.35)
    return round2(adj), {
        "status": "applied",
        "team_top5_avg_impact": round2(team_top5_avg_impact),
        "league_avg_top5_impact": round2(league_avg_top5_impact),
        "player_strength_ratio": round(ratio, 4),
        "adjustment": round2(adj),
        "explanation": "Adjustment player impact applicato con regole prudenti e cap ±0.35.",
    }

