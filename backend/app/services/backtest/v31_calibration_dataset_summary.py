"""Summary leggera dataset v3.1 da analisi persistite (senza rebuild PIT)."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.round_analysis_calibration_export import _select_analyses_for_calibration
from app.services.backtest.round_analysis_report_builder import _iso
from app.services.backtest.round_analysis_v21_trace_helpers import macro_index
from app.services.backtest.v31_calibration_anti_leakage import validate_v31_rows
from app.services.backtest.v31_calibration_dataset_builder import _iter_calibration_fixtures
from app.services.backtest.v31_calibration_row_builder_standard import build_standard_row

logger = logging.getLogger(__name__)

def _side_has_macro(expl: dict[str, Any] | None, macro_key: str) -> bool:
    if not isinstance(expl, dict):
        return False
    for side_key in ("home", "away"):
        side = expl.get(side_key)
        if macro_index(side if isinstance(side, dict) else None, macro_key) is not None:
            return True
    return False


def build_v31_calibration_summary(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
) -> dict[str, Any]:
    from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS

    t0 = time.perf_counter()
    logger.info(
        "V31_DATASET_SUMMARY_START competition_id=%s season_year=%s",
        competition_id,
        season_year,
    )

    analyses, _excluded, fixtures_by_id = _select_analyses_for_calibration(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    max_round = max((int(a.round_number) for a in analyses), default=38)

    fixtures_ok = 0
    fixtures_with_target = 0
    team_stats = player_layer = lineups = unavailable = macro_features = 0
    preview_rows: list[dict[str, Any]] = []
    last_updated: datetime | None = None

    for analysis in analyses:
        ts = analysis.completed_at or analysis.created_at
        if ts is not None and (last_updated is None or ts > last_updated):
            last_updated = ts

    for _analysis, orm_row, rn in _iter_calibration_fixtures(analyses, fixtures_by_id):
        fixtures_ok += 1
        fixtures_with_target += 1

        expl_all = dict(orm_row.explanation_json or {})
        expl_v21 = expl_all.get(BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS)
        if isinstance(expl_v21, dict):
            if _side_has_macro(expl_v21, "offensive_production"):
                team_stats += 1
            if _side_has_macro(expl_v21, "player_layer"):
                player_layer += 1
            if _side_has_macro(expl_v21, "lineups"):
                lineups += 1
            if _side_has_macro(expl_v21, "injuries_unavailable"):
                unavailable += 1
            if _side_has_macro(expl_v21, "chance_quality"):
                macro_features += 1

        preview_rows.append(
            build_standard_row(
                orm_row,
                competition_id=competition_id,
                season_year=season_year,
                round_number=rn,
                max_round=max_round,
            ),
        )

    anti = validate_v31_rows(preview_rows, sample_limit=20)
    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "V31_DATASET_SUMMARY_DONE fixtures=%s target=%s anti=%s duration_ms=%s",
        fixtures_with_target,
        fixtures_with_target,
        anti.get("status"),
        duration_ms,
    )

    return {
        "status": "ok",
        "competition_id": int(competition_id),
        "season_year": int(season_year),
        "season_label": season_label_from_year(int(season_year)),
        "rounds_available": len(analyses),
        "fixtures_available": fixtures_ok,
        "fixtures_with_target": fixtures_with_target,
        "features": {
            "team_stats_available": team_stats,
            "player_layer_available": player_layer,
            "lineups_available": lineups,
            "unavailable_available": unavailable,
            "macro_features_available": macro_features,
        },
        "anti_leakage_check": anti,
        "exportable": anti.get("status") == "ok",
        "last_updated_at": _iso(last_updated) if last_updated else None,
    }
