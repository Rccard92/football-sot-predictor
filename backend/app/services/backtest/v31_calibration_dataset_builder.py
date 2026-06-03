"""Costruzione dataset calibrazione v3.1 da Round Analysis + PIT storico."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.backtest.constants import BACKTEST_MODE_HISTORICAL_OFFICIAL_XI
from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models import Competition
from app.schemas.backtest_round_analysis import season_label_from_year
from app.services.backtest.point_in_time_context_service import PointInTimeContextService
from app.services.backtest.round_analysis_calibration_export import _select_analyses_for_calibration
from app.services.backtest.v31_calibration_anti_leakage import validate_v31_rows
from app.services.backtest.v31_calibration_feature_mappers import (
    build_features_bundle,
    map_comparisons,
    map_metadata,
    map_target,
)

logger = logging.getLogger(__name__)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _coverage_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {
            "fixtures_count": 0,
            "player_layer_available_pct": 0.0,
            "lineups_available_pct": 0.0,
            "unavailable_available_pct": 0.0,
            "top_warnings": [],
        }

    pl_ok = lu_ok = un_ok = 0
    warn_counts: dict[str, int] = {}
    for row in rows:
        feats = row.get("features") or {}
        pl = feats.get("player_layer") or {}
        if (pl.get("home") or {}).get("player_layer_index_existing") is not None:
            pl_ok += 1
        lu = feats.get("lineups") or {}
        if (lu.get("home") or {}).get("lineup_available"):
            lu_ok += 1
        un = feats.get("unavailable") or {}
        if (un.get("home") or {}).get("unavailable_macro_existing") is not None:
            un_ok += 1
        dq = row.get("data_quality") or {}
        for w in dq.get("warnings") or []:
            key = str(w).split(":")[0][:40]
            warn_counts[key] = warn_counts.get(key, 0) + 1

    top_warnings = sorted(warn_counts.items(), key=lambda x: -x[1])[:8]
    return {
        "fixtures_count": n,
        "player_layer_available_pct": round(100.0 * pl_ok / n, 1),
        "lineups_available_pct": round(100.0 * lu_ok / n, 1),
        "unavailable_available_pct": round(100.0 * un_ok / n, 1),
        "top_warnings": [{"code": k, "count": c} for k, c in top_warnings],
    }


def build_v31_dataset_rows(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
    max_fixtures: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    analyses, excluded, fixtures_by_id = _select_analyses_for_calibration(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    max_round = max((int(a.round_number) for a in analyses), default=38)
    pit_svc = PointInTimeContextService()
    rows: list[dict[str, Any]] = []
    pit_errors: list[dict[str, Any]] = []

    for analysis in sorted(analyses, key=lambda a: int(a.round_number)):
        rn = int(analysis.round_number)
        for orm_row in fixtures_by_id.get(int(analysis.id), []):
            if str(orm_row.status) != "ok" or orm_row.actual_total_sot is None:
                continue
            fid = int(orm_row.fixture_id)
            if max_fixtures is not None and len(rows) >= max_fixtures:
                return rows, excluded + pit_errors, max_round

            expl_all = dict(orm_row.explanation_json or {})
            explanation_v21 = expl_all.get(V21) if isinstance(expl_all.get(V21), dict) else None
            models_json = dict(orm_row.models_json or {})

            try:
                ctx = pit_svc.build_sot_context_with_historical(
                    db,
                    competition_id=int(competition_id),
                    fixture_id=fid,
                    mode=BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("v31 PIT build failed fixture_id=%s: %s", fid, exc)
                pit_errors.append({"fixture_id": fid, "error": str(exc)[:200]})
                continue

            bundle = build_features_bundle(ctx, explanation_v21=explanation_v21, max_round=max_round)
            row = {
                "metadata": map_metadata(
                    ctx,
                    competition_id=competition_id,
                    season_year=season_year,
                    round_number=rn,
                ),
                "target": map_target(ctx),
                "features": bundle["features"],
                "data_quality": bundle["data_quality"],
                "comparisons": map_comparisons(models_json),
            }
            rows.append(row)

    return rows, excluded + pit_errors, max_round


def build_v31_calibration_dataset(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
    max_fixtures: int | None = None,
) -> dict[str, Any]:
    comp = db.get(Competition, int(competition_id))
    rows, excluded, max_round = build_v31_dataset_rows(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
        max_fixtures=max_fixtures,
    )

    anti = validate_v31_rows(rows)
    coverage = _coverage_summary(rows)

    return {
        "report_type": "v31_calibration_dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "competition_id": int(competition_id),
        "competition_name": comp.name if comp else None,
        "season_year": int(season_year),
        "season_label": season_label_from_year(int(season_year)),
        "use_latest_version_per_round": use_latest_version_per_round,
        "fixtures_count": len(rows),
        "max_round_number": max_round,
        "coverage_summary": coverage,
        "comparisons_are_not_features": True,
        "anti_leakage_check": anti,
        "excluded_analyses": excluded,
        "rows": rows,
        "v31_model": {
            "model_key": "baseline_v3_1_sot_calibrated_predictor",
            "label": "v3.1 SOT Calibrated Predictor",
            "stage": "experimental",
            "description": (
                "Predittore indipendente pre-match; non usa predizioni finali v1.1/v2.0/v2.1/v3.0."
            ),
        },
    }
