"""
Blend componente Produzione offensiva composita v1.0 (solo DB, normalizzazione lega).
"""

from __future__ import annotations

from typing import Any

from app.models import Fixture
from app.services.predictions_v10.v10_prior_context import V10PriorContext

PRUDENTIAL_FALLBACK_SOT = 3.5
PRUDENTIAL_FALLBACK_SHOTS = 12.0
PRUDENTIAL_FALLBACK_ACCURACY = 0.32
PRUDENTIAL_FALLBACK_GOALS = 1.1
WEIGHT_IN_FINAL_FORMULA = 0.30

OFFENSIVE_INTERNAL_WEIGHTS: dict[str, float] = {
    "avg_sot_for": 0.30,
    "avg_total_shots_for": 0.18,
    "shot_accuracy_for": 0.14,
    "avg_inside_box_shots_for": 0.14,
    "avg_outside_box_shots_for": 0.05,
    "avg_blocked_shots_for": 0.05,
    "avg_shots_off_goal_for": 0.04,
    "avg_goals_for": 0.05,
    "offensive_trend": 0.05,
}

INPUT_LABELS: dict[str, str] = {
    "avg_sot_for": "Media tiri in porta fatti",
    "avg_total_shots_for": "Media tiri totali fatti",
    "shot_accuracy_for": "Precisione tiro",
    "avg_inside_box_shots_for": "Media tiri dentro area",
    "avg_outside_box_shots_for": "Media tiri fuori area",
    "avg_blocked_shots_for": "Media tiri bloccati",
    "avg_shots_off_goal_for": "Media tiri fuori dallo specchio",
    "avg_goals_for": "Media goal fatti",
    "offensive_trend": "Trend offensivo recente",
}

INPUT_API_SOURCES: dict[str, str] = {
    "avg_sot_for": "fixtures/statistics::Shots on Goal",
    "avg_total_shots_for": "fixtures/statistics::Total Shots",
    "shot_accuracy_for": "derived",
    "avg_inside_box_shots_for": "fixtures/statistics::Shots insidebox",
    "avg_outside_box_shots_for": "fixtures/statistics::Shots outsidebox",
    "avg_blocked_shots_for": "fixtures/statistics::Blocked Shots",
    "avg_shots_off_goal_for": "fixtures/statistics::Shots off Goal",
    "avg_goals_for": "fixtures::goals",
    "offensive_trend": "fixture_team_stats.shots_on_target",
}

INPUT_SOURCE_PATHS: dict[str, str] = {
    "avg_sot_for": "fixture_team_stats.shots_on_target",
    "avg_total_shots_for": "fixture_team_stats.total_shots",
    "shot_accuracy_for": "derived:shots_on_target/total_shots",
    "avg_inside_box_shots_for": "fixture_team_stats.shots_inside_box",
    "avg_outside_box_shots_for": "fixture_team_stats.shots_outside_box",
    "avg_blocked_shots_for": "fixture_team_stats.blocked_shots",
    "avg_shots_off_goal_for": "fixture_team_stats.shots_off_target",
    "avg_goals_for": "fixtures.goals",
    "offensive_trend": "derived:last5_sot_minus_season_sot",
}

INPUT_ORDER: tuple[str, ...] = tuple(OFFENSIVE_INTERNAL_WEIGHTS.keys())


def offensive_inputs_as_map(comp: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Indice inputs da lista o dict (compat audit/trace)."""
    if not isinstance(comp, dict):
        return {}
    raw_inp = comp.get("inputs")
    if isinstance(raw_inp, list):
        return {str(x.get("key")): x for x in raw_inp if isinstance(x, dict) and x.get("key")}
    if isinstance(raw_inp, dict):
        return {str(k): v for k, v in raw_inp.items() if isinstance(v, dict)}
    return {}


def _safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def _round2(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), 2)


def _round4(x: float) -> float:
    return round(float(x), 4)


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
    blocked_sum = blocked_n = 0
    off_goal_sum = off_goal_n = 0
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

    def mean(sum_: int, n: int) -> float | None:
        return (sum_ / n) if n > 0 else None

    return {
        "matches_count": len(fixtures),
        "sot_mean": mean(sot_sum, sot_n),
        "shots_mean": mean(shots_sum, shots_n),
        "inside_mean": mean(in_sum, in_n),
        "outside_mean": mean(out_sum, out_n),
        "blocked_mean": mean(blocked_sum, blocked_n),
        "off_goal_mean": mean(off_goal_sum, off_goal_n),
        "goals_mean": mean(goals_sum, goals_n),
    }


def _scale_to_sot(
    raw: float | None,
    league_avg_raw: float | None,
    league_avg_sot: float,
    *,
    fallback_signal: float,
) -> tuple[float, bool]:
    if raw is None:
        return fallback_signal, True
    if league_avg_raw is None or league_avg_raw <= 0 or league_avg_sot <= 0:
        return fallback_signal, True
    return float(raw) * float(league_avg_sot) / float(league_avg_raw), False


def _build_formula_symbolic() -> str:
    parts = [
        f"({key} × {OFFENSIVE_INTERNAL_WEIGHTS[key]})"
        for key in INPUT_ORDER
    ]
    return "offensive_production_component = " + " + ".join(parts)


def compute_offensive_production_component(ctx: V10PriorContext, prior_fixtures: list[Fixture]) -> dict[str, Any]:
    """Produzione offensiva composita con 9 input normalizzati e audit in lista."""
    team_id = ctx.team_id
    stats_map = ctx.stats_map
    lb = ctx.league_baselines if isinstance(ctx.league_baselines, dict) else {}
    league_sot = float(lb.get("league_avg_sot_for") or ctx.league_avg_sot or PRUDENTIAL_FALLBACK_SOT)
    league_shots = float(lb.get("league_avg_total_shots_for") or PRUDENTIAL_FALLBACK_SHOTS)
    league_inside = float(lb.get("league_avg_inside_box_shots_for") or league_sot)
    league_outside = float(lb.get("league_avg_outside_box_shots_for") or league_sot)
    league_blocked = float(lb.get("league_avg_blocked_shots_for") or league_sot)
    league_off_goal = float(lb.get("league_avg_shots_off_goal_for") or league_sot)
    league_goals = float(lb.get("league_avg_goals_for") or PRUDENTIAL_FALLBACK_GOALS)
    league_acc = float(lb.get("league_avg_shot_accuracy") or PRUDENTIAL_FALLBACK_ACCURACY)

    season_agg = _agg_for_team(fixtures=prior_fixtures, stats_map=stats_map, team_id=team_id)
    last5_agg = _agg_for_team(
        fixtures=_last_n(prior_fixtures, 5),
        stats_map=stats_map,
        team_id=team_id,
    )
    sample_count = int(season_agg.get("matches_count") or 0)

    avg_sot_raw = _safe_float(season_agg.get("sot_mean"))
    avg_shots_raw = _safe_float(season_agg.get("shots_mean"))
    avg_inside_raw = _safe_float(season_agg.get("inside_mean"))
    avg_outside_raw = _safe_float(season_agg.get("outside_mean"))
    avg_blocked_raw = _safe_float(season_agg.get("blocked_mean"))
    avg_off_goal_raw = _safe_float(season_agg.get("off_goal_mean"))
    avg_goals_raw = _safe_float(season_agg.get("goals_mean"))

    avg_sot_for = float(avg_sot_raw) if avg_sot_raw is not None else league_sot
    fb_sot = avg_sot_raw is None

    shot_accuracy_raw: float | None = None
    if avg_sot_raw is not None and avg_shots_raw is not None and avg_shots_raw > 0:
        shot_accuracy_raw = float(avg_sot_raw) / float(avg_shots_raw)
    shot_accuracy_fb = shot_accuracy_raw is None

    last5_sot = _safe_float(last5_agg.get("sot_mean"))
    trend_raw = (last5_sot - avg_sot_raw) if (last5_sot is not None and avg_sot_raw is not None) else 0.0
    trend_fb = last5_sot is None or avg_sot_raw is None

    normalized: dict[str, tuple[float, float, bool]] = {}

    normalized["avg_sot_for"] = (avg_sot_for, avg_sot_for, fb_sot)

    n_shots, fb_shots = _scale_to_sot(avg_shots_raw, league_shots, league_sot, fallback_signal=avg_sot_for)
    normalized["avg_total_shots_for"] = (float(avg_shots_raw or 0), n_shots, fb_shots or avg_shots_raw is None)

    if shot_accuracy_raw is not None and league_acc > 0:
        n_acc = (float(shot_accuracy_raw) / league_acc) * league_sot
        normalized["shot_accuracy_for"] = (float(shot_accuracy_raw), n_acc, shot_accuracy_fb)
    else:
        normalized["shot_accuracy_for"] = (PRUDENTIAL_FALLBACK_ACCURACY, avg_sot_for, True)

    n_in, fb_in = _scale_to_sot(avg_inside_raw, league_inside, league_sot, fallback_signal=avg_sot_for)
    normalized["avg_inside_box_shots_for"] = (float(avg_inside_raw or 0), n_in, fb_in or avg_inside_raw is None)

    n_out, fb_out = _scale_to_sot(avg_outside_raw, league_outside, league_sot, fallback_signal=avg_sot_for)
    normalized["avg_outside_box_shots_for"] = (float(avg_outside_raw or 0), n_out, fb_out or avg_outside_raw is None)

    n_blk, fb_blk = _scale_to_sot(avg_blocked_raw, league_blocked, league_sot, fallback_signal=avg_sot_for)
    normalized["avg_blocked_shots_for"] = (float(avg_blocked_raw or 0), n_blk, fb_blk or avg_blocked_raw is None)

    n_off, fb_off = _scale_to_sot(avg_off_goal_raw, league_off_goal, league_sot, fallback_signal=avg_sot_for)
    normalized["avg_shots_off_goal_for"] = (float(avg_off_goal_raw or 0), n_off, fb_off or avg_off_goal_raw is None)

    if avg_goals_raw is not None and league_goals > 0:
        n_goals = (float(avg_goals_raw) / league_goals) * league_sot
        normalized["avg_goals_for"] = (float(avg_goals_raw), n_goals, False)
    else:
        normalized["avg_goals_for"] = (float(avg_goals_raw or 0), avg_sot_for, avg_goals_raw is None)

    trend_clamped = _clamp(float(trend_raw), -1.0, 1.0)
    n_trend = avg_sot_for + trend_clamped
    normalized["offensive_trend"] = (float(trend_raw), n_trend, trend_fb)

    inputs_list: list[dict[str, Any]] = []
    component_sum = 0.0
    missing_inputs: list[str] = []
    fallback_count = 0

    for key in INPUT_ORDER:
        raw_v, norm_v, fb = normalized[key]
        iw = OFFENSIVE_INTERNAL_WEIGHTS[key]
        ic = _round4(norm_v * iw)
        component_sum += ic
        if fb:
            fallback_count += 1
        if key == "avg_inside_box_shots_for" and avg_inside_raw is None:
            missing_inputs.append(key)
        elif key not in ("avg_sot_for", "offensive_trend") and normalized[key][2]:
            if key not in missing_inputs:
                missing_inputs.append(key)

        inputs_list.append(
            {
                "key": key,
                "label": INPUT_LABELS[key],
                "raw_value": _round2(raw_v if key != "offensive_trend" else trend_raw),
                "normalized_value": _round2(norm_v),
                "internal_weight": iw,
                "internal_contribution": ic,
                "source_path": INPUT_SOURCE_PATHS[key],
                "api_source": INPUT_API_SOURCES[key],
                "sample_count": sample_count,
                "fallback_used": fb,
                "application_role": "component_input",
                "parent_component": "offensive_production_component",
            },
        )

    component_value = _round2(component_sum) or 0.0
    contrib_final = _round4(float(component_value) * WEIGHT_IN_FINAL_FORMULA)

    return {
        "key": "offensive_production_component",
        "label": "Produzione offensiva composita",
        "value": component_value,
        "weight_in_final_formula": WEIGHT_IN_FINAL_FORMULA,
        "weight_in_model": WEIGHT_IN_FINAL_FORMULA,
        "contribution_in_final_formula": contrib_final,
        "contribution": contrib_final,
        "formula": _build_formula_symbolic(),
        "inputs": inputs_list,
        "quality": {
            "inputs_total": len(INPUT_ORDER),
            "inputs_available": len(INPUT_ORDER) - len(missing_inputs),
            "fallback_count": fallback_count,
            "missing_inputs": missing_inputs,
        },
        "fallbacks_used": [inp["key"] for inp in inputs_list if inp.get("fallback_used")],
        "cap_applied": False,
        "explanation": (
            "Produzione offensiva composita: 9 segnali normalizzati alla scala SOT lega "
            "e combinati con pesi interni (totale 1.00), poi × 0.30 nella formula finale."
        ),
        "application_role": "direct_formula_component",
        "parent_component": None,
    }
