"""Export CSV piatto dataset calibrazione v3.1."""

from __future__ import annotations

import csv
import io
from typing import Any


CSV_COLUMNS = [
    "fixture_id",
    "round_number",
    "match",
    "actual_home_sot",
    "actual_away_sot",
    "actual_total_sot",
    "home_avg_sot_for",
    "away_avg_sot_for",
    "home_avg_sot_against",
    "away_avg_sot_against",
    "home_avg_xg_for",
    "away_avg_xg_for",
    "home_last5_sot_for",
    "away_last5_sot_for",
    "home_split_sot_for",
    "away_split_sot_for",
    "home_player_layer_index",
    "away_player_layer_index",
    "home_unavailable_index",
    "away_unavailable_index",
    "home_important_absences_count",
    "away_important_absences_count",
    "home_lineup_index",
    "away_lineup_index",
    "home_chance_quality_index",
    "away_chance_quality_index",
    "home_pace_control_index",
    "away_pace_control_index",
    "data_quality_flags",
    "warning_count",
    "fallback_count",
    "comparison_v11_predicted_total",
    "comparison_v20_predicted_total",
    "comparison_v21_predicted_total",
    "comparison_v30_decision",
    "comparison_v30_selected_line",
]


def _g(row: dict[str, Any], *path: str) -> Any:
    cur: Any = row
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def row_to_csv_dict(row: dict[str, Any]) -> dict[str, Any]:
    meta = row.get("metadata") or {}
    target = row.get("target") or {}
    tr = _g(row, "features", "team_raw_features", "home") or {}
    ta = _g(row, "features", "team_raw_features", "away") or {}
    plh = _g(row, "features", "player_layer", "home") or {}
    pla = _g(row, "features", "player_layer", "away") or {}
    unh = _g(row, "features", "unavailable", "home") or {}
    una = _g(row, "features", "unavailable", "away") or {}
    luh = _g(row, "features", "lineups", "home") or {}
    lua = _g(row, "features", "lineups", "away") or {}
    mah = _g(row, "features", "existing_macro_features", "home") or {}
    maa = _g(row, "features", "existing_macro_features", "away") or {}
    dq = _g(row, "features", "data_quality") or row.get("data_quality") or {}
    comp = row.get("comparisons") or {}

    flags = "|".join(
        [
            str(dq.get("team_stats_status") or ""),
            str(dq.get("player_layer_status") or ""),
            str(dq.get("lineup_status") or ""),
            str(dq.get("unavailable_status") or ""),
        ],
    )

    match = f"{meta.get('home_team_name', '')} vs {meta.get('away_team_name', '')}"

    return {
        "fixture_id": meta.get("fixture_id"),
        "round_number": meta.get("round_number"),
        "match": match,
        "actual_home_sot": target.get("actual_home_sot"),
        "actual_away_sot": target.get("actual_away_sot"),
        "actual_total_sot": target.get("actual_total_sot"),
        "home_avg_sot_for": tr.get("avg_sot_for"),
        "away_avg_sot_for": ta.get("avg_sot_for"),
        "home_avg_sot_against": tr.get("avg_sot_against"),
        "away_avg_sot_against": ta.get("avg_sot_against"),
        "home_avg_xg_for": tr.get("avg_xg_for"),
        "away_avg_xg_for": ta.get("avg_xg_for"),
        "home_last5_sot_for": tr.get("last5_avg_sot_for"),
        "away_last5_sot_for": ta.get("last5_avg_sot_for"),
        "home_split_sot_for": tr.get("home_away_split_sot_for"),
        "away_split_sot_for": ta.get("home_away_split_sot_for"),
        "home_player_layer_index": plh.get("player_layer_index_existing"),
        "away_player_layer_index": pla.get("player_layer_index_existing"),
        "home_unavailable_index": unh.get("unavailable_macro_existing"),
        "away_unavailable_index": una.get("unavailable_macro_existing"),
        "home_important_absences_count": unh.get("important_absences_count"),
        "away_important_absences_count": una.get("important_absences_count"),
        "home_lineup_index": luh.get("lineup_macro_existing"),
        "away_lineup_index": lua.get("lineup_macro_existing"),
        "home_chance_quality_index": mah.get("chance_quality_index"),
        "away_chance_quality_index": maa.get("chance_quality_index"),
        "home_pace_control_index": mah.get("pace_control_index"),
        "away_pace_control_index": maa.get("pace_control_index"),
        "data_quality_flags": flags,
        "warning_count": dq.get("warning_count"),
        "fallback_count": dq.get("fallback_count"),
        "comparison_v11_predicted_total": comp.get("v1_1_predicted_total"),
        "comparison_v20_predicted_total": comp.get("v2_0_predicted_total"),
        "comparison_v21_predicted_total": comp.get("v2_1_predicted_total"),
        "comparison_v30_decision": comp.get("v3_0_decision"),
        "comparison_v30_selected_line": comp.get("v3_0_selected_line"),
    }


def dataset_to_csv_text(payload: dict[str, Any]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in payload.get("rows") or []:
        if isinstance(row, dict):
            writer.writerow(row_to_csv_dict(row))
    return buf.getvalue()
