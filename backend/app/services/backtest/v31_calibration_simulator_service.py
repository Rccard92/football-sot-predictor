"""Servizio simulatore predittivo v3.1 (read-only, feature pre-match)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Competition
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.v31_calibration_dataset_builder import build_v31_dataset_rows_standard
from app.services.backtest.v31_calibration_simulator_cohort import build_cohort_from_rows
from app.services.backtest.v31_calibration_simulator_feature_engine import extract_fixture_signals
from app.services.backtest.v31_calibration_simulator_interactions import compute_fixture_interactions
from app.services.backtest.v31_calibration_simulator_metrics import (
    compute_best_by,
    summarize_strategy,
)
from app.services.backtest.v31_calibration_simulator_strategies import (
    STRATEGY_DESCRIPTIONS,
    STRATEGY_KEYS,
    STRATEGY_LABELS,
    get_strategy_weights_payload,
    predict_rows_for_strategy,
)
from app.services.backtest.v31_calibration_team_raw_resolver import aggregate_shots_availability

logger = logging.getLogger(__name__)

ROWS_SAMPLE_MAX = 20
ROUND_MIN = 5
ROUND_MAX = 37


def _filter_rounds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        rn = int((row.get("metadata") or {}).get("round_number") or 0)
        if ROUND_MIN <= rn <= ROUND_MAX:
            out.append(row)
    return out


def _interaction_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    open_scores: list[float] = []
    fav_scores: list[float] = []
    for row in rows:
        sig = extract_fixture_signals(row)
        if sig is None:
            continue
        inter = compute_fixture_interactions(sig)
        open_scores.append(float(inter.get("match_open_score") or 0))
        fav_scores.append(float(inter.get("favorite_pressure_score") or 0))
    if not open_scores:
        return {}
    return {
        "match_open_score_avg": round(sum(open_scores) / len(open_scores), 4),
        "favorite_pressure_score_avg": round(sum(fav_scores) / len(fav_scores), 4),
        "fixtures_with_interactions": len(open_scores),
    }


def _collect_shots_resolutions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        sig = extract_fixture_signals(row)
        if sig is None:
            continue
        sr = getattr(sig, "shots_resolution", {}) or {}
        if sr.get("home"):
            out.append(sr["home"])
        if sr.get("away"):
            out.append(sr["away"])
    return out


class V31CalibrationSimulatorService:
    def run_simulator(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        use_latest_version_per_round: bool = True,
        include_all_versions: bool = False,
        strategy: str = "all",
        include_rows: bool = False,
    ) -> dict[str, Any]:
        logger.info(
            "V31_PREDICTIVE_SIMULATOR_START competition_id=%s season_year=%s strategy=%s",
            competition_id,
            season_year,
            strategy,
        )
        comp = db.get(Competition, int(competition_id))
        rows, excluded, _max_round = build_v31_dataset_rows_standard(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
        )
        rows = _filter_rounds(rows)
        fixtures_count = len(rows)

        cohort = build_cohort_from_rows(rows)
        feature_availability = aggregate_shots_availability(_collect_shots_resolutions(rows))
        interaction_summary = _interaction_summary(rows)

        keys = list(STRATEGY_KEYS) if strategy == "all" else [strategy]
        if strategy != "all" and strategy not in STRATEGY_KEYS:
            keys = []

        strategy_blocks: list[dict[str, Any]] = []
        for key in keys:
            simulated = predict_rows_for_strategy(rows, key, cohort=cohort)
            summary = summarize_strategy(key, simulated)
            sample = simulated if include_rows else simulated[:ROWS_SAMPLE_MAX]
            for s in sample:
                s.pop("comparisons_snapshot", None)
            weights = get_strategy_weights_payload(key)
            strategy_blocks.append(
                {
                    "key": key,
                    "label": STRATEGY_LABELS.get(key, key),
                    "description": STRATEGY_DESCRIPTIONS.get(key, ""),
                    "weights": weights,
                    "strategy_family": weights.get("strategy_family"),
                    **summary,
                    "rows_sample": sample,
                },
            )

        best_by = compute_best_by(strategy_blocks, fixtures_total=fixtures_count)

        recommendation_note = best_by.get("recommendation_note")
        if recommendation_note is None and best_by.get("recommended_strategy"):
            rec = best_by["recommended_strategy"]
            label = STRATEGY_LABELS.get(rec, rec)
            recommendation_note = f"Strategia consigliata: {label} (score predittivo bilanciato)."

        payload = {
            "report_type": "v31_predictive_simulator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "competition_id": int(competition_id),
                "competition_name": comp.name if comp else None,
                "season_year": int(season_year),
                "season_label": season_label_from_year(int(season_year)),
                "fixtures_count": fixtures_count,
                "strategies_run": len(strategy_blocks),
                "excluded_analyses": excluded,
                "round_range": f"{ROUND_MIN}-{ROUND_MAX}",
                "recommended_strategy": best_by.get("recommended_strategy"),
                "recommendation_note": recommendation_note,
                "phase": "predictive_numeric",
                "betting_phase_enabled": False,
            },
            "strategies": strategy_blocks,
            "best_by": best_by,
            "feature_availability": feature_availability,
            "interaction_features_summary": interaction_summary,
            "audit": {
                "anti_leakage": True,
                "forbidden_fields_used": [],
                "legacy_predictions_used_as_features": False,
                "target_used_as_input": False,
                "simulation_only": True,
                "target_used_for_metrics_only": True,
                "comparisons_used_for_audit_only": True,
                "actual_bucket_metrics_only": True,
                "interaction_features_pre_match_only": True,
            },
        }
        logger.info(
            "V31_PREDICTIVE_SIMULATOR_DONE fixtures=%s strategies=%s",
            fixtures_count,
            len(strategy_blocks),
        )
        return payload
