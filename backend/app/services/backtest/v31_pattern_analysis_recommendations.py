"""Raccomandazioni intelligenti Pattern Analysis."""

from __future__ import annotations

from typing import Any

TOP3_KEYS = (
    "v31_bias_corrected",
    "v31_bias_dynamic_high_guard",
    "v31_chaos_game",
)


def build_recommendations(
    *,
    strategies: dict[str, dict[str, Any]],
    top3_cluster_summary: dict[str, Any],
    distribution: dict[str, Any],
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    bias = strategies.get("v31_bias_corrected") or {}
    chaos = strategies.get("v31_chaos_game") or {}
    hybrid = strategies.get("v31_bias_dynamic_high_guard") or {}

    bias_wp = (bias.get("winning_patterns") or {}).get("categories") or {}
    bias_wins = (bias.get("winning_patterns") or {}).get("total_wins") or 1
    understated = int((bias_wp.get("UNDERSTATED_WIN") or {}).get("count") or 0)
    understated_pct = 100.0 * understated / bias_wins if bias_wins else 0

    high_ne = bias.get("high_total_non_extreme_summary") or {}
    high_ne_count = int(high_ne.get("count_high_non_extreme") or 0)
    high_ne_under = int(high_ne.get("understated_count") or 0)

    if understated_pct >= 25 and high_ne_count > 0 and high_ne_under / max(high_ne_count, 1) >= 0.4:
        recs.append(
            {
                "type": "structural",
                "severity": "high",
                "message": (
                    "Il modello sottostima sistematicamente le partite high_total non estreme."
                ),
                "evidence": {
                    "understated_win_pct": round(understated_pct, 1),
                    "high_non_extreme_understated": high_ne_under,
                    "high_non_extreme_total": high_ne_count,
                },
            },
        )

    ext = (bias.get("extreme_outlier_summary") or {})
    ext_count = int(ext.get("extreme_actual_count") or 0)
    if ext_count > 0:
        recs.append(
            {
                "type": "outlier",
                "severity": "medium",
                "message": (
                    "Alcune sottostime derivano da partite oltre p95: "
                    "non vanno inseguite con boost generalizzati."
                ),
                "evidence": {
                    "extreme_actual_count": ext_count,
                    "p95": distribution.get("p95"),
                    "extreme_win_outlier_count": ext.get("extreme_win_outlier_count"),
                },
            },
        )

    chaos_hne = chaos.get("high_total_non_extreme_summary") or {}
    bias_hne_mae = high_ne.get("avg_abs_error")
    chaos_hne_mae = chaos_hne.get("avg_abs_error")
    if (
        chaos_hne_mae is not None
        and bias_hne_mae is not None
        and chaos_hne_mae < bias_hne_mae - 0.2
    ):
        recs.append(
            {
                "type": "useful_pattern",
                "severity": "medium",
                "message": (
                    "Quando chaos_game migliora su high_total non estreme, "
                    "recuperare parte della sua logica nel modello ibrido."
                ),
                "evidence": {
                    "chaos_avg_abs_error_high_ne": chaos_hne_mae,
                    "bias_avg_abs_error_high_ne": bias_hne_mae,
                },
            },
        )

    chaos_lp = chaos.get("losing_patterns") or {}
    bad = int(((chaos_lp.get("categories") or {}).get("BAD_LOSS_OVERESTIMATION") or {}).get("count") or 0)
    chaos_total = int(chaos_lp.get("total_fixtures") or 1)
    if bad / chaos_total >= 0.12:
        recs.append(
            {
                "type": "dangerous_pattern",
                "severity": "high",
                "message": (
                    "Quando chaos_game sbaglia, spesso sovrastima partite normali: "
                    "servono guardrail più forti."
                ),
                "evidence": {"bad_loss_overestimation_count": bad, "total_fixtures": chaos_total},
            },
        )

    clusters = top3_cluster_summary.get("counts") or {}
    if int(clusters.get("all_understate_high_non_extreme") or 0) >= 5:
        recs.append(
            {
                "type": "structural",
                "severity": "medium",
                "message": (
                    "Su diverse partite high non estreme tutti e 3 i modelli sottostimano: "
                    "problema strutturale di varianza."
                ),
                "evidence": {"cluster_count": clusters.get("all_understate_high_non_extreme")},
            },
        )

    hybrid_debug = hybrid.get("hybrid_debug") or {}
    if "V31_HYBRID_IDENTICAL_TO_BASELINE" in (hybrid_debug.get("hybrid_warnings") or []):
        recs.append(
            {
                "type": "structural",
                "severity": "high",
                "message": "La strategia ibrida non modifica la baseline: verificare boost high_guard.",
                "evidence": {"hybrid_warnings": hybrid_debug.get("hybrid_warnings")},
            },
        )

    return recs
