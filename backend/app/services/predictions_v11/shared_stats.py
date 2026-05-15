"""Utility di aggregazione statistiche squadra condivise tra i componenti v1.1.

Mantieni questo modulo libero da import circolari: niente offensive_production_strict,
home_away_split_strict, v11_features_debug, route o servizi baseline.
"""

from __future__ import annotations

from typing import Any

from app.models import Fixture


def expected_goals_from_team_stat(st: Any) -> tuple[float | None, str]:
    """Legge expected_goals dalla colonna DB o, se assente, da raw_json (tracciato come fonte alternativa)."""
    if st is None:
        return None, "fixture_team_stats.expected_goals"
    ev = getattr(st, "expected_goals", None)
    if ev is not None:
        try:
            v = float(ev)
            if v == v:
                return v, "fixture_team_stats.expected_goals"
        except (TypeError, ValueError):
            pass
    raw = getattr(st, "raw_json", None)
    if isinstance(raw, dict):
        for k in ("expected_goals", "value"):
            if k in raw:
                try:
                    vv = float(raw[k])
                    if vv == vv:
                        return vv, "fixture_team_stats.raw_json"
                except (TypeError, ValueError):
                    pass
        for block in raw.get("statistics") or []:
            if not isinstance(block, dict):
                continue
            t = str(block.get("type") or "").lower()
            if "expected" in t and "goal" in t:
                val = block.get("value") or block.get("Value")
                try:
                    if val is not None:
                        vv = float(val)
                        if vv == vv:
                            return vv, "fixture_team_stats.raw_json::statistics"
                except (TypeError, ValueError):
                    pass
    return None, "fixture_team_stats.expected_goals"


def agg_for_team(
    *,
    fixtures: list[Fixture],
    stats_map: dict,
    team_id: int,
) -> dict[str, Any]:
    sot_sum = sot_n = 0
    shots_sum = shots_n = 0
    in_sum = in_n = 0
    out_sum = out_n = 0
    blocked_sum = blocked_n = 0
    off_goal_sum = off_goal_n = 0
    goals_sum = goals_n = 0
    xg_sum = 0.0
    xg_n = 0

    for f in fixtures:
        st = stats_map.get((int(f.id), int(team_id)))
        if st and st.shots_on_target is not None:
            sot_sum += int(st.shots_on_target)
            sot_n += 1
        if st and st.total_shots is not None:
            shots_sum += int(st.total_shots)
            shots_n += 1
        if st and st.shots_inside_box is not None:
            in_sum += int(st.shots_inside_box)
            in_n += 1
        if st and st.shots_outside_box is not None:
            out_sum += int(st.shots_outside_box)
            out_n += 1
        if st and st.blocked_shots is not None:
            blocked_sum += int(st.blocked_shots)
            blocked_n += 1
        if st and st.shots_off_target is not None:
            off_goal_sum += int(st.shots_off_target)
            off_goal_n += 1
        gf = f.goals_home if int(f.home_team_id) == int(team_id) else f.goals_away
        if gf is not None:
            goals_sum += int(gf)
            goals_n += 1
        xg, _sp = expected_goals_from_team_stat(st)
        if xg is not None:
            xg_sum += float(xg)
            xg_n += 1

    def mean(sum_: int, n: int) -> float | None:
        return (sum_ / n) if n > 0 else None

    def mean_xg() -> float | None:
        return (xg_sum / xg_n) if xg_n > 0 else None

    return {
        "matches_count": len(fixtures),
        "sot_mean": mean(sot_sum, sot_n),
        "sot_n": sot_n,
        "shots_mean": mean(shots_sum, shots_n),
        "shots_n": shots_n,
        "inside_mean": mean(in_sum, in_n),
        "inside_n": in_n,
        "outside_mean": mean(out_sum, out_n),
        "outside_n": out_n,
        "blocked_mean": mean(blocked_sum, blocked_n),
        "blocked_n": blocked_n,
        "off_goal_mean": mean(off_goal_sum, off_goal_n),
        "off_goal_n": off_goal_n,
        "goals_mean": mean(goals_sum, goals_n),
        "goals_n": goals_n,
        "xg_mean": mean_xg(),
        "xg_n": xg_n,
    }
