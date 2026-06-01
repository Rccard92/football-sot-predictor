"""Simulatore strategie selezione pick v3.0 (solo lettura dati salvati)."""

from __future__ import annotations

from typing import Any, Callable

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_diagnostics_aggregator import diagnostics_actual_total_bucket
from app.services.backtest.round_analysis_mode_stats import advice_bucket, is_advised_label
from app.services.backtest.sot_pick_evaluation_logic import compute_pick_outcome

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS

STRATEGY_IDS = (
    "v1_1_cautious_advised",
    "v2_1_cautious_advised",
    "v2_1_cautious_line_6_5_only",
    "v2_1_no_high_lines",
    "v2_1_overheat_veto",
    "consensus_v11_v21_cautious_min_line",
    "consensus_v11_v21_cautious_v21_line",
    "conservative_selector_v30_candidate",
)

STRATEGY_LABELS: dict[str, str] = {
    "v1_1_cautious_advised": "v1.1 cauta consigliata",
    "v2_1_cautious_advised": "v2.1 cauta consigliata",
    "v2_1_cautious_line_6_5_only": "v2.1 solo linea 6.5",
    "v2_1_no_high_lines": "v2.1 no linee ≥8.5",
    "v2_1_overheat_veto": "v2.1 overheat veto",
    "consensus_v11_v21_cautious_min_line": "Consenso v1.1+v2.1 (linea min)",
    "consensus_v11_v21_cautious_v21_line": "Consenso v1.1+v2.1 (linea v2.1)",
    "conservative_selector_v30_candidate": "Selector conservativo v3.0 (candidato)",
}

MAX_WARNINGS_CONSERVATIVE = 6


def _round1(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 1)


def _round4(v: float | None) -> float | None:
    if v is None:
        return None
    return round(float(v), 4)


def _hit_rate(wins: int, losses: int) -> float | None:
    t = wins + losses
    if t <= 0:
        return None
    return _round1(100.0 * wins / t)


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return _round4(sum(vals) / len(vals))


def _block_cautious_gioca(block: dict[str, Any] | None) -> bool:
    if not isinstance(block, dict):
        return False
    return is_advised_label(str(block.get("cautious_advice") or ""))


def _cautious_line(block: dict[str, Any] | None) -> float | None:
    if not isinstance(block, dict):
        return None
    ln = block.get("cautious_line")
    return float(ln) if ln is not None else None


def _outcome_for_line(actual: int, line: float) -> str:
    return "WIN" if compute_pick_outcome(line, actual) == "win" else "LOSS"


def _pick_from_block(
    fx: dict[str, Any],
    block: dict[str, Any],
    *,
    model_key: str,
    line: float | None = None,
) -> dict[str, Any] | None:
    if line is None:
        line = _cautious_line(block)
    if line is None:
        return None
    actual = int(fx["actual_total_sot"])
    outcome = _outcome_for_line(actual, float(line))
    pt = block.get("predicted_total_sot")
    return {
        "analysis_id": fx["analysis_id"],
        "round_number": fx["round_number"],
        "fixture_id": fx["fixture_id"],
        "match": fx["match"],
        "actual_total_sot": actual,
        "predicted_total_sot": float(pt) if pt is not None else None,
        "line": float(line),
        "outcome": outcome,
        "model_key": model_key,
        "mode": "cautious",
    }


def _strategy_v11_cautious(fx: dict[str, Any]) -> dict[str, Any] | None:
    block = fx["models"].get(V11)
    if not _block_cautious_gioca(block):
        return None
    return _pick_from_block(fx, block, model_key=V11)


def _strategy_v21_cautious(fx: dict[str, Any]) -> dict[str, Any] | None:
    block = fx["models"].get(V21)
    if not _block_cautious_gioca(block):
        return None
    return _pick_from_block(fx, block, model_key=V21)


def _strategy_v21_line_65(fx: dict[str, Any]) -> dict[str, Any] | None:
    block = fx["models"].get(V21)
    if not _block_cautious_gioca(block):
        return None
    ln = _cautious_line(block)
    if ln is None or float(ln) != 6.5:
        return None
    return _pick_from_block(fx, block, model_key=V21)


def _strategy_v21_no_high_lines(fx: dict[str, Any]) -> dict[str, Any] | None:
    block = fx["models"].get(V21)
    if not _block_cautious_gioca(block):
        return None
    ln = _cautious_line(block)
    if ln is None or float(ln) >= 8.5:
        return None
    return _pick_from_block(fx, block, model_key=V21, line=ln)


def _overheat_veto(fx: dict[str, Any], line: float) -> bool:
    if float(line) < 7.5:
        return False
    macros = fx.get("v21_macros") or {}
    wmm = macros.get("weighted_macro_multiplier_avg")
    off = macros.get("offensive_production_avg")
    cq = macros.get("chance_quality_avg")
    pace = macros.get("pace_control_avg")
    if wmm is not None and float(wmm) > 1.08:
        return True
    if off is not None and cq is not None and float(off) > 1.10 and float(cq) > 1.10:
        return True
    if pace is not None and float(pace) > 1.10:
        return True
    return False


def _strategy_v21_overheat_veto(fx: dict[str, Any]) -> dict[str, Any] | None:
    block = fx["models"].get(V21)
    if not _block_cautious_gioca(block):
        return None
    ln = _cautious_line(block)
    if ln is None or _overheat_veto(fx, float(ln)):
        return None
    return _pick_from_block(fx, block, model_key=V21, line=ln)


def _strategy_consensus(fx: dict[str, Any], *, use_v21_line: bool) -> dict[str, Any] | None:
    v11 = fx["models"].get(V11)
    v21 = fx["models"].get(V21)
    if not _block_cautious_gioca(v11) or not _block_cautious_gioca(v21):
        return None
    ln11 = _cautious_line(v11)
    ln21 = _cautious_line(v21)
    if ln11 is None or ln21 is None:
        return None
    if use_v21_line:
        line = float(ln21)
    else:
        line = min(float(ln11), float(ln21))
    return _pick_from_block(fx, v21, model_key=V21, line=line)


def _strategy_conservative_v30(fx: dict[str, Any]) -> dict[str, Any] | None:
    block = fx["models"].get(V21)
    if not isinstance(block, dict):
        return None
    if not _block_cautious_gioca(block):
        return None
    ln = _cautious_line(block)
    if ln is None or float(ln) >= 8.5:
        return None
    warnings = list(block.get("warnings") or [])
    macros = fx.get("v21_macros") or {}
    split_st = fx.get("split_status") or "missing"
    conf = str(block.get("confidence") or "").lower()
    if len(warnings) >= MAX_WARNINGS_CONSERVATIVE:
        return None
    if "top_shooter_only_bench" in warnings:
        unav = macros.get("injuries_unavailable_avg")
        if unav is not None and float(unav) < 0.90:
            return None
    if float(ln) == 6.5:
        return _pick_from_block(fx, block, model_key=V21, line=ln)
    if float(ln) == 7.5:
        wmm = macros.get("weighted_macro_multiplier_avg")
        cq = macros.get("chance_quality_avg")
        pace = macros.get("pace_control_avg")
        if conf == "low":
            return None
        if split_st == "missing":
            return None
        if wmm is None or not (0.95 <= float(wmm) <= 1.08):
            return None
        if cq is not None and float(cq) > 1.15:
            return None
        if pace is not None and float(pace) > 1.15:
            return None
        return _pick_from_block(fx, block, model_key=V21, line=ln)
    return None


STRATEGY_FN: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {
    "v1_1_cautious_advised": _strategy_v11_cautious,
    "v2_1_cautious_advised": _strategy_v21_cautious,
    "v2_1_cautious_line_6_5_only": _strategy_v21_line_65,
    "v2_1_no_high_lines": _strategy_v21_no_high_lines,
    "v2_1_overheat_veto": _strategy_v21_overheat_veto,
    "consensus_v11_v21_cautious_min_line": lambda fx: _strategy_consensus(fx, use_v21_line=False),
    "consensus_v11_v21_cautious_v21_line": lambda fx: _strategy_consensus(fx, use_v21_line=True),
    "conservative_selector_v30_candidate": _strategy_conservative_v30,
}


def apply_strategy(strategy_id: str, fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fn = STRATEGY_FN.get(strategy_id)
    if fn is None:
        return []
    picks: list[dict[str, Any]] = []
    for fx in fixtures:
        pick = fn(fx)
        if pick is not None:
            picks.append(pick)
    return picks


def _compact_summary(picks: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for p in picks if p["outcome"] == "WIN")
    losses = sum(1 for p in picks if p["outcome"] == "LOSS")
    lines = [float(p["line"]) for p in picks]
    preds = [float(p["predicted_total_sot"]) for p in picks if p.get("predicted_total_sot") is not None]
    acts = [float(p["actual_total_sot"]) for p in picks]
    errs_signed = [
        float(p["predicted_total_sot"]) - float(p["actual_total_sot"])
        for p in picks
        if p.get("predicted_total_sot") is not None
    ]
    abs_errs = [abs(e) for e in errs_signed]
    return {
        "picks": len(picks),
        "wins": wins,
        "losses": losses,
        "hit_rate": _hit_rate(wins, losses),
        "avg_line": _mean(lines),
        "avg_predicted_total": _mean(preds),
        "avg_actual_total": _mean(acts),
        "mae": _mean(abs_errs),
        "bias": _mean(errs_signed),
    }


def _compare_baselines(
    picks: list[dict[str, Any]],
    baseline_picks: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_by_fx = {(int(p["analysis_id"]), int(p["fixture_id"])): p for p in baseline_picks}
    strat_by_fx = {(int(p["analysis_id"]), int(p["fixture_id"])): p for p in picks}
    avoided = missed = 0
    for key, bp in baseline_by_fx.items():
        if bp["outcome"] == "LOSS" and key not in strat_by_fx:
            avoided += 1
        if bp["outcome"] == "WIN" and key not in strat_by_fx:
            missed += 1
    return {"avoided_losses": avoided, "missed_wins": missed}


def _breakdown_by_line(picks: list[dict[str, Any]]) -> dict[str, Any]:
    acc: dict[str, dict[str, int]] = {}
    for p in picks:
        key = str(float(p["line"]))
        cell = acc.setdefault(key, {"wins": 0, "losses": 0})
        if p["outcome"] == "WIN":
            cell["wins"] += 1
        else:
            cell["losses"] += 1
    out: dict[str, Any] = {}
    for ln, cell in sorted(acc.items(), key=lambda x: float(x[0])):
        w, l = cell["wins"], cell["losses"]
        out[ln] = {"plays": w + l, "wins": w, "losses": l, "hit_rate": _hit_rate(w, l)}
    return out


def _breakdown_by_bucket(picks: list[dict[str, Any]], key_fn: Callable[[dict[str, Any]], str | None]) -> dict[str, Any]:
    acc: dict[str, list[dict[str, Any]]] = {}
    for p in picks:
        bucket = key_fn(p)
        if bucket:
            acc.setdefault(bucket, []).append(p)
    return {k: _compact_summary(v) for k, v in acc.items()}


def _season_phase(round_number: int) -> str:
    if round_number <= 15:
        return "early"
    if round_number <= 26:
        return "mid"
    return "late"


def _walk_forward(picks: list[dict[str, Any]]) -> dict[str, Any]:
    segments = {
        "rounds_5_15": lambda r: 5 <= r <= 15,
        "rounds_16_26": lambda r: 16 <= r <= 26,
        "rounds_27_38": lambda r: 27 <= r <= 38,
    }
    out: dict[str, Any] = {}
    for name, pred in segments.items():
        subset = [p for p in picks if pred(int(p["round_number"]))]
        out[name] = _compact_summary(subset)
    return out


def summarize_strategy(
    strategy_id: str,
    picks: list[dict[str, Any]],
    *,
    baseline_v21: list[dict[str, Any]],
    baseline_v11: list[dict[str, Any]],
    include_pick_lists: bool = False,
) -> dict[str, Any]:
    summary = _compact_summary(picks)
    v21_summary = _compact_summary(baseline_v21)
    v11_summary = _compact_summary(baseline_v11)
    vs_v21 = _compare_baselines(picks, baseline_v21)
    vs_v21["delta_hit_rate"] = None
    vs_v21["delta_picks"] = summary["picks"] - v21_summary["picks"]
    if summary["hit_rate"] is not None and v21_summary["hit_rate"] is not None:
        vs_v21["delta_hit_rate"] = _round1(float(summary["hit_rate"]) - float(v21_summary["hit_rate"]))
    vs_v11 = {
        "delta_hit_rate": None,
        "delta_picks": summary["picks"] - v11_summary["picks"],
    }
    if summary["hit_rate"] is not None and v11_summary["hit_rate"] is not None:
        vs_v11["delta_hit_rate"] = _round1(float(summary["hit_rate"]) - float(v11_summary["hit_rate"]))

    result: dict[str, Any] = {
        "strategy_id": strategy_id,
        "label": STRATEGY_LABELS.get(strategy_id, strategy_id),
        "summary": summary,
        "vs_v2_1_baseline": vs_v21,
        "vs_v1_1_baseline": vs_v11,
        "by_line": _breakdown_by_line(picks),
        "by_sot_bucket": _breakdown_by_bucket(
            picks,
            lambda p: diagnostics_actual_total_bucket(int(p["actual_total_sot"])),
        ),
        "by_round": _breakdown_by_bucket(picks, lambda p: str(int(p["round_number"]))),
        "by_season_phase": _breakdown_by_bucket(picks, lambda p: _season_phase(int(p["round_number"]))),
        "walk_forward": _walk_forward(picks),
    }
    if include_pick_lists:
        wins = [p for p in picks if p["outcome"] == "WIN"]
        losses = [p for p in picks if p["outcome"] == "LOSS"]
        result["filtered_wins_top"] = wins[:20]
        result["filtered_losses_top"] = losses[:20]
    return result


def _balanced_score(summary: dict[str, Any]) -> float:
    hr = summary.get("hit_rate")
    picks = int(summary.get("picks") or 0)
    if hr is None or picks <= 0:
        return -1.0
    return float(hr) * min(1.0, picks / 100.0)


def build_simulator_payload(
    fixtures: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    baseline_v11 = apply_strategy("v1_1_cautious_advised", fixtures)
    baseline_v21 = apply_strategy("v2_1_cautious_advised", fixtures)

    strategies_out: dict[str, Any] = {}
    summaries_for_rank: list[tuple[str, dict[str, Any]]] = []

    for sid in STRATEGY_IDS:
        picks = apply_strategy(sid, fixtures)
        include_lists = sid == "conservative_selector_v30_candidate"
        block = summarize_strategy(
            sid,
            picks,
            baseline_v21=baseline_v21,
            baseline_v11=baseline_v11,
            include_pick_lists=include_lists,
        )
        strategies_out[sid] = block
        summaries_for_rank.append((sid, block["summary"]))

    eligible_hr = [(s, sm) for s, sm in summaries_for_rank if sm.get("picks", 0) >= 10 and sm.get("hit_rate") is not None]
    eligible_vol = [(s, sm) for s, sm in summaries_for_rank if sm.get("picks", 0) > 0]

    best_hr = max(eligible_hr, key=lambda x: float(x[1]["hit_rate"] or 0))[0] if eligible_hr else None
    best_vol = max(eligible_vol, key=lambda x: int(x[1]["picks"]))[0] if eligible_vol else None
    best_bal = max(eligible_hr, key=lambda x: _balanced_score(x[1]))[0] if eligible_hr else None

    return {
        "report_type": "round_analysis_calibration_simulator_v30",
        "metadata": metadata,
        "baselines": {
            "v1_1_cautious_advised": _compact_summary(baseline_v11),
            "v2_1_cautious_advised": _compact_summary(baseline_v21),
        },
        "ranking": {
            "best_hit_rate": best_hr,
            "best_volume": best_vol,
            "most_balanced": best_bal,
        },
        "strategies": strategies_out,
    }
