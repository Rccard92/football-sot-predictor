"""Caricamento dati piatti per diagnostica Round Analysis (solo lettura DB)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.schemas.backtest_round_analysis import DEFAULT_ROUND_ANALYSIS_MODELS
from app.services.backtest.round_analysis_calibration_export import (
    _model_keys_from_analyses,
    _select_analyses_for_calibration,
)

V21 = BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def load_diagnostics_flat_rows(
    db: Session,
    *,
    competition_id: int,
    season_year: int,
    use_latest_version_per_round: bool = True,
    include_all_versions: bool = False,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Restituisce righe fixture×modello con actual_total_sot valorizzato."""
    analyses, excluded, fixtures_by_id = _select_analyses_for_calibration(
        db,
        competition_id=competition_id,
        season_year=season_year,
        use_latest_version_per_round=use_latest_version_per_round,
        include_all_versions=include_all_versions,
    )
    model_keys = _model_keys_from_analyses(analyses)
    flat: list[dict[str, Any]] = []

    for analysis in analyses:
        cfg = dict(analysis.config_json or {})
        keys = list(cfg.get("models") or model_keys)
        for row in fixtures_by_id.get(int(analysis.id), []):
            if str(row.status) != "ok":
                continue
            if row.actual_total_sot is None:
                continue
            expl_all = dict(row.explanation_json or {})
            for model_key in keys:
                block = (row.models_json or {}).get(model_key)
                if not isinstance(block, dict):
                    continue
                flat.append(
                    {
                        "analysis_id": int(analysis.id),
                        "round_number": int(analysis.round_number),
                        "fixture_id": int(row.fixture_id),
                        "home_team": row.home_team_name,
                        "away_team": row.away_team_name,
                        "match": f"{row.home_team_name} vs {row.away_team_name}",
                        "actual_home_sot": row.actual_home_sot,
                        "actual_away_sot": row.actual_away_sot,
                        "actual_total_sot": int(row.actual_total_sot),
                        "model_key": model_key,
                        "block": block,
                        "explanation_v21": expl_all.get(V21) if model_key == V21 else None,
                    },
                )

    return flat, model_keys, excluded
