"""Servizio simulatore calibrazione v3.1 (read-only, feature pre-match)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import Competition
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.v31_calibration_dataset_builder import build_v31_dataset_rows_standard
from app.services.backtest.v31_calibration_simulator_metrics import (
    compute_best_by,
    regression_metrics,
    summarize_strategy,
)
from app.services.backtest.v31_calibration_simulator_strategies import (
    STRATEGY_DESCRIPTIONS,
    STRATEGY_KEYS,
    STRATEGY_LABELS,
    get_strategy_weights_payload,
    simulate_row,
)

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
            "V31_CALIBRATION_SIMULATOR_START competition_id=%s season_year=%s strategy=%s",
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

        keys = list(STRATEGY_KEYS) if strategy == "all" else [strategy]
        if strategy != "all" and strategy not in STRATEGY_KEYS:
            keys = []

        simulated_by_key: dict[str, list[dict[str, Any]]] = {}
        for key in keys:
            simulated: list[dict[str, Any]] = []
            for row in rows:
                sim = simulate_row(row, key)
                if sim is not None:
                    simulated.append(sim)
            simulated_by_key[key] = simulated

        all_maes: list[tuple[str, float]] = []
        for k in keys:
            mae = regression_metrics(simulated_by_key[k]).get("mae")
            if mae is not None:
                all_maes.append((k, float(mae)))
        best_mae_val = min((m for _, m in all_maes), default=None)

        strategy_blocks: list[dict[str, Any]] = []
        for key in keys:
            simulated = simulated_by_key[key]
            summary = summarize_strategy(key, simulated, best_mae=best_mae_val)
            sample = simulated if include_rows else simulated[:ROWS_SAMPLE_MAX]
            for s in sample:
                s.pop("comparisons_snapshot", None)
            strategy_blocks.append(
                {
                    "key": key,
                    "label": STRATEGY_LABELS.get(key, key),
                    "description": STRATEGY_DESCRIPTIONS.get(key, ""),
                    "weights": get_strategy_weights_payload(key),
                    **summary,
                    "rows_sample": sample,
                },
            )

        best_by = compute_best_by(strategy_blocks)
        payload = {
            "report_type": "v31_calibration_simulator",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "competition_id": int(competition_id),
                "competition_name": comp.name if comp else None,
                "season_year": int(season_year),
                "season_label": season_label_from_year(int(season_year)),
                "fixtures_count": len(rows),
                "strategies_run": len(strategy_blocks),
                "excluded_analyses": excluded,
                "round_range": f"{ROUND_MIN}-{ROUND_MAX}",
                "recommended_strategy": best_by.get("recommended_strategy"),
            },
            "strategies": strategy_blocks,
            "best_by": best_by,
            "audit": {
                "anti_leakage": True,
                "forbidden_fields_used": [],
                "legacy_predictions_used_as_features": False,
                "simulation_only": True,
                "target_used_for_metrics_only": True,
                "comparisons_used_for_audit_only": True,
            },
        }
        logger.info(
            "V31_CALIBRATION_SIMULATOR_DONE fixtures=%s strategies=%s",
            len(rows),
            len(strategy_blocks),
        )
        return payload
