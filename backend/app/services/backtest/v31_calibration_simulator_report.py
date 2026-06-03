"""Costruzione report JSON leggero/completo simulatore v3.1."""

from __future__ import annotations

import copy
from typing import Any

from app.services.backtest.v31_calibration_simulator_metrics import error_distribution
from app.services.backtest.v31_calibration_simulator_predictor import (
    STRATEGY_STATUS,
    resolve_strategy_keys,
)


def _slim_row(row: dict[str, Any]) -> dict[str, Any]:
    trace = row.get("trace") if isinstance(row.get("trace"), dict) else {}
    return {
        "fixture_id": row.get("fixture_id"),
        "match": row.get("match"),
        "round_number": row.get("round_number"),
        "predicted_total_sot": row.get("predicted_total_sot"),
        "actual_total_sot": row.get("actual_total_sot"),
        "predicted_bucket": row.get("predicted_bucket"),
        "actual_bucket": row.get("actual_bucket"),
        "error": row.get("error"),
        "abs_error": row.get("abs_error"),
        "boost_applied": trace.get("boost_applied"),
        "high_total_signal": trace.get("high_total_signal"),
        "boost_reason": trace.get("boost_reason"),
    }


def _slim_strategy_block(
    block: dict[str, Any],
    *,
    worst_n: int = 10,
    fixture_sample_n: int = 10,
    include_all_rows: bool,
) -> dict[str, Any]:
    out = copy.deepcopy(block)
    rows = block.get("rows_sample") or block.get("_all_rows") or []
    if include_all_rows and block.get("_all_rows"):
        out["rows_sample"] = [_slim_row(r) for r in block["_all_rows"]]
    else:
        out["rows_sample"] = [_slim_row(r) for r in rows[:fixture_sample_n]]

    err = dict(block.get("error_distribution") or {})
    if not include_all_rows and rows:
        err = error_distribution(rows, top_n=worst_n)
        for key in ("worst_overestimations", "worst_underestimations"):
            err[key] = [_enrich_worst_entry(e) for e in err.get(key) or []]
    else:
        for key in ("worst_overestimations", "worst_underestimations"):
            err[key] = [_enrich_worst_entry(e) for e in err.get(key) or []]
    out["error_distribution"] = err
    out.pop("_all_rows", None)
    out.pop("coverage_samples", None)
    return out


def _enrich_worst_entry(entry: dict[str, Any]) -> dict[str, Any]:
    e = dict(entry)
    trace = e.get("trace") if isinstance(e.get("trace"), dict) else {}
    if not trace:
        return e
    e["boost_applied"] = trace.get("boost_applied")
    e["high_total_signal"] = trace.get("high_total_signal")
    return e


def build_report_payload(
    raw: dict[str, Any],
    *,
    detail: str = "summary",
    strategy: str = "all",
    strategy_status_filter: str = "active",
    worst_n: int = 10,
    fixture_sample_n: int = 10,
) -> dict[str, Any]:
    """detail=summary: report leggero; detail=full: righe complete per strategie richieste."""
    payload = copy.deepcopy(raw)
    include_all_rows = detail == "full"

    if strategy != "all":
        keys = resolve_strategy_keys(strategy, "all")
        if strategy in keys:
            keys = [strategy]
        else:
            keys = []
    else:
        keys = resolve_strategy_keys("all", strategy_status_filter)

    strategies = []
    for block in raw.get("strategies") or []:
        if block.get("key") not in keys:
            continue
        strategies.append(
            _slim_strategy_block(
                block,
                worst_n=worst_n,
                fixture_sample_n=fixture_sample_n if not include_all_rows else 999999,
                include_all_rows=include_all_rows,
            ),
        )

    payload["strategies"] = strategies
    payload["summary"] = dict(payload.get("summary") or {})
    payload["summary"]["strategies_run"] = len(strategies)
    payload["summary"]["report_detail"] = detail
    payload["summary"]["strategy_status_filter"] = strategy_status_filter
    payload["strategy_status_catalog"] = dict(STRATEGY_STATUS)
    return payload
