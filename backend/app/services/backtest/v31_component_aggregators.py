"""Aggregati giornata/stagione per confronto componenti predetto vs actual."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from app.services.backtest.v31_component_trace_builder import flatten_component_rows


def _aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggrega per strategy_key × macro_area × variable_key."""
    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in rows:
        sk = str(row.get("strategy_key") or "")
        ma = str(row.get("macro_area") or "")
        vk = str(row.get("key") or "")
        key = (sk, ma, vk)
        b = buckets.setdefault(
            key,
            {
                "strategy_key": sk,
                "macro_area": ma,
                "macro_area_label": row.get("macro_area_label"),
                "variable_key": vk,
                "label": row.get("label"),
                "predicted_values": [],
                "actual_values": [],
                "deltas": [],
                "abs_deltas": [],
                "contribution_deltas": [],
                "overestimated": 0,
                "underestimated": 0,
                "aligned": 0,
                "not_comparable": 0,
                "missing_actual": 0,
                "suspicious": 0,
                "count": 0,
            },
        )
        b["count"] += 1
        if row.get("predicted_value") is not None:
            b["predicted_values"].append(float(row["predicted_value"]))
        if row.get("actual_value") is not None:
            b["actual_values"].append(float(row["actual_value"]))
        if row.get("delta") is not None:
            b["deltas"].append(float(row["delta"]))
            b["abs_deltas"].append(abs(float(row["delta"])))
        if row.get("contribution_delta") is not None:
            b["contribution_deltas"].append(float(row["contribution_delta"]))

        ed = row.get("error_direction")
        if ed == "overestimated":
            b["overestimated"] += 1
        elif ed == "underestimated":
            b["underestimated"] += 1
        elif ed == "aligned":
            b["aligned"] += 1
        else:
            b["not_comparable"] += 1

        if row.get("actual_status") in ("unavailable", "missing") or row.get("actual_value") is None:
            if row.get("actual_comparison_type") not in ("diagnostic_only",):
                b["missing_actual"] += 1

        if row.get("suspicion_level") == "high":
            b["suspicious"] += 1

    out: list[dict[str, Any]] = []
    for b in buckets.values():
        pv = b["predicted_values"]
        av = b["actual_values"]
        dv = b["deltas"]
        cd = b["contribution_deltas"]
        out.append(
            {
                "strategy_key": b["strategy_key"],
                "macro_area": b["macro_area"],
                "macro_area_label": b["macro_area_label"],
                "variable_key": b["variable_key"],
                "label": b["label"],
                "count": b["count"],
                "avg_predicted": round(statistics.mean(pv), 4) if pv else None,
                "avg_actual": round(statistics.mean(av), 4) if av else None,
                "avg_delta": round(statistics.mean(dv), 4) if dv else None,
                "avg_abs_delta": round(statistics.mean(b["abs_deltas"]), 4) if b["abs_deltas"] else None,
                "contribution_delta_stddev": (
                    round(statistics.pstdev(cd), 4) if len(cd) > 1 else (round(cd[0], 4) if cd else None)
                ),
                "overestimated": b["overestimated"],
                "underestimated": b["underestimated"],
                "aligned": b["aligned"],
                "not_comparable": b["not_comparable"],
                "missing_actual": b["missing_actual"],
                "suspicious": b["suspicious"],
            },
        )
    out.sort(key=lambda x: (-(x.get("avg_abs_delta") or 0), x.get("variable_key") or ""))
    return out


def round_component_error_summary(
    payloads: list[dict[str, Any]],
    *,
    round_number: int | None = None,
    strategy_key: str | None = None,
) -> dict[str, Any]:
    flat: list[dict[str, Any]] = []
    for p in payloads:
        ms = p.get("match_summary") or {}
        if round_number is not None and int(ms.get("round_number") or 0) != int(round_number):
            continue
        if strategy_key and str(ms.get("strategy_key")) != strategy_key:
            continue
        flat.extend(flatten_component_rows(p))

    aggregates = _aggregate_rows(flat)
    return {
        "round_number": round_number,
        "strategy_key": strategy_key,
        "fixtures_count": len({(p.get("match_summary") or {}).get("fixture_id") for p in payloads}),
        "aggregates": aggregates,
    }


def season_component_error_summary(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    flat: list[dict[str, Any]] = []
    for p in payloads:
        flat.extend(flatten_component_rows(p))

    by_strategy: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in flat:
        by_strategy[str(row.get("strategy_key") or "")].append(row)

    strategies_out: dict[str, Any] = {}
    for sk, rows in by_strategy.items():
        agg = _aggregate_rows(rows)
        over = [a for a in agg if (a.get("overestimated") or 0) > (a.get("underestimated") or 0)]
        under = [a for a in agg if (a.get("underestimated") or 0) > (a.get("overestimated") or 0)]
        suspicious = sorted(agg, key=lambda x: -(x.get("suspicious") or 0))[:10]
        missing = sorted(agg, key=lambda x: -(x.get("missing_actual") or 0))[:10]
        unstable = sorted(
            agg,
            key=lambda x: -(x.get("contribution_delta_stddev") or 0),
        )[:10]

        macro_over: dict[str, float] = defaultdict(float)
        macro_under: dict[str, float] = defaultdict(float)
        for a in agg:
            ma = str(a.get("macro_area") or "")
            macro_over[ma] += float(a.get("overestimated") or 0)
            macro_under[ma] += float(a.get("underestimated") or 0)

        top_over_macro = sorted(macro_over.items(), key=lambda x: -x[1])[:5]
        top_under_macro = sorted(macro_under.items(), key=lambda x: -x[1])[:5]

        strategies_out[sk] = {
            "aggregates_count": len(agg),
            "top_overestimated_macros": [{"macro_area": k, "count": v} for k, v in top_over_macro],
            "top_underestimated_macros": [{"macro_area": k, "count": v} for k, v in top_under_macro],
            "top_suspicious_variables": suspicious,
            "top_missing_actual_variables": missing,
            "most_unstable_contributions": unstable,
            "severe_overestimation": [
                a for a in agg if (a.get("overestimated") or 0) >= 3 and (a.get("avg_abs_delta") or 0) >= 0.5
            ][:15],
            "severe_underestimation": [
                a for a in agg if (a.get("underestimated") or 0) >= 3 and (a.get("avg_abs_delta") or 0) >= 0.5
            ][:15],
        }

    return {"strategies": strategies_out, "fixtures_compared": len(payloads)}
