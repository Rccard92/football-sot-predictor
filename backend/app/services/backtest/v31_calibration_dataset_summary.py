"""Summary leggera dataset v3.1 da analisi persistite (senza rebuild PIT)."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.round_analysis_calibration_export import _select_analyses_for_calibration
from app.services.backtest.round_analysis_report_builder import _iso
from app.services.backtest.round_analysis_v21_trace_helpers import macro_index
from app.services.backtest.v31_calibration_anti_leakage import _walk

logger = logging.getLogger(__name__)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _side_has_macro(expl: dict[str, Any] | None, macro_key: str) -> bool:
    if not isinstance(expl, dict):
        return False
    for side_key in ("home", "away"):
        side = expl.get(side_key)
        if macro_index(side if isinstance(side, dict) else None, macro_key) is not None:
            return True
    return False


def _scan_explanation_forbidden(
    explanation_json: dict[str, Any] | None,
    *,
    fixture_id: int,
) -> list[str]:
    """Scan leggero su explanation_json (models_json escluso: contiene confronti legacy)."""
    found: list[str] = []
    if isinstance(explanation_json, dict):
        _walk(explanation_json, f"fixture_{fixture_id}.explanation_json", found)
    return found


def build_v31_calibration_summary(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
) -> dict[str, Any]:
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

    fixtures_ok = 0
    fixtures_with_target = 0
    team_stats = player_layer = lineups = unavailable = macro_features = 0
    all_forbidden: list[str] = []
    last_updated: datetime | None = None

    for analysis in analyses:
        ts = analysis.completed_at or analysis.created_at
        if ts is not None and (last_updated is None or ts > last_updated):
            last_updated = ts

        for orm_row in fixtures_by_id.get(int(analysis.id), []):
            if str(orm_row.status) != "ok":
                continue
            fixtures_ok += 1
            if orm_row.actual_total_sot is None:
                continue
            fixtures_with_target += 1

            fid = int(orm_row.fixture_id)
            expl_all = dict(orm_row.explanation_json or {})
            expl_v21 = expl_all.get(V21) if isinstance(expl_all.get(V21), dict) else None
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

            all_forbidden.extend(_scan_explanation_forbidden(expl_all, fixture_id=fid))

    forbidden_uniq = sorted(set(all_forbidden))
    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "V31_DATASET_SUMMARY_DONE fixtures=%s target=%s duration_ms=%s",
        fixtures_with_target,
        fixtures_with_target,
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
        "anti_leakage_check": {
            "status": "failed" if forbidden_uniq else "ok",
            "forbidden_fields_found": forbidden_uniq,
            "scope": "persisted_fixture_json",
        },
        "last_updated_at": _iso(last_updated) if last_updated else None,
    }
