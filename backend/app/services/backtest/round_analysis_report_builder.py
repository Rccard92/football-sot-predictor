"""Costruzione report JSON audit Round Analysis (solo dati persistiti)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR,
)
from app.services.backtest.round_analysis_v21_trace_helpers import extract_v21_macro_averages
from app.models import BacktestRoundAnalysis, BacktestRoundFixtureResult
from app.services.backtest.player_layer_fixture_status import merge_player_layer_into_data_quality_summary
from app.schemas.backtest_round_analysis import (
    DEFAULT_ROUND_ANALYSIS_MODELS,
    MODEL_LABELS,
    season_label_from_year,
)

V21_MODEL_KEY = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()


def _betting_side(block: dict[str, Any], prefix: str) -> dict[str, Any]:
    return {
        "line": block.get(f"{prefix}_line"),
        "edge": block.get(f"{prefix}_edge"),
        "advice": block.get(f"{prefix}_advice"),
        "reason": block.get(f"{prefix}_reason"),
        "outcome": block.get(f"{prefix}_outcome"),
    }


def _macro_indexes_from_explanation(expl: dict[str, Any] | None) -> dict[str, Any]:
    if not expl:
        return {}
    out: dict[str, Any] = {}
    for side in ("home", "away"):
        side_data = expl.get(side)
        if not isinstance(side_data, dict):
            continue
        macros = side_data.get("macros")
        if not isinstance(macros, list):
            continue
        for macro in macros:
            if isinstance(macro, dict) and macro.get("key"):
                key = str(macro["key"])
                out[f"{side}_{key}"] = {
                    "macro_index": macro.get("macro_index"),
                    "status": macro.get("status"),
                }
    return out


def _build_trace_summary_for_report(
    model_key: str,
    block: dict[str, Any],
    explanation_slice: dict[str, Any] | None,
) -> dict[str, Any]:
    trace = dict(block.get("trace_summary") or {})
    status = str(block.get("status") or block.get("model_status") or "")
    trace.setdefault("actuals_used_as_input", False)
    if "leakage_guard" not in trace:
        if explanation_slice and "leakage_guard" in explanation_slice:
            trace["leakage_guard"] = explanation_slice.get("leakage_guard")
        elif status == "ok":
            trace["leakage_guard"] = True

    if model_key == BASELINE_SOT_MODEL_VERSION_V11_SOT:
        for key in (
            "split_context",
            "formula_quality",
            "fallback_used",
            "formula_inputs",
            "formula_outputs",
            "prior_context",
            "inferred_error_code",
            "home_side",
            "away_side",
            "missing_fields",
        ):
            if key in block and key not in trace:
                trace[key] = block.get(key)

    if model_key == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT:
        trace.setdefault("base_v1_1_total", trace.get("base_predicted_total"))
        trace.setdefault("adjusted_total_sot", block.get("predicted_total_sot"))

    if model_key == V21_MODEL_KEY and explanation_slice:
        trace["v21_audit"] = {
            "leakage_guard": explanation_slice.get("leakage_guard"),
            "actuals_used_as_input": explanation_slice.get("actuals_used_as_input", False),
            "fallback_count": explanation_slice.get("fallback_count"),
            "warnings": explanation_slice.get("warnings"),
            "source_fixture_id_lineup_home": explanation_slice.get("source_fixture_id_lineup_home"),
            "source_fixture_id_lineup_away": explanation_slice.get("source_fixture_id_lineup_away"),
            "source_fixture_id_unavailable_home": explanation_slice.get(
                "source_fixture_id_unavailable_home",
            ),
            "source_fixture_id_unavailable_away": explanation_slice.get(
                "source_fixture_id_unavailable_away",
            ),
            "home": explanation_slice.get("home"),
            "away": explanation_slice.get("away"),
            "macro_indexes": _macro_indexes_from_explanation(explanation_slice),
        }

    if block.get("warnings"):
        trace.setdefault("warnings", list(block.get("warnings") or []))

    if model_key == BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR:
        selection = trace.get("selection") or block.get("selection") or {}
        audit = trace.get("audit") or block.get("audit") or {}
        trace["selection"] = selection
        trace["audit"] = audit
        trace["actuals_used_as_input"] = audit.get("actuals_used_as_input", False)
        trace["leakage_guard"] = audit.get("leakage_guard", True)
        trace["v1_1_predicted_total"] = block.get("v1_1_predicted_total")
        trace["v2_1_predicted_total"] = block.get("v2_1_predicted_total")
        v11 = trace.get("v1_1_predicted_total") or block.get("v1_1_predicted_total")
        v21 = trace.get("v2_1_predicted_total") or block.get("v2_1_predicted_total")
        if v11 is not None and v21 is not None:
            try:
                trace["prediction_gap"] = round(float(v21) - float(v11), 4)
            except (TypeError, ValueError):
                pass
        expl_v21 = None
        if explanation_slice and isinstance(explanation_slice.get("reference_explanation_v2_1"), dict):
            expl_v21 = explanation_slice["reference_explanation_v2_1"]
        elif isinstance(explanation_slice, dict) and explanation_slice.get("home"):
            expl_v21 = explanation_slice
        trace["macro_snapshot"] = extract_v21_macro_averages(expl_v21)

    return trace


def _value_selector_section(
    block: dict[str, Any],
    explanation_slice: dict[str, Any] | None,
) -> dict[str, Any]:
    trace = dict(block.get("trace_summary") or {})
    selection = dict(trace.get("selection") or block.get("selection") or {})
    audit = dict(trace.get("audit") or block.get("audit") or {})
    expl_v21 = None
    if explanation_slice:
        expl_v21 = explanation_slice.get("reference_explanation_v2_1")
        if not isinstance(expl_v21, dict):
            expl_v21 = explanation_slice if explanation_slice.get("home") else None
    v11 = block.get("v1_1_predicted_total")
    v21 = block.get("v2_1_predicted_total")
    gap = None
    if v11 is not None and v21 is not None:
        try:
            gap = round(float(v21) - float(v11), 4)
        except (TypeError, ValueError):
            gap = None
    return {
        "selection": selection,
        "audit": audit,
        "v1_1_predicted_total": v11,
        "v2_1_predicted_total": v21,
        "prediction_gap": gap,
        "macro_snapshot": extract_v21_macro_averages(expl_v21 if isinstance(expl_v21, dict) else None),
        "warnings": list(block.get("warnings") or []),
    }


def model_block_to_report(
    model_key: str,
    block: dict[str, Any],
    *,
    explanation_slice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = block.get("status") or block.get("model_status")
    out: dict[str, Any] = {
        "label": block.get("label") or MODEL_LABELS.get(model_key, model_key),
        "model_version_requested": block.get("model_version_requested") or model_key,
        "model_version_used": block.get("model_version_used") or model_key,
        "model_engine_name": block.get("model_engine_name"),
        "status": status,
        "error_code": block.get("error_code"),
        "error_message": block.get("error_message") or block.get("message"),
        "prediction": {
            "home_predicted_sot": block.get("predicted_home_sot"),
            "away_predicted_sot": block.get("predicted_away_sot"),
            "predicted_total_sot": block.get("predicted_total_sot"),
        },
        "betting": {
            "aggressive": _betting_side(block, "aggressive"),
            "cautious": _betting_side(block, "cautious"),
        },
        "trace_summary": _build_trace_summary_for_report(model_key, block, explanation_slice),
        "sample_bucket": block.get("sample_bucket"),
        "formula_quality": block.get("formula_quality"),
        "fallback_used": block.get("fallback_used"),
        "used_split": block.get("used_split"),
        "warnings": list(block.get("warnings") or []),
        "data_quality": dict(block.get("data_quality") or {}),
    }
    if model_key == BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR:
        out["value_selector"] = _value_selector_section(block, explanation_slice)
    return out


def build_fixture_report(
    row: BacktestRoundFixtureResult,
    *,
    kickoff_at: datetime | None = None,
    model_keys: list[str] | None = None,
) -> dict[str, Any]:
    models_json = dict(row.models_json or {})
    explanation = dict(row.explanation_json or {}) if row.explanation_json else {}
    keys = model_keys or list(DEFAULT_ROUND_ANALYSIS_MODELS)
    models_out: dict[str, Any] = {}
    for key in keys:
        block = models_json.get(key)
        if not isinstance(block, dict):
            continue
        expl_slice = explanation.get(key) if key in (V21_MODEL_KEY, BASELINE_SOT_MODEL_VERSION_V30_VALUE_SELECTOR) else None
        if expl_slice is None and key == V21_MODEL_KEY:
            expl_slice = explanation.get(V21_MODEL_KEY) or explanation
        models_out[key] = model_block_to_report(key, block, explanation_slice=expl_slice)

    dq_merged: dict[str, str] = {}
    for block in models_json.values():
        if isinstance(block, dict) and isinstance(block.get("data_quality"), dict):
            dq_merged.update({str(k): str(v) for k, v in block["data_quality"].items()})

    home = str(row.home_team_name)
    away = str(row.away_team_name)
    return {
        "fixture_id": int(row.fixture_id),
        "round_number": row.round_number,
        "kickoff_at": _iso(kickoff_at),
        "match": f"{home} vs {away}",
        "home_team": home,
        "away_team": away,
        "actuals": {
            "home_sot": row.actual_home_sot,
            "away_sot": row.actual_away_sot,
            "total_sot": row.actual_total_sot,
            "used_as_input": False,
        },
        "fixture_status": row.status,
        "fixture_error_message": row.error_message,
        "models": models_out,
        "data_quality": dq_merged,
    }


def build_round_report(
    analysis: BacktestRoundAnalysis,
    fixture_rows: list[BacktestRoundFixtureResult],
    *,
    competition_name: str | None = None,
    kickoff_by_fixture_id: dict[int, datetime | None] | None = None,
) -> dict[str, Any]:
    cfg = dict(analysis.config_json or {})
    season_label = str(cfg.get("season_label") or season_label_from_year(int(analysis.season_year)))
    model_keys = list(cfg.get("models") or DEFAULT_ROUND_ANALYSIS_MODELS)
    kickoff_map = kickoff_by_fixture_id or {}

    fixtures = [
        build_fixture_report(
            row,
            kickoff_at=kickoff_map.get(int(row.fixture_id)),
            model_keys=model_keys,
        )
        for row in fixture_rows
    ]

    ms = dict(analysis.model_summary_json or {})
    round_summary = {
        "total_fixtures": int(analysis.total_fixtures),
        "processed_fixtures": int(analysis.processed_fixtures),
        "failed_fixtures": int(analysis.failed_fixtures),
        "fixtures_in_report": len(fixtures),
        "status": str(analysis.status),
    }
    if ms:
        round_summary["models"] = ms

    fixture_row_dicts = [
        {
            "status": row.status,
            "models_json": dict(row.models_json or {}),
            "explanation_json": dict(row.explanation_json or {}),
        }
        for row in fixture_rows
    ]
    dq_raw = analysis.data_quality_summary_json
    dq_summary = (
        merge_player_layer_into_data_quality_summary(dict(dq_raw), fixture_row_dicts)
        if isinstance(dq_raw, dict)
        else merge_player_layer_into_data_quality_summary({}, fixture_row_dicts)
    )

    return {
        "report_type": "round_analysis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis": {
            "id": int(analysis.id),
            "competition_id": int(analysis.competition_id),
            "competition_name": competition_name,
            "season_year": int(analysis.season_year),
            "season_label": season_label,
            "round_number": int(analysis.round_number),
            "analysis_version": int(analysis.analysis_version),
            "status": str(analysis.status),
            "data_quality_status": (
                (analysis.data_quality_summary_json or {}).get("data_quality_status")
                if isinstance(analysis.data_quality_summary_json, dict)
                else None
            ),
            "created_at": _iso(analysis.created_at),
            "completed_at": _iso(analysis.completed_at),
        },
        "config": {
            "mode": str(analysis.mode),
            "models": model_keys,
            "lines": list(cfg.get("lines") or []),
            "cautious_drop_threshold": cfg.get("cautious_drop_threshold"),
            "advice_filters": dict(cfg.get("advice_filters") or {}),
            "season_label": season_label,
        },
        "round_summary": round_summary,
        "data_quality_summary": dq_summary,
        "model_summaries": ms,
        "fixtures": fixtures,
    }


def build_fixture_report_payload(
    analysis: BacktestRoundAnalysis,
    row: BacktestRoundFixtureResult,
    *,
    competition_name: str | None = None,
    kickoff_at: datetime | None = None,
) -> dict[str, Any]:
    cfg = dict(analysis.config_json or {})
    model_keys = list(cfg.get("models") or DEFAULT_ROUND_ANALYSIS_MODELS)
    return {
        "report_type": "round_analysis_fixture",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_id": int(analysis.id),
        "competition_id": int(analysis.competition_id),
        "competition_name": competition_name,
        "season_year": int(analysis.season_year),
        "season_label": str(cfg.get("season_label") or season_label_from_year(int(analysis.season_year))),
        "round_number": int(analysis.round_number),
        "analysis_version": int(analysis.analysis_version),
        "fixture": build_fixture_report(row, kickoff_at=kickoff_at, model_keys=model_keys),
    }
