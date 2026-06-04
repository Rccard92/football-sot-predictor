"""Quote statistiche KPI (CECCHINO W25–W32) da input_snapshot."""

from __future__ import annotations

from typing import Any

from app.services.cecchino.cecchino_match_balance import classify_match_balance


def safe_ratio(n: int, sample: int) -> float:
    if sample <= 0:
        return 0.0
    return float(n) / float(sample)


def _wdl(snapshot: dict[str, Any], key: str) -> tuple[int, int, int, int]:
    raw = snapshot.get(key)
    if not isinstance(raw, dict):
        return 0, 0, 0, 0
    wdl = raw.get("wdl") if isinstance(raw.get("wdl"), dict) else raw
    try:
        w = int(wdl.get("wins", 0))
        d = int(wdl.get("draws", 0))
        l = int(wdl.get("losses", 0))
    except (TypeError, ValueError):
        return 0, 0, 0, 0
    sample = int(raw.get("sample_count") or (w + d + l))
    return w, d, l, sample


def build_statistical_kpi_odds(input_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not input_snapshot:
        return {"status": "not_available", "warnings": ["input_snapshot_missing"]}

    snap = input_snapshot
    hc_w, hc_d, hc_l, hc_s = _wdl(snap, "home_context")
    ac_w, ac_d, ac_l, ac_s = _wdl(snap, "away_context")
    ht_w, ht_d, ht_l, ht_s = _wdl(snap, "home_total")
    at_w, at_d, at_l, at_s = _wdl(snap, "away_total")
    h5_w, h5_d, h5_l, h5_s = _wdl(snap, "home_recent_context_5")
    a5_w, a5_d, a5_l, a5_s = _wdl(snap, "away_recent_context_5")
    h6_w, h6_d, h6_l, h6_s = _wdl(snap, "home_recent_total_6")
    a6_w, a6_d, a6_l, a6_s = _wdl(snap, "away_recent_total_6")

    prob_stat_1 = (
        0.4 * safe_ratio(hc_w, hc_s)
        + 0.25 * safe_ratio(h5_w, h5_s)
        + 0.2 * safe_ratio(ht_w, ht_s)
        + 0.15 * safe_ratio(h6_w, h6_s)
        + 0.4 * safe_ratio(ac_l, ac_s)
        + 0.25 * safe_ratio(a5_l, a5_s)
        + 0.2 * safe_ratio(at_l, at_s)
        + 0.15 * safe_ratio(a6_l, a6_s)
    ) / 2.0

    prob_stat_x = (
        0.4 * safe_ratio(hc_d, hc_s)
        + 0.25 * safe_ratio(h5_d, h5_s)
        + 0.2 * safe_ratio(ht_d, ht_s)
        + 0.4 * safe_ratio(ac_d, ac_s)
        + 0.25 * safe_ratio(a5_d, a5_s)
        + 0.2 * safe_ratio(at_d, at_s)
    ) / (2.0 * 0.85)

    prob_stat_2 = (
        0.4 * safe_ratio(ac_w, ac_s)
        + 0.25 * safe_ratio(a5_w, a5_s)
        + 0.2 * safe_ratio(at_w, at_s)
        + 0.15 * safe_ratio(a6_w, a6_s)
        + 0.4 * safe_ratio(hc_l, hc_s)
        + 0.25 * safe_ratio(h5_l, h5_s)
        + 0.2 * safe_ratio(ht_l, ht_s)
        + 0.15 * safe_ratio(h6_l, h6_s)
    ) / 2.0

    warnings: list[str] = []
    if prob_stat_1 <= 0 or prob_stat_x <= 0 or prob_stat_2 <= 0:
        return {"status": "not_available", "warnings": ["zero_stat_probability"]}

    stat_odd_1 = 1.0 / prob_stat_1
    stat_odd_x = 1.0 / prob_stat_x
    stat_odd_2 = 1.0 / prob_stat_2
    stat_odd_1x = 1.0 / (prob_stat_1 + prob_stat_x)
    stat_odd_x2 = 1.0 / (prob_stat_x + prob_stat_2)
    stat_odd_12 = 1.0 / (prob_stat_1 + prob_stat_2)
    stat_delta = abs(prob_stat_1 - prob_stat_2)
    stat_analysis = classify_match_balance(prob_stat_1, prob_stat_x, prob_stat_2)

    return {
        "status": "available",
        "prob_1": prob_stat_1,
        "prob_x": prob_stat_x,
        "prob_2": prob_stat_2,
        "odd_1": round(stat_odd_1, 2),
        "odd_x": round(stat_odd_x, 2),
        "odd_2": round(stat_odd_2, 2),
        "odd_1x": round(stat_odd_1x, 2),
        "odd_x2": round(stat_odd_x2, 2),
        "odd_12": round(stat_odd_12, 2),
        "delta_forza": round(stat_delta * 100, 2),
        "delta_forza_decimal": stat_delta,
        "match_analysis": stat_analysis,
        "warnings": warnings,
    }
