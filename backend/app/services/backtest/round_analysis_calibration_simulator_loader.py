"""Caricamento fixture-centriche per simulatore calibrazione v3.0."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V11_SOT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.backtest.round_analysis_diagnostics_loader import load_diagnostics_flat_rows
from app.services.backtest.round_analysis_v21_trace_helpers import (
    extract_v21_macro_averages,
    extract_v21_split_status,
)

V11 = BASELINE_SOT_MODEL_VERSION_V11_SOT
V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def load_simulator_fixtures(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    flat_rows, model_keys, excluded = load_diagnostics_flat_rows(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    idx: dict[tuple[int, int], dict[str, Any]] = {}
    for row in flat_rows:
        key = (int(row["analysis_id"]), int(row["fixture_id"]))
        if key not in idx:
            idx[key] = {
                "analysis_id": row["analysis_id"],
                "round_number": row["round_number"],
                "fixture_id": row["fixture_id"],
                "match": row["match"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "actual_total_sot": row["actual_total_sot"],
                "models": {},
                "explanation_v21": None,
            }
        idx[key]["models"][row["model_key"]] = row["block"]
        if row["model_key"] == V21:
            idx[key]["explanation_v21"] = row.get("explanation_v21")

    fixtures: list[dict[str, Any]] = []
    for entry in idx.values():
        expl = entry.get("explanation_v21")
        entry["v21_macros"] = extract_v21_macro_averages(expl)
        entry["split_status"] = extract_v21_split_status(expl)
        fixtures.append(entry)

    fixtures.sort(key=lambda f: (int(f["round_number"]), int(f["fixture_id"])))
    return fixtures, model_keys, excluded
