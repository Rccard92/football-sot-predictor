from __future__ import annotations

from typing import Any

from .math_utils import cap, round2


def compute_h2h_adjustment(
    *,
    baseline_expected_sot: float,
    h2h_summary: dict[str, Any],
    is_home: bool,
) -> tuple[float, dict[str, Any]]:
    if not h2h_summary or h2h_summary.get("h2h_fetch_ok") is not True:
        return 0.0, {"status": "not_available"}
    if not h2h_summary.get("h2h_sot_available"):
        return 0.0, {"status": "not_available", "explanation": "SOT H2H non disponibile."}
    matches_total = int(h2h_summary.get("matches_total") or 0)
    sample_limited = bool(h2h_summary.get("h2h_sample_limited"))
    if matches_total < 5:
        return 0.0, {"status": "not_reliable", "h2h_matches_total": matches_total}
    team_avg = h2h_summary.get("avg_home_sot") if is_home else h2h_summary.get("avg_away_sot")
    if team_avg is None:
        return 0.0, {"status": "not_available", "h2h_matches_total": matches_total}
    h2h_diff = float(team_avg) - float(baseline_expected_sot)
    adj = h2h_diff * 0.10
    if sample_limited:
        adj = cap(adj, -0.10, 0.10)
    else:
        adj = cap(adj, -0.20, 0.20)
    return round2(adj), {
        "status": "applied",
        "h2h_matches_total": matches_total,
        "h2h_team_avg_sot": round2(float(team_avg)),
        "h2h_diff": round2(h2h_diff),
        "h2h_adjustment": round2(adj),
        "h2h_sample_limited": sample_limited,
        "explanation": "Adjustment H2H prudente (10% del diff) con cap.",
    }

