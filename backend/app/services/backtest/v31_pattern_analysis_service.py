"""Servizio Pattern Analysis v3.1 (post-match, anti-leakage)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Competition
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.v31_calibration_dataset_builder import build_v31_dataset_rows_standard
from app.services.backtest.v31_calibration_simulator_cohort import build_cohort_from_rows
from app.services.backtest.v31_calibration_simulator_high_guard import aggregate_hybrid_debug
from app.services.backtest.v31_calibration_simulator_metrics import summarize_strategy
from app.services.backtest.v31_calibration_simulator_strategies import (
    STRATEGY_DESCRIPTIONS,
    STRATEGY_LABELS,
    predict_rows_for_strategy,
)
from app.services.backtest.v31_pattern_analysis_aggregators import (
    extreme_outlier_summary,
    high_and_outlier_summary,
    high_total_non_extreme_summary,
    losing_patterns,
    loss_quality_summary,
    win_quality_summary,
    winning_patterns,
)
from app.services.backtest.v31_pattern_analysis_buckets import dynamic_bucket_thresholds
from app.services.backtest.v31_pattern_analysis_distribution import (
    compute_actual_sot_distribution,
    extract_actuals_from_rows,
)
from app.services.backtest.v31_pattern_analysis_recommendations import TOP3_KEYS, build_recommendations
from app.services.backtest.v31_pattern_analysis_top3 import build_top3_comparisons
from app.services.backtest.v31_pattern_analysis_verdict import build_pattern_verdict
from app.services.backtest.v31_pattern_analysis_win_quality import enrich_row_with_pattern_fields

logger = logging.getLogger(__name__)

ROUND_MIN = 5
ROUND_MAX = 37

PATTERN_AUDIT = {
    "actual_buckets_post_match_only": True,
    "win_quality_post_match_only": True,
    "actual_not_used_in_prediction": True,
    "outlier_classification_not_in_model": True,
    "pattern_analysis_no_weight_mutation": True,
    "diagnostic_weight_analysis_only": True,
}


def _filter_rounds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        rn = int((row.get("metadata") or {}).get("round_number") or 0)
        if ROUND_MIN <= rn <= ROUND_MAX:
            out.append(row)
    return out


def _enrich_all(
    rows: list[dict[str, Any]],
    *,
    p25: float | None,
    p75: float | None,
    p90: float | None,
    p95: float | None,
) -> list[dict[str, Any]]:
    return [
        enrich_row_with_pattern_fields(
            r,
            p25=p25,
            p75=p75,
            p90=p90,
            p95=p95,
        )
        for r in rows
    ]


class V31PatternAnalysisService:
    def run_pattern_analysis(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
        include_fixtures: bool = False,
        rows: list[dict[str, Any]] | None = None,
        excluded_analyses: list[Any] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "V31_PATTERN_ANALYSIS_START competition_id=%s season_year=%s",
            competition_id,
            season_year,
        )
        comp = db.get(Competition, int(competition_id))
        if rows is None:
            rows, excluded, _max_round = build_v31_dataset_rows_standard(
                db,
                competition_id=competition_id,
                season_year=season_year,
                use_latest_version_per_round=use_latest_version_per_round,
                include_all_versions=include_all_versions,
            )
        else:
            excluded = excluded_analyses or []
        rows = _filter_rounds(rows)
        cohort = build_cohort_from_rows(rows)

        # Predizioni prima dell'enrich (no leakage)
        raw_by_strategy: dict[str, list[dict[str, Any]]] = {}
        for key in TOP3_KEYS:
            raw_by_strategy[key] = predict_rows_for_strategy(rows, key, cohort=cohort)

        bias_raw = raw_by_strategy["v31_bias_corrected"]
        actuals = extract_actuals_from_rows(bias_raw)
        distribution = compute_actual_sot_distribution(actuals)
        thresholds = dynamic_bucket_thresholds(distribution)
        p25 = thresholds.get("p25")
        p75 = thresholds.get("p75")
        p90 = thresholds.get("p90")
        p95 = thresholds.get("p95")

        enriched_by_strategy: dict[str, list[dict[str, Any]]] = {}
        for key, raw_rows in raw_by_strategy.items():
            enriched_by_strategy[key] = _enrich_all(
                raw_rows,
                p25=p25,
                p75=p75,
                p90=p90,
                p95=p95,
            )

        top3_fixtures, top3_cluster_summary = build_top3_comparisons(enriched_by_strategy)

        strategy_blocks: list[dict[str, Any]] = []
        strategies_map: dict[str, dict[str, Any]] = {}

        for key in TOP3_KEYS:
            enriched = enriched_by_strategy[key]
            baseline = enriched_by_strategy["v31_bias_corrected"] if key == "v31_bias_dynamic_high_guard" else None
            sim_summary = summarize_strategy(key, enriched, baseline_rows=baseline)

            block: dict[str, Any] = {
                "key": key,
                "label": STRATEGY_LABELS.get(key, key),
                "description": STRATEGY_DESCRIPTIONS.get(key, ""),
                "win_quality_summary": win_quality_summary(enriched),
                "loss_quality_summary": loss_quality_summary(enriched),
                "winning_patterns": winning_patterns(enriched),
                "losing_patterns": losing_patterns(enriched),
                "high_and_outlier": high_and_outlier_summary(
                    enriched,
                    p75=p75,
                    p90=p90,
                    p95=p95,
                ),
                "extreme_outlier_summary": extreme_outlier_summary(enriched),
                "high_total_non_extreme_summary": high_total_non_extreme_summary(enriched),
                "predictive_metrics": sim_summary.get("predictive_metrics"),
                "coverage_metrics": sim_summary.get("coverage_metrics"),
            }
            if key == "v31_bias_dynamic_high_guard":
                block["hybrid_debug"] = aggregate_hybrid_debug(enriched, baseline)
            strategy_blocks.append(block)
            strategies_map[key] = block

        recommendations = build_recommendations(
            strategies=strategies_map,
            top3_cluster_summary=top3_cluster_summary,
            distribution=distribution,
        )
        pattern_verdict = build_pattern_verdict(strategy_blocks, top3_cluster_summary, distribution)

        payload: dict[str, Any] = {
            "report_type": "v31_pattern_analysis",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "competition_id": int(competition_id),
                "competition_name": comp.name if comp else None,
                "season_year": int(season_year),
                "season_label": season_label_from_year(int(season_year)),
                "fixtures_count": len(rows),
                "excluded_analyses": excluded,
                "round_range": f"{ROUND_MIN}-{ROUND_MAX}",
                "strategies_analyzed": list(TOP3_KEYS),
                "actual_sot_distribution": distribution,
                "dynamic_bucket_thresholds": thresholds,
                "win_quality_summary": {
                    b["key"]: b["win_quality_summary"] for b in strategy_blocks
                },
                "loss_quality_summary": {
                    b["key"]: b["loss_quality_summary"] for b in strategy_blocks
                },
                "extreme_outlier_summary": {
                    b["key"]: b["extreme_outlier_summary"] for b in strategy_blocks
                },
                "high_total_non_extreme_summary": {
                    b["key"]: b["high_total_non_extreme_summary"] for b in strategy_blocks
                },
                "top3_cluster_summary": top3_cluster_summary,
                "recommendations": recommendations,
                "pattern_verdict": pattern_verdict,
                "phase": "pattern_analysis_post_match",
                "betting_phase_enabled": False,
            },
            "strategies": strategy_blocks,
            "audit": PATTERN_AUDIT,
        }
        if include_fixtures:
            payload["top3_fixtures"] = top3_fixtures

        logger.info(
            "V31_PATTERN_ANALYSIS_DONE fixtures=%s strategies=%s",
            len(rows),
            len(TOP3_KEYS),
        )
        return payload
