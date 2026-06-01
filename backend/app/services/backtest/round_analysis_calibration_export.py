"""Export JSON/CSV calibrazione modello v3.0 da analisi Round Analysis persistite."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models import BacktestRoundAnalysis, BacktestRoundFixtureResult, Competition, Fixture
from app.schemas.backtest_round_analysis import DEFAULT_ROUND_ANALYSIS_MODELS, MODEL_LABELS, season_label_from_year
from app.services.backtest.round_analysis_aggregator import RoundAnalysisAggregator
from app.services.backtest.round_analysis_overview_aggregator import summarize_model_from_fixtures
COMPLETED_STATUSES = frozenset({"completed", "completed_with_warnings"})
from app.services.backtest.round_analysis_report_builder import (
    _build_trace_summary_for_report,
    _iso,
)
from app.services.backtest.round_analysis_summary_resolver import (
    fixture_rows_from_orm,
    resolve_round_display,
)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _round4(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)

from app.services.backtest.round_analysis_v21_trace_helpers import extract_v21_calibration_fields


def _global_model_summary(rows: list[dict[str, Any]], model_keys: list[str]) -> dict[str, Any]:
    agg = RoundAnalysisAggregator()
    out: dict[str, Any] = {}
    for key in model_keys:
        base = summarize_model_from_fixtures(key, rows)
        full = agg.build_model_summary(models=[key], fixture_results=rows).get(key, {})
        if isinstance(full, dict):
            base.update(
                {
                    "fixtures_ok": full.get("fixtures_ok"),
                    "fixtures_nd": full.get("fixtures_nd"),
                    "fixtures_error": full.get("fixtures_error"),
                    "avg_predicted_total": full.get("avg_predicted_total"),
                    "avg_actual_total": full.get("avg_actual_total"),
                },
            )
        out[key] = base
    return out


def _model_export_block(
    model_key: str,
    block: dict[str, Any],
    *,
    explanation_slice: dict[str, Any] | None,
    actual_total: int | None,
) -> dict[str, Any]:
    pt = block.get("predicted_total_sot")
    abs_error = bias = None
    if pt is not None and actual_total is not None:
        err = float(pt) - float(actual_total)
        abs_error = _round4(abs(err))
        bias = _round4(err)

    trace = _build_trace_summary_for_report(model_key, block, explanation_slice)
    trace["actuals_used_as_input"] = False
    if model_key == V21 and explanation_slice:
        trace["v21_calibration"] = extract_v21_calibration_fields(explanation_slice)

    return {
        "model_version_requested": block.get("model_version_requested") or model_key,
        "model_version_used": block.get("model_version_used") or model_key,
        "model_engine_name": block.get("model_engine_name"),
        "model_status": block.get("status") or block.get("model_status"),
        "predicted_home_sot": block.get("predicted_home_sot"),
        "predicted_away_sot": block.get("predicted_away_sot"),
        "predicted_total_sot": pt,
        "abs_error": abs_error,
        "bias": bias,
        "aggressive_line": block.get("aggressive_line"),
        "aggressive_edge": block.get("aggressive_edge"),
        "aggressive_advice": block.get("aggressive_advice"),
        "aggressive_reason": block.get("aggressive_reason"),
        "aggressive_outcome": block.get("aggressive_outcome"),
        "cautious_line": block.get("cautious_line"),
        "cautious_edge": block.get("cautious_edge"),
        "cautious_advice": block.get("cautious_advice"),
        "cautious_reason": block.get("cautious_reason"),
        "cautious_outcome": block.get("cautious_outcome"),
        "confidence": block.get("confidence"),
        "sample_bucket": block.get("sample_bucket"),
        "warnings": list(block.get("warnings") or []),
        "data_quality_json": dict(block.get("data_quality") or {}),
        "trace_summary_json": trace,
    }


def _load_fixtures_by_analysis(db: Session, analysis_ids: list[int]) -> dict[int, list[Any]]:
    if not analysis_ids:
        return {}
    rows = (
        db.query(BacktestRoundFixtureResult)
        .filter(BacktestRoundFixtureResult.analysis_id.in_(analysis_ids))
        .all()
    )
    out: dict[int, list[Any]] = {}
    for row in rows:
        out.setdefault(int(row.analysis_id), []).append(row)
    return out


def _model_keys_from_analyses(analyses: list[BacktestRoundAnalysis]) -> list[str]:
    keys: list[str] = []
    for analysis in analyses:
        cfg = dict(analysis.config_json or {})
        for k in cfg.get("models") or DEFAULT_ROUND_ANALYSIS_MODELS:
            if k not in keys:
                keys.append(str(k))
    return keys or list(DEFAULT_ROUND_ANALYSIS_MODELS)


def _select_analyses_for_calibration(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool,
    include_all_versions: bool,
) -> tuple[list[BacktestRoundAnalysis], list[dict[str, Any]], dict[int, list[Any]]]:
    all_rows = (
        db.query(BacktestRoundAnalysis)
        .filter(
            BacktestRoundAnalysis.competition_id == competition_id,
            BacktestRoundAnalysis.season_year == season_year,
        )
        .all()
    )

    excluded: list[dict[str, Any]] = []
    included: list[BacktestRoundAnalysis] = []
    latest_by_round: dict[int, BacktestRoundAnalysis] = {}

    for row in all_rows:
        if str(row.status) not in COMPLETED_STATUSES:
            excluded.append({"id": int(row.id), "reason": str(row.status)})
            continue
        rn = int(row.round_number)
        if use_latest_version_per_round and not include_all_versions:
            prev = latest_by_round.get(rn)
            if prev is None or int(row.analysis_version) > int(prev.analysis_version):
                if prev is not None:
                    excluded.append({"id": int(prev.id), "reason": "superseded_version"})
                latest_by_round[rn] = row
            else:
                excluded.append({"id": int(row.id), "reason": "superseded_version"})
        else:
            included.append(row)

    if use_latest_version_per_round and not include_all_versions:
        included = list(latest_by_round.values())

    fixtures_by_id = _load_fixtures_by_analysis(db, [int(a.id) for a in included])
    model_keys = _model_keys_from_analyses(included) if included else list(DEFAULT_ROUND_ANALYSIS_MODELS)

    final_included: list[BacktestRoundAnalysis] = []
    for analysis in sorted(included, key=lambda a: int(a.round_number)):
        rows = fixture_rows_from_orm(fixtures_by_id.get(int(analysis.id), []))
        keys = list((analysis.config_json or {}).get("models") or model_keys)
        display = resolve_round_display(
            status=str(analysis.status),
            model_summary=analysis.model_summary_json,
            rows=rows,
            model_keys=keys,
        )
        if display["completeness"] == "ok":
            final_included.append(analysis)
        else:
            excluded.append({"id": int(analysis.id), "reason": display["completeness"]})

    return final_included, excluded, fixtures_by_id


def build_calibration_report(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
) -> dict[str, Any]:
    comp = db.get(Competition, int(competition_id))
    analyses, excluded, fixtures_by_id = _select_analyses_for_calibration(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )

    model_keys = _model_keys_from_analyses(analyses)
    all_fixture_rows: list[dict[str, Any]] = []
    for analysis in analyses:
        all_fixture_rows.extend(fixture_rows_from_orm(fixtures_by_id.get(int(analysis.id), [])))

    fixture_ids = {int(r["fixture_id"]) for r in all_fixture_rows if r.get("fixture_id")}
    kickoff_map: dict[int, datetime | None] = {}
    if fixture_ids:
        for fx in db.query(Fixture).filter(Fixture.id.in_(fixture_ids)).all():
            kickoff_map[int(fx.id)] = fx.kickoff_at

    fixtures_out: list[dict[str, Any]] = []
    for analysis in analyses:
        cfg = dict(analysis.config_json or {})
        keys = list(cfg.get("models") or model_keys)
        for row in fixtures_by_id.get(int(analysis.id), []):
            if str(row.status) != "ok":
                continue
            expl_all = dict(row.explanation_json or {})
            models_out: dict[str, Any] = {}
            for key in keys:
                block = (row.models_json or {}).get(key)
                if not isinstance(block, dict):
                    continue
                expl_slice = expl_all.get(key) if key == V21 else None
                models_out[key] = _model_export_block(
                    key,
                    block,
                    explanation_slice=expl_slice,
                    actual_total=row.actual_total_sot,
                )
            fixtures_out.append(
                {
                    "analysis_id": int(analysis.id),
                    "round_number": int(analysis.round_number),
                    "fixture_id": int(row.fixture_id),
                    "kickoff_at": _iso(kickoff_map.get(int(row.fixture_id))),
                    "home_team": row.home_team_name,
                    "away_team": row.away_team_name,
                    "actual_home_sot": row.actual_home_sot,
                    "actual_away_sot": row.actual_away_sot,
                    "actual_total_sot": row.actual_total_sot,
                    "fixture_status": row.status,
                    "explanation_v21": expl_all.get(V21),
                    "models": models_out,
                },
            )

    return {
        "report_type": "round_analysis_calibration_v3",
        "metadata": {
            "competition_id": int(competition_id),
            "competition_name": comp.name if comp else None,
            "season_year": int(season_year),
            "season_label": season_label_from_year(season_year),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analyzed_rounds": len(analyses),
            "analyzed_fixtures": len(fixtures_out),
            "included_analysis_ids": [int(a.id) for a in analyses],
            "excluded_analysis_ids": excluded,
            "use_latest_version_per_round": use_latest_version_per_round and not include_all_versions,
        },
        "global_model_summary": _global_model_summary(all_fixture_rows, model_keys),
        "fixtures": fixtures_out,
    }


def build_calibration_csv(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
) -> str:
    from app.services.backtest.round_analysis_diagnostics_aggregator import (
        compute_low_total_risk_score,
        diagnostics_actual_total_bucket,
        diagnostics_predicted_total_bucket,
        low_total_risk_bucket,
    )

    report = build_calibration_report(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    fieldnames = [
        "round_number",
        "fixture_id",
        "match",
        "home_team",
        "away_team",
        "actual_home_sot",
        "actual_away_sot",
        "actual_total_sot",
        "model_key",
        "model_label",
        "model_status",
        "predicted_home_sot",
        "predicted_away_sot",
        "predicted_total_sot",
        "abs_error",
        "bias",
        "aggressive_line",
        "aggressive_edge",
        "aggressive_advice",
        "aggressive_outcome",
        "cautious_line",
        "cautious_edge",
        "cautious_advice",
        "cautious_outcome",
        "confidence",
        "sample_bucket",
        "actual_bucket",
        "predicted_bucket",
        "low_total_risk_bucket",
        "warnings",
        "base_anchor_sot_home",
        "base_anchor_sot_away",
        "weighted_macro_multiplier_home",
        "weighted_macro_multiplier_away",
        "split_index_home",
        "split_index_away",
        "player_layer_index_home",
        "player_layer_index_away",
        "lineups_index_home",
        "lineups_index_away",
        "injuries_unavailable_index_home",
        "injuries_unavailable_index_away",
        "chance_quality_index_home",
        "chance_quality_index_away",
        "recent_form_index_home",
        "recent_form_index_away",
        "pace_control_index_home",
        "pace_control_index_away",
        "fallback_count",
        "leakage_guard",
        "actuals_used_as_input",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for fx in report.get("fixtures") or []:
        match = f"{fx.get('home_team')} vs {fx.get('away_team')}"
        actual_total = fx.get("actual_total_sot")
        for model_key, block in (fx.get("models") or {}).items():
            trace = block.get("trace_summary_json") or {}
            v21 = trace.get("v21_calibration") or {}
            pt = block.get("predicted_total_sot")
            risk_row = {
                "block": {
                    "predicted_total_sot": pt,
                    "confidence": block.get("confidence"),
                    "sample_bucket": block.get("sample_bucket"),
                    "warnings": block.get("warnings") or [],
                },
                "explanation_v21": fx.get("explanation_v21") if model_key == V21 else None,
            }
            risk_score = compute_low_total_risk_score(risk_row) if model_key == V21 else 0.0
            warnings = block.get("warnings") or []
            writer.writerow(
                {
                    "round_number": fx.get("round_number"),
                    "fixture_id": fx.get("fixture_id"),
                    "match": match,
                    "home_team": fx.get("home_team"),
                    "away_team": fx.get("away_team"),
                    "actual_home_sot": fx.get("actual_home_sot"),
                    "actual_away_sot": fx.get("actual_away_sot"),
                    "actual_total_sot": actual_total,
                    "model_key": model_key,
                    "model_label": MODEL_LABELS.get(model_key, model_key),
                    "model_status": block.get("model_status"),
                    "predicted_home_sot": block.get("predicted_home_sot"),
                    "predicted_away_sot": block.get("predicted_away_sot"),
                    "predicted_total_sot": pt,
                    "abs_error": block.get("abs_error"),
                    "bias": block.get("bias"),
                    "aggressive_line": block.get("aggressive_line"),
                    "aggressive_edge": block.get("aggressive_edge"),
                    "aggressive_advice": block.get("aggressive_advice"),
                    "aggressive_outcome": block.get("aggressive_outcome"),
                    "cautious_line": block.get("cautious_line"),
                    "cautious_edge": block.get("cautious_edge"),
                    "cautious_advice": block.get("cautious_advice"),
                    "cautious_outcome": block.get("cautious_outcome"),
                    "confidence": block.get("confidence"),
                    "sample_bucket": block.get("sample_bucket"),
                    "actual_bucket": diagnostics_actual_total_bucket(actual_total),
                    "predicted_bucket": diagnostics_predicted_total_bucket(pt),
                    "low_total_risk_bucket": low_total_risk_bucket(risk_score) if model_key == V21 else "",
                    "warnings": "; ".join(str(w) for w in warnings),
                    "base_anchor_sot_home": v21.get("base_anchor_sot_home"),
                    "base_anchor_sot_away": v21.get("base_anchor_sot_away"),
                    "weighted_macro_multiplier_home": v21.get("weighted_macro_multiplier_home"),
                    "weighted_macro_multiplier_away": v21.get("weighted_macro_multiplier_away"),
                    "split_index_home": v21.get("split_index_home"),
                    "split_index_away": v21.get("split_index_away"),
                    "player_layer_index_home": v21.get("player_layer_index_home"),
                    "player_layer_index_away": v21.get("player_layer_index_away"),
                    "lineups_index_home": v21.get("lineups_index_home"),
                    "lineups_index_away": v21.get("lineups_index_away"),
                    "injuries_unavailable_index_home": v21.get("injuries_unavailable_index_home"),
                    "injuries_unavailable_index_away": v21.get("injuries_unavailable_index_away"),
                    "chance_quality_index_home": v21.get("chance_quality_index_home"),
                    "chance_quality_index_away": v21.get("chance_quality_index_away"),
                    "recent_form_index_home": v21.get("recent_form_index_home"),
                    "recent_form_index_away": v21.get("recent_form_index_away"),
                    "pace_control_index_home": v21.get("pace_control_index_home"),
                    "pace_control_index_away": v21.get("pace_control_index_away"),
                    "fallback_count": v21.get("fallback_count"),
                    "leakage_guard": v21.get("leakage_guard"),
                    "actuals_used_as_input": v21.get("actuals_used_as_input", False),
                },
            )
    return "\ufeff" + buf.getvalue()
