from __future__ import annotations

from typing import Any

from .math_utils import cap, round2


def compute_motivation_adjustment(
    *,
    team_context: dict[str, Any] | None,
    opp_context: dict[str, Any] | None,
) -> tuple[float, dict[str, Any]]:
    if not team_context:
        return 0.0, {"status": "not_available"}
    motivation = str(team_context.get("motivation_level") or "incerta")
    objective = str(team_context.get("competition_objective") or "incerto")
    turnover = str(team_context.get("turnover_risk") or "incerto")
    late = bool(team_context.get("late_season_risk"))
    opp_motivation = str((opp_context or {}).get("motivation_level") or "incerta")
    adj = 0.0
    if motivation == "alta" and opp_motivation == "bassa":
        adj += 0.15
    if motivation == "bassa" and turnover == "alto":
        adj -= 0.20
    if objective in ("gia_campione", "nessun_obiettivo_chiaro") and turnover == "alto":
        adj -= 0.20
    if objective in ("champions", "salvezza") and motivation == "alta":
        adj += 0.15
    elif objective in ("champions", "salvezza"):
        adj += 0.10
    if late and motivation == "incerta":
        adj += 0.0
    adj = cap(adj, -0.25, 0.25)
    return round2(adj), {
        "status": "applied",
        "motivation_level": motivation,
        "competition_objective": objective,
        "turnover_risk": turnover,
        "late_season_risk": late,
        "adjustment": round2(adj),
        "explanation": "Adjustment motivation/context prudente con cap ±0.25.",
    }

