"""
Blend componente offensiva v1.0 (logica allineata a v0.4, solo lettura DB).
Non importa SotPredictionV04OffensiveCoreSotService per non modificare v0.4.
"""

from __future__ import annotations

from typing import Any

from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext

PRUDENTIAL_FALLBACK_SOT = 3.5
PRUDENTIAL_FALLBACK_SHOTS = 12.0
PRUDENTIAL_FALLBACK_ACCURACY = 0.32
PRUDENTIAL_SOT_PER_GOAL = 3.0


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None
    except Exception:
        return None


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _last_n(fixtures: list[Fixture], n: int) -> list[Fixture]:
    xs = sorted(fixtures, key=lambda f: (f.kickoff_at, f.id), reverse=True)[:n]
    return sorted(xs, key=lambda f: (f.kickoff_at, f.id))


def _agg_for_team(
    *,
    fixtures: list[Fixture],
    stats_map: dict,
    team_id: int,
) -> dict[str, Any]:
    sot_sum = sot_n = 0
    shots_sum = shots_n = 0
    in_sum = in_n = 0
    out_sum = out_n = 0
    goals_sum = goals_n = 0

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
        if int(f.home_team_id) == int(team_id):
            gf = f.goals_home
        else:
            gf = f.goals_away
        if gf is not None:
            goals_sum += int(gf)
            goals_n += 1

    def mean(sum_: int, n: int) -> float | None:
        return (sum_ / n) if n > 0 else None

    return {
        "matches_count": len(fixtures),
        "sot_sum": sot_sum,
        "sot_n": sot_n,
        "sot_mean": mean(sot_sum, sot_n),
        "shots_sum": shots_sum,
        "shots_n": shots_n,
        "shots_mean": mean(shots_sum, shots_n),
        "inside_sum": in_sum,
        "inside_n": in_n,
        "inside_mean": mean(in_sum, in_n),
        "outside_sum": out_sum,
        "outside_n": out_n,
        "outside_mean": mean(out_sum, out_n),
        "goals_sum": goals_sum,
        "goals_n": goals_n,
        "goals_mean": mean(goals_sum, goals_n),
    }


def _resolve_with_fallback(raw: float | None, fallback: float, *, reason: str) -> tuple[float, dict[str, Any]]:
    if raw is None or (isinstance(raw, float) and raw != raw):
        return float(fallback), {"fallback_used": True, "fallback_value": fallback, "reason": reason}
    return float(raw), {"fallback_used": False}


def _ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return float(num) / float(den)


def compute_offensive_production_component(ctx: V10PriorContext, prior_fixtures: list[Fixture]) -> dict[str, Any]:
    """Ritorna dict con value, inputs, fallbacks_used, cap_applied (compatibile audit v0.4)."""
    team_id = ctx.team_id
    stats_map = ctx.stats_map
    last5 = _last_n(prior_fixtures, 5)
    last10 = _last_n(prior_fixtures, 10)
    season_agg = _agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=team_id)
    last5_agg = _agg_for_team(fixtures=last5, stats_map=stats_map, team_id=team_id)
    last10_agg = _agg_for_team(fixtures=last10, stats_map=stats_map, team_id=team_id)

    fallbacks_used: list[str] = []
    avg_sot_for_raw = _safe_float(season_agg.get("sot_mean"))
    avg_sot_for, fb = _resolve_with_fallback(avg_sot_for_raw, PRUDENTIAL_FALLBACK_SOT, reason="avg_sot_for_missing")
    if fb.get("fallback_used"):
        fallbacks_used.append("avg_sot_for")

    avg_total_shots_for_raw = _safe_float(season_agg.get("shots_mean"))
    avg_total_shots_for, fb2 = _resolve_with_fallback(
        avg_total_shots_for_raw,
        PRUDENTIAL_FALLBACK_SHOTS,
        reason="avg_total_shots_for_missing",
    )
    if fb2.get("fallback_used"):
        fallbacks_used.append("avg_total_shots_for")

    avg_inside_box_shots_for_raw = _safe_float(season_agg.get("inside_mean"))
    avg_outside_box_shots_for_raw = _safe_float(season_agg.get("outside_mean"))

    shot_accuracy_raw = _ratio(avg_sot_for_raw, avg_total_shots_for_raw)
    shot_accuracy_for, fb_acc = _resolve_with_fallback(
        shot_accuracy_raw,
        PRUDENTIAL_FALLBACK_ACCURACY,
        reason="shot_accuracy_missing_or_zero_denom",
    )
    if fb_acc.get("fallback_used"):
        fallbacks_used.append("shot_accuracy_for")

    avg_goals_for_raw = _safe_float(season_agg.get("goals_mean"))
    avg_goals_for, fb_g = _resolve_with_fallback(avg_goals_for_raw, 1.1, reason="avg_goals_for_missing")
    if fb_g.get("fallback_used"):
        fallbacks_used.append("avg_goals_for")

    total_shots_signal = avg_total_shots_for * shot_accuracy_for
    inside_box_signal = (
        None if avg_inside_box_shots_for_raw is None else float(avg_inside_box_shots_for_raw) * shot_accuracy_for
    )
    outside_box_signal = (
        None if avg_outside_box_shots_for_raw is None else float(avg_outside_box_shots_for_raw) * shot_accuracy_for * 0.7
    )

    acc_ratio = shot_accuracy_for / PRUDENTIAL_FALLBACK_ACCURACY if PRUDENTIAL_FALLBACK_ACCURACY else 1.0
    shot_accuracy_signal = _clamp(avg_sot_for * acc_ratio, avg_sot_for - 0.5, avg_sot_for + 0.5)

    goals_signal = avg_goals_for * PRUDENTIAL_SOT_PER_GOAL

    last5_sot = _safe_float(last5_agg.get("sot_mean"))
    last10_sot = _safe_float(last10_agg.get("sot_mean"))
    d5 = (last5_sot - avg_sot_for_raw) if (last5_sot is not None and avg_sot_for_raw is not None) else 0.0
    d10 = (last10_sot - avg_sot_for_raw) if (last10_sot is not None and avg_sot_for_raw is not None) else 0.0
    trend_delta = _clamp(float((d5 + d10) / 2.0), -0.5, 0.5)
    offensive_trend_signal = _clamp(avg_sot_for + trend_delta, avg_sot_for - 0.5, avg_sot_for + 0.5)

    w = {
        "avg_sot_for": 0.35,
        "avg_total_shots_for": 0.25,
        "avg_inside_box_shots_for": 0.15,
        "avg_outside_box_shots_for": 0.05,
        "shot_accuracy_for": 0.10,
        "avg_goals_for": 0.05,
        "offensive_trend": 0.05,
    }

    if inside_box_signal is None:
        fallbacks_used.append("avg_inside_box_shots_for_missing_redistribute")
        w["avg_sot_for"] += 0.10
        w["avg_total_shots_for"] += 0.05
        w["avg_inside_box_shots_for"] = 0.0

    def contrib(val: float | None, weight: float) -> float:
        if val is None or weight <= 0:
            return 0.0
        return float(val) * float(weight)

    numerator = denom = 0.0
    for val, wk in (
        (avg_sot_for, w["avg_sot_for"]),
        (total_shots_signal, w["avg_total_shots_for"]),
        (inside_box_signal, w["avg_inside_box_shots_for"]),
        (outside_box_signal, w["avg_outside_box_shots_for"]),
        (shot_accuracy_signal, w["shot_accuracy_for"]),
        (goals_signal, w["avg_goals_for"]),
        (offensive_trend_signal, w["offensive_trend"]),
    ):
        numerator += contrib(val, wk)
        denom += wk

    raw_component = numerator / denom if denom > 0 else avg_sot_for
    capped_component = _clamp(raw_component, avg_sot_for - 0.75, avg_sot_for + 0.75)
    cap_applied = abs(capped_component - raw_component) > 1e-9

    def mk_input(
        *,
        key: str,
        value: float | None,
        sum_key: str | None,
        weight: float,
        contribution: float,
        status: str,
        source_field: str,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "value": _round2(value),
            "source_table": "fixture_team_stats",
            "source_field": source_field,
            "source_path": f"fixture_team_stats.{source_field}",
            "api_source": "fixtures/statistics",
            "matches_count": int(season_agg.get("matches_count") or 0),
            "sum": int(season_agg.get(sum_key) or 0) if sum_key else None,
            "weight": weight,
            "contribution": _round2(contribution),
            "status": status,
            "fallback_used": status != "available",
            "no_data_leakage": True,
        }

    inputs = {
        "avg_sot_for": mk_input(
            key="avg_sot_for",
            value=avg_sot_for,
            sum_key="sot_sum",
            weight=w["avg_sot_for"],
            contribution=avg_sot_for * w["avg_sot_for"],
            status="available" if avg_sot_for_raw is not None else "fallback",
            source_field="shots_on_target",
        ),
        "avg_total_shots_for": mk_input(
            key="avg_total_shots_for",
            value=avg_total_shots_for,
            sum_key="shots_sum",
            weight=w["avg_total_shots_for"],
            contribution=total_shots_signal * w["avg_total_shots_for"],
            status="available" if avg_total_shots_for_raw is not None else "fallback",
            source_field="total_shots",
        ),
        "avg_inside_box_shots_for": mk_input(
            key="avg_inside_box_shots_for",
            value=avg_inside_box_shots_for_raw,
            sum_key="inside_sum",
            weight=w["avg_inside_box_shots_for"],
            contribution=(inside_box_signal or 0.0) * w["avg_inside_box_shots_for"],
            status="available" if avg_inside_box_shots_for_raw is not None else "fallback",
            source_field="shots_inside_box",
        ),
        "avg_outside_box_shots_for": mk_input(
            key="avg_outside_box_shots_for",
            value=avg_outside_box_shots_for_raw,
            sum_key="outside_sum",
            weight=w["avg_outside_box_shots_for"],
            contribution=(outside_box_signal or 0.0) * w["avg_outside_box_shots_for"],
            status="available" if avg_outside_box_shots_for_raw is not None else "fallback",
            source_field="shots_outside_box",
        ),
        "shot_accuracy_for": {
            **mk_input(
                key="shot_accuracy_for",
                value=shot_accuracy_for,
                sum_key=None,
                weight=w["shot_accuracy_for"],
                contribution=shot_accuracy_signal * w["shot_accuracy_for"],
                status="available" if shot_accuracy_raw is not None else "fallback",
                source_field="derived_shots_on_target/total_shots",
            ),
        },
        "avg_goals_for": {
            **mk_input(
                key="avg_goals_for",
                value=avg_goals_for,
                sum_key="goals_sum",
                weight=w["avg_goals_for"],
                contribution=goals_signal * w["avg_goals_for"],
                status="available" if avg_goals_for_raw is not None else "fallback",
                source_field="goals (fixtures)",
            ),
        },
        "offensive_trend": {
            **mk_input(
                key="offensive_trend",
                value=trend_delta,
                sum_key=None,
                weight=w["offensive_trend"],
                contribution=offensive_trend_signal * w["offensive_trend"],
                status="available" if (last5_sot is not None or last10_sot is not None) else "fallback",
                source_field="derived_last5_last10_vs_season",
            ),
        },
    }

    return {
        "value": _round2(capped_component),
        "inputs": inputs,
        "fallbacks_used": fallbacks_used,
        "cap_applied": cap_applied,
        "cap_bounds": {"min": _round2(avg_sot_for - 0.75), "max": _round2(avg_sot_for + 0.75)},
        "explanation": (
            "Componente offensiva in scala SOT da DB (v1.0 registry): SOT, volume tiri, inside/outside, "
            "precisione, goal e trend con cap ±0.75."
        ),
        "debug": {"raw_value": _round2(raw_component)},
        "weight_in_model": 0.30,
    }
