"""Costruzione dataset calibrazione v3.1 da Round Analysis + PIT storico."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Literal

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
from app.services.backtest.v31_calibration_row_builder_standard import build_standard_row

logger = logging.getLogger(__name__)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
PROGRESS_EVERY = 50
PROGRESS_EVERY_FULL = 25
DetailLevel = Literal["standard", "full"]


def _round_in_range(
    round_number: int,
    *,
    round_from: int | None,
    round_to: int | None,
) -> bool:
    if round_from is not None and round_number < int(round_from):
        return False
    if round_to is not None and round_number > int(round_to):
        return False
    return True


def _iter_calibration_fixtures(
    analyses: list[Any],
    fixtures_by_id: dict[int, list[Any]],
    *,
    round_from: int | None = None,
    round_to: int | None = None,
) -> list[tuple[Any, Any, int]]:
    """(analysis, orm_row, round_number) per fixture idonea, opz. filtrate per giornata."""
    out: list[tuple[Any, Any, int]] = []
    for analysis in sorted(analyses, key=lambda a: int(a.round_number)):
        rn = int(analysis.round_number)
        if not _round_in_range(rn, round_from=round_from, round_to=round_to):
            continue
        for orm_row in fixtures_by_id.get(int(analysis.id), []):
            if str(orm_row.status) != "ok" or orm_row.actual_total_sot is None:
                continue
            out.append((analysis, orm_row, rn))
    return out


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
        dq = feats.get("data_quality") or {}
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


def build_v31_dataset_rows_standard(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
    max_fixtures: int | None = None,
    rows_expected: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    analyses, excluded, fixtures_by_id = _select_analyses_for_calibration(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    max_round = max((int(a.round_number) for a in analyses), default=38)
    fixtures = _iter_calibration_fixtures(analyses, fixtures_by_id)
    if rows_expected is None:
        rows_expected = len(fixtures)

    logger.info(
        "V31_DATASET_EXPORT_START format=json detail=standard rows_expected=%s",
        rows_expected,
    )
    t0 = time.perf_counter()
    rows: list[dict[str, Any]] = []

    for _analysis, orm_row, rn in fixtures:
        if max_fixtures is not None and len(rows) >= max_fixtures:
            break
        rows.append(
            build_standard_row(
                orm_row,
                competition_id=competition_id,
                season_year=season_year,
                round_number=rn,
                max_round=max_round,
            ),
        )
        if len(rows) % PROGRESS_EVERY == 0:
            logger.info("V31_DATASET_EXPORT_PROGRESS rows=%s", len(rows))

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "V31_DATASET_EXPORT_DONE format=json detail=standard rows=%s duration_ms=%s",
        len(rows),
        duration_ms,
    )
    return rows, excluded, max_round


def build_single_full_row(
    db: Session,
    orm_row: Any,
    *,
    competition_id: int,
    season_year: int,
    round_number: int,
    max_round: int,
    pit_svc: PointInTimeContextService | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Costruisce una riga full con PIT. Ritorna (row, pit_error)."""
    fid = int(orm_row.fixture_id)
    pit = pit_svc or PointInTimeContextService()
    expl_all = dict(orm_row.explanation_json or {})
    explanation_v21 = expl_all.get(V21) if isinstance(expl_all.get(V21), dict) else None
    models_json = dict(orm_row.models_json or {})

    t_pit = time.perf_counter()
    logger.info("V31_FULL_EXPORT_PIT_RECONSTRUCTION_START fixture_id=%s", fid)
    try:
        ctx = pit.build_sot_context_with_historical(
            db,
            competition_id=int(competition_id),
            fixture_id=fid,
            mode=BACKTEST_MODE_HISTORICAL_OFFICIAL_XI,
        )
    except Exception as exc:  # noqa: BLE001
        pit_ms = int((time.perf_counter() - t_pit) * 1000)
        logger.warning(
            "V31_FULL_EXPORT_PIT_RECONSTRUCTION_DONE fixture_id=%s duration_ms=%s failed=1",
            fid,
            pit_ms,
        )
        return None, {"fixture_id": fid, "error": str(exc)[:200]}
    pit_ms = int((time.perf_counter() - t_pit) * 1000)
    logger.info(
        "V31_FULL_EXPORT_PIT_RECONSTRUCTION_DONE fixture_id=%s duration_ms=%s",
        fid,
        pit_ms,
    )

    bundle = build_features_bundle(ctx, explanation_v21=explanation_v21, max_round=max_round)
    meta = map_metadata(
        ctx,
        competition_id=competition_id,
        season_year=season_year,
        round_number=round_number,
    )
    meta["detail"] = "full"
    return (
        {
            "metadata": meta,
            "target": map_target(ctx),
            "features": bundle["features"],
            "comparisons": map_comparisons(models_json),
        },
        None,
    )


def build_v31_dataset_rows_full(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
    max_fixtures: int | None = None,
    rows_expected: int | None = None,
    round_from: int | None = None,
    round_to: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    analyses, excluded, fixtures_by_id = _select_analyses_for_calibration(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    max_round = max((int(a.round_number) for a in analyses), default=38)
    fixtures = _iter_calibration_fixtures(
        analyses,
        fixtures_by_id,
        round_from=round_from,
        round_to=round_to,
    )
    if rows_expected is None:
        rows_expected = len(fixtures)

    logger.info(
        "V31_DATASET_EXPORT_START format=json detail=full rows_expected=%s",
        rows_expected,
    )
    t0 = time.perf_counter()
    pit_svc = PointInTimeContextService()
    rows: list[dict[str, Any]] = []
    pit_errors: list[dict[str, Any]] = []

    for _analysis, orm_row, rn in fixtures:
        if max_fixtures is not None and len(rows) >= max_fixtures:
            break
        fid = int(orm_row.fixture_id)
        t_row = time.perf_counter()
        logger.info("V31_FULL_EXPORT_BUILD_ROW_START fixture_id=%s", fid)
        row, err = build_single_full_row(
            db,
            orm_row,
            competition_id=competition_id,
            season_year=season_year,
            round_number=rn,
            max_round=max_round,
            pit_svc=pit_svc,
        )
        row_ms = int((time.perf_counter() - t_row) * 1000)
        logger.info(
            "V31_FULL_EXPORT_BUILD_ROW_DONE fixture_id=%s duration_ms=%s",
            fid,
            row_ms,
        )
        if err:
            pit_errors.append(err)
            continue
        if row:
            rows.append(row)
        if len(rows) % PROGRESS_EVERY_FULL == 0 and len(rows) > 0:
            logger.info(
                "V31_DATASET_EXPORT_PROGRESS detail=full rows_done=%s rows_expected=%s",
                len(rows),
                rows_expected,
            )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "V31_DATASET_EXPORT_DONE format=json detail=full rows=%s duration_ms=%s",
        len(rows),
        duration_ms,
    )
    return rows, excluded + pit_errors, max_round


def assemble_full_dataset_payload(
    db: Session,
    *,
    rows: list[dict[str, Any]],
    excluded: list[dict[str, Any]],
    competition_id: int,
    season_year: int,
    max_round: int,
    use_latest_version_per_round: bool,
    chunk_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comp = db.get(Competition, int(competition_id))
    anti = validate_v31_rows(rows)
    coverage = _coverage_summary(rows)
    payload: dict[str, Any] = {
        "report_type": "v31_calibration_dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "competition_id": int(competition_id),
        "competition_name": comp.name if comp else None,
        "season_year": int(season_year),
        "season_label": season_label_from_year(int(season_year)),
        "detail": "full",
        "use_latest_version_per_round": use_latest_version_per_round,
        "fixtures_count": len(rows),
        "max_round_number": max_round,
        "coverage_summary": coverage,
        "comparisons_are_not_features": True,
        "anti_leakage_check": anti,
        "exportable": anti.get("status") == "ok",
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
    if chunk_meta:
        payload["chunk"] = chunk_meta
    return payload


def build_v31_dataset_rows(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
    max_fixtures: int | None = None,
    detail: DetailLevel = "standard",
    round_from: int | None = None,
    round_to: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    if detail == "full":
        return build_v31_dataset_rows_full(
            db,
            competition_id=competition_id,
            season_year=season_year,
            use_latest_version_per_round=use_latest_version_per_round,
            include_all_versions=include_all_versions,
            max_fixtures=max_fixtures,
            round_from=round_from,
            round_to=round_to,
        )
    return build_v31_dataset_rows_standard(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
        max_fixtures=max_fixtures,
    )


def build_v31_calibration_dataset(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
    max_fixtures: int | None = None,
    detail: DetailLevel = "standard",
    round_from: int | None = None,
    round_to: int | None = None,
    chunk_part: int | None = None,
    chunk_total_parts: int | None = None,
) -> dict[str, Any]:
    comp = db.get(Competition, int(competition_id))
    rows, excluded, max_round = build_v31_dataset_rows(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
        max_fixtures=max_fixtures,
        detail=detail,
        round_from=round_from,
        round_to=round_to,
    )

    if detail == "full":
        chunk_meta = None
        if chunk_part is not None and round_from is not None and round_to is not None:
            chunk_meta = {
                "part": int(chunk_part),
                "total_parts": int(chunk_total_parts or 1),
                "round_from": int(round_from),
                "round_to": int(round_to),
            }
        return assemble_full_dataset_payload(
            db,
            rows=rows,
            excluded=excluded,
            competition_id=competition_id,
            season_year=season_year,
            max_round=max_round,
            use_latest_version_per_round=use_latest_version_per_round,
            chunk_meta=chunk_meta,
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
        "detail": detail,
        "use_latest_version_per_round": use_latest_version_per_round,
        "fixtures_count": len(rows),
        "max_round_number": max_round,
        "coverage_summary": coverage,
        "comparisons_are_not_features": True,
        "anti_leakage_check": anti,
        "exportable": anti.get("status") == "ok",
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
